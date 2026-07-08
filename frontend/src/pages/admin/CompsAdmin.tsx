import React, { useEffect, useMemo, useState } from 'react';
import {
  Rocket, RefreshCw, Ticket, Gift, CircleCheck, XCircle, Clock,
  Copy, Download, Search, ShieldAlert, UserPlus, Ban, Crown, CreditCard,
  Plus,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { config } from '../../config';
import { useAuth } from '../../contexts/AuthContext';
import { showToast } from '../../components/Toast';
import { showConfirm } from '../../utils/notifications';

// ---------------------------------------------------------------------------
// Types (mirror backend api/admin_comps.py + api/invite_codes.py responses)
// ---------------------------------------------------------------------------
type CompStatus = 'active' | 'expired' | 'permanent' | 'superuser';

interface CompUser {
  id: number;
  email: string;
  username: string;
  full_name?: string | null;
  tier: string;
  status: CompStatus;
  tier_expires_at?: string | null;
  days_remaining?: number | null;
  is_founding_member: boolean;
  founding_cohort?: string | null;
  has_stripe: boolean;
  personal_org_slug?: string | null;
  personal_org_plan?: string | null;
  created_at?: string | null;
}

interface CompsSummary {
  total_nonfree: number;
  active_comps: number;
  expired_pending_revert: number;
  permanent: number;
  superusers: number;
  by_cohort: Record<string, number>;
  codes_total: number;
  codes_redeemed: number;
  codes_available: number;
}

interface InviteCodeAdminItem {
  code: string;
  is_active: boolean;
  redeemed: boolean;
  redeemed_by_email?: string | null;
  redeemed_at?: string | null;
  created_by_email?: string | null;
  note?: string | null;
  cohort?: string | null;
  created_at?: string | null;
}

interface CompSnapshot {
  email: string;
  tier: string;
  tier_expires_at?: string | null;
  personal_org_plan?: string | null;
}
interface CompActionResponse {
  action: string;
  before: CompSnapshot;
  after: CompSnapshot;
}

// ---------------------------------------------------------------------------
// API helpers (JWT + org headers auto-injected by the global fetch interceptor)
// ---------------------------------------------------------------------------
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* body not JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

function relative(iso?: string | null): string {
  if (!iso) return '—';
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

async function copy(text: string, label: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    showToast.success(label);
  } catch {
    showToast.error('Clipboard blocked by the browser.');
  }
}

// ---------------------------------------------------------------------------
// Small presentational bits
// ---------------------------------------------------------------------------
const CARD = 'rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6';

function SummaryCard({ icon, label, value, tone }: {
  icon: React.ReactNode; label: string; value: number | string; tone: string;
}) {
  return (
    <div className={`${CARD} flex items-center gap-3`}>
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${tone}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold leading-tight">{value}</div>
        <div className="truncate text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      </div>
    </div>
  );
}

function CompStatusBadge({ status, days }: { status: CompStatus; days?: number | null }) {
  if (status === 'active') {
    const soon = typeof days === 'number' && days <= 5;
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
        soon ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300'
      }`}>
        <CircleCheck className="h-3.5 w-3.5" />
        {typeof days === 'number' ? `${days}d left` : 'active'}
      </span>
    );
  }
  if (status === 'expired') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-300">
        <Clock className="h-3.5 w-3.5" /> expired
      </span>
    );
  }
  if (status === 'superuser') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-fuchsia-500/15 px-2.5 py-1 text-xs font-medium text-fuchsia-300">
        <Crown className="h-3.5 w-3.5" /> superuser
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2.5 py-1 text-xs font-medium text-sky-300">
      <CreditCard className="h-3.5 w-3.5" /> permanent
    </span>
  );
}

function CodeStatusBadge({ c }: { c: InviteCodeAdminItem }) {
  if (c.redeemed) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-700/50 px-2.5 py-1 text-xs font-medium text-zinc-300">
        <CircleCheck className="h-3.5 w-3.5" /> redeemed
      </span>
    );
  }
  if (!c.is_active) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-300">
        <XCircle className="h-3.5 w-3.5" /> inactive
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">
      <Ticket className="h-3.5 w-3.5" /> available
    </span>
  );
}

const BTN_PRIMARY =
  'inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50';
const BTN_OUTLINE =
  'inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 transition-colors hover:bg-zinc-800 disabled:opacity-50';
const INPUT =
  'rounded-lg border border-zinc-700 bg-zinc-950/70 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function CompsAdmin() {
  const { user } = useAuth();

  const [summary, setSummary] = useState<CompsSummary | null>(null);
  const [comps, setComps] = useState<CompUser[]>([]);
  const [codes, setCodes] = useState<InviteCodeAdminItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [compStatus, setCompStatus] = useState<'' | CompStatus>('');
  const [compQuery, setCompQuery] = useState('');
  const [codeFilter, setCodeFilter] = useState<'all' | 'available' | 'redeemed'>('all');
  const [cohortFilter, setCohortFilter] = useState('');

  // Grant form
  const [grantEmail, setGrantEmail] = useState('');
  const [grantTier, setGrantTier] = useState('pro');
  const [grantDays, setGrantDays] = useState(30);
  const [grantFounding, setGrantFounding] = useState(false);
  const [grantBusy, setGrantBusy] = useState(false);

  // Mint form
  const [mintCount, setMintCount] = useState(25);
  const [mintNote, setMintNote] = useState('');
  const [mintBusy, setMintBusy] = useState(false);

  const isSuper = Boolean(user?.is_superuser);

  const loadAll = async () => {
    setError(null);
    try {
      const [s, c, k] = await Promise.all([
        apiGet<CompsSummary>('/api/admin/comps/summary'),
        apiGet<CompUser[]>('/api/admin/comps'),
        apiGet<InviteCodeAdminItem[]>('/api/admin/invite-codes'),
      ]);
      setSummary(s);
      setComps(c);
      setCodes(k);
    } catch (err) {
      setError(`Failed to load launch data: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isSuper) loadAll();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuper]);

  // Client-side filtering (server returns the full set; these are cheap).
  const filteredComps = useMemo(() => {
    return comps.filter((u) => {
      if (compStatus && u.status !== compStatus) return false;
      if (compQuery) {
        const q = compQuery.trim().toLowerCase();
        if (!u.email.toLowerCase().includes(q) && !u.username.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [comps, compStatus, compQuery]);

  const cohorts = useMemo(() => {
    const set = new Set<string>();
    codes.forEach((c) => c.cohort && set.add(c.cohort));
    return Array.from(set).sort();
  }, [codes]);

  const filteredCodes = useMemo(() => {
    return codes.filter((c) => {
      if (codeFilter === 'available' && (c.redeemed || !c.is_active)) return false;
      if (codeFilter === 'redeemed' && !c.redeemed) return false;
      if (cohortFilter && c.cohort !== cohortFilter) return false;
      return true;
    });
  }, [codes, codeFilter, cohortFilter]);

  const grant = async (revoke: boolean, emailOverride?: string) => {
    const email = (emailOverride ?? grantEmail).trim();
    if (!email) {
      showToast.error('Enter an email.');
      return;
    }
    if (revoke) {
      const ok = await showConfirm(
        `Revoke the comp for ${email}? Their tier drops to free immediately.`,
        { confirmLabel: 'Revoke', tone: 'danger' },
      );
      if (!ok) return;
    }
    setGrantBusy(true);
    try {
      const path = revoke ? '/api/admin/comps/revoke' : '/api/admin/comps/grant';
      const body = revoke
        ? { email }
        : { email, tier: grantTier, days: grantDays, founding: grantFounding, cohort: 'meeting_ops_v1' };
      const res = await apiPost<CompActionResponse>(path, body);
      showToast.success(
        revoke
          ? `Revoked ${res.after.email} → free.`
          : `${res.after.email} → ${res.after.tier} (org ${res.after.personal_org_plan}).`,
      );
      if (!revoke && !emailOverride) setGrantEmail('');
      await loadAll();
    } catch (err) {
      showToast.error(`${revoke ? 'Revoke' : 'Grant'} failed: ${(err as Error).message}`);
    } finally {
      setGrantBusy(false);
    }
  };

  const mint = async () => {
    if (mintCount < 1) return;
    setMintBusy(true);
    try {
      const minted = await apiPost<{ code: string }[]>('/api/admin/invite-codes', {
        count: Math.min(mintCount, 50),
        note: mintNote.trim() || 'cohort=meeting_ops_v1 comp_days=30',
      });
      showToast.success(`Minted ${minted.length} code${minted.length === 1 ? '' : 's'}.`);
      setMintNote('');
      await loadAll();
    } catch (err) {
      showToast.error(`Mint failed: ${(err as Error).message}`);
    } finally {
      setMintBusy(false);
    }
  };

  const copyAvailable = async () => {
    const list = filteredCodes.filter((c) => c.is_active && !c.redeemed).map((c) => c.code);
    if (!list.length) {
      showToast.info('No available codes in the current filter.');
      return;
    }
    await copy(list.join('\n'), `Copied ${list.length} available codes.`);
  };

  const exportCsv = () => {
    const header = ['code', 'status', 'cohort', 'redeemed_by_email', 'redeemed_at', 'created_at', 'note'];
    const esc = (v: unknown) => {
      const s = v == null ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const rows = filteredCodes.map((c) => [
      c.code,
      c.redeemed ? 'redeemed' : c.is_active ? 'available' : 'inactive',
      c.cohort ?? '',
      c.redeemed_by_email ?? '',
      c.redeemed_at ?? '',
      c.created_at ?? '',
      c.note ?? '',
    ].map(esc).join(','));
    const blob = new Blob([[header.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `invite-codes-${cohortFilter || 'all'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // --- Non-superuser: access notice (AdminRoute lets org-admins reach here) ---
  if (!isSuper) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black p-6 text-white">
        <div className="mx-auto max-w-lg">
          <div className={`${CARD} flex items-start gap-3`}>
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div>
              <div className="font-medium">Platform superuser only</div>
              <p className="mt-1 text-sm text-zinc-400">
                The launch console manages comps and invite codes across the whole platform.
                It's restricted to a platform superuser.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black p-6 text-white">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600">
              <Rocket className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold">Launch Console</h1>
              <p className="text-sm text-zinc-500">Comps &amp; invite codes for the launch cohort</p>
            </div>
          </div>
          <button onClick={loadAll} className={BTN_OUTLINE} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Summary cards */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <SummaryCard icon={<CircleCheck className="h-5 w-5 text-emerald-300" />} tone="bg-emerald-500/15"
            label="Active comps" value={summary?.active_comps ?? '—'} />
          <SummaryCard icon={<Clock className="h-5 w-5 text-red-300" />} tone="bg-red-500/15"
            label="Expired" value={summary?.expired_pending_revert ?? '—'} />
          <SummaryCard icon={<CreditCard className="h-5 w-5 text-sky-300" />} tone="bg-sky-500/15"
            label="Permanent / paid" value={summary?.permanent ?? '—'} />
          <SummaryCard icon={<Ticket className="h-5 w-5 text-emerald-300" />} tone="bg-emerald-500/15"
            label="Codes available" value={summary?.codes_available ?? '—'} />
          <SummaryCard icon={<Gift className="h-5 w-5 text-fuchsia-300" />} tone="bg-fuchsia-500/15"
            label="Codes redeemed" value={summary?.codes_redeemed ?? '—'} />
          <SummaryCard icon={<Crown className="h-5 w-5 text-purple-300" />} tone="bg-purple-500/15"
            label="Superusers" value={summary?.superusers ?? '—'} />
        </div>

        {/* Action cards: grant + mint */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* Grant / extend a comp */}
          <div className={CARD}>
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <UserPlus className="h-4 w-4 text-indigo-300" /> Grant / extend a comp
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <input
                className={`${INPUT} min-w-[200px] flex-1`}
                placeholder="user@email.com"
                value={grantEmail}
                onChange={(e) => setGrantEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !grantBusy) grant(false); }}
              />
              <select className={INPUT} value={grantTier} onChange={(e) => setGrantTier(e.target.value)}>
                <option value="pro">pro</option>
                <option value="basic">basic</option>
                <option value="suite">suite</option>
                <option value="enterprise">enterprise</option>
              </select>
              <input
                type="number" min={1} max={3650}
                className={`${INPUT} w-24`}
                value={grantDays}
                onChange={(e) => setGrantDays(Math.max(1, Number(e.target.value) || 1))}
                title="days"
              />
              <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                <input type="checkbox" checked={grantFounding} onChange={(e) => setGrantFounding(e.target.checked)} />
                Founding
              </label>
              <button className={BTN_PRIMARY} disabled={grantBusy} onClick={() => grant(false)}>
                <UserPlus className="h-4 w-4" /> Grant
              </button>
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              Sets user tier + a {grantDays}-day expiry AND the personal org plan. Re-granting extends the window.
              Comps auto-revert to free at expiry unless the user subscribes.
            </p>
          </div>

          {/* Mint invite codes */}
          <div className={CARD}>
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Plus className="h-4 w-4 text-emerald-300" /> Mint invite codes
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <input
                type="number" min={1} max={50}
                className={`${INPUT} w-24`}
                value={mintCount}
                onChange={(e) => setMintCount(Math.min(50, Math.max(1, Number(e.target.value) || 1)))}
                title="count (max 50 per mint)"
              />
              <input
                className={`${INPUT} min-w-[180px] flex-1`}
                placeholder="note (default cohort=meeting_ops_v1 comp_days=30)"
                value={mintNote}
                onChange={(e) => setMintNote(e.target.value)}
              />
              <button className={BTN_PRIMARY} disabled={mintBusy} onClick={mint}>
                <Ticket className="h-4 w-4" /> Mint
              </button>
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              Single-use codes → a 30-day Pro comp on redemption (no card). Max 50 per mint.
            </p>
          </div>
        </div>

        {/* Comped users table */}
        <div className="mb-6">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
              Comped &amp; paid users {summary ? `(${summary.total_nonfree})` : ''}
            </h2>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                <input
                  className={`${INPUT} w-48 pl-8`}
                  placeholder="search email…"
                  value={compQuery}
                  onChange={(e) => setCompQuery(e.target.value)}
                />
              </div>
              <select className={INPUT} value={compStatus} onChange={(e) => setCompStatus(e.target.value as '' | CompStatus)}>
                <option value="">all statuses</option>
                <option value="active">active</option>
                <option value="expired">expired</option>
                <option value="permanent">permanent / paid</option>
                <option value="superuser">superuser</option>
              </select>
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="grid grid-cols-12 gap-3 border-b border-zinc-800 bg-zinc-950/70 px-4 py-3 text-xs uppercase tracking-wide text-zinc-500">
              <div className="col-span-4">User</div>
              <div className="col-span-2">Tier</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Expires</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 px-4 py-6 text-sm text-zinc-400">
                <RefreshCw className="h-4 w-4 animate-spin" /> Loading…
              </div>
            ) : filteredComps.length === 0 ? (
              <div className="px-4 py-8 text-sm text-zinc-500">No matching users.</div>
            ) : (
              filteredComps.map((u) => (
                <div key={u.id} className="grid grid-cols-12 items-center gap-3 border-b border-zinc-800 px-4 py-3 text-sm last:border-b-0">
                  <div className="col-span-4 min-w-0">
                    <div className="truncate font-medium">{u.email}</div>
                    <div className="truncate text-xs text-zinc-500">
                      @{u.username}
                      {u.is_founding_member && <span className="ml-1 text-amber-400">· founding</span>}
                      {u.has_stripe && <span className="ml-1 text-sky-400">· stripe</span>}
                    </div>
                  </div>
                  <div className="col-span-2">
                    <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs">{u.tier}</span>
                    {u.personal_org_plan && u.personal_org_plan !== u.tier && (
                      <span className="ml-1 text-xs text-amber-400" title="org plan differs from tier">
                        org:{u.personal_org_plan}
                      </span>
                    )}
                  </div>
                  <div className="col-span-2">
                    <CompStatusBadge status={u.status} days={u.days_remaining} />
                  </div>
                  <div className="col-span-2 text-xs text-zinc-400">{relative(u.tier_expires_at)}</div>
                  <div className="col-span-2 flex justify-end gap-1">
                    {u.status !== 'superuser' && (
                      <button
                        className="inline-flex items-center gap-1 rounded border border-red-900/70 px-2 py-1 text-xs text-red-300 hover:bg-red-950/50 disabled:opacity-50"
                        disabled={grantBusy}
                        onClick={() => grant(true, u.email)}
                        title="Revoke comp → free"
                      >
                        <Ban className="h-3.5 w-3.5" /> Revoke
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Invite codes table */}
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
              Invite codes {summary ? `(${summary.codes_available} available / ${summary.codes_total})` : ''}
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              <select className={INPUT} value={cohortFilter} onChange={(e) => setCohortFilter(e.target.value)}>
                <option value="">all cohorts</option>
                {cohorts.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select className={INPUT} value={codeFilter} onChange={(e) => setCodeFilter(e.target.value as 'all' | 'available' | 'redeemed')}>
                <option value="all">all</option>
                <option value="available">available</option>
                <option value="redeemed">redeemed</option>
              </select>
              <button className={BTN_OUTLINE} onClick={copyAvailable} title="Copy available codes">
                <Copy className="h-4 w-4" /> Copy available
              </button>
              <button className={BTN_OUTLINE} onClick={exportCsv} title="Export filtered as CSV">
                <Download className="h-4 w-4" /> CSV
              </button>
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="grid grid-cols-12 gap-3 border-b border-zinc-800 bg-zinc-950/70 px-4 py-3 text-xs uppercase tracking-wide text-zinc-500">
              <div className="col-span-3">Code</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Cohort</div>
              <div className="col-span-3">Redeemed by</div>
              <div className="col-span-2 text-right">Copy</div>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 px-4 py-6 text-sm text-zinc-400">
                <RefreshCw className="h-4 w-4 animate-spin" /> Loading…
              </div>
            ) : filteredCodes.length === 0 ? (
              <div className="px-4 py-8 text-sm text-zinc-500">No codes match the filter.</div>
            ) : (
              filteredCodes.slice(0, 500).map((c) => (
                <div key={c.code} className="grid grid-cols-12 items-center gap-3 border-b border-zinc-800 px-4 py-3 text-sm last:border-b-0">
                  <div className="col-span-3 font-mono text-sm">{c.code}</div>
                  <div className="col-span-2"><CodeStatusBadge c={c} /></div>
                  <div className="col-span-2 truncate text-xs text-zinc-400">{c.cohort ?? '—'}</div>
                  <div className="col-span-3 min-w-0">
                    {c.redeemed_by_email ? (
                      <div className="truncate">
                        <span className="truncate">{c.redeemed_by_email}</span>
                        <span className="ml-1 text-xs text-zinc-500">{relative(c.redeemed_at)}</span>
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-600">—</span>
                    )}
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <button
                      className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                      onClick={() => copy(c.code, `Copied ${c.code}.`)}
                      title="Copy code"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
          {filteredCodes.length > 500 && (
            <p className="mt-2 text-xs text-zinc-500">
              Showing first 500 of {filteredCodes.length}. Narrow with a cohort/status filter or export CSV.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
