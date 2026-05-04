import { config } from '../config';

export type UploadKind = 'audio' | 'video' | 'image' | 'document' | 'unknown';
export type UploadAction = 'transcribe' | 'attach';
export type UploadStage =
  | 'queued'
  | 'uploading'
  | 'extracting'
  | 'transcribing'
  | 'diarizing'
  | 'summarizing'
  | 'embedding'
  | 'done'
  | 'failed'
  | 'cancelled';

const AUDIO_EXTENSIONS = ['mp3', 'wav', 'm4a', 'ogg', 'flac', 'opus', 'aac'];
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'mkv', 'webm', 'avi'];
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'pdf'];
const DOCUMENT_EXTENSIONS = ['docx', 'txt', 'md'];

export interface UploadStatus {
  upload_id: string;
  job_id: string;
  filename: string;
  stage: UploadStage;
  progress_pct: number;
  error?: string | null;
  session_id?: number | null;
  bytes_received: number;
  total_size: number;
  received_chunks: number;
  total_chunks: number;
  last_completed_stage?: string | null;
  retry_count?: number;
}

export function detectFileKind(file: File): UploadKind {
  const mime = file.type.toLowerCase();
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (mime.startsWith('audio/') || AUDIO_EXTENSIONS.includes(ext)) return 'audio';
  if (mime.startsWith('video/') || VIDEO_EXTENSIONS.includes(ext)) return 'video';
  if (mime.startsWith('image/') || IMAGE_EXTENSIONS.includes(ext)) return 'image';
  if (DOCUMENT_EXTENSIONS.includes(ext)) return 'document';
  return 'unknown';
}

export function defaultActionForFile(file: File): UploadAction {
  const kind = detectFileKind(file);
  return kind === 'audio' || kind === 'video' ? 'transcribe' : 'attach';
}

export function actionLabelForFile(file: File): string {
  const kind = detectFileKind(file);
  if (kind === 'audio') return 'Transcribe as new meeting';
  if (kind === 'video') return 'Extract audio + transcribe';
  return 'Attach to meeting...';
}

export function autoTitleFromFilename(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, '');
  const cleaned = stem
    .replace(/^(zoom|recording|meeting|audio|video)[ _-]+/i, '')
    .replace(/(^|[ _-])\d{4}[-_]\d{2}[-_]\d{2}([ _-]|$)/g, ' ')
    .replace(/\b\d{8}\b/g, '')
    .replace(/[_-]+/g, ' ')
    .trim();
  const title = (cleaned || 'Uploaded Meeting')
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
  return title.slice(0, 80);
}

export function creationDateFromFile(file: File): Date | null {
  const match = file.name.match(/(\d{4})[-_](\d{2})[-_](\d{2})/);
  if (match) {
    const date = new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`);
    if (!Number.isNaN(date.getTime())) return date;
  }
  return file.lastModified ? new Date(file.lastModified) : null;
}

export function estimateProcessingLabel(file: File): string {
  const mb = file.size / (1024 * 1024);
  const estimatedMinutes = Math.max(1, Math.round(mb * 0.5));
  return `Est. ${estimatedMinutes} min`;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

export function buildUploadHeaders(orgSlug?: string | null): HeadersInit {
  const token = localStorage.getItem('access_token');
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(orgSlug ? { 'X-MeetingOps-Org': orgSlug } : {}),
  };
}

export async function uploadFileInChunks(
  file: File,
  uploadId: string,
  chunkSize: number,
  orgSlug: string | null | undefined,
  onChunk: (receivedChunks: number, totalChunks: number) => void,
  signal?: AbortSignal,
) {
  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));
  for (let index = 0; index < totalChunks; index += 1) {
    const start = index * chunkSize;
    const end = Math.min(start + chunkSize, file.size);
    const form = new FormData();
    form.append('chunk_index', String(index));
    form.append('data', file.slice(start, end), file.name);
    const res = await fetch(`${config.apiBaseUrl}/api/uploads/${uploadId}/chunk`, {
      method: 'POST',
      headers: buildUploadHeaders(orgSlug),
      body: form,
      signal,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || `Chunk ${index + 1} failed`);
    }
    const data = await res.json();
    onChunk(data.received_chunks, data.total_chunks);
  }
}

export function uploadWebSocketUrl(jobId: string, orgSlug?: string | null): string {
  const apiUrl = config.apiBaseUrl;
  const protocol = apiUrl.startsWith('https') ? 'wss:' : 'ws:';
  const host = apiUrl.replace(/^https?:\/\//, '');
  const orgQuery = orgSlug ? `?org=${encodeURIComponent(orgSlug)}` : '';
  return `${protocol}//${host}/ws/uploads/${jobId}${orgQuery}`;
}
