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

export type TransitionResearchPlaceLevel = 'region' | 'country' | 'city';

export type TransitionResearchTimeUnit =
  | 'event'
  | 'hour'
  | 'day'
  | 'friday'
  | 'week'
  | 'year';

export type PipelineEstimateSourceKind =
  | 'official_statistics'
  | 'census'
  | 'representative_survey'
  | 'research_article'
  | 'government_report'
  | 'university_report'
  | 'news'
  | 'online_opinion'
  | 'expert_commentary'
  | 'user_url'
  | 'user_upload'
  | 'user_text';

export interface TransitionOutcomeDefinition {
  id: string;
  description: string;
  localized_descriptions: Record<string, string>;
}

export interface TransitionResearchPlace {
  level: TransitionResearchPlaceLevel;
  place_id: string;
  place_label: string;
  population: number;
  country_code?: string | null;
  local_names: Record<string, string>;
  dominant_languages: string[];
}

export interface TransitionProbabilityResearchRequest {
  transition_id: string;
  outcome_id: string;
  outcome_description: string;
  outcomes: TransitionOutcomeDefinition[];
  conditioning_id: string;
  conditioning_description: string;
  localized_conditioning_descriptions: Record<string, string>;
  localized_search_terms: Record<string, string>;
  place: TransitionResearchPlace;
  time_unit: TransitionResearchTimeUnit;
  predictor_values: Record<string, string | number | boolean>;
  condition_values: Record<string, string | number | boolean>;
  population_basis?: string | null;
}

export interface PipelineEstimateSource {
  id: string;
  title: string;
  url: string | null;
  source_kind: PipelineEstimateSourceKind;
  observation_date: string | null;
  published_date: string | null;
  retrieved_date: string | null;
  language: string;
  excerpt: string;
  source_version: string;
  license: string;
  supports_joint_outcome: boolean;
}

export interface PipelineResearchLog {
  sequence: number;
  origin: 'user' | 'automatic';
  language: string;
  engine: string;
  query_or_source: string;
  source_kind: PipelineEstimateSourceKind;
  outcome: 'no_result' | 'candidate' | 'rejected' | 'error';
  source_ids: string[];
}

export interface PipelineTransitionEstimate {
  id: string;
  kind: 'pipeline_estimate';
  review_state: 'draft';
  pipeline_attempt_id: string;
  outcome_id: string;
  conditioning_id: string;
  place: string;
  time_unit: TransitionResearchTimeUnit;
  predictor_values: Record<string, string | number | boolean>;
  condition_values: Record<string, string | number | boolean>;
  probability: number;
  ci_low: number;
  ci_high: number;
  population: string;
  sample_size: number | null;
  reasoning: string;
  assumptions: string[];
  method: 'source_synthesis' | 'joint_outcome_synthesis';
  sources: PipelineEstimateSource[];
  selected_source_ids: string[];
  search_log: PipelineResearchLog[];
  pipeline_provider: string;
  pipeline_model: string;
  prompt_version: string;
}

export interface MarkovBuilderApi {
  propose(text: string, useLlm: boolean): Promise<ChainProposalResult>;
  validate(draft: ChainDraft): Promise<ChainValidationResult>;
  researchProbability(
    request: TransitionProbabilityResearchRequest,
  ): Promise<PipelineTransitionEstimate>;
  confirm(draft: ChainDraft): Promise<ConfirmationResult>;
}
