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

export type CityDetail = {
  city: AtlasCity;
  missing_fields: Array<"age_sex" | "income" | "education" | "ideology" | "household_size">;
  direct_observation_gaps: Array<"age_sex" | "income" | "education" | "ideology" | "household_size">;
  history: Array<Provenance>;
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
  country: "ITA" | "FRA" | "DEU" | "ESP";
  name: string;
  population: number;
  latitude: number;
  longitude: number;
  fake: true;
};

export type CoverageCounts = {
  full: number;
  partial: number;
  none: number;
};

export type DailySnapshot = {
  run_id: string;
  day: number;
  places: Array<PlaceSnapshot>;
  seed: number;
  engine_version: string;
  data_version: string;
};

export type DataGap = {
  geonameid: number;
  city: string;
  country_code: string;
  population: number;
  field: "age_sex" | "income" | "education" | "ideology" | "household_size";
  status: "present" | "inherited" | "imputed" | "missing";
  suggested_source: string;
};

export type FieldCoverage = {
  field: "age_sex" | "income" | "education" | "ideology" | "household_size";
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
  field: "age_sex" | "income" | "education" | "ideology" | "household_size";
  status: "present" | "inherited" | "imputed" | "missing";
  value: {
  [key: string]: number;
} | number | null;
  unit: string | null;
  provenance: Provenance | null;
  suggested_source: string;
  source_url: string;
};

export type Metrics = {
  totals: Totals;
  peak_day: number;
  peak_infected: number;
  days_recorded: number;
};

export type Parameters = {
  transmission: number;
  progression: number;
  recovery: number;
  mixing: number;
  initial_infected: number;
};

export type PlaceSnapshot = {
  country: "ITA" | "FRA" | "DEU" | "ESP";
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
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

export type RunComplete = {
  run_id: string;
  status: "done";
  metrics: Metrics;
};

export type RunConfig = {
  scenario: "pandemic";
  countries: Array<"ITA" | "FRA" | "DEU" | "ESP">;
  start_day: number;
  end_day: number;
  seed: number;
  parameters: Parameters;
};

export type RunCreated = {
  run_id: string;
  config_hash: string;
  config: RunConfig;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  last_sequence: number;
  metrics: Metrics | null;
  error: RunError | null;
  snapshots: Array<DailySnapshot>;
  cached: boolean;
};

export type RunDetail = {
  run_id: string;
  config_hash: string;
  config: RunConfig;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  last_sequence: number;
  metrics: Metrics | null;
  error: RunError | null;
  snapshots: Array<DailySnapshot>;
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
  metrics: Metrics | null;
  error: RunError | null;
};

export type SourceCatalog = {
  sources: Array<AtlasSource>;
  llm_available: boolean;
};

export type SourceFetch = {
  url: string;
  metadata: ImportMetadata;
  access_confirmed: boolean;
};

export type Totals = {
  population: number;
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
};

export type ValidationIssue = {
  row: number;
  field: string;
  message: string;
};

export type ValidationReport = {
  import_id: string;
  valid: boolean;
  total_rows: number;
  observations: number;
  issues: Array<ValidationIssue>;
  missingness: {
  [key: string]: number;
};
  mapping_hash: string;
};
