import React, { useEffect, useState } from 'react';
import { X, UserPlus, Copy, Trash2, RefreshCw, Mail, Users, ExternalLink, AlertCircle } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';

type AccessLevel = 'read' | 'comment' | 'edit';

interface CollaboratorUser {
  id: number;
  email: string;
  username?: string | null;
  full_name?: string | null;
}

interface Collaborator {
  id: number;
  user?: CollaboratorUser | null;
  email?: string | null;
  access_level: AccessLevel;
  invited_by_user_id?: number | null;
  token: string;
  expires_at?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  accepted: boolean;
  invite_url?: string | null;
}

interface PermissionsResponse {
  session_id: string;
  org_default: boolean;
  project_default: boolean;
  collaborators: Collaborator[];
}

interface Props {
  sessionId: string | number;
  isOpen: boolean;
  onClose: () => void;
}

const ACCESS_LEVELS: { id: AccessLevel; label: string; hint: string }[] = [
  { id: 'read', label: 'Can view', hint: 'See the transcript, summary, and audio.' },
  { id: 'comment', label: 'Can comment', hint: 'View plus add chat / comments.' },
  { id: 'edit', label: 'Can edit', hint: 'View plus rename speakers and tweak.' },
];

export const SessionPermissionsModal: React.FC<Props> = ({ sessionId, isOpen, onClose }) => {
  const { activeOrganization } = useOrg();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [permissions, setPermissions] = useState<PermissionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftEmail, setDraftEmail] = useState('');
  const [draftLevel, setDraftLevel] = useState<AccessLevel>('read');
  const [copiedTokenId, setCopiedTokenId] = useState<number | null>(null);

  const orgHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (activeOrganization?.slug) headers['X-MeetingOps-Org'] = activeOrganization.slug;
    return headers;
  };

  const loadPermissions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}/permissions`,
        { headers: orgHeaders() },
      );
      if (!res.ok) {
        const txt = await res.text();
        setError(`Failed to load permissions (HTTP ${res.status}): ${txt.slice(0, 160)}`);
        return;
      }
      const data: PermissionsResponse = await res.json();
      setPermissions(data);
    } catch (e) {
      setError('Network error loading permissions.');
    }
    setLoading(false);
  };

  useEffect(() => {
    if (isOpen) loadPermissions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, sessionId, activeOrganization?.slug]);

  const inviteByEmail = async () => {
    const email = draftEmail.trim();
    if (!email) {
      setError('Enter an email to invite.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}/permissions/collaborators`,
        {
          method: 'POST',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, access_level: draftLevel }),
        },
      );
      if (res.ok) {
        setDraftEmail('');
        await loadPermissions();
      } else {
        const txt = await res.text();
        setError(`Invite failed (HTTP ${res.status}): ${txt.slice(0, 160)}`);
      }
    } catch (e) {
      setError('Network error sending invite.');
    }
    setSaving(false);
  };

  const updateAccess = async (collaboratorId: number, level: AccessLevel) => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}/permissions/collaborators/${collaboratorId}`,
        {
          method: 'PATCH',
          headers: { ...orgHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ access_level: level }),
        },
      );
      if (res.ok) {
        await loadPermissions();
      } else {
        const txt = await res.text();
        setError(`Update failed (HTTP ${res.status}): ${txt.slice(0, 160)}`);
      }
    } catch (e) {
      setError('Network error updating access.');
    }
    setSaving(false);
  };

  const revokeCollaborator = async (collaboratorId: number) => {
    if (!confirm('Revoke this person’s access to the meeting?')) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiBaseUrl}/api/simple/recording-sessions/${sessionId}/permissions/collaborators/${collaboratorId}`,
        { method: 'DELETE', headers: orgHeaders() },
      );
      if (res.ok || res.status === 204) {
        await loadPermissions();
      } else {
        const txt = await res.text();
        setError(`Revoke failed (HTTP ${res.status}): ${txt.slice(0, 160)}`);
      }
    } catch (e) {
      setError('Network error revoking access.');
    }
    setSaving(false);
  };

  const copyInviteLink = (c: Collaborator) => {
    // Backend may hand back a relative path when MEETING_OPS_PUBLIC_URL is unset;
    // resolve against current origin so the copied link is always usable.
    const raw = c.invite_url || `/shared/sessions?token=${c.token}`;
    const url = raw.startsWith('http') ? raw : `${window.location.origin}${raw}`;
    navigator.clipboard.writeText(url);
    setCopiedTokenId(c.id);
    setTimeout(() => setCopiedTokenId(null), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <div className="w-full max-w-2xl rounded-lg border border-gray-700 bg-gray-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Share this meeting</h2>
            <p className="mt-0.5 text-xs text-gray-400">
              Internal teammates or external folks. Magic-link invites work for emails outside your org.
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
              Loading permissions…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded border border-red-700 bg-red-900/30 px-3 py-2 text-xs text-red-300">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {permissions && (
            <>
              {/* Defaults summary */}
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Default access</p>
                <div className="space-y-1.5">
                  {permissions.org_default && (
                    <div className="flex items-center gap-2 text-sm text-gray-200">
                      <Users className="h-4 w-4 text-cyan-400" />
                      Everyone in your org can view this meeting.
                    </div>
                  )}
                  {permissions.project_default && (
                    <div className="flex items-center gap-2 text-sm text-gray-200">
                      <Users className="h-4 w-4 text-emerald-400" />
                      Members of the linked project can view this meeting.
                    </div>
                  )}
                  {!permissions.org_default && !permissions.project_default && (
                    <p className="text-sm text-gray-500">
                      Only the people listed below can see this meeting.
                    </p>
                  )}
                </div>
              </div>

              {/* Add a collaborator */}
              <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-2">Invite by email</p>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative flex-1 min-w-[200px]">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <input
                      type="email"
                      value={draftEmail}
                      onChange={(e) => setDraftEmail(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !saving) inviteByEmail(); }}
                      placeholder="someone@example.com"
                      disabled={saving}
                      className="w-full pl-9 pr-3 py-2 rounded border border-gray-700 bg-gray-950 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                  <select
                    value={draftLevel}
                    onChange={(e) => setDraftLevel(e.target.value as AccessLevel)}
                    disabled={saving}
                    className="rounded border border-gray-700 bg-gray-950 px-2 py-2 text-sm text-white"
                  >
                    {ACCESS_LEVELS.map((l) => (
                      <option key={l.id} value={l.id}>{l.label}</option>
                    ))}
                  </select>
                  <button
                    onClick={inviteByEmail}
                    disabled={saving || !draftEmail.trim()}
                    className="rounded bg-cyan-600 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-500 disabled:opacity-50 flex items-center gap-2"
                  >
                    {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
                    Invite
                  </button>
                </div>
                <p className="mt-2 text-xs text-gray-500">
                  If they already have a unicorncommander.ai account they'll see the meeting on next sign-in.
                  Otherwise they get an email with a magic link.
                </p>
              </div>

              {/* Collaborator list */}
              {permissions.collaborators.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-400">People with access</p>
                  <div className="space-y-2">
                    {permissions.collaborators.map((c) => {
                      const displayName =
                        c.user?.full_name ||
                        c.user?.username ||
                        c.user?.email ||
                        c.email ||
                        '(unknown)';
                      const isPending = !c.accepted && !c.user;
                      return (
                        <div
                          key={c.id}
                          className="flex flex-wrap items-center gap-3 rounded-md border border-gray-800 bg-gray-900 px-3 py-2 text-sm"
                        >
                          <div className="flex-1 min-w-[180px]">
                            <div className="font-medium text-white truncate">{displayName}</div>
                            {c.user?.email && c.user.email !== displayName && (
                              <div className="text-xs text-gray-500 truncate">{c.user.email}</div>
                            )}
                            {isPending && (
                              <div className="mt-0.5 inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
                                pending acceptance
                              </div>
                            )}
                          </div>
                          <select
                            value={c.access_level}
                            onChange={(e) => updateAccess(c.id, e.target.value as AccessLevel)}
                            disabled={saving}
                            className="rounded border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-white"
                          >
                            {ACCESS_LEVELS.map((l) => (
                              <option key={l.id} value={l.id}>{l.label}</option>
                            ))}
                          </select>
                          {isPending && (
                            <button
                              onClick={() => copyInviteLink(c)}
                              className="flex items-center gap-1 rounded border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
                              title="Copy magic link"
                            >
                              {copiedTokenId === c.id ? (
                                <>Copied!</>
                              ) : (
                                <>
                                  <Copy className="h-3 w-3" />
                                  Copy link
                                </>
                              )}
                            </button>
                          )}
                          <button
                            onClick={() => revokeCollaborator(c.id)}
                            disabled={saving}
                            className="flex items-center gap-1 rounded border border-red-800/50 px-2 py-1 text-xs text-red-300 hover:bg-red-900/30 disabled:opacity-50"
                            title="Revoke access"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {permissions.collaborators.length === 0 && (
                <p className="text-xs text-gray-500">
                  No one has been explicitly invited yet. Org defaults still apply (see above).
                </p>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-gray-800 px-5 py-3">
          <a
            href="https://meetingops.magicunicorn.dev/settings/members"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
          >
            <ExternalLink className="h-3 w-3" />
            Manage org-level membership
          </a>
          <button
            onClick={onClose}
            className="rounded-md bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default SessionPermissionsModal;
