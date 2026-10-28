import { simulationGlobePlaceKey } from './run-globe-data';
import type {
  SimulationGlobeAggregateEvidence,
  SimulationGlobeAggregateRecord,
  SimulationGlobeEmploymentStatistic,
  SimulationGlobeFinanceStatistic,
  SimulationGlobePlaceLevel,
} from './run-globe-types';

export interface SimulationRunAggregateApiRecord {
  run_id: string;
  program_version: string;
  day: number;
  date: string;
  tick: number;
  place_level: SimulationGlobePlaceLevel | 'global';
  place_id: string;
  place_label: string;
  population: number;
  agent_count: number;
  agent_type_counts: Record<string, number>;
  agent_type_shares: Record<string, number>;
  action_counts: Record<string, number>;
  action_rates_per_1000: Record<string, number>;
  finances: Record<string, SimulationGlobeFinanceStatistic>;
  employment: SimulationGlobeEmploymentStatistic | null;
  histograms: Record<string, unknown>;
}

export interface SimulationGlobePlaceMetadata {
  place_level: SimulationGlobePlaceLevel;
  place_id: string;
  latitude: number;
  longitude: number;
  parent_place_id?: string | null;
  evidence: SimulationGlobeAggregateEvidence;
}

export const simulationGlobeRecordsFromRunStatistics = (
  apiRecords: readonly SimulationRunAggregateApiRecord[],
  places: readonly SimulationGlobePlaceMetadata[],
): SimulationGlobeAggregateRecord[] => {
  const placeByKey = new Map(
    places.map((place) => [simulationGlobePlaceKey(place.place_level, place.place_id), place]),
  );
  return apiRecords
    .filter(
      (
        record,
      ): record is SimulationRunAggregateApiRecord & {
        place_level: SimulationGlobePlaceLevel;
      } => record.place_level !== 'global',
    )
    .map((record) => {
      const place = placeByKey.get(simulationGlobePlaceKey(record.place_level, record.place_id));
      if (!place)
        throw new Error(
          `Globe place metadata is missing for ${record.place_level} ${record.place_id}`,
        );
      return {
        run_id: record.run_id,
        program_version: record.program_version,
        day: record.day,
        date: record.date,
        tick: record.tick,
        place_level: record.place_level,
        place_id: record.place_id,
        place_label: record.place_label,
        latitude: place.latitude,
        longitude: place.longitude,
        parent_place_id: place.parent_place_id,
        population: record.population,
        agent_count: record.agent_count,
        agent_type_counts: record.agent_type_counts,
        agent_type_shares: record.agent_type_shares,
        action_counts: record.action_counts,
        action_rates_per_1000: record.action_rates_per_1000,
        finances: record.finances,
        employment: record.employment,
        evidence: place.evidence,
      };
    });
};
