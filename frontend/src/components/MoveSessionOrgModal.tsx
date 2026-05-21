/**
 * MoveSessionOrgModal — pick a target organization to move the current
 * session to.
 *
 * Backend: POST /api/simple/recording-sessions/{id}/move-org
 *   { target_organization_id: number }
 *
 * Visible target orgs are the union of the user's memberships minus
 * the active org (active org would be a no-op the backend 400s).
 * Superusers see all orgs in their session — but we don't have a
 * /api/organizations browser today, so this UI only ever offers
 * memberships the user already has. That matches the typical
 * "I recorded under the wrong personal/work org" use case.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { X, AlertTriangle, Loader2, ArrowRightLeft } from 'lucide-react';
import { config } from '../config';
import { useOrg } from '../contexts/OrgContext';
import type { OrganizationMembership } from '../utils/organization';

interface MoveSessionOrgModalProps {
  open: boolean;
  sessionPublicId: string;
  sessionName: string;
  onClose: () => void;
  onMoved: (response: MoveResponse) => void;
}

interface OrphanedSpeakerLink {
  link_id: number;
  raw_label: string;
  speaker_id: number | null;
  speaker_display: string | null;
}

interface MoveResponse {
  session_id: number;
  source_organization_id: number;
  target_organization_id: number;
  moved_counts: Record<string, number>;
  orphaned_speaker_links: OrphanedSpeakerLink[];
  qdrant_repointed: boolean;
  qdrant_error: string | null;
}

export const MoveSessionOrgModal: React.FC<MoveSessionOrgModalProps> = ({
  open,
  sessionPublicId,
  sessionName,
  onClose,
  onMoved,
}) => {
  const { organizations, activeOrganization, switchOrganization } = useOrg();
  const [target, setTarget] = useState<OrganizationMembership | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Other orgs the user is a member of. Reset whenever the modal opens
  // so we don't carry stale state.
  const candidates = useMemo<OrganizationMembership[]>(
    () =>
      (organizations || []).filter(
        (org) =>
          org.is_active && (!activeOrganization || org.id !== activeOrganization.id),
      ),
    [organizations, activeOrganization],
  );

  useEffect(() => {
    if (open) {
      setTarget(candidates[0] || null);
      setError(null);
    }
  }, [open, candidates]);

  const submit = async () => {
    if (!target) {
      setError('Pick a target organization');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${config.apiUrl}/api/simple/recording-sessions/${sessionPublicId}/move-org`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_organization_id: target.id }),
        },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      // Switch the UI's active org to the new home so the session is
      // visible again on the next /sessions render.
      switchOrganization(target.slug);
      onMoved(body as MoveResponse);
    } catch (e: any) {
      setError(e?.message || 'Move failed');
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-start justify-between gap-2 border-b border-gray-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <ArrowRightLeft className="w-5 h-5 text-blue-600" />
            <h3 className="text-lg font-semibold text-gray-900">
              Move session to another org
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-gray-700">
            Move{' '}
            <span className="font-medium">{sessionName || 'this session'}</span>{' '}
            from{' '}
            <span className="font-medium">
              {activeOrganization?.name || 'current org'}
            </span>{' '}
            into a different organization. The full session moves — audio,
            transcripts, attachments, chat history, action items, and search
            index. Magic-link shares and participants stay attached.
          </p>

          {candidates.length === 0 ? (
            <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                You aren't a member of any other organization. Ask your admin
                to add you to the target org first.
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Target organization
              </label>
              <select
                value={target?.id ?? ''}
                onChange={(e) => {
                  const id = Number(e.target.value);
                  setTarget(candidates.find((o) => o.id === id) || null);
                }}
                disabled={busy}
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
              >
                {candidates.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name} ({org.role})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
            Heads up: speakers tagged from{' '}
            {activeOrganization?.name || 'this org'}'s speaker library may need
            to be re-linked in{' '}
            <span className="font-medium">{target?.name || 'the target org'}</span>{' '}
            after the move. We'll flag any that need attention.
          </div>

          {error && (
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>{error}</div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-gray-200 px-5 py-3">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || candidates.length === 0 || !target}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Move session
          </button>
        </div>
      </div>
    </div>
  );
};

export default MoveSessionOrgModal;
