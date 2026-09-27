import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { FileText, RefreshCw } from 'lucide-react';
import { useOrg } from '../contexts/OrgContext';
import { config } from '../config';
import { pollJob, JobPollError } from '../services/jobPoller';
import DigestEmailPreferences from '../components/settings/DigestEmailPreferences';

interface DigestData {
  id?: number;
  period: string;
  date: string;
  content: string;
  meeting_count: number;
  generated_at?: string;
  emailed_to_you?: boolean;
  delivery_status?: string;
  title?: string;
  week_range?: string;
  source_meetings?: { id: string; title: string }[];
  sources_recorded?: boolean;
}
type HistoryItem = Omit<DigestData, 'content'>;
const PERIODS = [
  { value: 'day', label: 'Day' }, { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' }, { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];
const buttonStyle = 'min-h-11 rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-100 disabled:opacity-40';
const timestamp = (value?: string) => value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString() : 'Unavailable';

export default function DigestsPage() {
  const { activeOrganization } = useOrg();
  return <DigestWorkspace key={activeOrganization?.slug || ''} slug={activeOrganization?.slug} />;
}

function DigestWorkspace({ slug }: { slug?: string }) {
  const [tab, setTab] = useState('day');
  const [period, setPeriod] = useState('day');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [digest, setDigest] = useState<DigestData | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [pageCursor, setPageCursor] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [progressMsg, setProgressMsg] = useState('');
  const request = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current += 1; activeRequest.current?.abort(); }, []);

  useEffect(() => {
    if (!slug) return;
    const controller = new AbortController();
    setHistoryLoading(true);
    setHistoryError('');
    const params = new URLSearchParams({ period: tab });
    if (pageCursor) params.set('cursor', pageCursor);
    fetch(`${config.apiBaseUrl}/api/digests/history?${params}`, {
      headers: { 'X-MeetingOps-Org': slug }, signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw new Error('Could not load digest history. Please retry.');
      const data: { items: HistoryItem[]; next_cursor: string | null } = await response.json();
      if (controller.signal.aborted) return;
      setHistory(previous => pageCursor ? [...previous, ...data.items] : data.items);
      setCursor(data.next_cursor);
    }).catch((err: Error) => {
      if (!controller.signal.aborted) setHistoryError(err.message);
    }).finally(() => {
      if (!controller.signal.aborted) setHistoryLoading(false);
    });
    return () => controller.abort();
  }, [slug, tab, pageCursor, revision]);

  const getHeaders = (): Record<string, string> => slug ? { 'X-MeetingOps-Org': slug } : {};

  async function openDigest(id: number) {
    const serial = ++request.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setDigest(null);
    setError('');
    setProgressMsg('Loading digest…');
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/digests/history/${id}`, { headers: getHeaders(), signal: controller.signal });
      if (!response.ok) throw new Error('Could not load this digest. Please select it again.');
      const data: DigestData = await response.json();
      if (request.current === serial) setDigest(data);
    } catch (err) {
      if (request.current === serial) setError(err instanceof Error ? err.message : 'Could not load digest.');
    } finally {
      if (request.current === serial) { setLoading(false); setProgressMsg(''); }
    }
  }

  async function fetchDigest(force = false) {
    const serial = ++request.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setDigest(null);
    setError('');
    setProgressMsg('Generating digest…');
    try {
      const params = new URLSearchParams({ period, date });
      if (force) params.set('force', 'true');
      const response = await fetch(`${config.apiBaseUrl}/api/digests?${params}`, { headers: getHeaders(), signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 403
        ? 'Generating digests requires a paid account and workspace. You can still read stored digests.'
        : 'Failed to generate digest.');
      let result: DigestData;
      if (response.status === 202) {
        const payload = await response.json();
        result = await pollJob<DigestData>(payload.job_id, {
          headers: getHeaders(), signal: controller.signal,
          onProgress: state => {
            if (request.current === serial) setProgressMsg(state.status === 'running' ? 'Summarizing meetings…' : 'Waiting in queue…');
          },
        });
      } else result = await response.json();
      if (request.current !== serial) return;
      setDigest(result);
      setPageCursor(null);
      setRevision(value => value + 1);
      if (result.id) await openDigest(result.id);
    } catch (err) {
      if (request.current === serial) setError(err instanceof JobPollError ? err.originalError || 'Digest generation failed.' : err instanceof Error ? err.message : 'Network error.');
    } finally {
      if (request.current === serial) { setLoading(false); setProgressMsg(''); }
    }
  }

  function changeTab(value: string) {
    if (value === tab) return;
    request.current += 1;
    activeRequest.current?.abort();
    setTab(value); setPeriod(value); setPageCursor(null); setCursor(null);
    setHistory([]); setDigest(null); setError(''); setLoading(false); setHistoryLoading(true);
  }

  return (
    <div className="h-full overflow-y-auto bg-zinc-950 p-4 sm:p-6 text-zinc-100 space-y-5">
      <h1 className="flex items-center gap-3 text-lg font-semibold"><FileText className="h-5 w-5 text-fuchsia-400" />Meeting Digests</h1>
      <p className="text-sm text-zinc-400">Daily and weekly summaries are saved here for eligible workspaces with completed meetings. Scheduled windows use UTC.</p>
      <DigestEmailPreferences />
      <section aria-label="Generate a digest" className="flex flex-wrap items-end gap-3">
        <label className="text-sm">Period<select aria-label="Period" value={period} onChange={event => setPeriod(event.target.value)} className={`${buttonStyle} block mt-1`}>
          {PERIODS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select></label>
        <label className="text-sm">Date<input aria-label="Date" type="date" value={date} onChange={event => setDate(event.target.value)} className={`${buttonStyle} block mt-1`} /></label>
        <button onClick={() => fetchDigest()} disabled={loading || !slug || !date} className={`${buttonStyle} bg-fuchsia-700`}>Generate now</button>
        <button onClick={() => fetchDigest(true)} disabled={loading || !slug || !date} title="Force regeneration" aria-label="Refresh selected window" className={buttonStyle}><RefreshCw className="h-4 w-4" /></button>
      </section>
      <div role="tablist" aria-label="Digest history" className="flex gap-2">
        {(['day', 'week'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} aria-controls="digest-history" id={`tab-${value}`} onClick={() => changeTab(value)} className={`${buttonStyle} ${tab === value ? 'bg-fuchsia-700' : ''}`}>{value === 'day' ? 'Daily' : 'Weekly'}</button>)}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section id="digest-history" role="tabpanel" aria-labelledby={`tab-${tab}`} className="space-y-3 min-w-0">
          {historyError && <p role="alert" className="text-red-300">{historyError} <button className="underline" onClick={() => setRevision(value => value + 1)}>Retry history</button></p>}
          {history.map(item => <button key={item.id} onClick={() => item.id && openDigest(item.id)} className="block w-full text-left border border-zinc-700 rounded-lg p-4 hover:bg-zinc-900 space-y-1" aria-pressed={digest?.id === item.id}>
            <span className="block font-medium">{item.title || `${item.date} · ${item.meeting_count} meeting${item.meeting_count !== 1 ? 's' : ''}`}</span>
            <span className="block text-sm text-zinc-400">Generated {timestamp(item.generated_at)}</span>
            <span className="block text-sm text-zinc-400">{item.emailed_to_you ? 'Emailed to you' : 'in-app only'}</span>
          </button>)}
          {historyLoading && <p role="status">Loading digest history…</p>}
          {!historyLoading && !historyError && history.length === 0 && <p className="rounded-lg border border-dashed border-zinc-700 p-6 text-zinc-400">No {tab === 'day' ? 'daily' : 'weekly'} digests yet. Completed meetings in eligible workspaces appear after the next scheduled run, or choose Generate now.</p>}
          {cursor && !historyLoading && !historyError && <button className={buttonStyle} onClick={() => setPageCursor(cursor)}>Load more</button>}
        </section>
        <section aria-label="Digest detail" className="min-w-0">
          {loading && <p role="status">{progressMsg}</p>}
          {error && <p role="alert" className="text-red-300">{error}</p>}
          {digest && !loading && <article className="rounded-lg border border-zinc-700 bg-zinc-900 p-4 space-y-4">
            <h2 className="font-semibold">{digest.title || `${digest.period} digest · ${digest.date}`}</h2>
            <p className="text-sm text-zinc-400">{digest.meeting_count} meetings · Generated {timestamp(digest.generated_at)}</p>
            {digest.delivery_status && <p className="text-sm text-zinc-400">{digest.delivery_status}</p>}
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{digest.content}</p>
            <h3 className="font-medium">Source meetings</h3>
            {digest.source_meetings?.length ? <ul className="space-y-2">{digest.source_meetings.map(meeting => <li key={meeting.id}><Link className="text-fuchsia-300 underline break-words" to={`/sessions/${encodeURIComponent(meeting.id)}`}>{meeting.title}</Link></li>)}</ul>
              : <p className="text-sm text-zinc-400">{digest.sources_recorded ? 'Source meetings are no longer available in this workspace.' : 'Source links were not recorded for this digest.'}</p>}
          </article>}
          {!digest && !loading && !error && <p className="text-zinc-400">Select a digest to read it and open its source meetings.</p>}
        </section>
      </div>
    </div>
  );
}
