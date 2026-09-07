// Badges + links for combined meetings (v1, 2026-09-07).
//
// A *combined meeting* is a session row that links to its parts in time
// order and owns only a unified summary / insights / action items. The
// parts keep their own audio, transcript and speakers. These two tiny
// presentational pieces are shared by the Sessions list (dark surface)
// and the SessionDetails header (light surface) so the two never drift.
import { Layers } from 'lucide-react';
import { Link } from 'react-router-dom';

export interface PartOfRef {
  id: number | string;
  name: string;
}

type Tone = 'dark' | 'light';

interface CombinedBadgeProps {
  partsCount: number;
  className?: string;
  tone?: Tone;
}

/** `Combined · N parts` pill. Sized by the caller via className. */
export function CombinedBadge({ partsCount, className = '', tone = 'dark' }: CombinedBadgeProps) {
  const palette = tone === 'light'
    ? 'border-sky-300 bg-sky-50 text-sky-800'
    : 'border-sky-500/40 bg-sky-500/10 text-sky-200';
  return (
    <span
      title="Combined meeting — one summary over several recordings. Open a part for its audio and transcript."
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border ${palette} ${className}`}
      data-testid="combined-badge"
    >
      <Layers className="h-3 w-3" aria-hidden="true" />
      Combined · {partsCount} part{partsCount === 1 ? '' : 's'}
    </span>
  );
}

interface PartOfLinksProps {
  partOf: PartOfRef[];
  className?: string;
  tone?: Tone;
}

/** `Part of <name>` link(s) shown on a session that belongs to one or more
 *  combined meetings. Clicks stop propagation so a card-level onClick
 *  (open session) doesn't also fire. */
export function PartOfLinks({ partOf, className = '', tone = 'dark' }: PartOfLinksProps) {
  if (!partOf || partOf.length === 0) return null;
  const text = tone === 'light' ? 'text-sky-700 hover:text-sky-900' : 'text-sky-300 hover:text-sky-100';
  const muted = tone === 'light' ? 'text-gray-500' : 'text-gray-400';
  return (
    <span className={`inline-flex flex-wrap items-center gap-x-1 text-xs ${muted} ${className}`}>
      <Layers className="h-3 w-3" aria-hidden="true" />
      Part of{' '}
      {partOf.map((ref, idx) => (
        <span key={String(ref.id)}>
          {idx > 0 && ', '}
          <Link
            to={`/sessions/${ref.id}`}
            onClick={(event) => event.stopPropagation()}
            className={`underline decoration-dotted underline-offset-2 ${text}`}
            title={`Open combined meeting: ${ref.name}`}
          >
            {ref.name}
          </Link>
        </span>
      ))}
    </span>
  );
}
