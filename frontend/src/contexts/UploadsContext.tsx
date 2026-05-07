import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { toast } from 'react-toastify';
import { useNavigate } from 'react-router-dom';
import { config } from '../config';
import { useOrg } from './OrgContext';
import {
  buildUploadHeaders,
  defaultActionForFile,
  detectFileKind,
  uploadFileInChunks,
  uploadWebSocketUrl,
  type UploadAction,
  type UploadStage,
  type UploadStatus,
} from '../utils/uploads';

export interface UploadItem {
  localId: string;
  uploadId?: string;
  jobId?: string;
  filename: string;
  size: number;
  contentType: string;
  action: UploadAction;
  stage: UploadStage;
  progress: number;
  error?: string | null;
  sessionId?: number | null;
  createdAt: number;
}

export interface StartUploadsOptions {
  action?: UploadAction;
  targetSessionId?: string;
}

interface UploadsContextValue {
  uploads: UploadItem[];
  startUploads: (files: File[], options?: StartUploadsOptions) => Promise<void>;
  cancelUpload: (item: UploadItem) => Promise<void>;
  dismissUpload: (item: UploadItem) => Promise<void>;
  retryUpload: (item: UploadItem) => Promise<void>;
  openSession: (item: UploadItem) => void;
}

const STORAGE_KEY = 'meetingops.uploads.v1';
const MAX_PARALLEL_STARTS = 4;
const UploadsContext = createContext<UploadsContextValue | undefined>(undefined);

function loadStoredUploads(): UploadItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistable(item: UploadItem): boolean {
  return item.stage !== 'cancelled';
}

export function UploadsProvider({ children }: { children: ReactNode }) {
  const { activeOrganization } = useOrg();
  const navigate = useNavigate();
  const [uploads, setUploads] = useState<UploadItem[]>(() => loadStoredUploads());
  const aborts = useRef<Map<string, AbortController>>(new Map());
  const sockets = useRef<Map<string, WebSocket>>(new Map());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(uploads.filter(persistable).slice(-50)));
  }, [uploads]);

  const updateUpload = useCallback((localId: string, patch: Partial<UploadItem>) => {
    setUploads((prev) => prev.map((item) => item.localId === localId ? { ...item, ...patch } : item));
  }, []);

  const applyStatus = useCallback((localId: string, status: UploadStatus) => {
    updateUpload(localId, {
      uploadId: status.upload_id,
      jobId: status.job_id,
      stage: status.stage,
      progress: status.progress_pct,
      error: status.error,
      sessionId: status.session_id,
    });
  }, [updateUpload]);

  const connectStatusSocket = useCallback((localId: string, jobId: string) => {
    if (sockets.current.has(localId)) return;
    const socket = new WebSocket(uploadWebSocketUrl(jobId, activeOrganization?.slug));
    sockets.current.set(localId, socket);
    socket.onmessage = (event) => {
      try {
        applyStatus(localId, JSON.parse(event.data));
      } catch {
        // Ignore malformed status frames.
      }
    };
    socket.onclose = () => sockets.current.delete(localId);
  }, [activeOrganization?.slug, applyStatus]);

  const reconcileUpload = useCallback(async (item: UploadItem) => {
    if (!item.uploadId || item.stage === 'done' || item.stage === 'failed') return;
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/uploads/${item.uploadId}/status`, {
        headers: buildUploadHeaders(activeOrganization?.slug),
      });
      if (res.ok) {
        const status = await res.json();
        applyStatus(item.localId, status);
        connectStatusSocket(item.localId, status.job_id);
      }
    } catch {
      // Polling is best effort on startup.
    }
  }, [activeOrganization?.slug, applyStatus, connectStatusSocket]);

  useEffect(() => {
    uploads.forEach(reconcileUpload);
  }, [activeOrganization?.slug]);

  const startOne = useCallback(async (file: File, forcedAction?: UploadAction, targetSessionId?: string) => {
    const localId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const action = forcedAction ?? defaultActionForFile(file);
    const item: UploadItem = {
      localId,
      filename: file.name,
      size: file.size,
      contentType: file.type,
      action,
      stage: 'queued',
      progress: 0,
      createdAt: Date.now(),
    };
    setUploads((prev) => [...prev, item]);

    const abort = new AbortController();
    aborts.current.set(localId, abort);

    try {
      const startRes = await fetch(`${config.apiBaseUrl}/api/uploads/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...buildUploadHeaders(activeOrganization?.slug),
        },
        body: JSON.stringify({
          filename: file.name,
          total_size: file.size,
          content_type: file.type || `${detectFileKind(file)}/unknown`,
          action,
          ...(targetSessionId ? { target_session_id: targetSessionId } : {}),
        }),
        signal: abort.signal,
      });
      if (!startRes.ok) {
        const detail = await startRes.text();
        throw new Error(detail || 'Upload was rejected.');
      }
      const started = await startRes.json();
      updateUpload(localId, { uploadId: started.upload_id, jobId: started.upload_id, stage: 'uploading' });
      connectStatusSocket(localId, started.upload_id);

      await uploadFileInChunks(
        file,
        started.upload_id,
        started.chunk_size,
        activeOrganization?.slug,
        (received, total) => updateUpload(localId, { progress: Math.round((received / total) * 100), stage: 'uploading' }),
        abort.signal,
      );

      const finalizeRes = await fetch(`${config.apiBaseUrl}/api/uploads/${started.upload_id}/finalize`, {
        method: 'POST',
        headers: buildUploadHeaders(activeOrganization?.slug),
        signal: abort.signal,
      });
      if (!finalizeRes.ok) {
        const detail = await finalizeRes.text();
        throw new Error(detail || 'Finalize failed.');
      }
      const finalized = await finalizeRes.json();
      updateUpload(localId, { jobId: finalized.job_id, sessionId: finalized.session_id ?? null, stage: 'queued', progress: 0 });
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        updateUpload(localId, { stage: 'cancelled', error: null, progress: 0 });
      } else {
        updateUpload(localId, { stage: 'failed', error: error?.message || 'Upload failed.' });
        toast.error(error?.message || 'Upload failed.');
      }
    } finally {
      aborts.current.delete(localId);
    }
  }, [activeOrganization?.slug, connectStatusSocket, updateUpload]);

  const startUploads = useCallback(async (files: File[], options?: StartUploadsOptions) => {
    const pending = [...files];
    const workers = Array.from({ length: Math.min(MAX_PARALLEL_STARTS, pending.length) }, async () => {
      while (pending.length > 0) {
        const file = pending.shift();
        if (file) await startOne(file, options?.action, options?.targetSessionId);
      }
    });
    await Promise.all(workers);
  }, [startOne]);

  const cancelUpload = useCallback(async (item: UploadItem) => {
    aborts.current.get(item.localId)?.abort();
    if (item.uploadId) {
      try {
        await fetch(`${config.apiBaseUrl}/api/uploads/${item.uploadId}`, {
          method: 'DELETE',
          headers: buildUploadHeaders(activeOrganization?.slug),
        });
      } catch {
        // Local cancellation still applies.
      }
    }
    updateUpload(item.localId, { stage: 'cancelled', progress: 0 });
  }, [activeOrganization?.slug, updateUpload]);

  const dismissUpload = useCallback(async (item: UploadItem) => {
    // Pure-frontend remove: drop the row from the tray and persisted list.
    // If the upload reached the backend, also fire-and-forget DELETE so the
    // server-side job and chunk dir are cleaned up.
    setUploads((prev) => prev.filter((u) => u.localId !== item.localId));
    if (item.uploadId && item.stage !== 'done') {
      try {
        await fetch(`${config.apiBaseUrl}/api/uploads/${item.uploadId}`, {
          method: 'DELETE',
          headers: buildUploadHeaders(activeOrganization?.slug),
        });
      } catch {
        // Local dismiss already applied.
      }
    }
  }, [activeOrganization?.slug]);

  const retryUpload = useCallback(async (item: UploadItem) => {
    if (!item.uploadId) {
      // Frontend-only failure (e.g. file rejected before /uploads/start).
      // Nothing to retry server-side; user must re-pick the file.
      return;
    }
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/uploads/${item.uploadId}/retry`, {
        method: 'POST',
        headers: buildUploadHeaders(activeOrganization?.slug),
      });
      if (!res.ok) {
        const detail = await res.text();
        updateUpload(item.localId, {
          error: detail || `Retry failed (${res.status})`,
        });
        return;
      }
      updateUpload(item.localId, { stage: 'queued', progress: 0, error: null });
      // Reconnect the WebSocket so progress events flow again.
      connectStatusSocket(item.localId, item.uploadId);
    } catch (err: any) {
      updateUpload(item.localId, { error: err?.message || 'Retry failed' });
    }
  }, [activeOrganization?.slug, connectStatusSocket, updateUpload]);

  const openSession = useCallback((item: UploadItem) => {
    if (item.sessionId) navigate(`/sessions/${item.sessionId}`);
  }, [navigate]);

  useEffect(() => () => {
    sockets.current.forEach((socket) => socket.close());
    aborts.current.forEach((abort) => abort.abort());
  }, []);

  const value = useMemo(
    () => ({ uploads, startUploads, cancelUpload, dismissUpload, retryUpload, openSession }),
    [uploads, startUploads, cancelUpload, dismissUpload, retryUpload, openSession],
  );
  return <UploadsContext.Provider value={value}>{children}</UploadsContext.Provider>;
}

export function useUploads() {
  const context = useContext(UploadsContext);
  if (!context) {
    throw new Error('useUploads must be used within an UploadsProvider');
  }
  return context;
}
