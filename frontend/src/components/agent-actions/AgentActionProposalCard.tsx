import React from 'react';
import { Check, Clock3, Loader2, X } from 'lucide-react';

import AgentActionDiff from './AgentActionDiff';
import type { AgentActionProposalMessageState } from '../../types/agent-actions.types';

interface Props {
  state: AgentActionProposalMessageState;
  busy?: boolean;
  onConfirm: (token: string) => void | Promise<void>;
  onCancel: (token: string) => void | Promise<void>;
}

export default function AgentActionProposalCard({ state, busy = false, onConfirm, onCancel }: Props) {
  const proposal = state.proposal;
  const proposalState = state.state || 'pending';
  const isPending = proposalState === 'pending';
  const statusLabel =
    proposalState === 'applied'
      ? 'Applied'
      : proposalState === 'cancelled'
        ? 'Cancelled'
        : 'Awaiting confirmation';

  return (
    <div className="mt-3 rounded-xl border border-fuchsia-500/30 bg-zinc-950/80 p-4 shadow-lg shadow-fuchsia-950/20">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-full bg-fuchsia-500/15 text-fuchsia-300">
          <Clock3 className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-medium text-zinc-100">Action proposal</div>
            <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-[11px] uppercase tracking-wide text-zinc-300">
              {proposal.action}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] uppercase tracking-wide ${
                proposalState === 'applied'
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : proposalState === 'cancelled'
                    ? 'bg-zinc-800 text-zinc-400'
                    : 'bg-amber-500/15 text-amber-300'
              }`}
            >
              {statusLabel}
            </span>
          </div>
          <p className="mt-1 text-sm text-zinc-300">{proposal.preview}</p>
          <p className="mt-1 text-[11px] text-zinc-500">
            Expires at {new Date(proposal.expires_at).toLocaleString()}
          </p>
        </div>
      </div>

      <AgentActionDiff diff={proposal.diff} />

      {proposalState === 'applied' && state.result && (
        <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-100">
          Applied successfully.
          <div className="mt-1 text-xs text-emerald-200/80">
            {JSON.stringify(state.result)}
          </div>
        </div>
      )}

      {proposalState === 'cancelled' && (
        <div className="mt-3 rounded-lg border border-zinc-700 bg-zinc-900 p-3 text-sm text-zinc-300">
          Proposal cancelled.
        </div>
      )}

      {isPending && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onConfirm(proposal.confirmation_token)}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Confirm
          </button>
          <button
            type="button"
            onClick={() => onCancel(proposal.confirmation_token)}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-4 w-4" />
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

