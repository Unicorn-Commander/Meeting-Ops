import React, { useEffect, useState } from 'react';
import { Users, Check, X, RefreshCw, AlertCircle } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

interface SpeakerLink {
  id: number;
  session_id: number;
  raw_label: string;
  speaker_id: number | null;
  speaker_name: string | null;
  similarity: number | null;
  source: 'auto' | 'manual';
  confirmed: boolean;
}

interface SpeakerOption {
  id: number;
  display_name: string;
  has_centroid: boolean;
  sample_count: number;
}

interface SpeakerTaggerProps {
  sessionId: string;
  onChange?: (links: SpeakerLink[]) => void;
}

/**
 * SpeakerTagger — inline UI for confirming or changing the
 * speaker_session_link rows for a single session. Surfaces under the
 * SessionDetails header so users can fix labels without leaving the page.
 */
export const SpeakerTagger: React.FC<SpeakerTaggerProps> = ({ sessionId, onChange }) => {
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
  const [redetectThreshold, setRedetectThreshold] = useState<number>(0.72);


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
        fetch(`${config.apiBaseUrl}/api/speakers`, { headers: orgHeaders() }),
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

  const redetectSpeakers = async () => {
    setRedetecting(true);
    setError(null);
    try {
      const body: any = redetectAuto
        ? { clustering_threshold: redetectThreshold }
        : { num_speakers: redetectCount };
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/rediarize`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
      );
      if (res.ok) {
        await loadAll();
      } else {
        const txt = await res.text();
        setError(`Re-detect failed (HTTP ${res.status}): ${txt.slice(0, 120)}`);
      }
    } catch (e) {
      setError('Network error during re-detect.');
    }
    setRedetecting(false);
  };

  const updateLink = async (link: SpeakerLink, speakerId: number | null) => {
    setPendingLinkId(link.id);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links/${link.id}`,
        {
          method: 'PATCH',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ speaker_id: speakerId, confirmed: true }),
        },
      );
      if (res.ok) {
        const updated: SpeakerLink = await res.json();
        const next = links.map(l => (l.id === updated.id ? updated : l));
        setLinks(next);
        if (onChange) onChange(next);
      } else {
        setError(`Failed to update label (HTTP ${res.status}).`);
      }
    } catch (e) {
      setError('Network error updating speaker label.');
    }
    setPendingLinkId(null);
  };

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
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-600">Re-detect with</label>
          <input
            type="number"
            min={1}
            max={24}
            value={redetectCount}
            onChange={(e) => setRedetectCount(Math.max(1, Math.min(24, Number(e.target.value) || 1)))}
            className="w-16 rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <label className="text-xs text-gray-600">speakers</label>
          <button
            onClick={redetectSpeakers}
            disabled={redetecting}
            className="text-xs px-3 py-1 rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
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
          {redetectAuto ? (
            <select
              value={redetectThreshold}
              onChange={(e) => setRedetectThreshold(Number(e.target.value))}
              className="text-xs rounded border border-gray-300 px-1 py-0.5"
              title="Speaker sensitivity"
            >
              <option value={0.78}>Strict</option>
              <option value={0.72}>Balanced</option>
              <option value={0.66}>Loose</option>
            </select>
          ) : (
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
            title={redetectAuto ? "Re-run with auto-detect at this sensitivity" : "Re-run diarization with this speaker count"}
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

      {error && (
        <div className="mb-2 text-xs text-red-600 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          {error}
        </div>
      )}

      <div className="space-y-2">
        {links.map(link => {
          const sim = link.similarity ?? null;
          const simBadge = sim !== null ? `${(sim * 100).toFixed(0)}%` : null;
          return (
            <div key={link.id} className="flex items-center gap-3 text-sm">
              <span className="font-mono text-xs text-gray-500 w-24 truncate" title={link.raw_label}>
                {link.raw_label}
              </span>
              <select
                aria-label={`Speaker for ${link.raw_label}`}
                value={link.speaker_id ?? ''}
                onChange={e => {
                  const v = e.target.value;
                  updateLink(link, v ? Number(v) : null);
                }}
                disabled={pendingLinkId === link.id}
                className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 disabled:opacity-50"
              >
                <option value="">— Unknown —</option>
                {speakers.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.display_name}
                    {!s.has_centroid && ' (no enrollment)'}
                  </option>
                ))}
              </select>
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
                <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700" title="No match found">
                  no match
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
