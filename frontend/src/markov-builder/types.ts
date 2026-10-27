export type ProposalOrigin =
  | 'user_explicit'
  | 'model_proposal'
  | 'structural'
  | 'manual_edit';

export interface ProposalAudit {
  provider: string;
  model: string;
  prompt_version: string;
  generated_at: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number | null;
  message: string;
}

export interface ChainNodeDraft {
  id: string;
  label: string;
  terminal: boolean;
  origin: ProposalOrigin;
  source_excerpt: string | null;
}

export interface ChainTransitionDraft {
  id: string;
  from_node: string;
  to_node: string;
  probability: number | null;
  condition: string | null;
  origin: ProposalOrigin;
  source_excerpt: string | null;
}

export interface ChainDraft {
  schema_version: '1';
  id: string;
  name: string;
  source_text: string;
  entry_node: string | null;
  nodes: ChainNodeDraft[];
  transitions: ChainTransitionDraft[];
  revision: number;
  proposal_audit: ProposalAudit | null;
}

export interface ChainValidationIssue {
  code: string;
  severity: 'error' | 'warning';
  path: string;
  message: string;
}

export interface OutgoingProbabilityTotal {
  node_id: string;
  known_total: number;
  unknown_count: number;
  complete: boolean;
  sums_to_one: boolean;
}

export interface ChainValidationResult {
  valid: boolean;
  can_confirm: boolean;
  issues: ChainValidationIssue[];
  outgoing_totals: OutgoingProbabilityTotal[];
  terminal_states: string[];
  dead_ends: string[];
  non_terminating_loops: string[][];
  missing_conditions: string[];
  missing_probabilities: string[];
  unreachable_nodes: string[];
}

export interface ChainProposalResult {
  draft: ChainDraft;
  validation: ChainValidationResult;
  audit: ProposalAudit;
}

export interface ConfirmedChainGraph {
  schema_version: '1';
  id: string;
  name: string;
  source_text: string;
  entry_node: string;
  nodes: ChainNodeDraft[];
  transitions: ChainTransitionDraft[];
  revision: number;
  proposal_audit: ProposalAudit | null;
}

export interface ConfirmationResult {
  chain: ConfirmedChainGraph;
  validation: ChainValidationResult;
  persisted: boolean;
  persistence_id: string | null;
}

export interface MarkovBuilderApi {
  propose(text: string, useLlm: boolean): Promise<ChainProposalResult>;
  validate(draft: ChainDraft): Promise<ChainValidationResult>;
  confirm(draft: ChainDraft): Promise<ConfirmationResult>;
}
