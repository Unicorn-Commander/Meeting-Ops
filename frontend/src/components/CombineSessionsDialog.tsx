// Confirm dialog for "Combine selected" on the Sessions list (v1, 2026-09-07).
//
// Shows the selected recordings in the order they will be combined
// (earliest first), lets the user name the combined meeting, and hands
// the final name back to the caller, which POSTs /api/sessions/combine.
// Pure presentation: no fetch in here so it can be unit-tested directly.
import { useEffect, useState } from 'react';
import { Calendar, Clock, Layers, Loader2 } from 'lucide-react';
import { Dialog } from './ui/Dialog';

export interface CombinePart {
  /** The list's session id (uuid-or-int string), sent back to the server as-is. */
  id: string;
  name: string;
  /** Best-known start of the recording (ISO). Null sorts last. */
  startedAt: string | null;
  /** Seconds. */
  duration?: number | null;
}

/** Earliest first; unknown start last; ties broken by id (numeric-aware). */
export function orderParts(parts: CombinePart[]): CombinePart[] {
  const key = (p: CombinePart) => {
    const t = p.startedAt ? Date.parse(p.startedAt) : NaN;
    return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
  };
  const idCmp = (a: string, b: string) => {
    const na = Number(a);
    const nb = Number(b);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return a.localeCompare(b);
  };
  return [...parts].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka !== kb) return ka < kb ? -1 : 1; // finite always sorts before Infinity
    return idCmp(a.id, b.id);
  });
}

/** Mirrors the server default: `<earliest part name> (combined, N parts)`. */
export function defaultCombinedName(orderedParts: CombinePart[]): string {
  if (orderedParts.length === 0) return '';
  const first = orderedParts[0].name?.trim() || 'Meeting';
  return `${first} (combined, ${orderedParts.length} parts)`;
}

function formatStart(iso: string | null): string {
  if (!iso) return 'date unknown';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'date unknown';
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return '—';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${total}s`;
}

export interface CombineSessionsDialogProps {
  open: boolean;
  /** Selected sessions, any order — the dialog sorts them. */
  parts: CombinePart[];
  busy?: boolean;
  error?: string | null;
  onConfirm: (name: string, orderedIds: string[]) => void;
  onCancel: () => void;
}

export default function CombineSessionsDialog({
  open,
  parts,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: CombineSessionsDialogProps) {
  const ordered = orderParts(parts);
  const suggested = defaultCombinedName(ordered);
  const [name, setName] = useState(suggested);

  // Re-seed the name whenever the dialog opens for a (possibly) different
  // selection; keep the user's edits while it stays open.
  useEffect(() => {
    if (open) setName(suggested);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, suggested]);

  if (!open) return null;

  const trimmed = name.trim();
  const canConfirm = ordered.length >= 2 && !busy;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onCancel(); }}>
      <Dialog.Content
        size="lg"
        onOpenAutoFocus={(event) => {
          // Land on the name field so Enter/typing is the natural flow.
          event.preventDefault();
          (document.getElementById('combine-sessions-name') as HTMLInputElement | null)?.focus();
        }}
      >
        <Dialog.Header>
          <div className="flex items-start gap-3">
            <Layers className="mt-0.5 h-5 w-5 text-sky-300" aria-hidden="true" />
            <div>
              <Dialog.Title>
                Combine {ordered.length} recordings
              </Dialog.Title>
              <Dialog.Description className="mt-1">
                The recordings stay separate. A new combined meeting gets one summary,
                insights and action items generated over all of them, in this order.
              </Dialog.Description>
            </div>
          </div>
          <Dialog.Close />
        </Dialog.Header>

        <div className="space-y-4 px-5 py-4">
          <ol className="space-y-1.5" aria-label="Parts in order">
            {ordered.map((part, index) => (
              <li
                key={part.id}
                className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-sm"
                data-testid="combine-part"
              >
                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-600/30 text-xs font-semibold text-sky-100">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-zinc-100" title={part.name}>
                  {part.name}
                </span>
                <span className="inline-flex shrink-0 items-center gap-1 text-xs text-zinc-400">
                  <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
                  {formatStart(part.startedAt)}
                </span>
                <span className="inline-flex w-14 shrink-0 items-center justify-end gap-1 text-xs tabular-nums text-zinc-400">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {formatDuration(part.duration)}
                </span>
              </li>
            ))}
          </ol>

          <label className="block text-sm text-zinc-300" htmlFor="combine-sessions-name">
            Combined meeting name
            <input
              id="combine-sessions-name"
              type="text"
              value={name}
              maxLength={200}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && canConfirm) {
                  event.preventDefault();
                  onConfirm(trimmed || suggested, ordered.map((p) => p.id));
                }
              }}
              className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-sky-500 focus:outline-none"
              placeholder={suggested}
            />
          </label>

          {error && (
            <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">
              {error}
            </p>
          )}
        </div>

        <Dialog.Footer>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(trimmed || suggested, ordered.map((p) => p.id))}
            disabled={!canConfirm}
            className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Layers className="h-4 w-4" aria-hidden="true" />}
            {busy ? 'Combining…' : `Combine ${ordered.length} recordings`}
          </button>
        </Dialog.Footer>
      </Dialog.Content>
    </Dialog>
  );
}
