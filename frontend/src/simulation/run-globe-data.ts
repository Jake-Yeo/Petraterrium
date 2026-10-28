import type {
  SimulationGlobeAggregateRecord,
  SimulationGlobeAgentPoint,
  SimulationGlobeAgentViewportRequest,
  SimulationGlobeDetailLevel,
  SimulationGlobePlaceLevel,
  SimulationGlobeStatistic,
  SimulationGlobeViewportBounds,
} from './run-globe-types';

export const simulationGlobePlaceKey = (
  level: SimulationGlobePlaceLevel,
  placeId: string,
): string => `${level}:${placeId}`;

export const simulationGlobeRecordKey = (record: SimulationGlobeAggregateRecord): string =>
  simulationGlobePlaceKey(record.place_level, record.place_id);

export const simulationGlobeDays = (records: readonly SimulationGlobeAggregateRecord[]): number[] =>
  [...new Set(records.map((record) => record.day))].sort((left, right) => left - right);

export const simulationGlobeActionIds = (
  records: readonly SimulationGlobeAggregateRecord[],
): string[] =>
  [
    ...new Set(
      records.flatMap((record) => [
        ...Object.keys(record.action_counts),
        ...Object.keys(record.action_rates_per_1000),
      ]),
    ),
  ].sort((left, right) => left.localeCompare(right));

export const simulationGlobeStatisticValue = (
  record: SimulationGlobeAggregateRecord,
  statistic: SimulationGlobeStatistic,
  actionId: string,
): number | null => {
  if (statistic === 'unemployment_rate') return record.employment?.unemployment_rate ?? null;
  if (statistic === 'mean_income') return record.finances.income?.mean ?? null;
  if (statistic === 'population') return record.population;
  return record.action_rates_per_1000[actionId] ?? 0;
};

export const simulationGlobeStatisticLabel = (
  statistic: SimulationGlobeStatistic,
  actionId: string,
): string => {
  if (statistic === 'unemployment_rate') return 'Unemployment rate';
  if (statistic === 'mean_income') return 'Mean income';
  if (statistic === 'population') return 'Population';
  const actionLabel = actionId
    ? actionId.replace(/[_-]+/g, ' ').replace(/^\w/, (character) => character.toUpperCase())
    : 'Action';
  return `${actionLabel} rate per 1,000`;
};

export const simulationGlobeFormatNumber = (value: number, maximumFractionDigits = 1): string =>
  new Intl.NumberFormat(undefined, {
    maximumFractionDigits,
    notation: Math.abs(value) >= 1_000_000 ? 'compact' : 'standard',
  }).format(value);

export const simulationGlobeFormatStatistic = (
  value: number | null,
  statistic: SimulationGlobeStatistic,
  unit = '',
): string => {
  if (value === null || !Number.isFinite(value)) return 'Unavailable in this recorded aggregate';
  if (statistic === 'unemployment_rate') return `${simulationGlobeFormatNumber(value * 100)}%`;
  if (statistic === 'mean_income')
    return `${simulationGlobeFormatNumber(value)}${unit ? ` ${unit}` : ''}`;
  return simulationGlobeFormatNumber(value);
};

export const simulationGlobeDetailLevelForDistance = (
  distance: number,
): SimulationGlobeDetailLevel => {
  if (distance >= 3.7) return 'world';
  if (distance >= 2.5) return 'country';
  if (distance >= 1.65) return 'city';
  return 'neighborhood';
};

export const simulationGlobeDistanceForDetailLevel = (
  detailLevel: SimulationGlobeDetailLevel,
): number => {
  if (detailLevel === 'world') return 4.5;
  if (detailLevel === 'country') return 3.1;
  if (detailLevel === 'city') return 2.05;
  return 1.4;
};

export const simulationGlobePointInBounds = (
  point: SimulationGlobeAgentPoint,
  bounds: SimulationGlobeViewportBounds,
): boolean => {
  const latitudeInside = point.latitude >= bounds.south && point.latitude <= bounds.north;
  const longitudeInside =
    bounds.west <= bounds.east
      ? point.longitude >= bounds.west && point.longitude <= bounds.east
      : point.longitude >= bounds.west || point.longitude <= bounds.east;
  return latitudeInside && longitudeInside;
};

export const simulationGlobeViewportRequestKey = (
  request: SimulationGlobeAgentViewportRequest,
): string =>
  [
    request.run_id,
    request.day,
    request.tick,
    request.detail_level,
    request.bounds.north.toFixed(2),
    request.bounds.east.toFixed(2),
    request.bounds.south.toFixed(2),
    request.bounds.west.toFixed(2),
    request.visible_city_ids.join(','),
  ].join('|');
