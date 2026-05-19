// IndexedDB-backed storage for local-only privacy-mode sessions.
//
// Schema is intentionally flat — one object store keyed by session id.
// No migrations system: if the shape ever needs to change, bump
// LOCAL_SESSION_DB_VERSION and add a clean reset in the upgrade
// handler. Local sessions are best-effort; we never trade reliability
// for compatibility with old browser-local data.

export const LOCAL_SESSION_DB_NAME = 'meetingops-local-sessions';
export const LOCAL_SESSION_DB_VERSION = 1;
export const LOCAL_SESSION_STORE = 'sessions';

export const LOCAL_SESSION_ID_PREFIX = 'local-';

export interface LocalTranscriptChunk {
  text: string;
  elapsedSeconds: number;
  durationSeconds: number;
  provenance: string;
  createdAt: string;
}

export interface LocalSummarySlice {
  text: string;
  wordRangeStart: number;
  wordRangeEnd: number;
  model: string;
  createdAt: string;
}

export interface LocalSession {
  id: string;
  title: string;
  startedAt: string;
  endedAt: string | null;
  durationSeconds: number;
  participants: string[];
  tags: string[];
  transcript: LocalTranscriptChunk[];
  slices: LocalSummarySlice[];
  finalSummary: string | null;
  wordCount: number;
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function isLocalSessionId(id: string): boolean {
  return id.startsWith(LOCAL_SESSION_ID_PREFIX);
}

export function makeLocalSessionId(): string {
  return `${LOCAL_SESSION_ID_PREFIX}${uuid()}`;
}

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('IndexedDB unavailable in this environment.'));
  }
  if (dbPromise) return dbPromise;

  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(LOCAL_SESSION_DB_NAME, LOCAL_SESSION_DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(LOCAL_SESSION_STORE)) {
        const store = db.createObjectStore(LOCAL_SESSION_STORE, { keyPath: 'id' });
        store.createIndex('startedAt', 'startedAt', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed.'));
    req.onblocked = () => reject(new Error('IndexedDB blocked by another tab.'));
  });

  return dbPromise;
}

function tx<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T> | Promise<T>,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(LOCAL_SESSION_STORE, mode);
        const store = transaction.objectStore(LOCAL_SESSION_STORE);
        let value: T | undefined;
        let pending = false;
        try {
          const ret = run(store);
          if (ret && typeof (ret as any).then === 'function') {
            pending = true;
            (ret as Promise<T>).then((v) => {
              value = v;
              pending = false;
            }, reject);
          } else {
            const req = ret as IDBRequest<T>;
            req.onsuccess = () => {
              value = req.result;
            };
            req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed.'));
          }
        } catch (err) {
          reject(err);
          return;
        }
        transaction.oncomplete = () => {
          if (pending) {
            // We were awaiting a promise; wait one tick.
            setTimeout(() => resolve(value as T), 0);
            return;
          }
          resolve(value as T);
        };
        transaction.onerror = () => reject(transaction.error ?? new Error('IndexedDB tx failed.'));
        transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB tx aborted.'));
      }),
  );
}

function defaultTitle(startedAt: string): string {
  // Match Granola-ish style: date + "(Local)" so the user immediately
  // knows what tier this is in the sessions list.
  const d = new Date(startedAt);
  if (Number.isNaN(d.getTime())) return 'Local meeting';
  return `Local meeting · ${d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`;
}

export async function createLocalSession(): Promise<LocalSession> {
  const startedAt = nowIso();
  const session: LocalSession = {
    id: makeLocalSessionId(),
    title: defaultTitle(startedAt),
    startedAt,
    endedAt: null,
    durationSeconds: 0,
    participants: [],
    tags: [],
    transcript: [],
    slices: [],
    finalSummary: null,
    wordCount: 0,
  };
  await tx('readwrite', (store) => store.add(session));
  return session;
}

export async function getLocalSession(id: string): Promise<LocalSession | null> {
  if (!isLocalSessionId(id)) return null;
  return tx('readonly', (store) => store.get(id))
    .then((result: any) => (result ? (result as LocalSession) : null))
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.warn('[local-session-store] getLocalSession failed:', err);
      return null;
    });
}

async function updateSession(
  id: string,
  mutator: (session: LocalSession) => LocalSession,
): Promise<LocalSession | null> {
  const existing = await getLocalSession(id);
  if (!existing) return null;
  const next = mutator(existing);
  await tx('readwrite', (store) => store.put(next));
  return next;
}

export async function appendChunk(
  sessionId: string,
  chunk: LocalTranscriptChunk,
): Promise<void> {
  await updateSession(sessionId, (session) => {
    const wordCount = countWords(chunk.text);
    return {
      ...session,
      transcript: [...session.transcript, chunk],
      wordCount: session.wordCount + wordCount,
      durationSeconds: Math.max(
        session.durationSeconds,
        chunk.elapsedSeconds + chunk.durationSeconds,
      ),
    };
  });
}

export async function appendSlice(
  sessionId: string,
  slice: LocalSummarySlice,
): Promise<void> {
  await updateSession(sessionId, (session) => ({
    ...session,
    slices: [...session.slices, slice],
  }));
}

export async function endSession(
  sessionId: string,
  finalSummary: string | null,
): Promise<void> {
  await updateSession(sessionId, (session) => ({
    ...session,
    endedAt: nowIso(),
    finalSummary: finalSummary ?? session.finalSummary,
  }));
}

export async function updateLocalSessionMeta(
  sessionId: string,
  patch: Partial<Pick<LocalSession, 'title' | 'participants' | 'tags'>>,
): Promise<void> {
  await updateSession(sessionId, (session) => ({
    ...session,
    ...patch,
  }));
}

export async function listLocalSessions(): Promise<LocalSession[]> {
  return tx('readonly', (store) => store.getAll())
    .then((result: any) => {
      const all = Array.isArray(result) ? (result as LocalSession[]) : [];
      return all.sort(
        (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
      );
    })
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.warn('[local-session-store] listLocalSessions failed:', err);
      return [];
    });
}

export async function deleteLocalSession(id: string): Promise<void> {
  if (!isLocalSessionId(id)) return;
  await tx('readwrite', (store) => store.delete(id));
}

export async function exportLocalSession(id: string): Promise<Blob | null> {
  const session = await getLocalSession(id);
  if (!session) return null;
  const md = buildSessionMarkdown(session);
  return new Blob([md], { type: 'text/markdown;charset=utf-8' });
}

function buildSessionMarkdown(session: LocalSession): string {
  const lines: string[] = [];
  lines.push(`# ${session.title}`);
  lines.push('');
  lines.push(`- Started: ${session.startedAt}`);
  if (session.endedAt) lines.push(`- Ended: ${session.endedAt}`);
  lines.push(`- Duration: ${session.durationSeconds.toFixed(1)}s`);
  lines.push(`- Word count: ${session.wordCount}`);
  if (session.participants.length) {
    lines.push(`- Participants: ${session.participants.join(', ')}`);
  }
  if (session.tags.length) {
    lines.push(`- Tags: ${session.tags.join(', ')}`);
  }
  lines.push('');
  lines.push('_Local-only session. Stored in browser IndexedDB; never sent to a server._');
  lines.push('');

  if (session.finalSummary) {
    lines.push('## Final summary');
    lines.push('');
    lines.push(session.finalSummary.trim());
    lines.push('');
  }

  if (session.slices.length) {
    lines.push('## Slice summaries');
    lines.push('');
    for (const slice of session.slices) {
      lines.push(`### ${slice.createdAt} (model: ${slice.model})`);
      lines.push('');
      lines.push(slice.text.trim());
      lines.push('');
    }
  }

  if (session.transcript.length) {
    lines.push('## Transcript');
    lines.push('');
    for (const chunk of session.transcript) {
      const stamp = formatTimestamp(chunk.elapsedSeconds);
      lines.push(`- [${stamp}] ${chunk.text.trim()}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

function formatTimestamp(elapsed: number): string {
  if (!Number.isFinite(elapsed) || elapsed < 0) return '00:00';
  const total = Math.floor(elapsed);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function countWords(text: string): number {
  if (!text) return 0;
  const m = text.trim().match(/\S+/g);
  return m ? m.length : 0;
}

export { isLocalSessionId };
