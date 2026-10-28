export type SimulationGlobeStatistic =
  'unemployment_rate' | 'mean_income' | 'population' | 'action_rate';

export type SimulationGlobePlaceLevel = 'region' | 'country' | 'city';

export type SimulationGlobeDetailLevel = 'world' | 'country' | 'city' | 'neighborhood';

export type SimulationGlobeEvidenceStatus = 'measured' | 'estimated';

export interface SimulationGlobeEvidence {
  status: SimulationGlobeEvidenceStatus;
  source: string;
  source_version: string;
  source_date?: string | null;
  uncertainty?: number | null;
}

export interface SimulationGlobeFinanceStatistic {
  total: number | null;
  mean: number | null;
  median: number | null;
  unit: string;
  unit_counts: Record<string, number>;
  comparable: boolean;
  basis: string;
  evidence_status: SimulationGlobeEvidenceStatus;
  source_ids: string[];
  observations: number;
  uncertainty?: number | null;
}

export interface SimulationGlobeEmploymentStatistic {
  agent_count: number;
  employed: number;
  unemployed: number;
  labour_force: number;
  unemployment_rate: number;
  student_share: number;
  caregiver_share: number;
  retired_share: number;
  worker_share: number;
  by_age_group_and_sex?: Record<
    string,
    Omit<SimulationGlobeEmploymentStatistic, 'by_age_group_and_sex'>
  >;
}

export interface SimulationGlobeAggregateEvidence {
  population: SimulationGlobeEvidence;
  employment: SimulationGlobeEvidence;
  agent_type_mix: SimulationGlobeEvidence;
  action_rates: SimulationGlobeEvidence;
}

export interface SimulationGlobeAggregateRecord {
  run_id: string;
  program_version: string;
  day: number;
  date: string;
  tick: number;
  place_level: SimulationGlobePlaceLevel;
  place_id: string;
  place_label: string;
  latitude: number;
  longitude: number;
  parent_place_id?: string | null;
  population: number;
  agent_count: number;
  agent_type_counts: Record<string, number>;
  agent_type_shares: Record<string, number>;
  action_counts: Record<string, number>;
  action_rates_per_1000: Record<string, number>;
  finances: Record<string, SimulationGlobeFinanceStatistic>;
  employment: SimulationGlobeEmploymentStatistic | null;
  evidence: SimulationGlobeAggregateEvidence;
}

export interface SimulationGlobeViewportBounds {
  north: number;
  east: number;
  south: number;
  west: number;
}

export interface SimulationGlobeAgentPoint {
  agent_id: string;
  latitude: number;
  longitude: number;
  state: string;
  place_id: string;
  color?: string;
}

export interface SimulationGlobeAgentViewportRequest {
  run_id: string;
  day: number;
  tick: number;
  detail_level: 'city' | 'neighborhood';
  bounds: SimulationGlobeViewportBounds;
  visible_city_ids: string[];
}

export interface SimulationGlobeAgentViewportResponse {
  points: SimulationGlobeAgentPoint[];
  total_in_bounds: number;
}

export interface SimulationGlobeSelection {
  level: SimulationGlobePlaceLevel;
  place_id: string;
  day: number;
  tick: number;
  record: SimulationGlobeAggregateRecord;
}

export interface SimulationRunGlobeOptions {
  records: readonly SimulationGlobeAggregateRecord[];
  initial_statistic?: SimulationGlobeStatistic;
  initial_action_id?: string;
  initial_day?: number;
  initial_tick?: number;
  total_ticks?: number;
  ticks_per_day?: number;
  playback_interval_ms?: number;
  load_agent_points?: (
    request: SimulationGlobeAgentViewportRequest,
  ) => Promise<SimulationGlobeAgentViewportResponse>;
  on_place_selected?: (selection: SimulationGlobeSelection) => void;
  on_agent_selected?: (agent: SimulationGlobeAgentPoint) => void;
  on_day_changed?: (day: number) => void;
  on_tick_changed?: (tick: number) => void;
}

export interface SimulationGlobeDiagnostics {
  render_count: number;
  aggregate_upload_count: number;
  agent_point_upload_count: number;
  area_color_upload_count: number;
  country_surface_count: number;
  displayed_agent_points: number;
  detail_level: SimulationGlobeDetailLevel;
}
