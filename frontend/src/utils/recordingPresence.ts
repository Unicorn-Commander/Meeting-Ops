/**
 * Cross-surface recording presence flags. Used by the
 * simultaneous-recording guard so the Record button warns when always-on
 * is active and vice versa.
 *
 * Why localStorage + storage events instead of a React context:
 *   - Both surfaces (always-on, explicit Record) can run from different
 *     React subtrees + even cross-tab in some PWA flows. localStorage +
 *     the native `storage` event is the simplest cross-realm channel.
 *   - The flags are advisory. The actual recording session lifecycle is
 *     still owned by AlwaysOnContext / LiveRecording / DesktopBrowserRecorder
 *     / MobileLiveRecording. This module only writes the flag and reads
 *     the OTHER flag for a "collision?" check.
 *
 * Keys + values:
 *   - meetingops.alwayson.active: 'true' when an always-on session is
 *     running (between start() and stop()). Cleared otherwise.
 *   - meetingops.record.active: 'true' when an explicit Record button
 *     session is running. Cleared otherwise.
 *
 * On a real collision we surface a confirm modal asking the user to stop
 * the other one first. Modal lives in components/ConfirmModal.tsx; this
 * module just exposes the state.
 *
 * Note: these flags are best-effort. A page crash that kills the
 * always-on tab without firing the unload handler will leave the flag
 * stuck. The check `isStaleFlag()` heuristic (looking at lastBeat) lets
 * the caller decide to ignore the flag if it's been ages since the last
 * heartbeat — but we keep the check simple for v1 and let the user clear
 * via "Stop it first" prompt.
 */

export const ALWAYSON_ACTIVE_KEY = 'meetingops.alwayson.active';
export const RECORD_ACTIVE_KEY = 'meetingops.record.active';

export const ALWAYSON_ACTIVE_EVENT = 'meetingops:alwayson-active-changed';
export const RECORD_ACTIVE_EVENT = 'meetingops:record-active-changed';

function safeLocalStorage(): Storage | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

function readFlag(key: string): boolean {
  const ls = safeLocalStorage();
  if (!ls) return false;
  return ls.getItem(key) === 'true';
}

function writeFlag(key: string, value: boolean, eventName: string): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  if (value) {
    ls.setItem(key, 'true');
  } else {
    ls.removeItem(key);
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<boolean>(eventName, { detail: value }),
    );
  }
}

export function isAlwaysOnActive(): boolean {
  return readFlag(ALWAYSON_ACTIVE_KEY);
}

export function isRecordActive(): boolean {
  return readFlag(RECORD_ACTIVE_KEY);
}

export function setAlwaysOnActive(active: boolean): void {
  writeFlag(ALWAYSON_ACTIVE_KEY, active, ALWAYSON_ACTIVE_EVENT);
}

export function setRecordActive(active: boolean): void {
  writeFlag(RECORD_ACTIVE_KEY, active, RECORD_ACTIVE_EVENT);
}

/**
 * Subscribe to changes to either flag. Returns an unsubscribe function.
 *
 * Listens to BOTH the same-tab custom events (synchronous, written by
 * the helpers above) AND the native cross-tab `storage` event (fires
 * when another tab writes the same key).
 */
export function subscribeRecordingPresence(
  callback: (state: { alwaysOn: boolean; record: boolean }) => void,
): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const emit = () => callback({
    alwaysOn: isAlwaysOnActive(),
    record: isRecordActive(),
  });

  const onAlwaysOn = () => emit();
  const onRecord = () => emit();
  const onStorage = (event: StorageEvent) => {
    if (event.key === ALWAYSON_ACTIVE_KEY || event.key === RECORD_ACTIVE_KEY) {
      emit();
    }
  };

  window.addEventListener(ALWAYSON_ACTIVE_EVENT, onAlwaysOn as EventListener);
  window.addEventListener(RECORD_ACTIVE_EVENT, onRecord as EventListener);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(ALWAYSON_ACTIVE_EVENT, onAlwaysOn as EventListener);
    window.removeEventListener(RECORD_ACTIVE_EVENT, onRecord as EventListener);
    window.removeEventListener('storage', onStorage);
  };
}
