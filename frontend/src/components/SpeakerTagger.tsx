import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Users, Check, X, RefreshCw, AlertCircle, Play, Search, CircleHelp } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';
import { showToast } from './Toast';
import { SpeakerCombobox, type PickerChoice, type PickerContact, type PickerSpeaker } from './SpeakerCombobox';

interface SpeakerLink {
  id: number;
  session_id: number;
  raw_label: string;
  speaker_id: number | null;
  speaker_name: string | null;
  similarity: number | null;
  source: 'auto' | 'manual';
  confirmed: boolean;
  /**
   * Backend contract (speakers.py): true = a sample was folded into the
   * caller's account voiceprint this request; false = a fold was attempted
   * but skipped (consistency floor / dim guard / no embedding); null or
   * absent = no fold was applicable.
   */
  my_voice_folded?: boolean | null;
  /**
   * Self-introduction name suggestions derived from THIS speaker's own
   * utterances (backend contract: speakers.py SelfIntroName). Only present
   * for unnamed links (speaker_id == null); [] otherwise. Always a
   * suggestion the user confirms — prefills the enroll input, never
   * auto-applies. `evidence` is the source sentence for the chip tooltip.
   */
  name_suggestions?: { name: string; evidence?: string }[];
}

/** Honest fingerprint toast keyed off `my_voice_folded` (see above). */
const toastVoiceFold = (folded: boolean | null | undefined): void => {
  if (folded === true) {
    showToast.success('Your personal voice fingerprint was updated.');
  } else if (folded === false) {
    showToast.warning(
      "Couldn't update your voice fingerprint from this meeting (audio didn't match or no usable sample).",
    );
  }
};

interface SpeakerOption extends PickerSpeaker {
  has_centroid: boolean;
  sample_count: number;
}

/** Names are rewritten in place the moment a voice is named; the LLM
 *  summary pass waits for a quiet period after the LAST pick (backend
 *  SPEAKER_SUMMARY_REFRESH_DEBOUNCE_SECONDS), so corrections are cheap. */
const NAMED_TOAST = 'Name applied to the transcript, summary and action items. The summary gets a full refresh a couple of minutes after your last change.';

interface SpeakerTaggerProps {
  sessionId: string;
  onChange?: (links: SpeakerLink[]) => void;
  segments?: SpeakerSampleSegment[];
  onPlaySample?: (start: number, end: number) => void;
}

export interface SpeakerSampleSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  raw_label?: string;
}

/**
 * SpeakerTagger — inline UI for confirming or changing the
 * speaker_session_link rows for a single session. Surfaces under the
 * SessionDetails header so users can fix labels without leaving the page.
 */
export const SpeakerTagger: React.FC<SpeakerTaggerProps> = ({
  sessionId,
  onChange,
  segments = [],
  onPlaySample,
}) => {
  const { activeOrganization } = useOrg();
  const [links, setLinks] = useState<SpeakerLink[]>([]);
  const [speakers, setSpeakers] = useState<SpeakerOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [identifying, setIdentifying] = useState(false);
  const [pendingLinkId, setPendingLinkId] = useState<number | null>(null);
  const [redetecting, setRedetecting] = useState(false);
  const [redetectCount, setRedetectCount] = useState<number>(2);
  // null = auto-detect speaker count (no num_speakers hint); use threshold instead.
  const [redetectAuto, setRedetectAuto] = useState<boolean>(false);
  // "This is me" — when checked, the next assign/enroll also updates the
  // current user's personal voice fingerprint (is_me: true in the body).
  // Unchecked by default and reset after a successful send so labeling
  // someone ELSE afterwards can't pollute the user's voiceprint.
  const [isMe, setIsMe] = useState(false);
  // Start in the smallest, highest-value queue: voices without a human name.
  // This is local presentation state only; it never changes a speaker link.
  const [reviewFilter, setReviewFilter] = useState<'unidentified' | 'needs-review' | 'all'>('unidentified');
  const [searchQuery, setSearchQuery] = useState('');


  const orgHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeOrganization?.slug) {
      headers['X-MeetingOps-Org'] = activeOrganization.slug;
    }
    return headers;
  };

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [linksRes, speakersRes] = await Promise.all([
        fetch(`${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links`, { headers: orgHeaders() }),
        fetch(
          `${config.apiBaseUrl}/api/speakers?session_id=${encodeURIComponent(sessionId)}`,
          { headers: orgHeaders() },
        ),
      ]);
      if (linksRes.ok) {
        const data: SpeakerLink[] = await linksRes.json();
        setLinks(data);
        if (onChange) onChange(data);
      } else if (linksRes.status === 404) {
        setLinks([]);
      } else {
        setError(`Failed to load speaker links (HTTP ${linksRes.status}).`);
      }
      if (speakersRes.ok) {
        setSpeakers(await speakersRes.json());
      }
    } catch (e) {
      setError('Network error loading speaker labels.');
    }
    setLoading(false);
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, activeOrganization?.slug]);

  const reidentify = async () => {
    setIdentifying(true);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/identify-speakers`,
        { method: 'POST', headers: orgHeaders() },
      );
      if (res.ok) {
        await loadAll();
      } else {
        setError(`Re-identify failed (HTTP ${res.status}).`);
      }
    } catch (e) {
      setError('Network error during re-identify.');
    }
    setIdentifying(false);
  };

  const pollRediarize = async (): Promise<void> => {
    const deadline = Date.now() + 6 * 60 * 1000; // 6 minutes
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 4000));
      try {
        const res = await fetch(
          `${config.apiBaseUrl}/api/sessions/${sessionId}/rediarize-status`,
          { headers: orgHeaders() },
        );
        if (!res.ok) continue;
        const data = await res.json();
        if (data.status === 'done') {
          await loadAll();
          return;
        }
        if (data.status === 'failed') {
          setError(`Re-detect failed: ${data.error || 'unknown error'}`);
          return;
        }
        // queued or running — keep polling
      } catch {
        // transient network blip; just keep polling
      }
    }
    setError('Re-detect timed out after 6 minutes. The job may still be running; refresh shortly.');
  };

  const redetectSpeakers = async () => {
    setRedetecting(true);
    setError(null);
    try {
      // Auto = plain auto-detect ({}). The speaker-svc rejects per-request
      // clustering_threshold overrides (VRAM churn — env-var-only now), so
      // sending one 400s the whole re-detect.
      const body: any = redetectAuto ? {} : { num_speakers: redetectCount };
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/rediarize`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
      );
      if (res.status === 202 || res.ok) {
        // Async path: backend accepted the job, poll for completion.
        await pollRediarize();
      } else {
        const txt = await res.text();
        setError(`Re-detect failed (HTTP ${res.status}): ${txt.slice(0, 120)}`);
      }
    } catch (e) {
      setError('Network error during re-detect.');
    }
    setRedetecting(false);
  };

  const searchContacts = useCallback(async (q: string): Promise<PickerContact[]> => {
    const res = await fetch(
      `${config.apiBaseUrl}/api/contact-ops/people/search?q=${encodeURIComponent(q)}&limit=8`,
      { headers: orgHeaders() },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data?.items) ? data.items : [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOrganization?.slug]);

  const applyUpdatedLink = (updated: SpeakerLink) => {
    const next = links.map(l => (l.id === updated.id ? updated : l));
    setLinks(next);
    if (onChange) onChange(next);
    toastVoiceFold(updated.my_voice_folded);
  };

  const readError = async (res: Response, what: string) => {
    let detail = '';
    try {
      const body = await res.json();
      detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* not JSON */ }
    return detail || `${what} failed (HTTP ${res.status}).`;
  };

  const updateLink = async (
    link: SpeakerLink,
    speakerId: number | null,
    contactId?: string,
  ): Promise<boolean> => {
    setPendingLinkId(link.id);
    setError(null);
    // Only stamp the user's voiceprint when actually assigning a speaker
    // (not when clearing back to Unknown).
    const sendIsMe = isMe && speakerId !== null;
    let ok = false;
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/${link.id}`,
        {
          method: 'PATCH',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            speaker_id: speakerId,
            confirmed: true,
            ...(sendIsMe ? { is_me: true } : {}),
            ...(contactId ? { contact_id: contactId } : {}),
          }),
        },
      );
      if (res.ok) {
        applyUpdatedLink(await res.json());
        if (sendIsMe) setIsMe(false);
        if (speakerId !== null) showToast.info(NAMED_TOAST);
        ok = true;
      } else {
        setError(await readError(res, 'Updating the label'));
      }
    } catch {
      setError('Network error updating speaker label.');
    }
    setPendingLinkId(null);
    return ok;
  };

  /**
   * Name a voice as a NEW (or same-name) speaker. Enroll first — it also
   * saves a voice sample so the next meeting recognizes them — and fall
   * back to a name-only profile when this voice has no clean audio turn
   * (short clusters, transcript-only imports).
   */
  const nameVoice = async (
    link: SpeakerLink,
    person: { display_name: string; email?: string | null; contact_id?: string },
  ): Promise<void> => {
    const name = person.display_name.trim();
    if (!name) return;
    setPendingLinkId(link.id);
    setError(null);
    const body = {
      display_name: name,
      ...(person.email ? { email: person.email } : {}),
      ...(person.contact_id ? { contact_id: person.contact_id } : {}),
      ...(isMe ? { is_me: true } : {}),
    };
    const post = (path: string) => fetch(
      `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/${link.id}/${path}`,
      {
        method: 'POST',
        headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
    try {
      let res = await post('enroll');
      if (res.status === 400) {
        // No usable audio for this voice: create a name-only profile. That
        // endpoint only fills an unassigned voice, so clear it first.
        if (link.speaker_id !== null && !(await updateLink(link, null))) {
          setPendingLinkId(null);
          return;
        }
        setPendingLinkId(link.id);
        res = await post('create-speaker');
      }
      if (res.ok) {
        applyUpdatedLink(await res.json());
        if (isMe) setIsMe(false);
        // A new profile may exist now; re-pull the people list.
        await loadAll();
        showToast.info(person.contact_id ? `Linked to ${name} in Contact-Ops. ${NAMED_TOAST}` : NAMED_TOAST);
      } else {
        setError(await readError(res, 'Naming the speaker'));
      }
    } catch {
      setError('Network error naming the speaker.');
    }
    setPendingLinkId(null);
  };

  const onPick = async (link: SpeakerLink, choice: PickerChoice) => {
    switch (choice.kind) {
      case 'speaker':
        if (choice.speaker.id !== link.speaker_id || !link.confirmed) {
          await updateLink(link, choice.speaker.id);
        }
        return;
      case 'clear':
        await updateLink(link, null);
        return;
      case 'create':
        await nameVoice(link, { display_name: choice.name });
        return;
      case 'contact': {
        const { contact, speaker } = choice;
        if (speaker) {
          const needsLink = speaker.contact_id !== contact.person_id;
          if (await updateLink(link, speaker.id, needsLink ? contact.person_id : undefined)) {
            if (needsLink) {
              await loadAll();
              showToast.success(`${speaker.display_name} is now linked to their Contact-Ops contact.`);
            }
          }
          return;
        }
        await nameVoice(link, {
          display_name: contact.display_name,
          email: contact.email,
          contact_id: contact.person_id,
        });
        return;
      }
    }
  };

  const unidentifiedCount = links.filter(link => link.speaker_id === null).length;
  const needsReviewCount = links.filter(link => !link.confirmed).length;
  const normalizedSearch = searchQuery.trim().toLocaleLowerCase();
  // If every voice is named, an empty unidentified queue should not look like
  // a broken screen. Keep the control selected, but transparently show all
  // voices and explain why in the helper copy below.
  const effectiveFilter = reviewFilter === 'unidentified' && unidentifiedCount === 0
    ? 'all'
    : reviewFilter;
  const visibleLinks = useMemo(() => links
    .filter(link => {
      if (effectiveFilter === 'unidentified' && link.speaker_id !== null) return false;
      if (effectiveFilter === 'needs-review' && link.confirmed) return false;
      if (!normalizedSearch) return true;
      const searchable = [
        link.raw_label,
        link.speaker_name || '',
        ...(link.name_suggestions || []).flatMap(suggestion => [suggestion.name, suggestion.evidence || '']),
      ].join(' ').toLocaleLowerCase();
      return searchable.includes(normalizedSearch);
    })
    // Even in "All voices", keep unresolved identity work at the top.
    .sort((a, b) => {
      const rank = (link: SpeakerLink) => link.speaker_id === null ? 0 : !link.confirmed ? 1 : 2;
      return rank(a) - rank(b) || a.raw_label.localeCompare(b.raw_label);
    }), [links, effectiveFilter, normalizedSearch]);

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4 text-sm text-gray-500 flex items-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin" />
        Loading speaker labels…
      </div>
    );
  }

  if (links.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-3">
          <Users className="w-4 h-4" />
          No diarized speakers detected for this session.
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-gray-600">Re-detect with</label>
          <label className="flex items-center gap-1 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={redetectAuto}
              onChange={(e) => setRedetectAuto(e.target.checked)}
              className="h-3 w-3"
            />
            Auto
          </label>
          {!redetectAuto && (
            <>
              <input
                type="number"
                min={1}
                max={24}
                value={redetectCount}
                onChange={(e) => setRedetectCount(Math.max(1, Math.min(24, Number(e.target.value) || 1)))}
                className="w-16 rounded border border-gray-300 px-2 py-1 text-sm"
              />
              <label className="text-xs text-gray-600">speakers</label>
            </>
          )}
          <button
            onClick={redetectSpeakers}
            disabled={redetecting}
            className="text-xs px-3 py-1 rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
            title={redetectAuto ? 'Re-run diarization with auto speaker detection' : 'Re-run diarization with this speaker count'}
          >
            {redetecting ? <RefreshCw className="w-3 h-3 animate-spin" /> : null}
            Run
          </button>
        </div>
        {error && (
          <div className="mt-2 text-xs text-red-600 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3 gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <Users className="w-4 h-4 text-purple-600" />
          Speaker labels
          <span className="text-xs text-gray-400">({links.length})</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={redetectAuto}
              onChange={(e) => setRedetectAuto(e.target.checked)}
              className="h-3 w-3"
            />
            Auto
          </label>
          {!redetectAuto && (
            <input
              type="number"
              min={1}
              max={24}
              value={redetectCount}
              onChange={(e) => setRedetectCount(Math.max(1, Math.min(24, Number(e.target.value) || 1)))}
              className="w-12 rounded border border-gray-300 px-1 py-0.5 text-xs"
              title="Speakers"
            />
          )}
          <button
            onClick={redetectSpeakers}
            disabled={redetecting}
            className="text-xs px-2 py-1 rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
            title={redetectAuto ? "Re-run diarization with auto speaker detection" : "Re-run diarization with this speaker count"}
          >
            {redetecting ? <RefreshCw className="w-3 h-3 animate-spin" /> : null}
            Re-detect
          </button>
          <button
            onClick={reidentify}
            disabled={identifying}
            className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50 flex items-center gap-1"
            title="Match existing labels against the speaker library"
          >
            {identifying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Re-identify
          </button>
        </div>
      </div>

      {onPlaySample && segments.length > 0 && (
        <p className="mb-3 text-xs text-gray-500">
          Listen to representative moments, then assign each voice to a person.
          Samples play from this meeting&apos;s existing audio and are not saved as
          separate biometric clips.
        </p>
      )}

      <div className="mb-3 rounded-lg border border-purple-100 bg-purple-50/60 p-2.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-1.5" aria-label="Speaker review filter">
            {([
              ['unidentified', `Needs a name (${unidentifiedCount})`],
              ['needs-review', `Needs review (${needsReviewCount})`],
              ['all', `All voices (${links.length})`],
            ] as const).map(([filter, label]) => (
              <button
                key={filter}
                type="button"
                onClick={() => setReviewFilter(filter)}
                aria-pressed={reviewFilter === filter}
                className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-1 ${
                  reviewFilter === filter
                    ? 'bg-purple-600 text-white'
                    : 'bg-white text-purple-800 ring-1 ring-purple-200 hover:bg-purple-100'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="relative block min-w-0 sm:w-64">
            <span className="sr-only">Search speaker labels and name suggestions</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Find a voice or name…"
              className="w-full rounded-md border border-purple-200 bg-white py-1.5 pl-8 pr-7 text-xs text-gray-900 placeholder:text-gray-400 focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
                aria-label="Clear speaker search"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </label>
        </div>
        <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-4 text-purple-900">
          <CircleHelp className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          {unidentifiedCount > 0
            ? 'Start with “Needs a name”: listen, then search for the person (or a Contact-Ops contact) and pick them. Nothing changes until you pick.'
            : 'Every detected voice has a name. Use “Needs review” to confirm suggested matches or “All voices” to revisit a label.'}
        </p>
      </div>

      {error && (
        <div className="mb-2 text-xs text-red-600 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          {error}
        </div>
      )}

      <label className="mb-3 flex items-start gap-2 text-xs text-gray-600 cursor-pointer">
        <input
          type="checkbox"
          checked={isMe}
          onChange={(e) => setIsMe(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 accent-purple-600"
        />
        <span>This is me — also update my personal voice fingerprint when I label a speaker below</span>
      </label>

      <p className="mb-2 text-xs text-gray-500" aria-live="polite">
        Showing {visibleLinks.length} of {links.length} voice{links.length === 1 ? '' : 's'}
        {effectiveFilter === 'unidentified' ? ' that need a name' : ''}.
      </p>
      <div className="space-y-2">
        {visibleLinks.map(link => {
          const sim = link.similarity ?? null;
          const simBadge = sim !== null ? `${(sim * 100).toFixed(0)}%` : null;
          const representativeSamples = segments
            .filter((segment) => {
              const raw = (segment.raw_label || '').trim();
              const named = (segment.speaker || '').trim();
              return (
                Number.isFinite(segment.start) &&
                !!segment.text?.trim() &&
                (
                  raw === link.raw_label ||
                  named === link.raw_label ||
                  (!!link.speaker_name && named === link.speaker_name)
                )
              );
            })
            .sort((a, b) => {
              const score = (segment: SpeakerSampleSegment) => {
                const duration = Math.max(0, segment.end - segment.start);
                const words = segment.text.trim().split(/\s+/).length;
                return Math.min(duration, 12) * 2 + Math.min(words, 30);
              };
              return score(b) - score(a);
            })
            .slice(0, 3);
          return (
            <div key={link.id} className={`rounded-lg border p-3 ${link.speaker_id === null ? 'border-amber-300 bg-amber-50/60' : link.confirmed ? 'border-gray-200 bg-gray-50/70' : 'border-blue-200 bg-blue-50/50'}`}>
            <div className="flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:gap-3">
              <span className="font-mono text-xs text-gray-500 w-24 truncate" title={link.raw_label}>
                {link.raw_label}
              </span>
              <SpeakerCombobox
                label={`Speaker for ${link.raw_label}`}
                speakers={speakers}
                value={link.speaker_id}
                suggestions={(link.name_suggestions || []).map(sugg => sugg.name)}
                searchContacts={searchContacts}
                onPick={choice => { void onPick(link, choice); }}
                busy={pendingLinkId === link.id}
              />
              {link.confirmed && (
                <span title="Manually confirmed" className="text-green-600">
                  <Check className="w-4 h-4" />
                </span>
              )}
              {!link.confirmed && link.source === 'auto' && simBadge && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700" title="Auto-matched confidence">
                  {simBadge}
                </span>
              )}
              {!link.confirmed && link.source === 'auto' && !simBadge && link.speaker_id === null && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-800" title="No matching profile was found">
                  no match · needs a name
                </span>
              )}
            </div>
            <p className={`mt-1.5 text-xs ${link.speaker_id === null ? 'text-amber-800' : link.confirmed ? 'text-green-700' : 'text-blue-700'}`}>
              {link.speaker_id === null
                ? 'Unidentified voice — search for the person, pick a Contact-Ops contact, or type a new name.'
                : link.confirmed
                  ? 'Confirmed identity.'
                  : 'Suggested identity — confirm or correct it after listening.'}
            </p>
            {onPlaySample && representativeSamples.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {representativeSamples.map((sample, index) => {
                  const mins = Math.floor(sample.start / 60);
                  const secs = Math.floor(sample.start % 60).toString().padStart(2, '0');
                  const excerpt = sample.text.trim().replace(/\s+/g, ' ');
                  return (
                    <button
                      key={`${sample.start}-${index}`}
                      type="button"
                      onClick={() => onPlaySample(sample.start, sample.end)}
                      className="group inline-flex max-w-full items-center gap-1.5 rounded-full border border-purple-200 bg-white px-2.5 py-1 text-xs text-purple-700 shadow-sm hover:border-purple-400 hover:bg-purple-50"
                      title={`Play ${link.speaker_name || link.raw_label} at ${mins}:${secs}`}
                    >
                      <Play className="h-3 w-3 shrink-0 fill-current" />
                      <span className="font-mono text-[10px] text-purple-500">{mins}:{secs}</span>
                      <span className="max-w-[18rem] truncate text-gray-600">
                        {excerpt}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            </div>
          );
        })}
        {visibleLinks.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-sm text-gray-600">
            No voices match this view. Try clearing the search or choose “All voices”.
          </div>
        )}
      </div>
    </div>
  );
};
