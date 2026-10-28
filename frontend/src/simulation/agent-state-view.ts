import './agent-state-view.css';

export type StateEvidenceStatus =
  | 'measured_joint'
  | 'measured_marginal'
  | 'inherited'
  | 'imputed'
  | 'literature_support'
  | 'default_estimated'
  | 'unknown'
  | 'simulated';

export type StateEvidence = {
  status: StateEvidenceStatus;
  source: string;
  source_version: string;
  source_date: string | null;
  url: string | null;
  place: string;
  population: string;
  language: string | null;
  original_title: string | null;
  english_title: string | null;
  search_source: string | null;
  uncertainty: number;
  default_reason: string | null;
};

export type StateEventEffect = {
  event_id: string;
  direction: 'increases' | 'decreases' | 'sets' | 'contextual';
  parameter_id: string;
  formula: string;
  evidence: StateEvidence;
};

export type StateDecisionModifier = {
  decision_id: string;
  state_id: string;
  formula: string;
  coefficient: number | null;
  center: number;
  minimum_factor: number;
  maximum_factor: number;
  direction: 'increases' | 'decreases' | 'nonlinear' | 'contextual';
  evidence: StateEvidence;
};

export type StatePropagation = {
  target_state_id: string;
  direction: 'increases' | 'decreases' | 'nonlinear' | 'contextual';
  parameter_id: string;
  formula: string;
  evidence: StateEvidence;
};

export type AgentStateDefinition = {
  id: string;
  name: string;
  group: 'emotion' | 'slow_trait' | 'health_body' | 'life_social' | 'social_economic';
  description: string;
  value_range: { minimum: number; maximum: number; unit: string };
  initial_feature_ids: string[];
  initial_evidence: StateEvidence;
  event_effects: StateEventEffect[];
  recovery: {
    mode: 'stable' | 'decay' | 'recover' | 'event_driven';
    parameter_id: string | null;
    formula: string;
    evidence: StateEvidence;
  };
  decision_modifiers: StateDecisionModifier[];
  propagation: StatePropagation[];
};

export type AgentStateCatalog = {
  version: string;
  status: 'draft' | 'confirmed';
  definitions: AgentStateDefinition[];
};

export type RelationshipStateDefinition = {
  id: string;
  name: string;
  description: string;
  value_range: { minimum: number; maximum: number; unit: string };
  direction: 'source_to_target';
  event_effects: StateEventEffect[];
  recovery: AgentStateDefinition['recovery'];
};

export type AgentStateSystem = {
  agent_states: AgentStateCatalog;
  relationship_states: { version: string; definitions: RelationshipStateDefinition[] };
};

export type EducationProfile = {
  years_of_education: number | null;
  isced_level: number | null;
  country_label: string;
  country_code: string;
  specialization: string | null;
  specialization_threshold_years: number;
  specialization_status: 'present' | 'not_applicable' | 'awaiting_data';
  provenance: StateEvidence;
};

export type FinanceQuantity = { value: number | null; evidence: StateEvidence & { currency: string } };

export type FinanceState = {
  currency: string;
  status: StateEvidenceStatus;
  source_distribution_id: string | null;
  source_cell_id: string | null;
  money: FinanceQuantity;
  income: FinanceQuantity;
  expenses: FinanceQuantity;
  savings: FinanceQuantity;
  debt: FinanceQuantity;
  evidence: StateEvidence & { currency: string };
  formula: string;
};

export type AgentStateVector = {
  catalog_version: string;
  values: Array<{
    state_id: string;
    value: number | null;
    status: 'present' | 'unknown';
    evidence: StateEvidence;
  }>;
};

const groupLabels: Record<AgentStateDefinition['group'], string> = {
  emotion: 'Emotions',
  slow_trait: 'Slow traits',
  health_body: 'Health and body',
  life_social: 'Life and social status',
  social_economic: 'Social and economic state',
};

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const displayId = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const evidenceMarkup = (evidence: StateEvidence): string => `
  <div class="agent-state-evidence is-${escapeHtml(evidence.status)}">
    <span>${escapeHtml(displayId(evidence.status))}</span>
    <strong>${escapeHtml(evidence.source)}</strong>
    <small>${escapeHtml(evidence.source_version)} · ${escapeHtml(evidence.place)} · uncertainty ${Math.round(evidence.uncertainty * 100)}%</small>
    ${evidence.default_reason ? `<p>${escapeHtml(evidence.default_reason)}</p>` : ''}
  </div>`;

function stateDefinitionMarkup(definition: AgentStateDefinition): string {
  const events = definition.event_effects.length
    ? definition.event_effects
        .map(
          (effect) => `<li><span>${escapeHtml(displayId(effect.event_id))} · ${escapeHtml(effect.direction)}</span><code>${escapeHtml(effect.formula)}</code>${evidenceMarkup(effect.evidence)}</li>`,
        )
        .join('')
    : '<li>No event effect is attached.</li>';
  const modifiers = definition.decision_modifiers.length
    ? definition.decision_modifiers
        .map(
          (modifier) => `<li><span>${escapeHtml(displayId(modifier.decision_id))} · ${escapeHtml(modifier.direction)}</span><code>${escapeHtml(modifier.formula)}</code><small>${modifier.coefficient === null ? 'Coefficient awaiting linked outcome data' : `Coefficient ${modifier.coefficient.toLocaleString('en')}`}</small>${evidenceMarkup(modifier.evidence)}</li>`,
        )
        .join('')
    : '<li>No decision modifier is attached.</li>';
  const propagation = definition.propagation.length
    ? definition.propagation
        .map(
          (loop) => `<li><span>Feeds ${escapeHtml(displayId(loop.target_state_id))} · ${escapeHtml(loop.direction)}</span><code>${escapeHtml(loop.formula)}</code>${evidenceMarkup(loop.evidence)}</li>`,
        )
        .join('')
    : '<li>No cross-state propagation is attached.</li>';
  return `
    <details class="agent-state-definition">
      <summary><span><strong>${escapeHtml(definition.name)}</strong><small>${escapeHtml(definition.description)}</small></span><i>${definition.value_range.minimum}–${definition.value_range.maximum} ${escapeHtml(definition.value_range.unit)}</i></summary>
      <div class="agent-state-definition-body">
        <section><h5>Initial evidence</h5>${evidenceMarkup(definition.initial_evidence)}</section>
        <section><h5>Events</h5><ul>${events}</ul></section>
        <section><h5>Decay or recovery</h5><code>${escapeHtml(definition.recovery.formula)}</code>${evidenceMarkup(definition.recovery.evidence)}</section>
        <section><h5>Decision modifiers</h5><ul>${modifiers}</ul></section>
        <section><h5>State loops</h5><ul>${propagation}</ul></section>
      </div>
    </details>`;
}

export function agentStateDefinitionsMarkup(system: AgentStateSystem): string {
  const groups = Object.entries(groupLabels)
    .map(([group, label]) => {
      const definitions = system.agent_states.definitions.filter(
        (definition) => definition.group === group,
      );
      return `<section class="agent-state-group"><header><h4>${label}</h4><span>${definitions.length}</span></header>${definitions.map(stateDefinitionMarkup).join('')}</section>`;
    })
    .join('');
  const relationships = system.relationship_states.definitions
    .map(
      (definition) => `<article class="relationship-state-definition"><div><strong>${escapeHtml(definition.name)}</strong><span>Directed: source → target</span></div><p>${escapeHtml(definition.description)}</p><code>${escapeHtml(definition.recovery.formula)}</code></article>`,
    )
    .join('');
  return `<div class="agent-state-catalog"><div class="agent-state-catalog-heading"><span>STATE SYSTEM</span><strong>${escapeHtml(system.agent_states.version)}</strong></div>${groups}<section class="agent-state-group relationship-state-group"><header><h4>Directed relationship states</h4><span>${system.relationship_states.definitions.length}</span></header>${relationships}</section></div>`;
}

export function educationProfileMarkup(profile: EducationProfile): string {
  const years =
    profile.years_of_education === null
      ? 'Unknown'
      : `${profile.years_of_education.toLocaleString('en')} completed years`;
  const specialization =
    profile.specialization_status === 'not_applicable'
      ? `Not applicable before ${profile.specialization_threshold_years} years`
      : profile.specialization ?? 'Awaiting specialization data';
  return `<section class="agent-profile-panel" aria-label="Education profile"><header><h3>Education</h3><span>${escapeHtml(profile.country_code)}</span></header><dl><div><dt>Years</dt><dd>${escapeHtml(years)}</dd></div><div><dt>Country label</dt><dd>${escapeHtml(profile.country_label)}</dd></div><div><dt>ISCED</dt><dd>${profile.isced_level === null ? 'Unknown' : `ISCED ${profile.isced_level}`}</dd></div><div><dt>Specialization</dt><dd>${escapeHtml(specialization)}</dd></div></dl>${evidenceMarkup(profile.provenance)}</section>`;
}

const amountMarkup = (quantity: FinanceQuantity, currency: string): string =>
  quantity.value === null
    ? 'Unknown'
    : new Intl.NumberFormat('en', {
        style: 'currency',
        currency: currency === 'XXX' ? 'USD' : currency,
        maximumFractionDigits: 0,
      }).format(quantity.value) + (currency === 'XXX' ? ' currency unknown' : '');

export function financeStateMarkup(finances: FinanceState): string {
  const fields: Array<[string, FinanceQuantity]> = [
    ['Money', finances.money],
    ['Income', finances.income],
    ['Expenses', finances.expenses],
    ['Savings', finances.savings],
    ['Debt', finances.debt],
  ];
  return `<section class="agent-profile-panel" aria-label="Finance state"><header><h3>Finances</h3><span>${escapeHtml(displayId(finances.status))}</span></header><dl>${fields.map(([label, quantity]) => `<div><dt>${label}</dt><dd>${escapeHtml(amountMarkup(quantity, finances.currency))}</dd></div>`).join('')}</dl><code class="agent-finance-formula">${escapeHtml(finances.formula)}</code>${evidenceMarkup(finances.evidence)}</section>`;
}

export function stateVectorMarkup(
  vector: AgentStateVector,
  catalog?: AgentStateCatalog,
): string {
  const definitions = new Map(
    (catalog?.definitions ?? []).map((definition) => [definition.id, definition]),
  );
  const groups = new Map<string, typeof vector.values>();
  for (const value of vector.values) {
    const group = definitions.get(value.state_id)?.group ?? 'unclassified';
    groups.set(group, [...(groups.get(group) ?? []), value]);
  }
  return `<section class="agent-state-vector" aria-label="Agent state vector"><header><h3>State vector</h3><span>${escapeHtml(vector.catalog_version)}</span></header>${[...groups.entries()]
    .map(
      ([group, values]) => `<div class="agent-state-values"><h4>${escapeHtml(group in groupLabels ? groupLabels[group as keyof typeof groupLabels] : displayId(group))}</h4><dl>${values
        .map((value) => {
          const definition = definitions.get(value.state_id);
          return `<div><dt>${escapeHtml(definition?.name ?? displayId(value.state_id))}</dt><dd>${value.value === null ? 'Unknown' : value.value.toFixed(3)}</dd></div>`;
        })
        .join('')}</dl></div>`,
    )
    .join('')}</section>`;
}
