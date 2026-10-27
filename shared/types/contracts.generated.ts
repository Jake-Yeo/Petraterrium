export type ActionDefinition = {
  id: string;
  system?: string | null;
  probability: ProbabilitySpec;
  duration_minutes: number;
  priority: number;
  meaningful?: boolean;
  interruptible?: boolean;
  protected?: boolean;
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

export type AgentDetail = {
  agent_id: string;
  run_id: string;
  place: string;
  role: string;
  synthetic: true;
  log_tier: "spotlight" | "sampled" | "mass";
  log_scope: string;
  traits: {

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

export type AgentRelationship = {
  target_id: string;
  kind: string;
  weight: number;
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

export type AggregateBenchmark = {
  action_id: string;
  population: number;
  observed_annual_count: number;
  tolerance_factor?: number;
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
  status: "present" | "inherited" | "imputed" | "missing";
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
  rows: Array<ChoiceEvidence>;
};

export type CityDetail = {
  city: AtlasCity;
  missing_fields: Array<"age_sex" | "income" | "education" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size">;
  direct_observation_gaps: Array<"age_sex" | "income" | "education" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size">;
  history: Array<Provenance>;
  legacy_fields: Array<LegacyMarginalField>;
  revision: number;
  simulation_note: string;
};

export type ColumnMapping = {
  column: string;
  target: string | null;
  ambiguous: boolean;
  reason: string;
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
  field: "age_sex" | "income" | "education" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  status: "present" | "inherited" | "imputed" | "missing";
  suggested_source: string;
};

export type DecisionGraph = {
  view: "static" | "run";
  run_id: string | null;
  unfiltered: boolean;
  filters: DecisionGraphFilter;
  nodes: Array<DecisionGraphNode>;
  edges: Array<DecisionGraphEdge>;
  diagnostics: Array<DecisionGraphDiagnostic>;
  path: Array<DecisionPathStep>;
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

export type DecisionPathStep = {
  agent_id: string;
  action_id: string;
  previous_action_id: string | null;
  chain_id: string | null;
  chain_step_index: number;
  tick: number;
  place: string;
  target_agent_id: string | null;
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

export type Distribution = {
  values: {
  [key: string]: number;
};
  provenance: Evidence;
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
  field: "age_sex" | "income" | "education" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  present: number;
  inherited: number;
  imputed: number;
  missing: number;
  direct_percent: number;
  direct_plus_inherited_percent: number;
  direct_population_percent: number;
  direct_plus_inherited_population_percent: number;
  imputed_population_percent: number;
};

export type GraphTraversal = {
  primitive?: "neighbors";
  network: string;
  depth: number;
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
  [key: string]: "present" | "inherited" | "imputed" | "missing";
};
  coverage_by_field: {
  [key: string]: number;
};
  region_override: boolean;
  weight_source: string;
  children_paged: boolean;
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
  field: "age_sex" | "income" | "education" | "ideology_economic" | "ideology_state" | "ideology_cultural" | "household_size";
  status: "present" | "inherited" | "imputed" | "missing";
  value: {
  [key: string]: number;
} | number | null;
  unit: string | null;
  provenance: Provenance | null;
  suggested_source: string;
  source_url: string;
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

export type NetworkDefinition = {
  id: string;
  max_depth: number;
  friend_weight?: number;
  stranger_weight?: number;
  enemy_weight?: number;
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

export type Promotion = {
  confirmed: boolean;
  redistribution_confirmed: boolean;
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
  access_status: "imported" | "unavailable" | "available_remote";
  source_url: string;
  version: string;
  source_date: string;
  license: string;
  mapping: {

};
  coverage: {

};
  restriction_reason: string;
  fallback: string;
  required_action: string;
  files: Array<{

}>;
};

export type RoleDefinition = {
  id: string;
  actions?: Array<string>;
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

export type SliderSpec = {
  parameter: string;
  value: number;
  unit: string;
  evidence_status: "present" | "inherited" | "imputed" | "missing" | "unknown" | "label_only" | "literature_estimate" | "hint_only";
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

export type Totals = {
  population: number;
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
};

export type TransitionDefinition = {
  id: string;
  from_state: string;
  to_state: string;
  probability: ProbabilitySpec;
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

export type petraterrium__dsl__models__ValidationIssue = {
  path: string;
  message: string;
};
