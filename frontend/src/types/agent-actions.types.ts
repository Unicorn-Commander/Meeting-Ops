export type AgentActionName =
  | 'create_session'
  | 'rename_session'
  | 'add_tag'
  | 'remove_tag'
  | 'trigger_reprocess'
  | 'draft_followup_email';

export interface AgentActionDiffEntry {
  from: unknown;
  to: unknown;
}

export interface AgentActionProposal {
  status: 'needs_confirmation';
  action: AgentActionName;
  preview: string;
  diff: Record<string, AgentActionDiffEntry>;
  confirmation_token: string;
  proposal_id: string;
  expires_at: string;
  payload?: Record<string, unknown>;
  before?: unknown;
  after?: unknown;
}

export interface AgentActionResult {
  status: 'applied' | 'cancelled';
  action: AgentActionName;
  proposal_id: string;
  result?: Record<string, unknown>;
}

export interface AgentActionProposalMessageState {
  proposal: AgentActionProposal;
  state?: 'pending' | 'applied' | 'cancelled';
  result?: AgentActionResult['result'];
}

