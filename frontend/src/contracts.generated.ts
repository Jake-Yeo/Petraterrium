export type Catalog = {
  countries: Array<Country>;
  engine_version: string;
  data_version: string;
  contract_version: string;
  notice: string;
};

export type Country = {
  country: "ITA" | "FRA" | "DEU" | "ESP";
  name: string;
  population: number;
  latitude: number;
  longitude: number;
  fake: true;
};

export type DailySnapshot = {
  run_id: string;
  day: number;
  places: Array<PlaceSnapshot>;
  seed: number;
  engine_version: string;
  data_version: string;
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

export type Totals = {
  population: number;
  susceptible: number;
  exposed: number;
  infected: number;
  recovered: number;
};
