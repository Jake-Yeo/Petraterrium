import './initial-agents.css';

export interface InitialAgentLocation {
  country: string;
  region: string | null;
  city: string;
  neighbourhood: string | null;
  specific_place: string | null;
}

export interface InitialAgentRoutineLink {
  routine_id: string;
  name: string;
  agent_type: string;
  inherited_from: string | null;
}

export interface InitialAgentDecisionTreeLink {
  tree_id: string;
  name: string;
  agent_type: string;
  inherited_from: string | null;
}

export interface InitialAgentFamilyRelationship {
  target_agent_id: string;
  display_name: string;
  relationship: string;
  age: number | null;
  weight: number;
}

export interface InitialInteractionEvidence {
  status: string;
  source: string | null;
  version: string | null;
  source_date: string | null;
  evidence_id: string | null;
  licence: string | null;
  uncertainty: number | null;
}

export interface InitialInteractionCounterpart {
  target_agent_id: string;
  display_name: string;
  relationship: string;
  relationship_kind: string;
  weight: number;
  trust: number | null;
  similarity: number | null;
  evidence: InitialInteractionEvidence;
  specific_place: string | null;
  target_specific_place: string | null;
  same_specific_place: boolean | null;
  in_person_eligibility: 'eligible' | 'ineligible' | 'unknown';
  eligibility_reason: string;
  applicable_rule_ids: string[];
}

export interface InitialInteractionFactor {
  kind: 'base' | 'relationship' | 'co_location' | 'place' | 'time' | 'context';
  condition: string;
  factor_id: string;
  label: string;
  value: number;
  provenance: InitialInteractionEvidence;
}

export interface InitialInteractionRule {
  rule_id: string;
  source_action: string;
  interaction_type: string;
  channel: string;
  interaction_tree_id: string | null;
  formula: string;
  factors: InitialInteractionFactor[];
}

export interface InitialInteractionContext {
  program_status: 'absent' | 'draft' | 'confirmed';
  program_version: string | null;
  history_available: boolean;
  history_message: string;
  counterparts: InitialInteractionCounterpart[];
  rules: InitialInteractionRule[];
}

export interface InitialAgentHouseholdMember {
  agent_id: string;
  display_name: string;
  age: number | null;
  relationship: string;
  agent_types: string[];
}

export interface InitialAgentHousehold {
  household_id: string;
  members: InitialAgentHouseholdMember[];
}

export interface InitialAgentListItem {
  agent_id: string;
  display_name: string;
  agent_types: string[];
  age: number | null;
  sex: string;
  country: string;
  city: string;
  current_location: string | null;
  household_id: string | null;
  household_size: number;
  family_status: string;
}

export interface InitialAgentDetail extends InitialAgentListItem {
  location: InitialAgentLocation;
  household: InitialAgentHousehold | null;
  family_relationships: InitialAgentFamilyRelationship[];
  traits: Record<string, unknown>;
  initial_states: Record<string, string>;
  occupation: string | null;
  income: string | number | null;
  education: string | null;
  health: string | null;
  routines: InitialAgentRoutineLink[];
  decision_trees: InitialAgentDecisionTreeLink[];
  interaction_context?: InitialInteractionContext;
  representative_weight: number;
}

export interface InitialAgentFacets {
  agent_types: string[];
  countries: string[];
  cities: string[];
  family_statuses: string[];
}

export interface InitialAgentQuery {
  search: string;
  agent_type: string;
  country: string;
  city: string;
  age_min: number | null;
  age_max: number | null;
  household: string;
  family_status: string;
  page: number;
  page_size: number;
}

export interface InitialAgentPage {
  items: InitialAgentListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  facets: InitialAgentFacets;
}

export interface InitialAgentsClient {
  list(query: InitialAgentQuery): Promise<InitialAgentPage>;
  detail(agentId: string): Promise<InitialAgentDetail>;
}

export interface InitialAgentsViewOptions {
  onOpenRoutine?: (routine: InitialAgentRoutineLink, agent: InitialAgentDetail) => void;
  onOpenDecisionTree?: (tree: InitialAgentDecisionTreeLink, agent: InitialAgentDetail) => void;
}

const emptyQuery = (): InitialAgentQuery => ({
  search: '',
  agent_type: '',
  country: '',
  city: '',
  age_min: null,
  age_max: null,
  household: '',
  family_status: '',
  page: 1,
  page_size: 50,
});

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const displayValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'Unknown';
  if (typeof value === 'number') return value.toLocaleString('en');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value).replaceAll('_', ' ');
};

const ageLabel = (value: number | null): string =>
  value === null ? 'Age unknown' : `Age ${Number.isInteger(value) ? value : value.toFixed(1)}`;

const optionList = (values: string[], current: string, empty: string): string =>
  `<option value="">${escapeHtml(empty)}</option>${values
    .map(
      (value) =>
        `<option value="${escapeHtml(value)}"${value === current ? ' selected' : ''}>${escapeHtml(displayValue(value))}</option>`,
    )
    .join('')}`;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

const isListItem = (value: unknown): value is InitialAgentListItem =>
  isRecord(value) &&
  typeof value.agent_id === 'string' &&
  typeof value.display_name === 'string' &&
  isStringArray(value.agent_types) &&
  (value.age === null || typeof value.age === 'number') &&
  typeof value.sex === 'string' &&
  typeof value.country === 'string' &&
  typeof value.city === 'string' &&
  typeof value.household_size === 'number' &&
  typeof value.family_status === 'string';

const isFacets = (value: unknown): value is InitialAgentFacets =>
  isRecord(value) &&
  isStringArray(value.agent_types) &&
  isStringArray(value.countries) &&
  isStringArray(value.cities) &&
  isStringArray(value.family_statuses);

const isPage = (value: unknown): value is InitialAgentPage =>
  isRecord(value) &&
  Array.isArray(value.items) &&
  value.items.every(isListItem) &&
  typeof value.total === 'number' &&
  typeof value.page === 'number' &&
  typeof value.page_size === 'number' &&
  typeof value.pages === 'number' &&
  isFacets(value.facets);

const nullable = (value: unknown, kind: 'string' | 'number'): boolean =>
  value === null || typeof value === kind;

const isInteractionEvidence = (value: unknown): value is InitialInteractionEvidence =>
  isRecord(value) &&
  typeof value.status === 'string' &&
  nullable(value.source, 'string') &&
  nullable(value.version, 'string') &&
  nullable(value.source_date, 'string') &&
  nullable(value.evidence_id, 'string') &&
  nullable(value.licence, 'string') &&
  nullable(value.uncertainty, 'number');

const isInteractionFactor = (value: unknown): value is InitialInteractionFactor =>
  isRecord(value) &&
  typeof value.kind === 'string' &&
  typeof value.condition === 'string' &&
  typeof value.factor_id === 'string' &&
  typeof value.label === 'string' &&
  typeof value.value === 'number' &&
  isInteractionEvidence(value.provenance);

const isInteractionCounterpart = (value: unknown): value is InitialInteractionCounterpart =>
  isRecord(value) &&
  typeof value.target_agent_id === 'string' &&
  typeof value.display_name === 'string' &&
  typeof value.relationship === 'string' &&
  typeof value.relationship_kind === 'string' &&
  typeof value.weight === 'number' &&
  nullable(value.trust, 'number') &&
  nullable(value.similarity, 'number') &&
  isInteractionEvidence(value.evidence) &&
  nullable(value.specific_place, 'string') &&
  nullable(value.target_specific_place, 'string') &&
  (value.same_specific_place === null || typeof value.same_specific_place === 'boolean') &&
  ['eligible', 'ineligible', 'unknown'].includes(String(value.in_person_eligibility)) &&
  typeof value.eligibility_reason === 'string' &&
  isStringArray(value.applicable_rule_ids);

const isInteractionRule = (value: unknown): value is InitialInteractionRule =>
  isRecord(value) &&
  typeof value.rule_id === 'string' &&
  typeof value.source_action === 'string' &&
  typeof value.interaction_type === 'string' &&
  typeof value.channel === 'string' &&
  nullable(value.interaction_tree_id, 'string') &&
  typeof value.formula === 'string' &&
  Array.isArray(value.factors) &&
  value.factors.every(isInteractionFactor);

const isInteractionContext = (value: unknown): value is InitialInteractionContext =>
  isRecord(value) &&
  ['absent', 'draft', 'confirmed'].includes(String(value.program_status)) &&
  nullable(value.program_version, 'string') &&
  typeof value.history_available === 'boolean' &&
  typeof value.history_message === 'string' &&
  Array.isArray(value.counterparts) &&
  value.counterparts.every(isInteractionCounterpart) &&
  Array.isArray(value.rules) &&
  value.rules.every(isInteractionRule);

const isDetail = (value: unknown): value is InitialAgentDetail => {
  if (!isListItem(value)) return false;
  const fields = value as unknown as Record<string, unknown>;
  return (
    isRecord(fields.location) &&
    Array.isArray(fields.family_relationships) &&
    isRecord(fields.traits) &&
    isRecord(fields.initial_states) &&
    Array.isArray(fields.routines) &&
    Array.isArray(fields.decision_trees) &&
    (fields.interaction_context === undefined ||
      isInteractionContext(fields.interaction_context)) &&
    typeof fields.representative_weight === 'number'
  );
};

async function request<T>(url: string, validate: (value: unknown) => value is T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : null;
    throw new Error(detail ?? `Initial agents request failed (${response.status})`);
  }
  if (!validate(body)) throw new Error('The server returned an invalid initial agents contract.');
  return body;
}

export function createInitialAgentsHttpClient(
  basePath = '/api/simulation/initial-agents',
): InitialAgentsClient {
  return {
    list: (query) => {
      const parameters = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) {
        if (value !== '' && value !== null) parameters.set(key, String(value));
      }
      return request(`${basePath}?${parameters}`, isPage);
    },
    detail: (agentId) => request(`${basePath}/${encodeURIComponent(agentId)}`, isDetail),
  };
}

export class InitialAgentsView {
  private query = emptyQuery();
  private page: InitialAgentPage | null = null;
  private detail: InitialAgentDetail | null = null;
  private requestVersion = 0;
  private disposed = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: InitialAgentsClient = createInitialAgentsHttpClient(),
    private readonly options: InitialAgentsViewOptions = {},
  ) {
    this.host.classList.add('initial-agents');
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('submit', this.onSubmit);
    this.host.addEventListener('change', this.onChange);
    this.renderLoading('Loading initial agents…');
    void this.loadList();
  }

  dispose(): void {
    this.disposed = true;
    this.requestVersion += 1;
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.removeEventListener('change', this.onChange);
  }

  refresh(): Promise<void> {
    this.detail = null;
    return this.loadList();
  }

  private async loadList(): Promise<void> {
    const version = ++this.requestVersion;
    this.renderLoading('Loading initial agents…');
    try {
      const page = await this.client.list(this.query);
      if (this.disposed || version !== this.requestVersion) return;
      this.page = page;
      this.renderList();
    } catch (error) {
      if (this.disposed || version !== this.requestVersion) return;
      this.renderError(error);
    }
  }

  private async loadDetail(agentId: string): Promise<void> {
    const version = ++this.requestVersion;
    this.renderLoading('Loading initial state…');
    try {
      const detail = await this.client.detail(agentId);
      if (this.disposed || version !== this.requestVersion) return;
      this.detail = detail;
      this.renderDetail(detail);
    } catch (error) {
      if (this.disposed || version !== this.requestVersion) return;
      this.renderError(error);
    }
  }

  private renderLoading(message: string): void {
    this.host.innerHTML = `<div class="initial-agents-state" role="status">${escapeHtml(message)}</div>`;
  }

  private renderError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.host.innerHTML = `<div class="initial-agents-state initial-agents-error" role="alert"><strong>Initial agents unavailable</strong><span>${escapeHtml(message)}</span><button type="button" class="button secondary" data-initial-action="retry">Retry</button></div>`;
  }

  private renderList(): void {
    if (!this.page) return;
    const facets = this.page.facets;
    this.host.innerHTML = `
      <div class="initial-agents-heading">
        <div><span class="small-label">POPULATION BEFORE TICK ZERO</span><h2>Initial agents</h2><p>Inspect sampled people, linked households, routines, and decision trees.</p></div>
        <strong>${this.page.total.toLocaleString('en')} agents</strong>
      </div>
      <form class="initial-agents-filters" data-initial-filters>
        <label class="initial-agents-search">Search<input type="search" name="search" value="${escapeHtml(this.query.search)}" placeholder="Name, ID, occupation, or type" /></label>
        <label>Agent type<select name="agent_type">${optionList(facets.agent_types, this.query.agent_type, 'All types')}</select></label>
        <label>Country<select name="country">${optionList(facets.countries, this.query.country, 'All countries')}</select></label>
        <label>City<select name="city">${optionList(facets.cities, this.query.city, 'All cities')}</select></label>
        <label>Minimum age<input type="number" name="age_min" min="0" step="1" value="${this.query.age_min ?? ''}" /></label>
        <label>Maximum age<input type="number" name="age_max" min="0" step="1" value="${this.query.age_max ?? ''}" /></label>
        <label>Household<input type="search" name="household" value="${escapeHtml(this.query.household)}" placeholder="Household ID" /></label>
        <label>Family status<select name="family_status">${optionList(facets.family_statuses, this.query.family_status, 'Any status')}</select></label>
        <div class="initial-agents-filter-actions"><button type="submit" class="button primary">Apply filters</button><button type="button" class="button secondary" data-initial-action="reset">Reset filters</button></div>
      </form>
      <div class="initial-agents-column-labels" aria-hidden="true"><span>Agent</span><span>Type</span><span>Demographics</span><span>Place</span><span>Household</span><span></span></div>
      <div class="initial-agents-list">${this.agentRows()}</div>
      ${this.pagination()}`;
  }

  private agentRows(): string {
    if (!this.page?.items.length) {
      return '<div class="initial-agents-empty">No initial agents match these filters.</div>';
    }
    return this.page.items
      .map(
        (
          agent,
        ) => `<button type="button" class="initial-agent-row" data-agent-id="${escapeHtml(agent.agent_id)}" aria-label="Open ${escapeHtml(agent.display_name)} initial state">
          <span class="initial-agent-identity"><strong>${escapeHtml(agent.display_name)}</strong><small>${escapeHtml(agent.agent_id)}</small></span>
          <span class="initial-agent-types">${agent.agent_types.map((value) => `<i>${escapeHtml(value)}</i>`).join('')}</span>
          <span><strong>${escapeHtml(ageLabel(agent.age))}</strong><small>${escapeHtml(displayValue(agent.sex))}</small></span>
          <span><strong>${escapeHtml(agent.city)}</strong><small>${escapeHtml(agent.country)} · ${escapeHtml(agent.current_location ?? 'Location unknown')}</small></span>
          <span><strong>${escapeHtml(agent.household_id ?? 'No household')}</strong><small>${agent.household_size} members · ${escapeHtml(displayValue(agent.family_status))}</small></span>
          <b aria-hidden="true">›</b>
        </button>`,
      )
      .join('');
  }

  private pagination(): string {
    if (!this.page || this.page.pages <= 1) return '';
    return `<nav class="initial-agents-pagination" aria-label="Initial agents pages"><button type="button" class="button secondary" data-page="${this.page.page - 1}"${this.page.page <= 1 ? ' disabled' : ''}>Previous</button><span>Page ${this.page.page} of ${this.page.pages}</span><button type="button" class="button secondary" data-page="${this.page.page + 1}"${this.page.page >= this.page.pages ? ' disabled' : ''}>Next</button></nav>`;
  }

  private renderDetail(agent: InitialAgentDetail): void {
    this.host.innerHTML = `
      <button type="button" class="initial-agent-back" data-initial-action="back">← Back to initial agents</button>
      <div class="initial-agent-detail-heading">
        <div><span class="small-label">INITIAL STATE · ${escapeHtml(agent.agent_id)}</span><h2>${escapeHtml(agent.display_name)}</h2><div class="initial-agent-type-pills">${agent.agent_types.map((value) => `<span>${escapeHtml(value)}</span>`).join('')}</div></div>
        <div><span>${escapeHtml(ageLabel(agent.age))}</span><span>${escapeHtml(displayValue(agent.sex))}</span><span>${escapeHtml(displayValue(agent.family_status))}</span></div>
      </div>
      <section class="initial-agent-facts" aria-label="Core initial state">
        ${this.fact('Country', agent.country)}${this.fact('City', agent.city)}${this.fact('Current location', agent.current_location)}${this.fact('Occupation', agent.occupation)}${this.fact('Income', agent.income)}${this.fact('Education', agent.education)}${this.fact('Health', agent.health)}${this.fact('Representative weight', agent.representative_weight)}
      </section>
      ${this.interactions(agent)}
      <div class="initial-agent-detail-grid">
        ${this.household(agent)}
        ${this.family(agent)}
        ${this.links(agent)}
        ${this.recordSection('Traits', agent.traits)}
        ${this.recordSection('Initial states', agent.initial_states)}
        ${this.location(agent.location)}
      </div>`;
  }

  private fact(label: string, value: unknown): string {
    return `<div><small>${escapeHtml(label)}</small><strong>${escapeHtml(displayValue(value))}</strong></div>`;
  }

  private interactions(agent: InitialAgentDetail): string {
    const context = agent.interaction_context;
    if (!context) {
      return `<section class="initial-agent-interactions" role="region" aria-label="Pre-run interaction context"><header><div><span class="small-label">PRE-RUN INTERACTION CONTEXT</span><h3>Potential interactions</h3></div><span class="initial-interaction-program is-absent">Program unavailable</span></header><p class="initial-interaction-empty">No confirmed interaction program is available for this saved population.</p><div class="initial-interaction-history">No interaction frequency or history exists before a run. Run the simulation, then open Run Results for recorded interactions.</div></section>`;
    }
    const statusText =
      context.program_status === 'confirmed'
        ? `Confirmed${context.program_version ? ` · ${context.program_version}` : ''}`
        : context.program_status === 'draft'
          ? `Draft${context.program_version ? ` · ${context.program_version}` : ''}`
          : 'No program';
    const programNotice =
      context.program_status === 'confirmed'
        ? ''
        : `<p class="initial-interaction-empty">${context.program_status === 'draft' ? 'A draft interaction program exists. Only confirmed rules can establish eligibility or execute.' : 'No confirmed interaction program exists. Co-location is shown, but rule eligibility is unknown.'}</p>`;
    const counterparts = context.counterparts.length
      ? context.counterparts.map((counterpart) => this.interactionCounterpart(counterpart)).join('')
      : '<p class="initial-interaction-empty">No potential counterpart relationships are attached to this agent.</p>';
    const rules = context.rules.length
      ? context.rules.map((rule) => this.interactionRule(rule)).join('')
      : context.program_status === 'confirmed'
        ? '<p class="initial-interaction-empty">No confirmed interaction rule matches this agent\'s counterpart relationship kinds.</p>'
        : '';
    return `<section class="initial-agent-interactions" role="region" aria-label="Pre-run interaction context">
      <header><div><span class="small-label">PRE-RUN INTERACTION CONTEXT</span><h3>Potential interactions</h3></div><span class="initial-interaction-program is-${escapeHtml(context.program_status)}">${escapeHtml(statusText)}</span></header>
      ${programNotice}
      <div class="initial-interaction-layout"><div><h4>Counterpart relationships</h4><div class="initial-interaction-counterparts">${counterparts}</div></div><div><h4>Applicable confirmed rules</h4><div class="initial-interaction-rules">${rules}</div></div></div>
      <div class="initial-interaction-history">${escapeHtml(context.history_message)}</div>
    </section>`;
  }

  private interactionCounterpart(counterpart: InitialInteractionCounterpart): string {
    const colocation =
      counterpart.same_specific_place === true
        ? 'Same exact place'
        : counterpart.same_specific_place === false
          ? 'Different exact places'
          : 'Exact-place co-location unknown';
    const eligibility =
      counterpart.in_person_eligibility === 'eligible'
        ? 'In-person eligible'
        : counterpart.in_person_eligibility === 'ineligible'
          ? 'In-person ineligible'
          : 'In-person eligibility unknown';
    const provenance = counterpart.evidence.source
      ? `${escapeHtml(counterpart.evidence.source)} · ${escapeHtml(counterpart.evidence.version ?? 'Version unknown')} · ${escapeHtml(counterpart.evidence.source_date ?? 'Date unknown')}`
      : 'Relationship evidence provenance unavailable';
    const rules = counterpart.applicable_rule_ids.length
      ? `Current rules: ${counterpart.applicable_rule_ids.map(displayValue).join(', ')}`
      : 'No confirmed rule is currently applicable';
    return `<button type="button" class="initial-interaction-counterpart" data-agent-id="${escapeHtml(counterpart.target_agent_id)}" aria-label="Open ${escapeHtml(counterpart.display_name)} interaction counterpart">
      <span class="initial-interaction-counterpart-heading"><span><strong>${escapeHtml(counterpart.display_name)}</strong><small>${escapeHtml(displayValue(counterpart.relationship))} · ${escapeHtml(displayValue(counterpart.relationship_kind))}</small></span><i class="is-${escapeHtml(counterpart.in_person_eligibility)}">${escapeHtml(eligibility)}</i></span>
      <span class="initial-interaction-gates"><b>${escapeHtml(colocation)}</b><small>${escapeHtml(counterpart.specific_place ?? 'Actor place unknown')} ↔ ${escapeHtml(counterpart.target_specific_place ?? 'Counterpart place unknown')}</small></span>
      <span class="initial-interaction-measures"><small>Weight <b>${counterpart.weight.toFixed(2)}</b></small><small>Trust <b>${counterpart.trust === null ? 'Unknown' : counterpart.trust.toFixed(2)}</b></small><small>Similarity <b>${counterpart.similarity === null ? 'Unknown' : counterpart.similarity.toFixed(2)}</b></small></span>
      <span class="initial-interaction-evidence"><b>${escapeHtml(displayValue(counterpart.evidence.status))}</b><small>${provenance}</small><small>${escapeHtml(rules)}</small><small>${escapeHtml(counterpart.eligibility_reason)}</small></span>
    </button>`;
  }

  private interactionRule(rule: InitialInteractionRule): string {
    const factors = rule.factors
      .map(
        (factor) =>
          `<li><div><span>${escapeHtml(displayValue(factor.kind))}</span><strong>${escapeHtml(factor.label)}</strong><small>${escapeHtml(displayValue(factor.condition))} · value ${factor.value.toLocaleString('en')}</small></div><div><b>${escapeHtml(displayValue(factor.provenance.status))}</b><small>${escapeHtml(factor.provenance.source ?? 'Source unavailable')} · ${escapeHtml(factor.provenance.version ?? 'Version unknown')} · ${escapeHtml(factor.provenance.source_date ?? 'Date unknown')}</small><small>Evidence ${escapeHtml(factor.provenance.evidence_id ?? 'unknown')} · uncertainty ${factor.provenance.uncertainty === null ? 'unknown' : `±${factor.provenance.uncertainty}`}</small></div></li>`,
      )
      .join('');
    return `<details class="initial-interaction-rule"><summary><span><strong>${escapeHtml(displayValue(rule.interaction_type))}</strong><small>${escapeHtml(displayValue(rule.channel))} · trigger ${escapeHtml(displayValue(rule.source_action))}</small></span><b>Formula + evidence</b></summary><div><p class="initial-interaction-formula">${escapeHtml(rule.formula)}</p>${rule.interaction_tree_id ? `<p>Interaction tree ${escapeHtml(rule.interaction_tree_id)}</p>` : ''}<ul>${factors}</ul><p class="initial-interaction-caveat">Configured factors are shown separately. A rate is evaluated only during a run when the trigger, time, place, and runtime context are known.</p></div></details>`;
  }

  private household(agent: InitialAgentDetail): string {
    if (!agent.household) {
      return '<section class="initial-agent-card"><span class="small-label">HOUSEHOLD</span><p>No linked household.</p></section>';
    }
    return `<section class="initial-agent-card initial-agent-household" aria-label="Household ${escapeHtml(agent.household.household_id)}"><div class="initial-agent-card-heading"><span class="small-label">HOUSEHOLD</span><strong>${escapeHtml(agent.household.household_id)}</strong></div><div>${agent.household.members
      .map(
        (member) =>
          `<button type="button" data-agent-id="${escapeHtml(member.agent_id)}"${member.agent_id === agent.agent_id ? ' disabled' : ''}><span><strong>${escapeHtml(member.display_name)}</strong><small>${escapeHtml(member.relationship)} · ${escapeHtml(ageLabel(member.age))}</small></span><i>${escapeHtml(member.agent_types.join(' · '))}</i></button>`,
      )
      .join('')}</div></section>`;
  }

  private family(agent: InitialAgentDetail): string {
    const content = agent.family_relationships.length
      ? agent.family_relationships
          .map(
            (relationship) =>
              `<button type="button" data-agent-id="${escapeHtml(relationship.target_agent_id)}"><span><strong>${escapeHtml(relationship.display_name)}</strong><small>${escapeHtml(relationship.relationship)} · ${escapeHtml(ageLabel(relationship.age))}</small></span><i>Weight ${relationship.weight.toFixed(2)}</i></button>`,
          )
          .join('')
      : '<p>No family relationships linked.</p>';
    return `<section class="initial-agent-card initial-agent-family" aria-label="Family relationships"><span class="small-label">FAMILY RELATIONSHIPS</span><div>${content}</div></section>`;
  }

  private links(agent: InitialAgentDetail): string {
    const routines = agent.routines.length
      ? agent.routines
          .map(
            (routine) =>
              `<button type="button" data-routine-id="${escapeHtml(routine.routine_id)}" aria-label="Open ${escapeHtml(routine.name)} routine"><span><strong>${escapeHtml(routine.name)}</strong><small>${escapeHtml(routine.agent_type)}${routine.inherited_from ? ` · inherited from ${escapeHtml(routine.inherited_from)}` : ''}</small></span><b>Open ↗</b></button>`,
          )
          .join('')
      : '<p>No routine assigned.</p>';
    const trees = agent.decision_trees.length
      ? agent.decision_trees
          .map(
            (tree) =>
              `<button type="button" data-tree-id="${escapeHtml(tree.tree_id)}" aria-label="Open ${escapeHtml(tree.name)} decision tree"><span><strong>${escapeHtml(tree.name)}</strong><small>${escapeHtml(tree.agent_type)}${tree.inherited_from ? ` · inherited from ${escapeHtml(tree.inherited_from)}` : ''}</small></span><b>Open graph ↗</b></button>`,
          )
          .join('')
      : '<p>No decision tree assigned.</p>';
    return `<section class="initial-agent-card initial-agent-links" aria-label="Routine and decision trees"><div><span class="small-label">ROUTINES</span>${routines}</div><div><span class="small-label">DECISION TREES</span>${trees}</div></section>`;
  }

  private recordSection(title: string, values: Record<string, unknown>): string {
    const rows = Object.entries(values)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(
        ([name, value]) =>
          `<div><dt>${escapeHtml(displayValue(name))}</dt><dd>${escapeHtml(displayValue(value))}</dd></div>`,
      )
      .join('');
    return `<section class="initial-agent-card initial-agent-record"><span class="small-label">${escapeHtml(title.toUpperCase())}</span><dl>${rows || '<div><dt>None recorded</dt><dd>—</dd></div>'}</dl></section>`;
  }

  private location(location: InitialAgentLocation): string {
    const path = [
      location.country,
      location.region,
      location.city,
      location.neighbourhood,
      location.specific_place,
    ].filter((value): value is string => Boolean(value));
    return `<section class="initial-agent-card initial-agent-location"><span class="small-label">LOCATION</span><ol>${path.map((value) => `<li>${escapeHtml(value)}</li>`).join('')}</ol></section>`;
  }

  private updateQuery(form: HTMLFormElement): void {
    const values = new FormData(form);
    const numberValue = (name: string): number | null => {
      const value = String(values.get(name) ?? '').trim();
      return value ? Number(value) : null;
    };
    this.query = {
      ...this.query,
      search: String(values.get('search') ?? ''),
      agent_type: String(values.get('agent_type') ?? ''),
      country: String(values.get('country') ?? ''),
      city: String(values.get('city') ?? ''),
      age_min: numberValue('age_min'),
      age_max: numberValue('age_max'),
      household: String(values.get('household') ?? ''),
      family_status: String(values.get('family_status') ?? ''),
      page: 1,
    };
  }

  private onSubmit = (event: SubmitEvent): void => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-initial-filters]')) return;
    event.preventDefault();
    this.updateQuery(form);
    void this.loadList();
  };

  private onChange = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) return;
    const form = target.closest<HTMLFormElement>('[data-initial-filters]');
    if (!form) return;
    this.updateQuery(form);
    void this.loadList();
  };

  private onClick = (event: MouseEvent): void => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const action = target.closest<HTMLElement>('[data-initial-action]')?.dataset.initialAction;
    if (action === 'retry') {
      void (this.detail ? this.loadDetail(this.detail.agent_id) : this.loadList());
      return;
    }
    if (action === 'reset') {
      this.query = emptyQuery();
      void this.loadList();
      return;
    }
    if (action === 'back') {
      this.detail = null;
      this.renderList();
      return;
    }
    const page = target.closest<HTMLElement>('[data-page]')?.dataset.page;
    if (page) {
      this.query.page = Number(page);
      void this.loadList();
      return;
    }
    const routineId = target.closest<HTMLElement>('[data-routine-id]')?.dataset.routineId;
    if (routineId && this.detail) {
      const routine = this.detail.routines.find((candidate) => candidate.routine_id === routineId);
      if (routine) {
        this.options.onOpenRoutine?.(routine, this.detail);
        this.host.dispatchEvent(
          new CustomEvent('initial-agents:open-routine', {
            bubbles: true,
            detail: { routine, agent: this.detail },
          }),
        );
      }
      return;
    }
    const treeId = target.closest<HTMLElement>('[data-tree-id]')?.dataset.treeId;
    if (treeId && this.detail) {
      const tree = this.detail.decision_trees.find((candidate) => candidate.tree_id === treeId);
      if (tree) {
        this.options.onOpenDecisionTree?.(tree, this.detail);
        this.host.dispatchEvent(
          new CustomEvent('initial-agents:open-decision-tree', {
            bubbles: true,
            detail: { tree, agent: this.detail },
          }),
        );
      }
      return;
    }
    const agentId = target.closest<HTMLElement>('[data-agent-id]')?.dataset.agentId;
    if (agentId) void this.loadDetail(agentId);
  };
}
