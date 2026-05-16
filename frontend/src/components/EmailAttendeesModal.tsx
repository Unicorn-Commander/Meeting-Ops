import React, { useEffect, useMemo, useState } from 'react';
import { X, Mail, RefreshCw, Send, AlertCircle, Check } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

interface SpeakerLink {
  id: number;
  raw_label: string;
  speaker_id: number | null;
  speaker?: {
    id: number;
    display_name: string;
    email?: string | null;
  } | null;
}

interface Props {
  sessionId: string | number;
  isOpen: boolean;
  onClose: () => void;
}

interface SendResult {
  sent: number;
  skipped: number;
  failures: Array<{ speaker_id: number; name?: string; email?: string; reason: string }>;
}

export const EmailAttendeesModal: React.FC<Props> = ({ sessionId, isOpen, onClose }) => {
  const { activeOrganization } = useOrg();
  const [links, setLinks] = useState<SpeakerLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SendResult | null>(null);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [includeLink, setIncludeLink] = useState(true);
  const [includeSummary, setIncludeSummary] = useState(false);
  const [includeTranscript, setIncludeTranscript] = useState(false);
  const [customMessage, setCustomMessage] = useState('');

  const orgHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
    return headers;
  };

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `${config.apiBaseUrl}/api/sessions/${sessionId}/speaker-links`,
          { headers: orgHeaders() },
        );
        if (cancelled) return;
        if (res.ok) {
          const data = await res.json();
          // We want full speaker info (incl. email) — speaker-links endpoint
          // returns the nested speaker object when speaker_id is set.
          setLinks(Array.isArray(data) ? data : []);
          // Default-select every speaker who has an email on file.
          const auto = new Set<number>();
          for (const l of Array.isArray(data) ? data : []) {
            if (l.speaker_id && l.speaker?.email) auto.add(l.speaker_id as number);
          }
          setSelected(auto);
        } else {
          setError(`Couldn't load attendee list (HTTP ${res.status}).`);
        }
      } catch (e) {
        setError('Network error loading speakers.');
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, sessionId, activeOrganization?.slug]);

  const namedSpeakers = useMemo(
    () =>
      links
        .filter((l) => l.speaker_id && l.speaker)
        .map((l) => ({
          link_id: l.id,
          speaker_id: l.speaker_id!,
          name: l.speaker?.display_name || l.raw_label,
          email: l.speaker?.email || '',
        })),
    [links],
  );

  const unmappedLinks = links.filter((l) => !l.speaker_id);

  const toggle = (id: number) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSend = async () => {
    if (selected.size === 0) {
      setError('Pick at least one attendee.');
      return;
    }
    const include: string[] = [];
    if (includeLink) include.push('link');
    if (includeSummary) include.push('summary_pdf');
    if (includeTranscript) include.push('transcript_pdf');
    if (include.length === 0) {
      setError('Pick at least one thing to include (link or attachments).');
      return;
    }
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}/email-attendees`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            speaker_ids: Array.from(selected),
            include,
            message: customMessage.trim() || undefined,
          }),
        },
      );
      const data = await res.json();
      if (res.ok) {
        setResult(data as SendResult);
      } else {
        setError(`Send failed (HTTP ${res.status}): ${(data?.detail || JSON.stringify(data)).toString().slice(0, 200)}`);
      }
    } catch (e) {
      setError('Network error during send.');
    }
    setSending(false);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <div className="w-full max-w-2xl rounded-lg border border-gray-700 bg-gray-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Email this meeting</h2>
            <p className="mt-0.5 text-xs text-gray-400">
              Pick attendees and what to send. Magic-link recipients can view the meeting without an account.
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 space-y-5">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading attendee list…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded border border-red-700 bg-red-900/30 px-3 py-2 text-xs text-red-300">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="space-y-2 rounded border border-emerald-700 bg-emerald-900/20 px-3 py-2 text-sm text-emerald-200">
              <div className="flex items-center gap-2">
                <Check className="h-4 w-4" />
                Sent {result.sent} email{result.sent === 1 ? '' : 's'}. Skipped {result.skipped}.
              </div>
              {result.failures.length > 0 && (
                <ul className="ml-5 list-disc text-xs text-amber-300">
                  {result.failures.map((f, idx) => (
                    <li key={idx}>
                      <span className="font-medium">{f.name || f.email || `speaker ${f.speaker_id}`}</span>: {f.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {!loading && !result && (
            <>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  Attendees
                </p>
                <div className="space-y-1.5">
                  {namedSpeakers.length === 0 && (
                    <p className="text-xs text-gray-500">
                      No named attendees on this meeting yet. Click a speaker label in the
                      transcript to rename + enroll them first, then return here.
                    </p>
                  )}
                  {namedSpeakers.map((s) => {
                    const checked = selected.has(s.speaker_id);
                    const missing = !s.email;
                    return (
                      <label
                        key={s.speaker_id}
                        className="flex items-center gap-3 rounded-md border border-gray-800 bg-gray-900 px-3 py-2 text-sm cursor-pointer hover:border-gray-700"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={missing}
                          onChange={() => toggle(s.speaker_id)}
                          className="h-3.5 w-3.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-white truncate">{s.name}</div>
                          {missing ? (
                            <div className="text-[11px] text-amber-300">
                              No email on file — click the speaker in the transcript to add one.
                            </div>
                          ) : (
                            <div className="text-[11px] text-gray-500 truncate">{s.email}</div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                  {unmappedLinks.length > 0 && (
                    <p className="text-[11px] text-gray-500 pt-1">
                      {unmappedLinks.length} unnamed cluster{unmappedLinks.length === 1 ? '' : 's'} ({unmappedLinks.map((l) => l.raw_label).join(', ')}) — give them a name in the transcript first.
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">Include</p>
                <div className="space-y-1.5">
                  <label className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeLink}
                      onChange={(e) => setIncludeLink(e.target.checked)}
                      className="h-3.5 w-3.5"
                    />
                    Magic link to view the meeting
                  </label>
                  <label className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeSummary}
                      onChange={(e) => setIncludeSummary(e.target.checked)}
                      className="h-3.5 w-3.5"
                    />
                    Summary (PDF attachment)
                  </label>
                  <label className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeTranscript}
                      onChange={(e) => setIncludeTranscript(e.target.checked)}
                      className="h-3.5 w-3.5"
                    />
                    Full transcript (PDF attachment)
                  </label>
                </div>
              </div>

              <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  Note (optional)
                </p>
                <textarea
                  rows={3}
                  value={customMessage}
                  onChange={(e) => setCustomMessage(e.target.value)}
                  placeholder="Add a short message that appears at the top of the email…"
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
                <p className="mt-1 text-[11px] text-gray-500">
                  Replies go straight to you, not to a shared inbox.
                </p>
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-gray-800 px-5 py-3">
          <span className="text-xs text-gray-500">
            {result
              ? 'Send another batch by closing and reopening this dialog.'
              : `${selected.size} attendee${selected.size === 1 ? '' : 's'} selected`}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"
            >
              {result ? 'Done' : 'Cancel'}
            </button>
            {!result && (
              <button
                onClick={handleSend}
                disabled={sending || selected.size === 0}
                className="inline-flex items-center gap-2 rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
              >
                {sending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmailAttendeesModal;
