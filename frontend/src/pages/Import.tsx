/**
 * Bulk audio import — v1 minimal UI (B-import.1).
 *
 * This is the Phase 1 surface: file picker -> parse preview -> submit
 * -> 5s status poll. The polished preview table with inline editing,
 * tag bulk-apply, project linking, and the WebSocket-driven progress
 * stream lands in B-import.2 per `docs/bulk-audio-import-design.md`.
 *
 * Lifecycle:
 *   1. User clicks "Create job" -> POST /api/import/jobs -> backend
 *      returns {job_id, status:'queued'}. We hold the job_id in state.
 *   2. User picks one or more audio files via the native picker. We
 *      run the shared filename parser in-browser so the preview list
 *      shows the title + date the backend will also parse.
 *   3. "Upload N files" iterates through the staged files and POSTs
 *      each to /api/import/jobs/{job_id}/files (multipart). The
 *      backend persists the bytes + creates the file row + queues it.
 *   4. A 5s interval polls /api/import/jobs/{job_id} for the status
 *      block until the job is in a terminal state.
 *
 * Auth: cookies/SSO are carried via credentials:'include' (oauth2-proxy
 * + Keycloak). The single-file upload page does the same — no special
 * handling needed.
 *
 * Errors: any non-2xx from the backend short-circuits with a banner
 * above the status panel. The minimal UI doesn't have per-row retry
 * yet — that's B-import.2.
 */

import { useEffect, useMemo, useState } from 'react';
import { parseFilename } from '../utils/filenameParser';

type JobCreateResponse = {
  job_id: string;
  status: string;
};

type JobStatusFile = {
  file_id: string;
  original_filename: string;
  parsed_title: string | null;
  parsed_date: string | null;
  parsed_time: string | null;
  parsed_confidence: number | null;
  status: string;
  session_id: string | null;
  error_message: string | null;
  bytes_total: number | null;
};

type JobStatusResponse = {
  job_id: string;
  status: string;
  total_files: number;
  succeeded: number;
  failed: number;
  skipped: number;
  started_at: string | null;
  finished_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  files: JobStatusFile[];
};

const TERMINAL_STATES = new Set(['complete', 'cancelled', 'failed']);

function formatBytes(n: number | null): string {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function statusColor(status: string): string {
  switch (status) {
    case 'complete':
      return '#2ecc71';
    case 'failed':
      return '#e74c3c';
    case 'skipped':
      return '#f39c12';
    case 'cancelled':
      return '#bdc3c7';
    case 'processing':
    case 'uploading':
      return '#3498db';
    default:
      return '#7f8c8d';
  }
}

export default function Import() {
  const [job, setJob] = useState<JobCreateResponse | null>(null);
  const [creatingJob, setCreatingJob] = useState(false);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number }>({
    done: 0,
    total: 0,
  });
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  // Run the shared filename parser in-browser so users see the
  // parsed title + date BEFORE committing to an upload. The backend
  // re-parses on its own so a frontend bug here can't poison the
  // stored metadata.
  const parsedPreviews = useMemo(
    () =>
      stagedFiles.map((f) => ({
        file: f,
        parsed: parseFilename(f.name),
      })),
    [stagedFiles],
  );

  const createJob = async () => {
    setError(null);
    setCreatingJob(true);
    try {
      const resp = await fetch('/api/import/jobs', {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        throw new Error(`create job failed: ${resp.status} ${resp.statusText}`);
      }
      const data = (await resp.json()) as JobCreateResponse;
      setJob(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreatingJob(false);
    }
  };

  const uploadAll = async () => {
    if (!job || stagedFiles.length === 0) return;
    setError(null);
    setUploading(true);
    setUploadProgress({ done: 0, total: stagedFiles.length });
    try {
      // Strict serial loop. v1 is one-at-a-time to keep the request
      // pipeline simple; B-import.2 lets the browser fire 2-3 in
      // parallel against the backend (the backend's worker pool still
      // caps reprocess concurrency at 2, so client-side parallelism
      // only speeds the upload phase, not the GPU phase).
      for (let i = 0; i < stagedFiles.length; i++) {
        const f = stagedFiles[i];
        const fd = new FormData();
        fd.append('audio', f, f.name);
        const resp = await fetch(`/api/import/jobs/${job.job_id}/files`, {
          method: 'POST',
          body: fd,
          credentials: 'include',
        });
        if (!resp.ok) {
          throw new Error(
            `upload of ${f.name} failed: ${resp.status} ${resp.statusText}`,
          );
        }
        setUploadProgress({ done: i + 1, total: stagedFiles.length });
      }
      // Clear the staged list once everything is on the wire — the
      // status poll takes over from here.
      setStagedFiles([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const cancelJob = async () => {
    if (!job) return;
    setError(null);
    setCancelling(true);
    try {
      const resp = await fetch(`/api/import/jobs/${job.job_id}/cancel`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        throw new Error(`cancel failed: ${resp.status} ${resp.statusText}`);
      }
      const data = (await resp.json()) as JobStatusResponse;
      setStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCancelling(false);
    }
  };

  // Poll the job status every 5s until we hit a terminal state. Kicks
  // off as soon as a job_id exists; tears down on unmount.
  useEffect(() => {
    if (!job) return;
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const resp = await fetch(`/api/import/jobs/${job.job_id}`, {
          credentials: 'include',
        });
        if (!resp.ok) {
          throw new Error(`status fetch ${resp.status}`);
        }
        const data = (await resp.json()) as JobStatusResponse;
        if (!cancelled) setStatus(data);
        return data;
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
        return null;
      }
    };

    // Fire once immediately so the UI shows something the moment the
    // job is created, then start the 5s interval.
    void fetchStatus();
    const interval = setInterval(async () => {
      const data = await fetchStatus();
      if (data && TERMINAL_STATES.has(data.status)) {
        clearInterval(interval);
      }
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [job]);

  return (
    <div style={{ padding: 24, color: '#e7e7e7', maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ marginBottom: 4 }}>Bulk import</h1>
      <p style={{ opacity: 0.65, marginTop: 0, marginBottom: 24, fontSize: 14 }}>
        v1 minimal UI. Drop audio files, upload, watch them transcribe. The
        polished preview-table UX with inline editing + per-row retry lands
        in B-import.2.
      </p>

      {error && (
        <div
          style={{
            background: '#3b1414',
            border: '1px solid #e74c3c',
            color: '#ffb0a8',
            padding: 12,
            borderRadius: 6,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {!job && (
        <button
          onClick={createJob}
          disabled={creatingJob}
          style={{
            background: '#2563eb',
            color: 'white',
            padding: '10px 16px',
            borderRadius: 6,
            border: 'none',
            cursor: 'pointer',
            fontSize: 14,
          }}
        >
          {creatingJob ? 'Creating…' : 'Create import job'}
        </button>
      )}

      {job && (
        <div style={{ marginBottom: 24 }}>
          <p style={{ opacity: 0.7, fontSize: 13, marginTop: 0 }}>
            Job <code>{job.job_id}</code>
          </p>

          <div
            style={{
              border: '1px dashed #2f3438',
              borderRadius: 6,
              padding: 16,
              marginBottom: 12,
            }}
          >
            <input
              type="file"
              multiple
              accept=".m4a,.mp3,.wav,.flac,.ogg,.opus,.aac,.mp4,.mov,.mkv,.webm,.avi,audio/*,video/*"
              onChange={(e) =>
                setStagedFiles(Array.from(e.target.files ?? []))
              }
              disabled={uploading}
            />
            <p style={{ opacity: 0.55, fontSize: 12, marginTop: 8, marginBottom: 0 }}>
              Pick one or more audio files. Filenames matching
              <code> notes__YYYY-MM-DD_HHMMSS__title.m4a</code> auto-fill
              meeting date + title.
            </p>
          </div>

          {stagedFiles.length > 0 && (
            <>
              <ul
                style={{
                  background: '#111417',
                  border: '1px solid #1f2326',
                  borderRadius: 6,
                  padding: 12,
                  marginBottom: 12,
                  listStyle: 'none',
                  fontSize: 13,
                }}
              >
                {parsedPreviews.map(({ file: f, parsed }) => (
                  <li
                    key={f.name + ':' + f.size}
                    style={{
                      padding: '6px 4px',
                      borderBottom: '1px solid #1a1d20',
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 500 }}>{f.name}</span>
                      <span style={{ opacity: 0.5, marginLeft: 8 }}>
                        {formatBytes(f.size)}
                      </span>
                    </div>
                    {parsed.confidence > 0 && (
                      <div style={{ opacity: 0.7, fontSize: 12, marginTop: 2 }}>
                        → {parsed.title ?? '(no title)'}
                        {parsed.meetingDate && ` on ${parsed.meetingDate}`}
                        {parsed.meetingTime && ` at ${parsed.meetingTime}`}
                        <span
                          style={{
                            marginLeft: 8,
                            opacity: 0.55,
                          }}
                        >
                          confidence {Math.round(parsed.confidence * 100)}%
                        </span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <button
                onClick={uploadAll}
                disabled={uploading || stagedFiles.length === 0}
                style={{
                  background: uploading ? '#3b4045' : '#2563eb',
                  color: 'white',
                  padding: '10px 16px',
                  borderRadius: 6,
                  border: 'none',
                  cursor: uploading ? 'wait' : 'pointer',
                  fontSize: 14,
                }}
              >
                {uploading
                  ? `Uploading ${uploadProgress.done}/${uploadProgress.total}…`
                  : `Upload ${stagedFiles.length} file${stagedFiles.length === 1 ? '' : 's'}`}
              </button>
            </>
          )}
        </div>
      )}

      {status && (
        <div
          style={{
            background: '#0f1215',
            border: '1px solid #1f2326',
            borderRadius: 8,
            padding: 16,
            marginTop: 16,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>
              Status: <span style={{ color: statusColor(status.status) }}>{status.status}</span>
            </h2>
            {!TERMINAL_STATES.has(status.status) && (
              <button
                onClick={cancelJob}
                disabled={cancelling}
                style={{
                  background: 'transparent',
                  color: '#e74c3c',
                  padding: '6px 12px',
                  borderRadius: 6,
                  border: '1px solid #e74c3c',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                {cancelling ? 'Cancelling…' : 'Cancel job'}
              </button>
            )}
          </div>
          <p style={{ opacity: 0.7, fontSize: 13, marginTop: 0 }}>
            {status.succeeded} done · {status.failed} failed · {status.skipped} skipped · of {status.total_files} files
          </p>

          <ul
            style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              fontSize: 13,
              maxHeight: 480,
              overflowY: 'auto',
            }}
          >
            {(status.files ?? []).map((f) => (
              <li
                key={f.file_id}
                style={{
                  padding: '6px 4px',
                  borderBottom: '1px solid #1a1d20',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span
                  style={{
                    color: statusColor(f.status),
                    minWidth: 80,
                    fontSize: 12,
                  }}
                >
                  {f.status}
                </span>
                <span style={{ flex: 1, opacity: 0.85 }}>
                  {f.parsed_title ?? f.original_filename}
                  {f.parsed_date && (
                    <span style={{ opacity: 0.55, marginLeft: 8 }}>
                      {f.parsed_date}
                    </span>
                  )}
                </span>
                {f.session_id && (
                  <a
                    href={`/sessions/${f.session_id}`}
                    style={{ color: '#3498db', fontSize: 12 }}
                  >
                    open
                  </a>
                )}
                {f.error_message && (
                  <span
                    style={{
                      color: '#e74c3c',
                      fontSize: 12,
                      maxWidth: 320,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={f.error_message}
                  >
                    {f.error_message}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
