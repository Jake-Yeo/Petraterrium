import type { DecisionEdgeTemplate } from '../contracts.generated';
import type { InitialAgentDetail } from './initial-agents';

type DecisionScalar = string | number | boolean;
type DecisionInputKind = 'trait' | 'place' | 'time' | 'context';

export interface AgentDecisionContextRequest {
  agent_id: string;
  place: {
    region_id: string;
    country_id: string;
    city_id: string | null;
  };
  traits: Record<string, DecisionScalar>;
  place_attributes: Record<string, DecisionScalar>;
  time: Record<string, DecisionScalar>;
  context: Record<string, DecisionScalar>;
}

export interface PreparedAgentDecisionContext {
  request: AgentDecisionContextRequest;
  limitations: string[];
}

function scalarRecord(values: Record<string, unknown>): Record<string, DecisionScalar> {
  return Object.fromEntries(
    Object.entries(values).filter(
      (entry): entry is [string, DecisionScalar] =>
        typeof entry[1] === 'string' ||
        (typeof entry[1] === 'number' && Number.isFinite(entry[1])) ||
        typeof entry[1] === 'boolean',
    ),
  );
}

function nestedScalarRecord(
  values: Record<string, unknown>,
  key: string,
): Record<string, DecisionScalar> {
  const nested = values[key];
  if (nested === null || typeof nested !== 'object' || Array.isArray(nested)) return {};
  return scalarRecord(nested as Record<string, unknown>);
}

function textTrait(agent: InitialAgentDetail, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = agent.traits[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return null;
}

function unavailableInputs(
  evidence: DecisionEdgeTemplate | null,
  inputs: Record<DecisionInputKind, Record<string, DecisionScalar>>,
): Record<DecisionInputKind, string[]> {
  const unavailable: Record<DecisionInputKind, string[]> = {
    trait: [],
    place: [],
    time: [],
    context: [],
  };
  evidence?.formula.factors.forEach((factor) => {
    if (!Object.hasOwn(inputs[factor.input_kind], factor.input_key)) {
      unavailable[factor.input_kind].push(factor.input_key);
    }
  });
  return unavailable;
}

function uniqueList(values: string[]): string {
  return [...new Set(values)].join(', ');
}

function inputLimitations(
  evidence: DecisionEdgeTemplate | null,
  inputs: Record<DecisionInputKind, Record<string, DecisionScalar>>,
): string[] {
  if (!evidence) {
    return [
      'Confirmed probability formula metadata is unavailable, so required preview inputs cannot be verified.',
    ];
  }
  const unavailable = unavailableInputs(evidence, inputs);
  const limitations: string[] = [];
  if (unavailable.trait.length) {
    limitations.push(
      `Agent traits are unavailable for: ${uniqueList(unavailable.trait)}. These factors remain unknown in this initial-agent preview.`,
    );
  }
  if (unavailable.place.length) {
    limitations.push(
      `Actual place attributes are unavailable for: ${uniqueList(unavailable.place)}. These factors remain unknown in this initial-agent preview.`,
    );
  }
  if (unavailable.time.length) {
    limitations.push(
      `Run time is unavailable for: ${uniqueList(unavailable.time)}. This preview cannot derive run time without a confirmed run start date, so these factors remain unknown.`,
    );
  }
  if (unavailable.context.length) {
    limitations.push(
      `Agent or place context is unavailable for: ${uniqueList(unavailable.context)}. These factors remain unknown in this initial-agent preview.`,
    );
  }
  return limitations;
}

export function prepareAgentDecisionContext(
  agent: InitialAgentDetail,
  evidence: DecisionEdgeTemplate | null,
): PreparedAgentDecisionContext {
  const traits = scalarRecord(agent.traits);
  const placeAttributes = nestedScalarRecord(agent.traits, 'place_attributes');
  const time = nestedScalarRecord(agent.traits, 'time');
  const context = {
    ...scalarRecord(agent.initial_states),
    ...nestedScalarRecord(agent.traits, 'context'),
  };
  const regionId = textTrait(agent, 'region');
  const countryId = textTrait(agent, 'country_id') ?? (agent.country.trim() || null);
  const cityId = textTrait(agent, 'city_id', 'city');
  const inputs = {
    trait: traits,
    place: placeAttributes,
    time,
    context,
  };
  const limitations = inputLimitations(evidence, inputs);
  if (!regionId) {
    limitations.push(
      'The actual region identifier is unavailable. Region evidence resolution remains unknown for this preview.',
    );
  }
  if (!countryId) {
    limitations.push(
      'The actual country identifier is unavailable. Country evidence resolution remains unknown for this preview.',
    );
  }
  return {
    request: {
      agent_id: agent.agent_id,
      place: {
        region_id: regionId ?? 'unknown-region',
        country_id: countryId ?? 'unknown-country',
        city_id: cityId,
      },
      traits,
      place_attributes: placeAttributes,
      time,
      context,
    },
    limitations,
  };
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );
}

export function renderDecisionContextLimitations(host: HTMLElement, limitations: string[]): void {
  if (!limitations.length) return;
  host.insertAdjacentHTML(
    'beforeend',
    `<aside class="simulation-decision-context-limitations" role="note" aria-label="Preview limitations"><strong>Preview limitations</strong><ul>${limitations.map((limitation) => `<li>${escapeHtml(limitation)}</li>`).join('')}</ul></aside>`,
  );
}
