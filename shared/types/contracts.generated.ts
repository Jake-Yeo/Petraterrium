export type AIConnectionTest = {
  ok: boolean;
  message?: string | null;
  error?: string | null;
  provenance?: AISourceProvenance | null;
};

export type AISettingsUpdate = {
  source?: "openai_cli" | "openai_api" | null;
  cli_command?: string | null;
  cli_model?: string | null;
  api_model?: string | null;
  api_key?: string | null;
  clear_api_key?: boolean;
};

export type AISettingsView = {
  source: "openai_cli" | "openai_api";
  cli_command: string;
  cli_model: string;
  api_model: string;
  api_key_configured: boolean;
  api_key_storage: string;
  updated_at: string;
};

export type AISourceProvenance = {
  source: "openai_cli" | "openai_api";
  source_label: "OpenAI CLI" | "OpenAI API";
  model: string;
  generated_at: string;
  prompt_version: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
};

export type ActionDefinition = {
  id: string;
  system?: string | null;
  category?: string | null;
  probability: ProbabilitySpec;
  duration?: DurationDistribution | null;
  duration_minutes?: number | null;
  priority: number;
  meaningful?: boolean;
  passive?: boolean;
  interruptible?: boolean;
  protected?: boolean;
  interruption_outcome?: "defer" | "cancel" | null;
  emergency_interruptions?: Array<string>;
  reschedulable?: boolean;
  compatible_with?: Array<string>;
  priority_modifiers?: {
  [key: string]: number;
};
  requires_role?: string | null;
  target_requires_role?: string | null;
  loser_outcome: "paused" | "deferred" | "cancelled" | "relationship_cost" | "continues";
  effects?: {
  [key: string]: number;
};
};

export type ActionLogEntry = {
  chain_id: string | null;
  agent_id: string;
  tick: number;
  action_id: string;
  target_agent_id: string | null;
  place: string;
  cause: string;
  state_before: {
  [key: string]: string;
};
  state_after: {
  [key: string]: string;
};
  previous_action_id: string | null;
  chain_step_index: number;
  segment: string;
  role: string;
};

export type ActionPlaceEvidenceSummary = {
  action_id: string;
  place: CoefficientPlace;
  fitted_count: number;
  measured_count?: number;
  default_estimated_count: number;
  blocked_count: number;
  coefficients: Array<RunCoefficientReceipt>;
};

export type AgentBehaviorProposalDraft = {
  schema_version?: "2";
  id: string;
  prompt: string;
  imported_feature_ids?: Array<string>;
  types: Array<AgentTypeDefinition>;
  audit: AgentTypeProposalAudit;
  status?: "awaiting_confirmation";
  revision?: number;
  routine_drafts?: Array<RoutineProposalDraft>;
  decision_tree_drafts: DecisionTreeRegistryDefinition;
  decision_inputs?: Array<DecisionEdgeInputPlan>;
  evidence_requirements?: Array<BehaviorEvidenceRequirement>;
};

export type AgentDetail = {
  agent_id: string;
  run_id: string;
  place: string;
  role: string;
  synthetic: true;
  log_tier: "spotlight" | "sampled" | "mass";
  log_scope: string;
  traits: {
  [key: string]: unknown;
};
  states: {
  [key: string]: string;
};
  behaviour: {
  [key: string]: number;
};
  relationships: Array<AgentRelationship>;
  timeline: Array<AgentTimelineEntry>;
  media: Array<string>;
};

export type AgentHousehold = {
  household_id: string;
  members: Array<HouseholdMember>;
};

export type AgentInitialStateProvenance = {
  source_template_id: string;
  sampling_basis: "measured_joint" | "measured_marginal" | "imputed" | "unknown";
  household_evidence: EvidenceReference;
  field_evidence: {
  [key: string]: EvidenceReference;
};
  unknown_fields: Array<string>;
};

export type AgentInteractionDetail = {
  tick: number;
  role: "initiator" | "target";
  interaction_type: string;
  channel: string;
  other_agent_id: string;
  place: string;
  state_deltas: Array<AppliedStateDelta>;
  relationship_deltas: Array<AppliedRelationshipDelta>;
  interaction_tree?: InteractionTreeTrace | null;
};

export type AgentLocation = {
  country: string;
  region?: string | null;
  city: string;
  neighbourhood?: string | null;
  specific_place?: string | null;
};

export type AgentPoint = {
  agent_id: string;
  place: string;
  latitude: number;
  longitude: number;
  state: string;
  color: string;
  log_tier: "spotlight" | "sampled" | "mass";
};

export type AgentPointList = {
  agents: Array<AgentPoint>;
  total: number;
  returned: number;
  representative: boolean;
};

export type AgentRecord = {
  agent_id: string;
  place: string;
  latitude: number;
  longitude: number;
  role: string;
  log_tier: "spotlight" | "sampled" | "mass";
  traits: {
  [key: string]: unknown;
};
  states: {
  [key: string]: string;
};
  behaviour: {
  [key: string]: number;
};
  behaviour_provenance: {
  [key: string]: Evidence;
};
  relationships: Array<Relationship>;
  weight: number;
};

export type AgentRelationship = {
  target_id: string;
  kind: string;
  weight: number;
};

export type AgentRoutineEffect = {
  kind?: "agent_routine";
  participant: "actor" | "target";
  operation: "add" | "remove";
  routine_id: string;
};

export type AgentStateValue = {
  state_id: string;
  value?: number | null;
  status: "present" | "unknown";
  evidence: StateEvidence;
};

export type AgentStateVector = {
  catalog_version: string;
  values: Array<AgentStateValue>;
};

export type AgentTimelineEntry = {
  tick: number;
  day: number;
  action: string;
  chain_id: string | null;
  previous_action_id: string | null;
  chain_step_index: number | null;
  target_agent_id: string | null;
  causes: {
  [key: string]: number;
};
  state_before: {
  [key: string]: string;
};
  state_after: {
  [key: string]: string;
};
};

export type AgentTimelinePoint = {
  day: number;
  date: string;
  tick: number;
  elapsed_hours: number;
  module: string;
  state: string;
  location: string;
  memory?: {
  [key: string]: number;
};
  state_receipts?: Array<{
  [key: string]: unknown;
}>;
  action_receipts?: Array<{
  [key: string]: unknown;
}>;
  actions: Array<string>;
  routine_actions: Array<string>;
  interactions: Array<string>;
  interaction_details?: Array<AgentInteractionDetail>;
  decision_path: Array<petraterrium__simulation__run_service__DecisionPathStep>;
  location_transitions: Array<LocationTransitionStep>;
  time_receipts?: Array<{
  [key: string]: unknown;
}>;
  daily_time?: {
  [key: string]: unknown;
} | null;
};

export type AgentTypeDefinition = {
  id: string;
  name: string;
  description?: string | null;
  parent_ids?: Array<string>;
  traits?: Array<AgentTypeMember>;
  routines?: Array<AgentTypeMember>;
  decisions?: Array<AgentTypeMember>;
  overrides?: Array<AgentTypeOverride>;
};

export type AgentTypeMember = {
  id: string;
  name: string;
  definition: string;
  description?: string | null;
  source_feature_ids?: Array<string>;
};

export type AgentTypeOverride = {
  member_kind: "trait" | "routine" | "decision";
  member_id: string;
  source_type_id: string;
};

export type AgentTypeProposalAudit = {
  provider: "openai_cli" | "openai_api" | "deterministic" | "manual";
  model: string;
  generated_at: string;
  prompt_version: string;
};

export type AgentTypeProposalDraft = {
  schema_version?: "1";
  id: string;
  prompt: string;
  imported_feature_ids?: Array<string>;
  types: Array<AgentTypeDefinition>;
  audit: AgentTypeProposalAudit;
  status?: "awaiting_confirmation";
  revision?: number;
};

export type AgentTypeProposalRequest = {
  prompt: string;
};

export type AgentTypeRegistryView = {
  configured: boolean;
  confirmed: ConfirmedAgentTypeRegistry | null;
  resolved: ResolvedAgentTypeRegistry;
};

export type AggregateBenchmark = {
  action_id: string;
  population: number;
  observed_annual_count: number;
  tolerance_factor?: number;
};

export type AppliedRelationshipDelta = {
  source_agent_id: string;
  target_agent_id: string;
  field: "weight" | "trust" | "similarity";
  before: number;
  delta: number;
  after: number;
};

export type AppliedStateDelta = {
  agent_id: string;
  state: string;
  before: number;
  delta: number;
  after: number;
};

export type AtlasAgentTypeAssignment = {
  status: "confirmed";
  fallback_agent_type_id: string;
  rules: Array<AtlasAgentTypeRule>;
};

export type AtlasAgentTypeCondition = {
  field: string;
  operator: "equals" | "not_equals" | "one_of" | "at_least" | "at_most" | "between";
  value?: string | number | null;
  upper_value?: string | number | null;
  values?: Array<string | number>;
};

export type AtlasAgentTypeRule = {
  id: string;
  agent_type_ids: Array<string>;
  conditions: Array<AtlasAgentTypeCondition>;
};

export type AtlasCity = {
  geonameid: number;
  name: string;
  asciiname: string;
  country_code: string;
  country_name: string;
  admin1: string;
  admin2: string;
  latitude: number;
  longitude: number;
  population: number;
  population_status: "present" | "missing";
  timezone: string;
  simulation_tier: "simulated" | "disaggregated";
  simulation_ready: boolean;
  tier_reason: string;
  coverage_percent: number;
  inherited_coverage_percent: number;
  resolved_coverage_percent: number;
  status: "present" | "inherited" | "imputed" | "estimated" | "missing";
  coverage_state: "full" | "partial" | "none";
  fields: Array<MarginalField>;
  behaviour: Array<BehaviourModel>;
  density_per_km2: number | null;
  density_provenance: Provenance | null;
};

export type AtlasCountry = {
  country_code: string;
  name: string;
  cities: number;
};

export type AtlasOverview = {
  summary: AtlasSummary;
  cities: Array<AtlasCity>;
  filtered_count: number;
  page: number;
  page_size: number;
  countries: Array<AtlasCountry>;
  gaps: Array<DataGap>;
  backbone: Backbone;
};

export type AtlasPopulationFeatureCoverage = {
  feature_id: string;
  measured_agents: number;
  imputed_agents: number;
  unknown_agents: number;
  sources: Array<string>;
};

export type AtlasPopulationRequest = {
  population_id?: string;
  selector: PlaceSelector;
  scope?: string;
  seed?: number;
  target_agents?: number;
  agent_type_id?: string;
  type_assignment?: AtlasAgentTypeAssignment | null;
};

export type AtlasPopulationResult = {
  selector: PlaceSelector;
  scope: string;
  materialization: InitialPopulationMaterialization;
  feature_coverage: Array<AtlasPopulationFeatureCoverage>;
  agent_type_counts: {
  [key: string]: number;
};
  warnings: Array<string>;
};

export type AtlasScope = {
  run_id: string;
  label: string;
  run_available: boolean;
};

export type AtlasScopes = {
  scopes: Array<AtlasScope>;
};

export type AtlasSource = {
  source_id: string;
  name: string;
  url: string;
  access: "public" | "registration" | "licensed";
  license: string;
  fields: Array<string>;
  adapter: string;
  instructions: string;
  download_hosts: Array<string>;
};

export type AtlasSummary = {
  total_cities: number;
  total_population: number;
  cities_without_population: number;
  direct: CoverageCounts;
  direct_plus_inherited: CoverageCounts;
  fields: Array<FieldCoverage>;
  simulated_cities: number;
  disaggregated_cities: number;
  countries_with_fitted_behaviour: number;
  revision: number;
  scope: string;
  as_of: string;
};

export type AttributeDefinition = {
  id: string;
  kind: "categorical" | "continuous" | "boolean";
  values?: Array<string>;
  distribution?: Distribution | null;
  provenance: Evidence;
};

export type AutoImportAllFilteredSelection = {
  mode: "all_filtered";
  query: {
  [key: string]: unknown;
};
  excluded_item_ids: Array<string>;
};

export type AutoImportAttemptView = {
  attempt_id: string;
  target: AutoImportTargetView;
  stage: "collecting" | "mapping" | "verifying" | "review" | "ready" | "failed" | "promoted";
  mappings: Array<AutoImportMappingColumn>;
  verification: Array<AutoImportVerificationCheck>;
  sources: Array<AutoImportResearchSource>;
  search_log: Array<AutoImportSearchEntry>;
  evidence_kind: "measured" | "estimated" | null;
  estimate_trace: AutoImportEstimateTraceView | null;
  candidate_values: {
  [key: string]: number | string | null;
};
  distribution_changes: Array<AutoImportDistributionChange>;
  draft_status: "editable_draft" | "confirmed" | "promoted";
  usable_in_demo: boolean;
  can_promote: boolean;
  error: string | null;
  promoted_at: string | null;
  promotion_id: string | null;
};

export type AutoImportBatchItemView = {
  item_id: string;
  attempt_id: string | null;
  target: AutoImportTargetView;
  status: "queued" | "running" | "ready" | "failed" | "promoted";
  evidence_kind: "measured" | "estimated" | null;
  mappings: Array<AutoImportMappingColumn>;
  mapping_confirmed: boolean;
  can_promote: boolean;
  error: string | null;
};

export type AutoImportBatchPromotionRequest = {
  mode: "all_eligible" | "selected";
  item_ids: Array<string>;
  mapping_confirmed: boolean;
  redistribution_confirmed: boolean;
};

export type AutoImportBatchRequest = {
  scope: string;
  as_of: string;
  concurrency: number;
  selection: AutoImportExplicitSelection | AutoImportAllFilteredSelection;
};

export type AutoImportBatchSummary = {
  total: number;
  completed: number;
  queued: number;
  running: number;
  ready: number;
  measured: number;
  estimated: number;
  failed: number;
  retryable_failed: number;
  promoted: number;
};

export type AutoImportBatchView = {
  batch_id: string;
  status: "queued" | "running" | "review" | "partial" | "complete" | "failed";
  summary: AutoImportBatchSummary;
  items: Array<AutoImportBatchItemView>;
  created_at: string;
  updated_at: string;
};

export type AutoImportCanonicalValue = {
  id: string;
  label: string;
};

export type AutoImportDistributionChange = {
  source_label: string;
  target_label: string;
  before: number;
  after: number;
};

export type AutoImportDistributionRequirement = {
  values: Array<AutoImportCanonicalValue>;
  denominator: string;
  time_unit: string;
  unit: string;
  range: string | null;
  total: string | null;
};

export type AutoImportEstimateInput = {
  label: string;
  value: string;
  source_id: string | null;
};

export type AutoImportEstimateTraceView = {
  method: string;
  calculation: string;
  assumptions: Array<string>;
  inputs: Array<AutoImportEstimateInput>;
  confidence_interval: string;
  source_ids_used: Array<string>;
  limitations: Array<string>;
};

export type AutoImportEvidenceView = {
  attempts: Array<AutoImportAttemptView>;
};

export type AutoImportExplicitSelection = {
  mode: "explicit";
  item_ids: Array<string>;
};

export type AutoImportMappingColumn = {
  column: string;
  target: string | null;
  ambiguous: boolean;
  samples: Array<string>;
  options: Array<AutoImportMappingOption>;
};

export type AutoImportMappingEdit = {
  column: string;
  target: string | null;
};

export type AutoImportMappingOption = {
  id: string;
  label: string;
};

export type AutoImportMappingReview = {
  mappings: Array<AutoImportMappingEdit>;
  reviewed: boolean;
  distribution: {
  [key: string]: number;
} | null;
};

export type AutoImportPromotionRequest = {
  redistribution_confirmed: boolean;
};

export type AutoImportQueueItemView = {
  place_id: string;
  place_label: string;
  level: "region" | "country" | "city";
  country_code: string | null;
  geonameid: number | null;
  population: number;
  field_id: string;
  field_label: string;
  current_status: "present" | "inherited" | "imputed" | "estimated" | "missing";
  as_of: string;
  required_distribution: AutoImportDistributionRequirement;
  item_id: string;
  missing_impact: number;
  priority: "primary" | "lower";
  place_item_count: number;
};

export type AutoImportQueuePageView = {
  items: Array<AutoImportQueueItemView>;
  filtered_count: number;
  filtered_population: number;
  page: number;
  page_size: number;
  primary_count: number;
  primary_population: number;
  lower_priority_count: number;
  lower_priority_population: number;
};

export type AutoImportRerunRequest = {
  source_tiers: Array<"official_statistics" | "census" | "representative_survey" | "research_article" | "government_report" | "university_report" | "news" | "online_opinion" | "expert_commentary">;
};

export type AutoImportResearchSource = {
  source_id: string;
  title: string;
  publisher: string;
  url: string | null;
  source_date: string | null;
  published_date: string | null;
  version: string | null;
  licence: string | null;
  language: string;
  original_excerpt: string | null;
  translated_excerpt: string | null;
  accepted: boolean;
  rejection_reason: string | null;
  ai_provenance: AISourceProvenance | null;
};

export type AutoImportSearchEntry = {
  engine: string;
  language: string;
  query: string;
  searched_at: string | null;
  result_count: number;
  outcome: string;
  rejection_reasons: Array<string>;
};

export type AutoImportTargetView = {
  place_id: string;
  place_label: string;
  level: "region" | "country" | "city";
  country_code: string | null;
  geonameid: number | null;
  population: number;
  field_id: string;
  field_label: string;
  current_status: "present" | "inherited" | "imputed" | "estimated" | "missing";
  as_of: string;
  required_distribution: AutoImportDistributionRequirement;
};

export type AutoImportVerificationCheck = {
  id: string;
  label: string;
  status: "passed" | "failed" | "unknown";
  detail: string;
};

export type Backbone = {
  loaded: boolean;
  source: string;
  source_url: string;
  license: string;
  version: string;
  downloaded_at: string | null;
  source_date: string | null;
  original_rows: number;
  retained_rows: number;
  excluded_rows: number;
  duplicate_rows: number;
  tier_policy: string;
  selection_policy: string;
};

export type BacktestComparison = {
  metric: string;
  simulated: Array<number>;
  observed: Array<number>;
  mean_absolute_error: number;
  outcome: "hit" | "miss";
  cutoff_date: string;
  provenance: string;
};

export type BehaviorEvidenceRequirement = {
  id: string;
  kind: "routine_schedule" | "decision_probability";
  status: "matched" | "missing";
  target_id: string;
  source_feature_ids?: Array<string>;
  outcome: string;
  population_scope: string;
  place_scope: "global" | "region" | "country" | "city";
  time_scope: string;
  accepted_bases: Array<"measured" | "user_defined" | "measured_joint" | "fitted_model">;
  required_fields: Array<string>;
  matched_evidence_ids?: Array<string>;
  message: string;
};

export type BehaviourBundle = {
  id: string;
  layer: number;
  inherits?: Array<string>;
  values?: {
  [key: string]: number;
};
  issue_values?: {
  [key: string]: {
  [key: string]: number;
};
};
  blends?: {
  [key: string]: {
  [key: string]: number;
};
};
  provenance: Evidence;
};

export type BehaviourEvidenceRow = {
  id: string;
  action_id: string;
  country_code: string;
  definition: string;
  model_status: "active_fitted" | "rejected_fit" | "label_only";
  source_status: "measured" | "source_unclassified";
  source_type: string;
  source_tier: number | null;
  outcome_rate: number | null;
  ci_low: number | null;
  ci_high: number | null;
  uncertainty: number | null;
  sample_size: number;
  effective_sample_size: number | null;
  ci_method: string | null;
  population: string;
  denominator: string;
  traits: Array<string>;
  algorithm: string | null;
  reason: string | null;
  training_rows: number;
  heldout_rows: number;
  heldout_loss: number | null;
  baseline_loss: number | null;
  provenance: Provenance;
};

export type BehaviourModel = {
  country_code: string;
  behaviour: string;
  fitted: boolean;
  label_only: boolean;
  provenance: Provenance;
  heldout_loss: number | null;
  baseline_loss: number | null;
  training_rows: number;
  heldout_rows: number;
  traits: Array<string>;
};

export type BrokenModuleReference = {
  module_id: string;
  node_id: string;
  target_module_id: string;
};

export type Catalog = {
  countries: Array<Country>;
  engine_version: string;
  data_version: string;
  contract_version: string;
  notice: string;
};

export type ChainBranch = {
  action: string;
  probability: number;
  delay_ticks?: number;
  formula?: string | null;
  conditions?: {
  [key: string]: string;
};
  cross_agent?: boolean;
  terminates?: boolean;
};

export type ChainDefinition = {
  id: string;
  trigger: string;
  branches: Array<ChainBranch>;
  max_length?: number | null;
  continue_probability?: number;
};

export type ChainDraft = {
  schema_version?: "1";
  id: string;
  name: string;
  source_text: string;
  entry_node?: string | null;
  nodes: Array<ChainNodeDraft>;
  transitions: Array<ChainTransitionDraft>;
  revision?: number;
  proposal_audit?: ProposalAudit | null;
};

export type ChainNodeDraft = {
  id: string;
  label: string;
  terminal?: boolean;
  origin: "user_explicit" | "model_proposal" | "structural" | "manual_edit";
  source_excerpt?: string | null;
};

export type ChainProposalRequest = {
  text: string;
  chain_id?: string | null;
  name?: string | null;
  use_llm?: boolean;
};

export type ChainProposalResult = {
  draft: ChainDraft;
  validation: ChainValidationResult;
  audit: ProposalAudit;
};

export type ChainTransitionDraft = {
  id: string;
  from_node: string;
  to_node: string;
  probability?: number | null;
  condition?: string | null;
  origin: "user_explicit" | "model_proposal" | "structural" | "manual_edit";
  source_excerpt?: string | null;
};

export type ChainValidationIssue = {
  code: string;
  severity: "error" | "warning";
  path: string;
  message: string;
};

export type ChainValidationResult = {
  valid: boolean;
  can_confirm: boolean;
  issues: Array<ChainValidationIssue>;
  outgoing_totals: Array<OutgoingProbabilityTotal>;
  terminal_states: Array<string>;
  dead_ends: Array<string>;
  non_terminating_loops: Array<Array<string>>;
  missing_conditions: Array<string>;
  missing_probabilities: Array<string>;
  unreachable_nodes: Array<string>;
};

export type ChoiceCondition = {
  traits?: {
  [key: string]: string;
};
  state?: {
  [key: string]: string;
};
  context?: {
  [key: string]: string;
};
  place?: string | null;
  segment?: string | null;
  role?: string | null;
};

export type ChoiceEvidence = {
  id: string;
  action_id: string;
  conditioning_id: string;
  conditioning?: ChoiceCondition;
  definition: string;
  value?: number | null;
  ci_low: number;
  ci_high: number;
  source_type: "administrative" | "mobility" | "transaction" | "time_use_diary" | "representative_survey" | "small_study" | "poll" | "news" | "ethnography" | "social_media" | "unknown";
  tier: number;
  sample_size?: number | null;
  source_date?: string | null;
  population: string;
  denominator: string;
  time_unit: "event" | "hour" | "day" | "friday" | "week" | "year";
  source_time_unit: "event" | "hour" | "day" | "friday" | "week" | "year";
  explicit_time_adjustment?: boolean;
  tier_flag: "measured" | "imputed" | "hint_only" | "unknown";
  provenance: Evidence;
  missing_requirement?: string;
};

export type ChoiceEvidenceCatalog = {
  rows: Array<BehaviourEvidenceRow>;
};

export type CityDetail = {
  city: AtlasCity;
  missing_fields: Array<"age_sex" | "income" | "education" | "specialization" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size">;
  direct_observation_gaps: Array<"age_sex" | "income" | "education" | "specialization" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size">;
  history: Array<Provenance>;
  legacy_fields: Array<LegacyMarginalField>;
  revision: number;
  simulation_note: string;
};

export type CoefficientInterval = {
  low: number;
  high: number;
};

export type CoefficientPlace = {
  level: "city" | "country" | "region" | "global";
  place_id: string;
  region_id?: string | null;
  country_id?: string | null;
  city_id?: string | null;
};

export type ColumnMapping = {
  column: string;
  target: string | null;
  ambiguous: boolean;
  reason: string;
};

export type ConditionClause = {
  input_id: string;
  operator: "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "in";
  value: string | number | number | boolean | Array<string | number | number | boolean>;
};

export type ConfirmAgentBehaviorProposalRequest = {
  draft: AgentBehaviorProposalDraft;
  user_confirmed: true;
};

export type ConfirmAgentTypeProposalRequest = {
  draft: AgentTypeProposalDraft;
  user_confirmed: true;
};

export type ConfirmChainRequest = {
  draft: ChainDraft;
  user_confirmed: true;
};

export type ConfirmDecisionEvidenceRegistryRequest = {
  registry: {
  [key: string]: unknown;
};
  user_confirmed: true;
};

export type ConfirmDecisionTreeRegistryRequest = {
  registry: DecisionTreeRegistryDefinition;
  user_confirmed: true;
};

export type ConfirmInteractionProgramRequest = {
  program: InteractionProgramDefinition;
  user_confirmed: true;
};

export type ConfirmMobilityRequest = {
  registry: MobilityRegistryDefinition;
  user_confirmed: true;
};

export type ConfirmRoutineRegistryRequest = {
  registry: RoutineRegistryDefinition;
  user_confirmed: true;
};

export type ConfirmationResult = {
  chain: ConfirmedChainGraph;
  validation: ChainValidationResult;
  persisted: boolean;
  persistence_id?: string | null;
};

export type ConfirmedAgentBehaviorBundle = {
  schema_version?: "2";
  agent_types: ConfirmedAgentTypeRegistry;
  routines: RoutineRegistryDefinition;
  decision_trees: DecisionTreeRegistryDefinition;
  evidence_requirements: Array<BehaviorEvidenceRequirement>;
  audit: AgentTypeProposalAudit;
  confirmed?: true;
  revision: number;
};

export type ConfirmedAgentTypeRegistry = {
  schema_version?: "1";
  id: string;
  imported_feature_ids: Array<string>;
  types: Array<AgentTypeDefinition>;
  resolved: ResolvedAgentTypeRegistry;
  audit: AgentTypeProposalAudit;
  confirmed?: true;
  revision: number;
};

export type ConfirmedChainGraph = {
  schema_version?: "1";
  id: string;
  name: string;
  source_text: string;
  entry_node: string;
  nodes: Array<ChainNodeDraft>;
  transitions: Array<ChainTransitionDraft>;
  revision: number;
  proposal_audit?: ProposalAudit | null;
};

export type Country = {
  country: string;
  name: string;
  population: number;
  latitude: number;
  longitude: number;
  fake: true;
};

export type CouplingDefinition = {
  id: string;
  source_system: string;
  target_system: string;
  source_metric: string;
  target_parameter: string;
  scale: number;
};

export type CoverageCounts = {
  full: number;
  partial: number;
  none: number;
};

export type DSLConfig = {
  schema_version?: "1";
  id: string;
  version: string;
  states: Array<StateDefinition>;
  attributes?: Array<AttributeDefinition>;
  feature_registry?: FeatureRegistry | null;
  choice_evidence?: Array<ChoiceEvidence>;
  place_states?: Array<string>;
  parameters?: Array<ParameterDefinition>;
  systems: Array<SystemDefinition>;
  scenarios?: Array<ScenarioDefinition>;
  rules?: Array<RuleDefinition>;
  actions?: Array<ActionDefinition>;
  chains?: Array<ChainDefinition>;
  markov_chain_drafts?: Array<ConfirmedChainGraph>;
  markov_programs?: Array<MarkovProgram>;
  transition_evidence?: Array<TransitionEvidence>;
  roles?: Array<RoleDefinition>;
  default_states?: Array<DefaultDefinition>;
  behaviour_bundles?: Array<BehaviourBundle>;
  networks?: Array<NetworkDefinition>;
  media_rules?: Array<MediaRule>;
  leader_actions?: Array<LeaderActionDefinition>;
  events?: Array<EventDefinition>;
  couplings?: Array<CouplingDefinition>;
  tick: TickConfig;
  outputs: OutputSpec;
  population: PopulationReference;
  benchmarks?: Array<AggregateBenchmark>;
};

export type DSLRender = {
  plain_language: string;
  sliders: Array<SliderSpec>;
};

export type DSLValidationResult = {
  valid: boolean;
  errors: Array<petraterrium__dsl__models__ValidationIssue>;
  warnings: Array<petraterrium__dsl__models__ValidationIssue>;
  implied_aggregates: Array<ImpliedAggregate>;
};

export type DailySnapshot = {
  run_id: string;
  day: number;
  places: Array<PlaceSnapshot>;
  seed: number;
  engine_version: string;
  data_version: string;
  config_hash: string;
  tick: number;
  elapsed_hours: number;
};

export type DataGap = {
  geonameid: number;
  city: string;
  country_code: string;
  population: number;
  field: "age_sex" | "income" | "education" | "specialization" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  status: "present" | "inherited" | "imputed" | "estimated" | "missing";
  suggested_source: string;
};

export type DecisionEdgeInputPlan = {
  tree_id: string;
  module_id: string;
  edge_id: string;
  source_feature_ids?: Array<string>;
  outcome: string;
  population_scope: string;
  place_scope: "global" | "region" | "country" | "city";
  time_scope: string;
  decision_id?: string | null;
  evidence_edge_id?: string | null;
};

export type DecisionEdgeTemplate = {
  id: string;
  decision_id: string;
  domain: "work" | "social" | "family" | "health" | "consumption" | "political" | "other";
  from_state: string;
  to_state: string;
  label: string;
  formula: DecisionProbabilityFormula;
  source: ResearchCitation | NoSourceAttachment;
};

export type DecisionEvidenceCatalogItem = {
  id: string;
  name: string;
  domain: string;
  status: string;
  edge_count: number;
  evidence_count: number;
};

export type DecisionEvidenceDetail = {
  template: DecisionTreeTemplate;
  evidence: Array<DecisionFactorEvidence>;
};

export type DecisionEvidenceRegistryDefinition = {
  version: string;
  templates?: Array<DecisionTreeTemplate>;
  evidence?: Array<DecisionFactorEvidence>;
};

export type DecisionEvidenceRegistryStatus = {
  configured: boolean;
  version?: string | null;
  template_count?: number;
  evidence_count?: number;
  valid?: boolean | null;
  issue_count?: number;
};

export type DecisionEvidenceRegistryView = {
  status: DecisionEvidenceRegistryStatus;
  registry: DecisionEvidenceRegistryDefinition | null;
  validation: DecisionEvidenceValidation | null;
  catalog: Array<DecisionEvidenceCatalogItem>;
};

export type DecisionEvidenceValidation = {
  valid: boolean;
  issues: Array<DecisionEvidenceValidationIssue>;
};

export type DecisionEvidenceValidationIssue = {
  code: string;
  path: string;
  message: string;
};

export type DecisionFactorEvidence = {
  id: string;
  decision_id: string;
  edge_id: string;
  factor_id: string;
  place: EvidencePlace;
  predicate: EvidencePredicate;
  basis: "measured_joint" | "fitted_model" | "marginal";
  estimate: number;
  ci_low: number;
  ci_high: number;
  sample_size: number;
  held_out_sample_size?: number | null;
  fittable: boolean;
  source: ResearchCitation;
};

export type DecisionGraph = {
  view: "static" | "run";
  run_id: string | null;
  unfiltered: boolean;
  filters: DecisionGraphFilter;
  nodes: Array<DecisionGraphNode>;
  edges: Array<DecisionGraphEdge>;
  diagnostics: Array<DecisionGraphDiagnostic>;
  path: Array<petraterrium__contracts__DecisionPathStep>;
  transition_matrix: {
  [key: string]: {
  [key: string]: number;
};
};
  filter_options: DecisionGraphFilterOptions;
};

export type DecisionGraphDiagnostic = {
  kind: "orphan" | "dead_end" | "nonterminating_loop" | "unreachable_role" | "choice_sum" | "chain_length";
  subject: string;
  message: string;
};

export type DecisionGraphEdge = {
  edge_id: string;
  source: string;
  target: string;
  chain_id: string;
  intended_probability: number;
  formula: string;
  delay_ticks: number;
  delay_label: string;
  conditions: {
  [key: string]: string;
};
  cross_agent: boolean;
  terminates: boolean;
  observed_count: number;
  observed_frequency: number;
  sample_agents: Array<string>;
};

export type DecisionGraphFilter = {
  state: string;
  segment: string;
  place: string;
  role: string;
  tick_start: number | null;
  tick_end: number | null;
};

export type DecisionGraphFilterOptions = {
  states: Array<string>;
  segments: Array<string>;
  places: Array<string>;
  roles: Array<string>;
  agents: Array<string>;
  maximum_tick: number;
};

export type DecisionGraphNode = {
  action_id: string;
  system: string;
  base_probability: number;
  time_unit: string;
  parameter: string | null;
  source_state: string | null;
  opportunity: string | null;
  requires_role: string | null;
  target_requires_role: string | null;
  priority: number;
  interruptible: boolean;
  protected: boolean;
  reschedulable: boolean;
  loser_outcome: string;
  duration_minutes: number;
  compatible_with: Array<string>;
  priority_modifiers: {
  [key: string]: number;
};
  observed_count: number;
};

export type DecisionNodeTemplate = {
  id: string;
  label: string;
  kind: "decision" | "state" | "action" | "terminal";
};

export type DecisionProbabilityFormula = {
  id: string;
  name: string;
  combination: "product";
  factors: Array<ProbabilityFactor>;
};

export type DecisionTreeDefinition = {
  id: string;
  version: string;
  name: string;
  description?: string;
  root_module_id: string;
  agent_type_ids?: Array<string>;
  place_ids?: Array<string>;
  source: string;
  status: "draft" | "ready" | "blocked" | "deprecated";
  proposal_audit?: DecisionTreeProposalAudit | null;
};

export type DecisionTreeEdge = {
  id: string;
  from_node: string;
  to_node: string;
  label?: string;
  condition?: string;
  decision_id?: string | null;
  evidence_edge_id?: string | null;
  formula?: string | null;
  probability?: number | null;
  place_requirements?: Array<string>;
  time_requirements?: Array<string>;
  runtime_rules?: Array<{
  [key: string]: unknown;
}>;
};

export type DecisionTreeLink = {
  tree_id: string;
  name: string;
  agent_type: string;
  inherited_from?: string | null;
};

export type DecisionTreeModule = {
  id: string;
  version: string;
  name: string;
  description?: string;
  entry_node: string;
  nodes: Array<DecisionTreeNode>;
  edges?: Array<DecisionTreeEdge>;
  source: string;
  status: "draft" | "ready" | "blocked" | "deprecated";
  proposal_audit?: DecisionTreeProposalAudit | null;
};

export type DecisionTreeNode = {
  id: string;
  label: string;
  kind: "decision" | "action" | "terminal" | "module_reference";
  description?: string;
  target_module_id?: string | null;
  action_id?: string | null;
};

export type DecisionTreeProposalAudit = {
  origin: "ai" | "deterministic" | "manual";
  source_id: string;
  source_label: string;
  model: string;
  generated_at?: string | null;
  prompt_version: string;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost_usd?: number | null;
  message: string;
};

export type DecisionTreeRegistryDefinition = {
  version: string;
  trees: Array<DecisionTreeDefinition>;
  modules: Array<DecisionTreeModule>;
};

export type DecisionTreeRegistryView = {
  registry: DecisionTreeRegistryDefinition;
  validation: TreeRegistryValidation;
};

export type DecisionTreeTemplate = {
  id: string;
  name: string;
  domain: "work" | "social" | "family" | "health" | "consumption" | "political" | "other";
  status: "awaiting_evidence" | "ready";
  entry_state: string;
  terminal_states: Array<string>;
  nodes: Array<DecisionNodeTemplate>;
  edges: Array<DecisionEdgeTemplate>;
};

export type DefaultDefinition = {
  id: string;
  distribution: Distribution;
  depends_on?: Array<string>;
  when?: {
  [key: string]: string;
};
  place?: string | null;
  age_min?: number | null;
  age_max?: number | null;
};

export type DirectedRelationship = {
  source_agent_id: string;
  target_agent_id: string;
  eligible: boolean;
  relationship_type: string;
  states?: {
  [key: string]: number;
};
};

export type Distribution = {
  values: {
  [key: string]: number;
};
  provenance: Evidence;
};

export type DurationDistribution = {
  duration_min_hours: number;
  duration_median_hours: number;
  duration_max_hours: number;
  shape: "triangular" | "uniform" | "lognormal";
  shape_parameters?: {
  [key: string]: number;
};
  provenance: Evidence;
};

export type EducationProfile = {
  years_of_education?: number | null;
  isced_level?: number | null;
  country_label: string;
  country_code: string;
  specialization?: string | null;
  specialization_threshold_years: number;
  specialization_status: "present" | "not_applicable" | "awaiting_data";
  provenance: StateEvidence;
};

export type EnsembleUpdate = {
  run_id: string;
  completed: number;
  total: number;
  seeds: Array<number>;
  quantiles: {
  [key: string]: {
  [key: string]: number;
};
};
  evidence_table_version: string;
};

export type EvaluatedInteractionFactor = {
  kind: "base" | "relationship" | "co_location" | "place" | "time" | "context";
  factor: InteractionFactor;
};

export type EvaluatedInteractionProbabilityFactor = {
  factor_id: string;
  label: string;
  case_id: string;
  multiplier: number;
  inputs: {
  [key: string]: number | string | boolean;
};
  evidence: InteractionTransitionEvidence;
};

export type EvaluatedInteractionTransition = {
  transition_id: string;
  outcome: string;
  base_probability: number;
  unnormalized_weight: number;
  probability: number;
  factors?: Array<EvaluatedInteractionProbabilityFactor>;
  evidence: InteractionTransitionEvidence;
};

export type EventDefinition = {
  id: string;
  metric: string;
  threshold: number;
  direction: "above" | "below" | "increase" | "decrease";
};

export type Evidence = {
  source: string;
  version: string;
  status: "present" | "inherited" | "imputed" | "missing" | "unknown" | "label_only" | "literature_estimate" | "hint_only";
  uncertainty: number;
  source_date?: string | null;
};

export type EvidencePlace = {
  level: "city" | "country" | "region" | "global";
  place_id: string;
  region_id?: string | null;
  country_id?: string | null;
  city_id?: string | null;
};

export type EvidencePredicate = {
  operator: "exact" | "one_of" | "between" | "any";
  value?: string | number | number | boolean | null;
  values?: Array<string | number | number | boolean>;
  lower?: number | null;
  upper?: number | null;
};

export type EvidenceReference = {
  evidence_id: string;
  source: string;
  source_version: string;
  observed_at: string;
  licence: string;
  place: string;
  status: "measured_joint" | "measured_marginal" | "imputed" | "unknown";
  fields: Array<string>;
  uncertainty: string;
  url?: string | null;
};

export type FamilyRelationship = {
  target_agent_id: string;
  relationship: string;
  age?: number | null;
  weight: number;
};

export type FeatureDefinition = {
  id: string;
  name?: string | null;
  description?: string;
  kind: "categorical" | "continuous" | "binary";
  canonical_values?: Array<string>;
  value_range?: FeatureRange | null;
  provenance: Evidence;
  predictive?: boolean;
  ancestry_linked?: boolean;
};

export type FeatureDistribution = {
  feature_id: string;
  level: "global" | "region" | "subregion" | "country" | "city";
  place: string;
  population: string;
  population_count?: number | null;
  coverage_percent: number;
  values?: {
  [key: string]: number;
};
  mean?: number | null;
  standard_deviation?: number | null;
  provenance: Evidence;
  method?: "measured" | "compositional" | "fallback";
  fallback_for?: Array<string>;
  explicit_fallback?: boolean;
};

export type FeatureRange = {
  minimum: number;
  maximum: number;
  unit: string;
};

export type FeatureRegistry = {
  version: string;
  definitions: Array<FeatureDefinition>;
  distributions?: Array<FeatureDistribution>;
  joint_data?: Array<JointDataProof>;
};

export type FeatureResolutionRecord = {
  feature_id: string;
  city: string;
  country: string;
  region: string;
  status: string;
  resolved_level: string;
  source: string | null;
  version: string | null;
  source_date: string | null;
  population: string | null;
  coverage_percent: number | null;
  region_override: boolean;
  missing_requirement: string;
};

export type FieldCoverage = {
  field: "age_sex" | "income" | "education" | "specialization" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  present: number;
  inherited: number;
  imputed: number;
  estimated: number;
  missing: number;
  direct_percent: number;
  direct_plus_inherited_percent: number;
  direct_population_percent: number;
  direct_plus_inherited_population_percent: number;
  imputed_population_percent: number;
  estimated_population_percent: number;
};

export type FinanceEvidence = {
  status: "measured_joint" | "measured_marginal" | "inherited" | "imputed" | "literature_support" | "default_estimated" | "unknown" | "simulated";
  source: string;
  source_version: string;
  source_date?: string | null;
  url?: string | null;
  place: string;
  population: string;
  language?: string | null;
  original_title?: string | null;
  english_title?: string | null;
  search_source?: string | null;
  uncertainty: number;
  default_reason?: string | null;
  currency: string;
};

export type FinanceQuantity = {
  value?: number | null;
  evidence: FinanceEvidence;
};

export type FinanceState = {
  currency: string;
  status: "measured_joint" | "measured_marginal" | "inherited" | "imputed" | "literature_support" | "default_estimated" | "unknown" | "simulated";
  source_distribution_id?: string | null;
  source_cell_id?: string | null;
  money: FinanceQuantity;
  income: FinanceQuantity;
  expenses: FinanceQuantity;
  savings: FinanceQuantity;
  debt: FinanceQuantity;
  evidence: FinanceEvidence;
  formula?: string;
};

export type GraphTraversal = {
  primitive?: "neighbors";
  network: string;
  depth: number;
};

export type HeldOutValidationReceipt = {
  metric?: "log_loss";
  held_out_rows: number;
  fitted_score: number;
  default_score: number;
};

export type HierarchyOverview = {
  rows: Array<HierarchyRow>;
  scope: string;
  as_of: string;
  resolution_order: Array<string>;
  mapping_version: string;
};

export type HierarchyRow = {
  row_id: string;
  level: "global" | "region" | "subregion" | "country" | "city";
  parent_id: string | null;
  label: string;
  country_code: string | null;
  population: number;
  city_count: number;
  statuses: {
  [key: string]: "present" | "inherited" | "imputed" | "estimated" | "missing";
};
  coverage_by_field: {
  [key: string]: number;
};
  region_override: boolean;
  weight_source: string;
  children_paged: boolean;
};

export type HouseholdMember = {
  agent_id: string;
  age?: number | null;
  relationship: string;
  agent_types: Array<string>;
};

export type HouseholdMemberSeed = {
  member_id: string;
  age: number;
  sex: string;
  relationship_to_reference: "self" | "spouse" | "child" | "parent" | "sibling" | "other";
  agent_types: Array<string>;
  traits?: {
  [key: string]: unknown;
};
  states?: {
  [key: string]: string;
};
  field_evidence?: {
  [key: string]: string;
};
};

export type HouseholdSeed = {
  template_id: string;
  place: string;
  country: string;
  country_id?: string | null;
  region?: string | null;
  city: string;
  city_id?: string | null;
  neighbourhood?: string | null;
  latitude: number;
  longitude: number;
  weight: number;
  evidence_id: string;
  members: Array<HouseholdMemberSeed>;
};

export type ImpliedAggregate = {
  action_id: string;
  implied_annual_count: number;
  observed_annual_count: number;
  ratio: number;
};

export type ImportCommit = {
  mapping_hash: string;
  confirmed: boolean;
};

export type ImportHistory = {
  versions: Array<ImportVersion>;
};

export type ImportMetadata = {
  run_id: string;
  kind: "marginals" | "behaviour" | "population";
  source: string;
  source_date: string;
  published_date: string;
  version: string;
  uploader: string;
  source_id: string | null;
  country_code: string | null;
  unit: string;
  redistribution_allowed: boolean;
  processing_notes: Array<string>;
};

export type ImportPreview = {
  import_id: string;
  filename: string;
  metadata: ImportMetadata;
  row_count: number;
  sample_rows: Array<{
  [key: string]: string | number | number | boolean | null;
}>;
  mappings: Array<ColumnMapping>;
  mapping_audit: MappingAudit;
  status: "awaiting_confirmation";
};

export type ImportVersion = {
  import_id: string;
  source: string;
  source_date: string;
  published_date: string;
  version: string;
  scope: string;
  uploader: string;
  kind: string;
  filename: string;
  rows: number;
  status: string;
  live_fields: number;
  promoted_from: string | null;
  redistribution_allowed: boolean;
  models: Array<BehaviourModel>;
};

export type InitialAgentDetail = {
  agent_id: string;
  agent_types: Array<string>;
  age?: number | null;
  sex: string;
  country: string;
  city: string;
  current_location?: string | null;
  household_id?: string | null;
  household_size: number;
  family_status: string;
  location: AgentLocation;
  household?: AgentHousehold | null;
  family_relationships: Array<FamilyRelationship>;
  traits: {
  [key: string]: unknown;
};
  initial_states: {
  [key: string]: string;
};
  education_profile: EducationProfile;
  state_vector: AgentStateVector;
  finances: FinanceState;
  occupation?: string | null;
  health?: string | null;
  routines: Array<RoutineLink>;
  decision_trees: Array<DecisionTreeLink>;
  interaction_context: InitialInteractionContext;
  representative_weight: number;
};

export type InitialAgentDeviation = {
  deviation_id: string;
  field: string;
  status: "estimated" | "regional_imputed" | "omitted";
  places: Array<string>;
  reason: string;
  full_requirement: string;
};

export type InitialAgentDistribution = {
  field_id: string;
  label: string;
  summary: string;
  evidence_status: "measured" | "own_country_inherited" | "regional_imputed" | "estimated";
  source?: string | null;
  source_place?: string | null;
  bins: Array<InitialAgentDistributionBin>;
};

export type InitialAgentDistributionBin = {
  label: string;
  percentage: number;
  estimated_agents: number;
};

export type InitialAgentFacets = {
  agent_types: Array<string>;
  countries: Array<string>;
  cities: Array<string>;
  family_statuses: Array<string>;
};

export type InitialAgentFieldCoverage = {
  measured: Array<string>;
  own_country_inherited: Array<string>;
  regional_imputed: Array<string>;
  estimated: Array<string>;
  place_evidence?: Array<InitialAgentFieldPlaceEvidence>;
};

export type InitialAgentFieldPlaceEvidence = {
  country: string;
  country_code: string;
  status: "measured" | "own_country_inherited" | "regional_imputed" | "estimated";
  source?: string | null;
  source_place?: string | null;
  source_level: "country" | "region" | "global";
  source_version?: string | null;
};

export type InitialAgentGlobalInteractionSummary = {
  status?: "configured" | "recorded" | "unavailable";
  run_id?: string | null;
  participating_countries?: Array<string>;
  participating_regions?: Array<string>;
  cross_country_interactions?: number;
  cross_region_interactions?: number;
};

export type InitialAgentListItem = {
  agent_id: string;
  agent_types: Array<string>;
  age?: number | null;
  sex: string;
  country: string;
  city: string;
  current_location?: string | null;
  household_id?: string | null;
  household_size: number;
  family_status: string;
};

export type InitialAgentPage = {
  items: Array<InitialAgentListItem>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  facets: InitialAgentFacets;
  evidence_summary: InitialPopulationEvidenceSummary;
};

export type InitialAgentPlaceComparison = {
  comparison_id: string;
  level: "global" | "country" | "region";
  place: string;
  agent_count: number;
  distributions: Array<InitialAgentDistribution>;
};

export type InitialInteractionContext = {
  program_status: "absent" | "draft" | "confirmed";
  program_version?: string | null;
  history_available?: boolean;
  history_message: string;
  counterparts: Array<InitialInteractionCounterpart>;
  rules: Array<InitialInteractionRule>;
};

export type InitialInteractionCounterpart = {
  target_agent_id: string;
  relationship: string;
  relationship_kind: string;
  weight: number;
  trust?: number | null;
  similarity?: number | null;
  evidence: InitialInteractionEvidence;
  specific_place?: string | null;
  target_specific_place?: string | null;
  same_specific_place: boolean | null;
  in_person_eligibility: "eligible" | "ineligible" | "unknown";
  eligibility_reason: string;
  applicable_rule_ids: Array<string>;
};

export type InitialInteractionEvidence = {
  status: string;
  source?: string | null;
  version?: string | null;
  source_date?: string | null;
  evidence_id?: string | null;
  licence?: string | null;
  uncertainty?: number | null;
};

export type InitialInteractionFactor = {
  kind: "base" | "relationship" | "co_location" | "place" | "time" | "context";
  condition: string;
  factor_id: string;
  label: string;
  value: number;
  provenance: InitialInteractionEvidence;
};

export type InitialInteractionRule = {
  rule_id: string;
  source_action: string;
  interaction_type: string;
  channel: string;
  interaction_tree_id?: string | null;
  formula: string;
  factors: Array<InitialInteractionFactor>;
};

export type InitialPopulationEvidenceSummary = {
  total_agents?: number;
  country_agent_counts: {
  [key: string]: number;
};
  region_agent_counts: {
  [key: string]: number;
};
  fields: {
  [key: string]: InitialAgentFieldCoverage;
};
  comparisons?: Array<InitialAgentPlaceComparison>;
  deviations?: Array<InitialAgentDeviation>;
  interactions?: InitialAgentGlobalInteractionSummary;
};

export type InitialPopulationMaterialization = {
  population: PopulationTable;
  provenance: {
  [key: string]: AgentInitialStateProvenance;
};
  validation: InitialPopulationValidation;
  input_hash: string;
};

export type InitialPopulationRequest = {
  population_id: string;
  version: string;
  seed: number;
  target_agents: number;
  household_templates: Array<HouseholdSeed>;
  evidence: Array<EvidenceReference>;
};

export type InitialPopulationStatus = {
  configured: boolean;
  population_id?: string | null;
  version?: string | null;
  seed?: number | null;
  agent_count?: number;
  input_hash?: string | null;
  agent_type_mix?: {
  [key: string]: number;
};
};

export type InitialPopulationValidation = {
  valid: boolean;
  issues: Array<InitialPopulationValidationIssue>;
};

export type InitialPopulationValidationIssue = {
  code: string;
  path: string;
  message: string;
};

export type InputBinding = {
  target_input: string;
  source_kind: "input" | "output" | "external";
  source_id: string;
};

export type InteractionBreakdown = {
  by_relationship: {
  [key: string]: number;
};
  by_channel: {
  [key: string]: number;
};
  by_place: {
  [key: string]: number;
};
  by_counterparty: {
  [key: string]: number;
};
};

export type InteractionEventDetail = {
  event_id: string;
  tick: number;
  hour: number;
  weekday: number;
  rule_id: string;
  interaction_type: string;
  channel: "in_person" | "phone_message" | "online";
  initiator_id: string;
  target_id: string;
  place_id: string;
  relationship_type: string;
  probability: number;
  effect_count: number;
  relationship_weight: number;
  trust: number;
  similarity: number;
  factors: Array<EvaluatedInteractionFactor>;
  state_deltas: Array<AppliedStateDelta>;
  relationship_deltas: Array<AppliedRelationshipDelta>;
  interaction_tree?: InteractionTreeTrace | null;
};

export type InteractionFacets = {
  agents: Array<string>;
  interaction_types: Array<string>;
  channels: Array<"in_person" | "phone_message" | "online">;
  relationships: Array<string>;
  places: Array<string>;
};

export type InteractionFactor = {
  id: string;
  label: string;
  value: number;
  provenance: InteractionFactorProvenance;
};

export type InteractionFactorProvenance = {
  source: string;
  version: string;
  source_date?: string | null;
  evidence_id?: string | null;
  licence?: string | null;
  status: "measured_joint" | "fitted_model" | "default_estimated" | "approved_estimate" | "unknown" | "label_only" | "ambiguous" | "legacy";
  uncertainty: number;
  user_approved?: boolean;
};

export type InteractionListItem = {
  event_id: string;
  tick: number;
  hour: number;
  weekday: number;
  rule_id: string;
  interaction_type: string;
  channel: "in_person" | "phone_message" | "online";
  initiator_id: string;
  target_id: string;
  place_id: string;
  relationship_type: string;
  probability: number;
  effect_count: number;
};

export type InteractionPage = {
  items: Array<InteractionListItem>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  facets: InteractionFacets;
  breakdown: InteractionBreakdown;
};

export type InteractionParticipant = {
  agent_id: string;
  place_id: string;
  traits?: {
  [key: string]: number | string | boolean;
};
  states?: {
  [key: string]: number;
};
  routines?: Array<string>;
};

export type InteractionPathStep = {
  tree_id?: string | null;
  node_id: string;
  transition_id: string;
  outcome: string;
  probability: number;
  draw: number;
  evidence: InteractionTransitionEvidence;
  factors?: Array<EvaluatedInteractionProbabilityFactor>;
  outgoing_probabilities?: Array<EvaluatedInteractionTransition>;
};

export type InteractionPlaceContext = {
  id: string;
  kind: string;
  states?: {
  [key: string]: number;
};
};

export type InteractionProbabilityFactor = {
  id: string;
  label: string;
  cases: Array<InteractionProbabilityFactorCase>;
  evidence: InteractionTransitionEvidence;
};

export type InteractionProbabilityFactorCase = {
  id: string;
  conditions: Array<InteractionTreeCondition>;
  multiplier: number;
};

export type InteractionProgramDefinition = {
  version: string;
  status: "draft" | "confirmed";
  relationship_evidence?: Array<RelationshipKindEvidence>;
  rules?: Array<InteractionRule>;
};

export type InteractionProgramValidation = {
  valid: boolean;
  issues: Array<InteractionProgramValidationIssue>;
};

export type InteractionProgramValidationIssue = {
  path: string;
  message: string;
};

export type InteractionProgramView = {
  configured: boolean;
  program: InteractionProgramDefinition;
};

export type InteractionQuery = {
  search?: string;
  agent_id?: string | null;
  direction?: "either" | "initiator" | "target";
  interaction_type?: string | null;
  channel?: "in_person" | "phone_message" | "online" | null;
  relationship_type?: string | null;
  place_id?: string | null;
  page?: number;
  page_size?: number;
};

export type InteractionRule = {
  id: string;
  source_action: string;
  interaction_type: string;
  channel: "in_person" | "phone_message" | "online";
  max_targets_per_initiator: number;
  allowed_relationships?: Array<string>;
  allowed_place_kinds?: Array<string>;
  base_factor: InteractionFactor;
  relationship_factors: {
  [key: string]: InteractionFactor;
};
  colocation_factors: {
  [key: string]: InteractionFactor;
};
  place_factors: {
  [key: string]: InteractionFactor;
};
  time_factors: Array<TimeFactorWindow>;
  context_factors?: Array<InteractionFactor>;
  unrelated_relationship?: RelationshipProfile | null;
  agent_effects?: Array<petraterrium__simulation__interactions__AgentStateEffect>;
  relationship_effects?: Array<petraterrium__simulation__interactions__RelationshipStateEffect>;
  interaction_tree_id?: string | null;
  interaction_tree_context?: {
  [key: string]: string | number | boolean;
};
};

export type InteractionTimeContext = {
  weekday: number;
  hour: number;
};

export type InteractionTransitionEvidence = {
  source: string;
  version: string;
  status: "measured_joint" | "fitted_model" | "approved_estimate";
  uncertainty: number;
  source_date?: string | null;
  evidence_id?: string | null;
};

export type InteractionTreeChange = {
  recipient: "actor" | "target" | "relationship";
  field: string;
  before: number | string | boolean;
  after: number | string | boolean;
};

export type InteractionTreeCondition = {
  input: string;
  operator: "eq" | "ne" | "gt" | "gte" | "lt" | "lte";
  value: number | string | boolean;
};

export type InteractionTreeContext = {
  actor: InteractionParticipant;
  target: InteractionParticipant;
  relationship: DirectedRelationship;
  place: InteractionPlaceContext;
  time: InteractionTimeContext;
  channel: string;
  attributes?: {
  [key: string]: number | string | boolean;
};
};

export type InteractionTreeDefinition = {
  id: string;
  name: string;
  version: string;
  entry_node: string;
  allowed_channels: Array<string>;
  co_location_policy: "required" | "remote_allowed";
  nodes: Array<InteractionTreeNode>;
  transitions: Array<InteractionTreeTransition>;
};

export type InteractionTreeNode = {
  id: string;
  label: string;
  terminal: boolean;
  target_tree_id?: string | null;
};

export type InteractionTreeReceipt = {
  actor_id: string;
  target_id: string;
  relationship_direction: string;
  place_id: string;
  channel: string;
  weekday: number;
  hour: number;
};

export type InteractionTreeRequest = {
  seed: number;
  tick: number;
  tree: InteractionTreeDefinition;
  trees?: {
  [key: string]: InteractionTreeDefinition;
};
  context: InteractionTreeContext;
};

export type InteractionTreeResult = {
  tree_id: string;
  tree_version: string;
  seed: number;
  tick: number;
  outcome_node: string;
  outcome: string;
  path: Array<InteractionPathStep>;
  receipt: InteractionTreeReceipt;
  actor_before: InteractionParticipant;
  actor_after: InteractionParticipant;
  target_before: InteractionParticipant;
  target_after: InteractionParticipant;
  relationship_before: DirectedRelationship;
  relationship_after: DirectedRelationship;
  changes: Array<InteractionTreeChange>;
};

export type InteractionTreeSummary = {
  id: string;
  name: string;
  version: string;
  node_count: number;
  transition_count: number;
  co_location_policy: "required" | "remote_allowed";
  allowed_channels: Array<string>;
};

export type InteractionTreeTrace = {
  tree_id: string;
  tree_version: string;
  outcome_node: string;
  outcome: string;
  path: Array<InteractionPathStep>;
};

export type InteractionTreeTransition = {
  id: string;
  from_node: string;
  to_node: string;
  outcome: string;
  probability: number;
  probability_factors?: Array<InteractionProbabilityFactor>;
  evidence: InteractionTransitionEvidence;
  conditions?: Array<InteractionTreeCondition>;
  effects?: Array<unknown>;
};

export type JointDataProof = {
  feature_id: string;
  outcomes: Array<string>;
  population: string;
  provenance: Evidence;
};

export type LeaderActionDefinition = {
  id: string;
  parameter_effects: {
  [key: string]: number;
};
  evidence: Evidence;
};

export type LegacyMarginalField = {
  field: "ideology";
  status: "legacy_only";
  value: {
  [key: string]: number;
} | number;
  unit: string;
  provenance: Provenance;
  predictive: false;
};

export type LocationAgentDetail = {
  agent_id: string;
  current_location: LocationPlaceSummary;
  ancestry: Array<LocationPlaceSummary>;
  history: Array<LocationHistoryRecord>;
  co_located_agents: Array<LocationAgentSummary>;
  elsewhere_agents: Array<LocationAgentSummary>;
  effective_place_state: {
  [key: string]: number;
};
};

export type LocationAgentSummary = {
  agent_id: string;
  current_location_id: string;
};

export type LocationDecisionTreeAvailability = {
  tree_id: string;
  tree_name: string;
  available: boolean;
  required_place_kinds: Array<string>;
  reason?: string | null;
};

export type LocationEvidence = {
  source_title: string;
  source_version: string;
  source_date: string;
  licence: string;
  evidence_id: string;
  status: "measured" | "user_defined";
  uncertainty: number;
};

export type LocationHistoryRecord = {
  tick: number;
  agent_id: string;
  from_location_id: string;
  to_location_id: string;
  route_location_ids: Array<string>;
};

export type LocationLivePlaceState = {
  runtime_place_index: number;
  runtime_place_id: string;
  location_id: string;
  kind: string;
  accepts_arrivals: boolean;
  allows_in_person: boolean;
  capacity?: number | null;
  occupancy: number;
  crowd_density?: number | null;
  state: {
  [key: string]: number;
};
};

export type LocationPlaceSummary = {
  id: string;
  name: string;
  level: "country" | "region" | "state" | "city" | "district" | "building" | "room";
  parent_id: string | null;
  child_ids: Array<string>;
  current_agent_count: number;
  accepts_arrivals: boolean;
  allows_in_person: boolean;
  capacity: number | null;
  state: {
  [key: string]: number;
};
  state_source?: "rust_numeric_core" | "location_registry";
  runtime_place_id?: string | null;
  runtime_place_kind?: string | null;
  evidence: LocationEvidence | null;
  decision_trees: Array<LocationDecisionTreeAvailability>;
};

export type LocationRunSnapshot = {
  run_id: string;
  tick: number;
  root_location_ids: Array<string>;
  places: Array<LocationPlaceSummary>;
  agents: Array<LocationAgentSummary>;
};

export type LocationTransitionStep = {
  tick: number;
  kind: string;
  source: string;
  schedule?: string | null;
  from_location: string;
  to_location: string;
  destination_location: string;
  provenance: {
  [key: string]: unknown;
};
};

export type MappingAudit = {
  provider: string;
  model: string;
  prompt_version: string;
  estimated_cost_usd: number | null;
  input_tokens: number;
  output_tokens: number;
  message: string;
};

export type MappingConfirmation = {
  mappings: Array<ColumnMapping>;
  confirmed: boolean;
};

export type MarginalField = {
  field: "age_sex" | "income" | "education" | "specialization" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  status: "present" | "inherited" | "imputed" | "estimated" | "missing";
  value: {
  [key: string]: number;
} | number | null;
  unit: string | null;
  provenance: Provenance | null;
  research_trace: {
  [key: string]: unknown;
} | null;
  suggested_source: string;
  source_url: string;
};

export type MarkovModule = {
  id: string;
  version: string;
  name: string;
  entry_state: string;
  exit_states: Array<string>;
  inputs?: Array<ModuleInput>;
  outputs?: Array<ModuleOutput>;
  states: Array<ModuleState>;
  transitions?: Array<ModuleTransition>;
};

export type MarkovProgram = {
  id: string;
  version: string;
  entry_module: string;
  modules: Array<MarkovModule>;
  links?: Array<ModuleLink>;
  terminal_exits: Array<ProgramExit>;
  external_inputs?: Array<ModuleInput>;
};

export type MediaRule = {
  id: string;
  interest_weight: number;
  social_weight: number;
  recency_weight: number;
  trust_weight: number;
};

export type MetricPeak = {
  day: number;
  value: number;
};

export type Metrics = {
  totals: Totals;
  peak_day: number;
  peak_infected: number;
  days_recorded: number;
  state_totals: {
  [key: string]: {
  [key: string]: number;
};
};
  metric_peaks: {
  [key: string]: MetricPeak;
};
  stories_generated: number;
};

export type MissingFallback = {
  field: string;
  status: "inherited" | "imputed" | "missing" | "unknown" | "label_only" | "literature_estimate" | "hint_only";
  fallback: string;
  impact: string;
};

export type MobilityEvidence = {
  status: "measured" | "user_defined" | "unknown" | "imputed";
  source_title?: string | null;
  source_version?: string | null;
  source_date?: string | null;
  licence?: string | null;
  evidence_id?: string | null;
  uncertainty?: number | null;
  note?: string | null;
};

export type MobilityRegistryDefinition = {
  version: string;
  status: "draft" | "confirmed";
  place_profiles: Array<PlaceProfileDefinition>;
  routes: Array<TravelRouteDefinition>;
};

export type MobilityRegistryView = {
  configured: boolean;
  registry: MobilityRegistryDefinition | null;
};

export type ModuleInput = {
  id: string;
  kind: "agent_trait" | "place" | "time" | "context" | "persisted_state" | "place_state" | "media_state";
  value_type: "categorical" | "continuous" | "boolean" | "identifier";
  feature_id?: string | null;
  required?: boolean;
};

export type ModuleLink = {
  from_module: string;
  exit_state: string;
  to_module: string;
  bindings?: Array<InputBinding>;
};

export type ModuleOutput = {
  id: string;
  kind: "location" | "health" | "friends" | "persisted_state" | "place_state" | "media_state" | "event";
  value_type: "categorical" | "continuous" | "boolean" | "identifier";
};

export type ModuleState = {
  id: string;
  label?: string | null;
  effects?: Array<string>;
};

export type ModuleTransition = {
  id: string;
  from_state: string;
  to_state: string;
  condition?: TransitionCondition | null;
  probability: ProbabilityQuery;
};

export type NetworkDefinition = {
  id: string;
  max_depth: number;
  friend_weight?: number;
  stranger_weight?: number;
  enemy_weight?: number;
};

export type NoSourceAttachment = {
  kind?: "none";
  label?: "no source attached \u2014 estimated / unknown";
  reason: string;
};

export type OutgoingProbabilityTotal = {
  node_id: string;
  known_total: number;
  unknown_count: number;
  complete: boolean;
  sums_to_one: boolean;
};

export type OutputSpec = {
  snapshots?: boolean;
  metrics?: boolean;
  stories?: boolean;
  agent_logs?: "none" | "tiered" | "all";
  backtest_comparisons?: boolean;
  ensemble_updates?: boolean;
};

export type ParameterDefinition = {
  id: string;
  value?: number | null;
  unit: string;
  provenance: Evidence;
};

export type Parameters = {
  transmission: number;
  progression: number;
  recovery: number;
  mixing: number;
  initial_infected: number;
};

export type PlaceDetail = {
  place_id: string;
  run_id: string;
  status: string;
  metrics: {
  [key: string]: number;
};
  events: Array<string>;
  arc: Array<string>;
};

export type PlaceHierarchy = {
  city?: string | null;
  country: string;
  subregion?: string | null;
  region: string;
};

export type PlaceLevel = "global" | "region" | "subregion" | "country" | "city";

export type PlaceProfileDefinition = {
  id: string;
  place_id?: string | null;
  place_kind: string;
  accepts_arrivals: boolean;
  allows_in_person: boolean;
  capacity: number | null;
  state: {
  [key: string]: number;
};
  available_decision_tree_ids: Array<string>;
  evidence: MobilityEvidence;
};

export type PlaceSelector = {
  level: PlaceLevel;
  place: string;
  label: string;
};

export type PlaceSnapshot = {
  country: string;
  latitude: number | null;
  longitude: number | null;
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
  states: {
  [key: string]: {
  [key: string]: number;
};
};
  metrics: {
  [key: string]: number;
};
};

export type PopulationReference = {
  id: string;
  version: string;
  size: number;
  places: Array<string>;
  place_populations?: {
  [key: string]: number;
};
  place_coordinates?: {
  [key: string]: [number, number];
};
  place_hierarchy?: {
  [key: string]: PlaceHierarchy;
};
  initial_state_overrides?: {
  [key: string]: {
  [key: string]: {
  [key: string]: number;
};
};
};
};

export type PopulationTable = {
  population_id: string;
  version: string;
  seed: number;
  agents: Array<AgentRecord>;
};

export type ProbabilityFactor = {
  id: string;
  name: string;
  input_kind: "trait" | "place" | "time" | "context";
  input_key: string;
  feature_id?: string | null;
};

export type ProbabilityQuery = {
  outcome_id: string;
  conditioning_id: string;
  place_input: string;
  time_input: string;
  predictor_inputs?: Array<string>;
  allowed_evidence?: Array<"measured_choice" | "measured_joint" | "fitted_choice">;
};

export type ProbabilitySpec = {
  base: number;
  mode?: "probability" | "hazard";
  time_unit: "event" | "hour" | "day" | "week" | "year";
  parameter?: string | null;
  source_state?: string | null;
  mixing_parameter?: string | null;
  opportunity?: string | null;
  modifiers?: {
  [key: string]: number;
};
};

export type ProgramExit = {
  module_id: string;
  state_id: string;
};

export type Promotion = {
  confirmed: boolean;
  redistribution_confirmed: boolean;
};

export type ProposalAudit = {
  provider: string;
  model: string;
  prompt_version: string;
  generated_at?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost_usd?: number | null;
  message: string;
};

export type Provenance = {
  import_id: string;
  source: string;
  source_date: string;
  published_date: string;
  version: string;
  scope: string;
  uploader: string;
};

export type RegistrySource = {
  source_id: string;
  source: string;
  scope_order: number;
  level: "region" | "country" | "city";
  access_status: "imported" | "imported_aggregate" | "unavailable" | "available_remote";
  source_url: string;
  version: string;
  source_date: string;
  license: string;
  mapping: {
  [key: string]: unknown;
};
  coverage: {
  [key: string]: unknown;
};
  restriction_reason: string;
  fallback: string;
  required_action: string;
  files: Array<{
  [key: string]: unknown;
}>;
};

export type Relationship = {
  target_id: string;
  kind: "family" | "household" | "friend" | "enemy" | "workplace" | "school";
  weight: number;
  trust?: number | null;
  similarity?: number | null;
  evidence_id?: string | null;
  evidence_status?: "measured_joint" | "fitted_model" | "default_estimated" | "approved_estimate" | "user_defined" | "imputed" | "unknown" | null;
};

export type RelationshipKindEffect = {
  kind?: "relationship_kind";
  relationship_type: string;
};

export type RelationshipKindEvidence = {
  kind: string;
  weight: number;
  trust: number;
  similarity: number;
  provenance: InteractionFactorProvenance;
};

export type RelationshipProfile = {
  kind: string;
  weight: number;
  trust: number;
  similarity: number;
};

export type ResearchCitation = {
  kind: "article" | "research_paper";
  imported_source_id: string;
  title: string;
  source: string;
  publication_date: string;
  population_studied: string;
  link_or_reference: string;
  supports_decision_ids: Array<string>;
  supports_factor_ids: Array<string>;
};

export type ResolvedAgentRoutines = {
  agent_type_id: string;
  agent_type_name: string;
  routines: Array<ResolvedRoutine>;
};

export type ResolvedAgentType = {
  id: string;
  name: string;
  description?: string | null;
  parent_ids: Array<string>;
  traits: Array<ResolvedAgentTypeMember>;
  routines: Array<ResolvedAgentTypeMember>;
  decisions: Array<ResolvedAgentTypeMember>;
};

export type ResolvedAgentTypeMember = {
  member: AgentTypeMember;
  source_type_id: string;
  inherited: boolean;
  explicit_override: boolean;
  overridden_source_type_ids?: Array<string>;
};

export type ResolvedAgentTypeRegistry = {
  types: Array<ResolvedAgentType>;
};

export type ResolvedRoutine = {
  routine: RoutineDefinition;
  source_type_id: string;
  inherited: boolean;
  explicit_override: boolean;
  overridden_source_type_ids?: Array<string>;
};

export type ResolvedRoutineRegistry = {
  agent_types: Array<ResolvedAgentRoutines>;
};

export type RoleDefinition = {
  id: string;
  actions?: Array<string>;
};

export type RoutineDefinition = {
  id: string;
  name: string;
  agent_type_id: string;
  description?: string | null;
  evidence: RoutineEvidence;
  steps: Array<RoutineStep>;
};

export type RoutineEvidence = {
  status: "measured" | "user_defined" | "default_estimated" | "illustrative" | "unknown";
  source_title?: string | null;
  source_date?: string | null;
  source_uri?: string | null;
  note?: string | null;
};

export type RoutineLink = {
  routine_id: string;
  name: string;
  agent_type: string;
  inherited_from?: string | null;
};

export type RoutineProposalDraft = {
  id: string;
  name: string;
  agent_type_id: string;
  description?: string | null;
  source_feature_ids?: Array<string>;
  evidence: RoutineEvidence;
  steps: Array<RoutineStepProposal>;
};

export type RoutineRegistryDefinition = {
  agent_types: Array<AgentTypeDefinition>;
  routines?: Array<RoutineDefinition>;
};

export type RoutineRegistryStatus = {
  configured: boolean;
  agent_type_count?: number;
  routine_count?: number;
  valid?: boolean | null;
  issue_count?: number;
};

export type RoutineRegistryView = {
  status: RoutineRegistryStatus;
  registry: RoutineRegistryDefinition | null;
  validation: RoutineValidationResult | null;
  resolved: ResolvedRoutineRegistry | null;
};

export type RoutineSchedule = {
  days: Array<"monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday">;
  start_time: string;
  end_time: string;
  ends_next_day?: boolean;
  place_ids: Array<string>;
  role_ids: Array<string>;
};

export type RoutineStep = {
  id: string;
  name: string;
  activity: string;
  schedule: RoutineSchedule;
  decision_tree_module_id?: string | null;
};

export type RoutineStepProposal = {
  id: string;
  name: string;
  activity: string;
  decision_tree_module_id?: string | null;
  schedule?: RoutineSchedule | null;
};

export type RoutineValidationIssue = {
  code: string;
  path: string;
  message: string;
};

export type RoutineValidationResult = {
  valid: boolean;
  issues: Array<RoutineValidationIssue>;
};

export type RuleCondition = {
  attribute: string;
  operator: "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "in";
  value: string | number | boolean | Array<string>;
};

export type RuleDefinition = {
  id: string;
  conditions?: Array<RuleCondition>;
  traversal?: GraphTraversal | null;
  action?: string | null;
  effects?: {
  [key: string]: number;
};
  max_applications?: number;
};

export type RunAgentDetail = {
  agent_id: string;
  final_module: string;
  final_state: string;
  final_location: string;
  initial_module: string;
  initial_state: string;
  initial_location: string;
  traits: {
  [key: string]: string | number;
};
  memory: {
  [key: string]: number;
};
  initial_profile?: {
  [key: string]: unknown;
};
  timeline: Array<AgentTimelinePoint>;
};

export type RunAgentPage = {
  items: Array<RunAgentSummary>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type RunAgentSummary = {
  agent_id: string;
  final_module: string;
  final_state: string;
  final_location: string;
};

export type RunCoefficientReceipt = {
  action_id: string;
  edge_id: string;
  place: CoefficientPlace;
  source_place?: CoefficientPlace | null;
  resolution_status?: "direct" | "inherited" | "imputed";
  evidence_state: "measured" | "fitted" | "default_estimated" | "blocked";
  value: number;
  interval: CoefficientInterval;
  coefficient_set_id: string;
  default_coefficient_set_id: string;
  default_value: number;
  fitted_delta?: number | null;
  promotion_id?: string | null;
  source_label: string;
  source_version: string;
  source_id?: string | null;
  default_reason?: string | null;
  held_out?: HeldOutValidationReceipt | null;
  affected_agents?: number;
};

export type RunComplete = {
  run_id: string;
  status: "done";
  metrics: Metrics;
};

export type RunConfig = {
  scenario: string;
  countries: Array<string>;
  start_day: number;
  end_day: number;
  seed: number;
  parameters: Parameters;
  dsl: DSLConfig | null;
  population: PopulationReference | null;
  tick: TickConfig | null;
  outputs: OutputSpec | null;
  evidence_table_version: string;
};

export type RunCreated = {
  run_id: string;
  config_hash: string;
  config: RunConfig;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  last_sequence: number;
  outputs: OutputSpec;
  evidence_table_version: string;
  population_version: string;
  missing_fallbacks: Array<MissingFallback>;
  metrics: Metrics | null;
  error: RunError | null;
  snapshots: Array<DailySnapshot>;
  ensemble_updates: Array<EnsembleUpdate>;
  stories: Array<StoryRecord>;
  backtests: Array<BacktestComparison>;
  cached: boolean;
};

export type RunDetail = {
  run_id: string;
  config_hash: string;
  config: RunConfig;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  last_sequence: number;
  outputs: OutputSpec;
  evidence_table_version: string;
  population_version: string;
  missing_fallbacks: Array<MissingFallback>;
  metrics: Metrics | null;
  error: RunError | null;
  snapshots: Array<DailySnapshot>;
  ensemble_updates: Array<EnsembleUpdate>;
  stories: Array<StoryRecord>;
  backtests: Array<BacktestComparison>;
};

export type RunError = {
  code: string;
  message: string;
};

export type RunEvent = {
  day: number;
  date: string;
  tick: number;
  kind: "action" | "routine" | "transition" | "location" | "availability" | "synchronization" | "interaction";
  label: string;
  agent_ids: Array<string>;
  location?: string | null;
  details?: {
  [key: string]: unknown;
};
};

export type RunEventPage = {
  items: Array<RunEvent>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type RunEvidenceSummary = {
  fitted_count: number;
  measured_count?: number;
  default_estimated_count: number;
  blocked_count: number;
  by_action_place: Array<ActionPlaceEvidenceSummary>;
};

export type RunEvidenceWarning = {
  code?: "default_estimated_coefficients";
  action_id: string;
  place: CoefficientPlace;
  coefficient_ids: Array<string>;
  message: string;
};

export type RunFailed = {
  run_id: string;
  status: "failed";
  error: RunError;
};

export type RunList = {
  runs: Array<RunSummary>;
};

export type RunSummary = {
  run_id: string;
  config_hash: string;
  config: RunConfig;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  last_sequence: number;
  outputs: OutputSpec;
  evidence_table_version: string;
  population_version: string;
  missing_fallbacks: Array<MissingFallback>;
  metrics: Metrics | null;
  error: RunError | null;
};

export type ScenarioDefinition = {
  id: string;
  systems: Array<string>;
  actions?: Array<string>;
  events?: Array<string>;
};

export type SimulationPlaceScope = {
  level: "global" | "region" | "country" | "city";
  identifier?: string | null;
};

export type SimulationResult = {
  source?: "rust";
  protocol_version: string;
  engine_version: string;
  data_version: string;
  program_version: string;
  default_dsl_version?: string | null;
  default_dsl_hash?: string | null;
  input_hash: string;
  output_hash: string;
  snapshots: Array<SnapshotSummary>;
};

export type SimulationRunConfig = {
  population_size: number;
  seed: number;
  days: number;
  tick_interval_hours: number;
  start_date: string;
  place_scope: SimulationPlaceScope;
  agent_type_mix?: {
  [key: string]: number;
};
};

export type SimulationRunView = {
  run_id: string;
  config: SimulationRunConfig;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  progress: number;
  completed_ticks: number;
  total_ticks: number;
  result?: SimulationResult | null;
  error?: string | null;
  default_dsl_version?: string | null;
  default_dsl_hash?: string | null;
  evidence_summary?: RunEvidenceSummary;
  evidence_warnings?: Array<RunEvidenceWarning>;
  global_demo_summary?: InitialPopulationEvidenceSummary | null;
  aggregate_record_count?: number;
  aggregate_statistics_version?: string | null;
  routine_agent_action_logging?: false;
};

export type SliderSpec = {
  parameter: string;
  value: number;
  unit: string;
  evidence_status: "present" | "inherited" | "imputed" | "missing" | "unknown" | "label_only" | "literature_estimate" | "hint_only";
};

export type SnapshotSummary = {
  day: number;
  date: string;
  tick: number;
  elapsed_hours: number;
  state_counts: {
  [key: string]: number;
};
  place_counts: {
  [key: string]: number;
};
  live_places?: Array<LocationLivePlaceState>;
  transition_counts: Array<{
  [key: string]: unknown;
}>;
  interaction_outcome_counts?: {
  [key: string]: number;
};
  event_count: number;
  interaction_count: number;
};

export type SourceCatalog = {
  sources: Array<AtlasSource>;
  llm_available: boolean;
  registry_sources: Array<RegistrySource>;
};

export type SourceFetch = {
  url: string;
  metadata: ImportMetadata;
  access_confirmed: boolean;
};

export type StateDefinition = {
  id: string;
  values: Array<string>;
  initial: Distribution;
};

export type StateEvidence = {
  status: "measured_joint" | "measured_marginal" | "inherited" | "imputed" | "literature_support" | "default_estimated" | "unknown" | "simulated";
  source: string;
  source_version: string;
  source_date?: string | null;
  url?: string | null;
  place: string;
  population: string;
  language?: string | null;
  original_title?: string | null;
  english_title?: string | null;
  search_source?: string | null;
  uncertainty: number;
  default_reason?: string | null;
};

export type StoryDetail = {
  story: StoryRecord;
  place_metrics: {
  [key: string]: number;
};
  agents: Array<AgentPoint>;
  arc: Array<StoryRecord>;
};

export type StoryList = {
  stories: Array<StoryRecord>;
};

export type StoryRecord = {
  story_id: string;
  event_id: string;
  place: string;
  day: number;
  headline: string;
  body: string;
  metrics: {
  [key: string]: number;
};
  template: boolean;
  arc_id: string;
};

export type SystemDefinition = {
  id: string;
  state: string;
  transitions: Array<TransitionDefinition>;
};

export type TickConfig = {
  tick_hours?: number;
  total_ticks?: number;
  snapshot_every_hours?: number;
  story_every_days?: number;
  update_order?: "double_buffered" | "seeded_random";
};

export type TimeFactorWindow = {
  weekdays: Array<number>;
  start_hour: number;
  end_hour: number;
  factor: InteractionFactor;
};

export type Totals = {
  population: number;
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
};

export type TransitionCondition = {
  mode: "always" | "all" | "any";
  clauses?: Array<ConditionClause>;
};

export type TransitionDefinition = {
  id: string;
  from_state: string;
  to_state: string;
  probability: ProbabilitySpec;
};

export type TransitionEvidence = {
  id: string;
  kind: "measured_joint" | "fitted_choice";
  outcome_id: string;
  conditioning_id: string;
  place: string;
  time_unit: "event" | "hour" | "day" | "friday" | "week" | "year";
  predictor_values?: {
  [key: string]: string | number | number | boolean;
};
  condition_values?: {
  [key: string]: string | number | number | boolean;
};
  probability: number;
  ci_low: number;
  ci_high: number;
  sample_size: number;
  held_out_sample_size?: number | null;
  population: string;
  provenance: Evidence;
};

export type TravelRouteDefinition = {
  id: string;
  from_place_kind: string;
  to_place_kind: string;
  transit_place_kind: string;
  duration_minutes: number;
  evidence: MobilityEvidence;
};

export type TreeModuleIssue = {
  code: string;
  path: string;
  message: string;
};

export type TreeRegistryValidation = {
  valid: boolean;
  issues: Array<TreeModuleIssue>;
  broken_references: Array<BrokenModuleReference>;
  reference_cycles: Array<Array<string>>;
  unreachable_nodes: {
  [key: string]: Array<string>;
};
};

export type UniversalFeatureOverview = {
  registry: FeatureRegistry;
  resolutions: Array<FeatureResolutionRecord>;
};

export type ValidationReport = {
  import_id: string;
  valid: boolean;
  total_rows: number;
  observations: number;
  issues: Array<petraterrium__atlas__contracts__ValidationIssue>;
  missingness: {
  [key: string]: number;
};
  mapping_hash: string;
};

export type petraterrium__atlas__contracts__ValidationIssue = {
  row: number;
  field: string;
  message: string;
};

export type petraterrium__contracts__DecisionPathStep = {
  agent_id: string;
  action_id: string;
  previous_action_id: string | null;
  chain_id: string | null;
  chain_step_index: number;
  tick: number;
  place: string;
  target_agent_id: string | null;
};

export type petraterrium__dsl__models__ValidationIssue = {
  path: string;
  message: string;
};

export type petraterrium__simulation__interaction_trees__AgentStateEffect = {
  kind?: "agent_state";
  participant: "actor" | "target";
  field: string;
  operation: "set" | "add";
  value: number;
  minimum?: number | null;
  maximum?: number | null;
  scale_by?: Array<string>;
};

export type petraterrium__simulation__interaction_trees__RelationshipStateEffect = {
  kind?: "relationship_state";
  field: string;
  operation: "set" | "add";
  value: number;
  minimum?: number | null;
  maximum?: number | null;
  scale_by?: Array<string>;
};

export type petraterrium__simulation__interactions__AgentStateEffect = {
  recipient: "initiator" | "target";
  state: string;
  delta: number;
  minimum: number;
  maximum: number;
  scale_by?: Array<"relationship_weight" | "trust" | "similarity">;
};

export type petraterrium__simulation__interactions__RelationshipStateEffect = {
  direction: "initiator_to_target" | "target_to_initiator";
  field: "weight" | "trust" | "similarity";
  delta: number;
  minimum: number;
  maximum: number;
};

export type petraterrium__simulation__run_service__DecisionPathStep = {
  tick: number;
  module: string;
  transition: string;
  from_state: string;
  to_state: string;
  probability: number;
  provenance: {
  [key: string]: unknown;
};
};
