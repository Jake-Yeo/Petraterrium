import {
  SimulationRunGlobe,
  simulationGlobeRecordsFromRunStatistics,
  type SimulationGlobeAgentViewportRequest,
  type SimulationGlobeEvidence,
  type SimulationGlobePlaceMetadata,
  type SimulationRunAggregateApiRecord,
} from '../../src/simulation/simulation-run-globe';

const measured: SimulationGlobeEvidence = {
  status: 'measured',
  source: 'National labour force survey',
  source_version: '2026-Q3',
  source_date: '2026-09-30',
  uncertainty: 0.012,
};

const estimated: SimulationGlobeEvidence = {
  status: 'estimated',
  source: 'Population-weighted regional synthesis',
  source_version: 'regional-v2',
  source_date: '2026-10-01',
  uncertainty: 0.12,
};

const places: SimulationGlobePlaceMetadata[] = [
  {
    place_level: 'region',
    place_id: 'northern-america',
    latitude: 0,
    longitude: 0,
    evidence: {
      population: measured,
      employment: estimated,
      agent_type_mix: estimated,
      action_rates: estimated,
    },
  },
  {
    place_level: 'country',
    place_id: 'US',
    latitude: 0,
    longitude: 0,
    parent_place_id: 'northern-america',
    evidence: {
      population: measured,
      employment: measured,
      agent_type_mix: measured,
      action_rates: measured,
    },
  },
  {
    place_level: 'country',
    place_id: 'CA',
    latitude: 28,
    longitude: -24,
    parent_place_id: 'northern-america',
    evidence: {
      population: measured,
      employment: measured,
      agent_type_mix: estimated,
      action_rates: estimated,
    },
  },
  {
    place_level: 'city',
    place_id: 'new-york',
    latitude: 0,
    longitude: 0,
    parent_place_id: 'US',
    evidence: {
      population: measured,
      employment: estimated,
      agent_type_mix: estimated,
      action_rates: estimated,
    },
  },
  {
    place_level: 'city',
    place_id: 'toronto',
    latitude: 28,
    longitude: -24,
    parent_place_id: 'CA',
    evidence: {
      population: measured,
      employment: estimated,
      agent_type_mix: estimated,
      action_rates: estimated,
    },
  },
];

const apiRecord = (
  day: number,
  placeLevel: 'region' | 'country' | 'city' | 'global',
  placeId: string,
  placeLabel: string,
  agentCount: number,
  population: number,
  unemploymentRate: number,
  meanIncome: number,
): SimulationRunAggregateApiRecord => ({
  run_id: 'global-run-1',
  program_version: 'global-aggregates-v1',
  day,
  date: `2026-11-${String(day).padStart(2, '0')}`,
  tick: day * 24,
  place_level: placeLevel,
  place_id: placeId,
  place_label: placeLabel,
  population,
  agent_count: agentCount,
  agent_type_counts: {
    person: Math.round(agentCount * 0.35),
    worker: Math.round(agentCount * 0.5),
    student: agentCount - Math.round(agentCount * 0.35) - Math.round(agentCount * 0.5),
  },
  agent_type_shares: { person: 0.35, worker: 0.5, student: 0.15 },
  action_counts: { work: Math.round(agentCount * 0.55), socialize: Math.round(agentCount * 0.12) },
  action_rates_per_1000: { work: 550 + day * 5, socialize: 120 + day * 3 },
  finances: {
    income: {
      total: meanIncome * agentCount,
      mean: meanIncome,
      median: meanIncome * 0.82,
      unit: 'PPP USD/year',
      unit_counts: { 'PPP USD/year': agentCount },
      comparable: true,
      basis: 'annual person income',
      evidence_status: placeLevel === 'region' ? 'estimated' : 'measured',
      source_ids: [placeLevel === 'region' ? 'regional-synthesis:v2' : `wdi:${placeId}`],
      observations: agentCount,
    },
    expenses: {
      total: meanIncome * agentCount * 0.72,
      mean: meanIncome * 0.72,
      median: meanIncome * 0.66,
      unit: 'PPP USD/year',
      unit_counts: { 'PPP USD/year': agentCount },
      comparable: true,
      basis: 'annual person expenses',
      evidence_status: 'estimated',
      source_ids: [`expense-model:${placeId}`],
      observations: agentCount,
    },
    savings: {
      total: meanIncome * agentCount * 0.15,
      mean: meanIncome * 0.15,
      median: meanIncome * 0.09,
      unit: 'PPP USD',
      unit_counts: { 'PPP USD': agentCount },
      comparable: true,
      basis: 'current balance',
      evidence_status: 'estimated',
      source_ids: [`savings-model:${placeId}`],
      observations: agentCount,
    },
    debt: {
      total: meanIncome * agentCount * 0.11,
      mean: meanIncome * 0.11,
      median: meanIncome * 0.04,
      unit: 'PPP USD',
      unit_counts: { 'PPP USD': agentCount },
      comparable: true,
      basis: 'current balance',
      evidence_status: 'estimated',
      source_ids: [`debt-model:${placeId}`],
      observations: agentCount,
    },
  },
  employment: {
    agent_count: agentCount,
    employed: Math.round(agentCount * 0.61),
    unemployed: Math.round(agentCount * unemploymentRate),
    labour_force: Math.round(agentCount * 0.7),
    unemployment_rate: unemploymentRate,
    student_share: 0.15,
    caregiver_share: 0.08,
    retired_share: 0.12,
    worker_share: 0.5,
  },
  histograms: {},
});

const apiRecords: SimulationRunAggregateApiRecord[] = [];
for (let day = 1; day <= 3; day += 1) {
  apiRecords.push(
    apiRecord(
      day,
      'global',
      'global',
      'Global',
      1_000,
      8_100_000_000,
      0.07 + day * 0.002,
      31_000 + day * 250,
    ),
    apiRecord(
      day,
      'region',
      'northern-america',
      'Northern America',
      250,
      510_000_000,
      0.06 + day * 0.003,
      48_000 + day * 500,
    ),
    apiRecord(
      day,
      'country',
      'US',
      'United States',
      210,
      340_000_000,
      0.05 + day * 0.004,
      54_000 + day * 750,
    ),
    apiRecord(
      day,
      'country',
      'CA',
      'Canada',
      40,
      41_000_000,
      0.055 + day * 0.003,
      49_000 + day * 600,
    ),
    apiRecord(
      day,
      'city',
      'new-york',
      'New York',
      80,
      8_800_000,
      0.052 + day * 0.004,
      58_000 + day * 800,
    ),
    apiRecord(
      day,
      'city',
      'toronto',
      'Toronto',
      25,
      3_000_000,
      0.057 + day * 0.003,
      52_000 + day * 650,
    ),
  );
}

const requests: SimulationGlobeAgentViewportRequest[] = [];
const selectedAgents: string[] = [];
const root = document.querySelector<HTMLElement>('#globe-fixture');
if (!root) throw new Error('Globe fixture root is missing');

const globe = new SimulationRunGlobe(root, {
  records: simulationGlobeRecordsFromRunStatistics(apiRecords, places),
  playback_interval_ms: 300,
  load_agent_points: async (request) => {
    requests.push(request);
    return {
      total_in_bounds: 2,
      points: [
        {
          agent_id: 'agent-visible-1',
          latitude: 0,
          longitude: 0,
          state: 'working',
          place_id: 'new-york',
        },
        {
          agent_id: 'agent-visible-2',
          latitude: 0.15,
          longitude: 0.2,
          state: 'socializing',
          place_id: 'new-york',
        },
        {
          agent_id: 'agent-outside-viewport',
          latitude: 70,
          longitude: 120,
          state: 'working',
          place_id: 'outside-city',
        },
      ],
    };
  },
  on_agent_selected: (agent) => selectedAgents.push(agent.agent_id),
});

Object.assign(window, {
  simulationRunGlobeHarness: {
    globe,
    requests,
    selectedAgents,
  },
});
