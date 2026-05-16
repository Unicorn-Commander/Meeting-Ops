import React, { useEffect, useRef, useState } from 'react';
import { Edit2, Check, RefreshCw, GitMerge, X } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

interface SpeakerLink {
  id: number;
  raw_label: string;
  speaker_id: number | null;
  speaker_display?: string | null;
}

interface SpeakerOption {
  id: number;
  display_name: string;
  has_centroid: boolean;
}

interface Props {
  /** Display name currently rendered for this segment (raw_label or
   *  resolved SpeakerProfile.display_name). */
  speaker: string;
  /** Recording session id (uuid or numeric — backend resolves both). */
  sessionId: string;
  /** All speaker_session_link rows for this session. */
  links: SpeakerLink[];
  /** All enrolled SpeakerProfiles in the org. */
  speakers: SpeakerOption[];
  /** Called after a successful mutation so the caller can refresh. */
  onChanged: () => void;
}

/**
 * Inline editor that turns a speaker label in the transcript into a
 * click-target. Click opens a popover with three actions:
 *
 *  - Rename + enroll: type a name -> create-or-reuse SpeakerProfile,
 *    grab the cluster's longest turn, embed via ECAPA, save voice
 *    sample, relabel the cluster. Powered by the
 *    /sessions/{id}/speaker-links/{link_id}/enroll endpoint.
 *
 *  - Assign to existing speaker: pick from the org's SpeakerProfiles
 *    via PATCH /speaker-links/{id}.
 *
 *  - Merge into another cluster: pick another cluster present in this
 *    session via POST /speaker-links/merge. Useful when pyannote
 *    over-splits one voice into multiple SPEAKER_XX clusters.
 */
export const SpeakerLabelEditor: React.FC<Props> = ({
  speaker,
  sessionId,
  links,
  speakers,
  onChanged,
}) => {
  const { activeOrganization } = useOrg();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'menu' | 'rename'>('menu');
  const [draftName, setDraftName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const orgHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
    return headers;
  };

  // Resolve which link this speaker label points at. The transcript
  // segment may show either raw_label (SPEAKER_00) or display_name
  // (Aaron Stransky). Match against either to find the right link row.
  const ownLink = links.find(
    (l) => l.raw_label === speaker || l.speaker_display === speaker,
  );
  const otherLinks = links.filter((l) => l.id !== ownLink?.id);

  // Close on outside click + Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
        setMode('menu');
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); setMode('menu'); }
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const handleEnroll = async () => {
    if (!ownLink) {
      setError('Could not find the speaker link for this segment.');
      return;
    }
    const name = draftName.trim();
    if (!name) {
      setError('Enter a name first.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/${ownLink.id}/enroll`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: name }),
        },
      );
      if (res.ok) {
        setOpen(false);
        setMode('menu');
        setDraftName('');
        onChanged();
      } else {
        const txt = await res.text();
        setError(`Save failed (${res.status}): ${txt.slice(0, 140)}`);
      }
    } catch (e) {
      setError('Network error.');
    }
    setBusy(false);
  };

  const handleAssign = async (speakerId: number) => {
    if (!ownLink) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/${ownLink.id}`,
        {
          method: 'PATCH',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ speaker_id: speakerId, confirmed: true }),
        },
      );
      if (res.ok) {
        setOpen(false);
        onChanged();
      } else {
        setError(`Assign failed (${res.status}).`);
      }
    } catch (e) {
      setError('Network error.');
    }
    setBusy(false);
  };

  const handleMerge = async (targetLinkId: number) => {
    if (!ownLink) return;
    if (!confirm(`Merge "${speaker}" into "${links.find(l => l.id === targetLinkId)?.speaker_display || links.find(l => l.id === targetLinkId)?.raw_label}"? This rewrites every turn of this cluster.`)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/merge`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_link_id: ownLink.id, target_link_id: targetLinkId }),
        },
      );
      if (res.ok) {
        setOpen(false);
        onChanged();
      } else {
        const txt = await res.text();
        setError(`Merge failed (${res.status}): ${txt.slice(0, 140)}`);
      }
    } catch (e) {
      setError('Network error.');
    }
    setBusy(false);
  };

  return (
    <span className="relative inline-flex items-center">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); setMode('menu'); setError(null); }}
        className="inline-flex items-center gap-1 text-sm font-medium text-purple-600 hover:text-purple-800 hover:underline group"
        title="Click to rename or merge this speaker"
      >
        {speaker}
        <Edit2 className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
      </button>

      {open && (
        <div
          ref={popoverRef}
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-full mt-1 z-30 w-72 rounded-lg border border-gray-200 bg-white shadow-xl text-gray-800"
        >
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
            <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Speaker</span>
            <button
              onClick={() => { setOpen(false); setMode('menu'); }}
              className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {error && (
            <div className="px-3 py-2 text-xs text-red-600 bg-red-50 border-b border-red-100">
              {error}
            </div>
          )}

          {mode === 'menu' && (
            <div className="p-2 space-y-1">
              <button
                onClick={() => { setMode('rename'); setDraftName(''); setError(null); }}
                className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-purple-50 text-gray-700 hover:text-purple-700"
              >
                Rename + enroll voice…
              </button>

              {speakers.length > 0 && (
                <div className="pt-1 pb-0.5">
                  <p className="px-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                    Assign to existing
                  </p>
                  <div className="max-h-32 overflow-y-auto">
                    {speakers.map((s) => (
                      <button
                        key={s.id}
                        disabled={busy}
                        onClick={() => handleAssign(s.id)}
                        className="w-full text-left px-2 py-1 rounded text-sm hover:bg-purple-50 text-gray-700 hover:text-purple-700 truncate"
                      >
                        {s.display_name}
                        {!s.has_centroid && (
                          <span className="ml-1 text-[10px] text-gray-400">(no voice sample yet)</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {otherLinks.length > 0 && (
                <div className="pt-1 pb-0.5 border-t border-gray-100">
                  <p className="px-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                    Merge into another cluster
                  </p>
                  <div className="max-h-32 overflow-y-auto">
                    {otherLinks.map((l) => (
                      <button
                        key={l.id}
                        disabled={busy}
                        onClick={() => handleMerge(l.id)}
                        className="w-full text-left px-2 py-1 rounded text-sm hover:bg-amber-50 text-gray-700 hover:text-amber-700 flex items-center gap-2"
                      >
                        <GitMerge className="h-3 w-3" />
                        <span className="truncate">{l.speaker_display || l.raw_label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {busy && (
                <div className="px-2 py-1 text-xs text-gray-500 flex items-center gap-1">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Working…
                </div>
              )}
            </div>
          )}

          {mode === 'rename' && (
            <div className="p-3 space-y-2">
              <input
                type="text"
                value={draftName}
                placeholder="e.g. Aaron Stransky"
                autoFocus
                onChange={(e) => setDraftName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !busy) handleEnroll(); }}
                disabled={busy}
                className="w-full rounded border border-purple-400 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={() => { setMode('menu'); setError(null); }}
                  disabled={busy}
                  className="px-2.5 py-1 text-xs text-gray-600 hover:text-gray-800 disabled:opacity-50"
                >
                  Back
                </button>
                <button
                  onClick={handleEnroll}
                  disabled={busy || !draftName.trim()}
                  className="inline-flex items-center gap-1 rounded bg-purple-600 px-3 py-1 text-xs font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                >
                  {busy ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                  Save
                </button>
              </div>
              <p className="text-[10px] text-gray-500">
                Creates (or reuses) a speaker profile by name and enrolls a voice
                sample from this cluster's longest turn for auto-recognition in
                future meetings.
              </p>
            </div>
          )}
        </div>
      )}
    </span>
  );
};

export default SpeakerLabelEditor;
