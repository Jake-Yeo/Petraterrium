import type {
  AtlasAgentTypeAssignment,
  AtlasAgentTypeCondition,
  AtlasAgentTypeRule,
} from '../contracts.generated';
import './atlas-population.css';

export type {
  AtlasAgentTypeAssignment,
  AtlasAgentTypeCondition,
  AtlasAgentTypeRule,
} from '../contracts.generated';

export type AtlasPlaceSelector = {
  level: 'global' | 'region' | 'subregion' | 'country' | 'city';
  place: string;
  label: string;
};

export type AtlasPopulationFeatureCoverage = {
  feature_id: string;
  measured_agents: number;
  imputed_agents: number;
  unknown_agents: number;
  sources: string[];
};

export type AtlasPopulationMaterializeRequest = {
  population_id: string;
  selector: AtlasPlaceSelector;
  scope: string;
  seed: number;
  target_agents: number;
  agent_type_id: string;
  type_assignment?: AtlasAgentTypeAssignment;
};

export type AtlasPopulationResult = {
  selector: AtlasPlaceSelector;
  scope: string;
  materialization: {
    input_hash: string;
    population: { agents: Array<{ agent_id: string }> };
  };
  feature_coverage: AtlasPopulationFeatureCoverage[];
  agent_type_counts: Record<string, number>;
  warnings: string[];
};

export type AtlasPopulationClient = {
  places(search: string): Promise<AtlasPlaceSelector[]>;
  materialize(request: AtlasPopulationMaterializeRequest): Promise<AtlasPopulationResult>;
};

export type AtlasPopulationGeneratorOptions = {
  client?: AtlasPopulationClient;
  agentTypes?: () => Array<{ id: string; name: string }>;
  onGenerated?: (result: AtlasPopulationResult) => void;
};

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return body as T;
}

export function createAtlasPopulationHttpClient(
  endpoint = '/api/simulation/initial-population/atlas',
): AtlasPopulationClient {
  return {
    async places(search) {
      const response = await fetch(
        `${endpoint}/places?search=${encodeURIComponent(search)}&limit=50`,
      );
      const body = await responseBody<{ places: AtlasPlaceSelector[] }>(response);
      return body.places;
    },
    async materialize(request) {
      const response = await fetch(`${endpoint}/materialize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      return responseBody<AtlasPopulationResult>(response);
    },
  };
}

function placeKey(place: AtlasPlaceSelector): string {
  return `${place.level}:${place.place}`;
}

function featureLabel(value: string): string {
  return value.replaceAll('_', ' ').replaceAll('-', ' ');
}

const agentTypeIdPattern = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

const assignmentFields = [
  ['age', 'Age'],
  ['sex', 'Sex'],
  ['occupation_isco', 'Occupation (ISCO)'],
  ['education_isced', 'Education (ISCED)'],
  ['income', 'Income'],
  ['relationship_to_reference', 'Household relationship'],
  ['household_role', 'Household role'],
  ['household_size', 'Household size'],
  ['ideology_economic', 'Economic ideology'],
  ['ideology_state', 'State ideology'],
  ['ideology_cultural', 'Cultural ideology'],
  ['openness', 'Openness'],
  ['conscientiousness', 'Conscientiousness'],
  ['extraversion', 'Extraversion'],
  ['agreeableness', 'Agreeableness'],
  ['neuroticism', 'Neuroticism'],
  ['risk_aversion', 'Risk aversion'],
  ['time_preference', 'Time preference'],
  ['generalized_trust', 'Generalized trust'],
  ['religiosity', 'Religiosity'],
  ['schwartz_values', 'Schwartz values'],
  ['mbti', 'MBTI label'],
] as const;

const conditionOperators = [
  ['equals', 'Equals'],
  ['not_equals', 'Does not equal'],
  ['at_least', 'At least'],
  ['at_most', 'At most'],
  ['between', 'Between'],
] as const;

export class AtlasPopulationGenerator {
  private readonly client: AtlasPopulationClient;
  private places = new Map<string, AtlasPlaceSelector>();
  private result?: AtlasPopulationResult;
  private nextRuleId = 1;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: AtlasPopulationGeneratorOptions = {},
  ) {
    this.client = options.client ?? createAtlasPopulationHttpClient();
  }

  mount(): void {
    this.host.addEventListener('submit', this.onSubmit);
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
    this.render();
    void this.loadPlaces('');
  }

  destroy(): void {
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.host.replaceChildren();
  }

  private render(): void {
    const configuredTypes = this.options.agentTypes?.() ?? [];
    const fallbackType = configuredTypes[0]?.id ?? 'person';
    const fallbackControl = configuredTypes.length
      ? `<select name="agent_type_id" required>${configuredTypes.map((agentType) => `<option value="${escapeHtml(agentType.id)}">${escapeHtml(agentType.name)} · ${escapeHtml(agentType.id)}</option>`).join('')}</select>`
      : `<input name="agent_type_id" value="${fallbackType}" pattern="[a-zA-Z][a-zA-Z0-9_-]*" required>`;
    this.host.innerHTML = `
      <section class="atlas-population-generator" aria-label="Generate population from atlas">
        <header>
          <div><span>DATA ATLAS</span><h2>Generate initial agents</h2><p>Select a place and sample its imported distributions with a repeatable seed.</p></div>
          <strong>Evidence-backed</strong>
        </header>
        <form data-atlas-population-form>
          <div class="atlas-population-grid">
            <label class="atlas-population-search">Find a place<input name="search" autocomplete="off" placeholder="Country, region, or city"></label>
            <button class="button secondary" name="action" value="search" type="submit">Search</button>
            <label>Place<select name="place" aria-label="Place" required><option value="">Loading places…</option></select></label>
            <label>Agents<input name="target_agents" type="number" min="1" max="100000" step="1" value="1000" required></label>
            <label>Seed<input name="seed" type="number" step="1" value="42" required></label>
            <label>Data scope<span class="atlas-population-scope">Shared atlas</span><input name="scope" type="hidden" value="shared"></label>
            <label>Fallback type${fallbackControl}</label>
          </div>
          <section class="atlas-type-assignment" aria-label="Agent type assignment">
            <header><div><strong>Agent type rules</strong><span>Assign types from sampled Atlas values. Overlapping rules give an agent multiple types.</span></div><button class="button secondary" data-type-rule-action="add" type="button">Add type rule</button></header>
            <div class="atlas-type-rule-list" data-type-rule-list><p data-type-rule-empty>Everyone receives the fallback type until you add a rule.</p></div>
            <label class="atlas-type-rule-confirmation" hidden><input name="confirm_type_rules" type="checkbox">Confirm these type assignment rules</label>
          </section>
          <div class="atlas-population-actions">
            <p>Run-scoped imports stay inside the named scope. Missing fields remain unknown.</p>
            <button class="button primary" name="action" value="generate" type="submit">Generate from atlas</button>
          </div>
          <div class="atlas-population-feedback" role="alert" hidden></div>
          <div class="atlas-population-result" role="status" hidden></div>
        </form>
      </section>`;
  }

  private onSubmit = (event: SubmitEvent): void => {
    const form = event.target as HTMLFormElement;
    if (!form.matches('[data-atlas-population-form]')) return;
    event.preventDefault();
    const submitter = event.submitter as HTMLButtonElement | null;
    const data = new FormData(form);
    if (submitter?.value === 'search') {
      void this.loadPlaces(String(data.get('search') ?? ''));
      return;
    }
    void this.generate(data);
  };

  private onClick = (event: Event): void => {
    const target = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-type-rule-action]',
    );
    if (!target) return;
    const action = target.dataset.typeRuleAction;
    if (action === 'add') this.addTypeRule();
    if (action === 'remove') {
      target.closest<HTMLElement>('[data-type-rule]')?.remove();
      this.updateTypeRuleState();
    }
  };

  private onChange = (event: Event): void => {
    const eventTarget = event.target as HTMLElement;
    if (eventTarget.closest('[data-type-rule]')) this.clearTypeRuleConfirmation();
    const select = eventTarget.closest<HTMLSelectElement>(
      'select[data-type-rule-operator]',
    );
    if (!select) return;
    const row = select.closest<HTMLElement>('[data-type-rule]');
    const upper = row?.querySelector<HTMLElement>('[data-type-rule-upper]');
    const input = upper?.querySelector<HTMLInputElement>('input');
    if (!upper || !input) return;
    const between = select.value === 'between';
    upper.hidden = !between;
    input.disabled = !between;
    input.required = between;
  };

  private addTypeRule(): void {
    const list = this.host.querySelector<HTMLElement>('[data-type-rule-list]');
    if (!list) return;
    const ordinal = this.nextRuleId++;
    list.insertAdjacentHTML('beforeend', this.typeRuleMarkup(ordinal));
    this.updateTypeRuleState();
  }

  private typeRuleMarkup(ordinal: number): string {
    const fieldOptions = assignmentFields
      .map(([value, label]) => `<option value="${value}">${label}</option>`)
      .join('');
    const operatorOptions = conditionOperators
      .map(([value, label]) => `<option value="${value}">${label}</option>`)
      .join('');
    const configuredTypes = this.options.agentTypes?.() ?? [];
    const agentTypeControl = configuredTypes.length
      ? `<select data-type-rule-agent-type>${configuredTypes.map((agentType) => `<option value="${escapeHtml(agentType.id)}">${escapeHtml(agentType.name)} · ${escapeHtml(agentType.id)}</option>`).join('')}</select>`
      : '<input data-type-rule-agent-type pattern="[a-zA-Z][a-zA-Z0-9_-]*" placeholder="worker" required>';
    return `
      <fieldset class="atlas-type-rule" data-type-rule data-rule-id="rule-${ordinal}">
        <legend>Rule ${ordinal}</legend>
        <label>Assigned type for rule ${ordinal}${agentTypeControl}</label>
        <label>Atlas field for rule ${ordinal}<select data-type-rule-field>${fieldOptions}</select></label>
        <label>Match for rule ${ordinal}<select data-type-rule-operator>${operatorOptions}</select></label>
        <label>Value for rule ${ordinal}<input data-type-rule-value required></label>
        <label data-type-rule-upper hidden>Maximum for rule ${ordinal}<input data-type-rule-upper-value disabled></label>
        <button class="button secondary" data-type-rule-action="remove" type="button" aria-label="Remove rule ${ordinal}">Remove</button>
      </fieldset>`;
  }

  private updateTypeRuleState(): void {
    const hasRules = Boolean(this.host.querySelector('[data-type-rule]'));
    const empty = this.host.querySelector<HTMLElement>('[data-type-rule-empty]');
    const confirmation = this.host.querySelector<HTMLElement>(
      '.atlas-type-rule-confirmation',
    );
    if (empty) empty.hidden = hasRules;
    if (confirmation) confirmation.hidden = !hasRules;
    this.clearTypeRuleConfirmation();
  }

  private clearTypeRuleConfirmation(): void {
    const input = this.host.querySelector<HTMLInputElement>(
      'input[name="confirm_type_rules"]',
    );
    if (input) input.checked = false;
  }

  private async loadPlaces(search: string): Promise<void> {
    this.setBusy(true);
    this.feedback('');
    try {
      const places = await this.client.places(search.trim());
      this.places = new Map(places.map((place) => [placeKey(place), place]));
      const select = this.host.querySelector<HTMLSelectElement>('select[name="place"]')!;
      select.innerHTML = places.length
        ? places
            .map(
              (place) =>
                `<option value="${escapeHtml(placeKey(place))}">${escapeHtml(place.label)} · ${escapeHtml(place.level)}</option>`,
            )
            .join('')
        : '<option value="">No matching places</option>';
    } catch (error) {
      this.feedback(error instanceof Error ? error.message : String(error));
    } finally {
      this.setBusy(false);
    }
  }

  private async generate(data: FormData): Promise<void> {
    const selector = this.places.get(String(data.get('place') ?? ''));
    if (!selector) {
      this.feedback('Choose a place before generating agents.');
      return;
    }
    const targetAgents = Number(data.get('target_agents'));
    const seed = Number(data.get('seed'));
    if (!Number.isInteger(targetAgents) || targetAgents < 1 || !Number.isInteger(seed)) {
      this.feedback('Agents must be a positive integer and seed must be an integer.');
      return;
    }
    const fallbackAgentType = String(data.get('agent_type_id') ?? '').trim();
    if (!agentTypeIdPattern.test(fallbackAgentType)) {
      this.feedback('Fallback type must start with a letter and use letters, numbers, _ or -.');
      return;
    }
    let typeAssignment: AtlasAgentTypeAssignment | undefined;
    try {
      typeAssignment = this.readTypeAssignment(fallbackAgentType, data);
    } catch (error) {
      this.feedback(error instanceof Error ? error.message : String(error));
      return;
    }
    this.setBusy(true);
    this.feedback('');
    try {
      this.result = await this.client.materialize({
        population_id: `atlas-${selector.level}-${selector.place}`,
        selector,
        scope: String(data.get('scope') ?? '').trim(),
        seed,
        target_agents: targetAgents,
        agent_type_id: fallbackAgentType,
        ...(typeAssignment ? { type_assignment: typeAssignment } : {}),
      });
      this.renderResult();
      this.options.onGenerated?.(this.result);
    } catch (error) {
      this.feedback(error instanceof Error ? error.message : String(error));
    } finally {
      this.setBusy(false);
    }
  }

  private readTypeAssignment(
    fallbackAgentType: string,
    data: FormData,
  ): AtlasAgentTypeAssignment | undefined {
    const rows = [...this.host.querySelectorAll<HTMLElement>('[data-type-rule]')];
    if (!rows.length) return undefined;
    if (data.get('confirm_type_rules') !== 'on') {
      throw new Error('Confirm the type assignment rules before generating agents.');
    }
    const rules = rows.map((row, index): AtlasAgentTypeRule => {
      const agentTypeId = row
        .querySelector<HTMLInputElement | HTMLSelectElement>('[data-type-rule-agent-type]')!
        .value.trim();
      const field = row.querySelector<HTMLSelectElement>('[data-type-rule-field]')!.value;
      const operator = row.querySelector<HTMLSelectElement>('[data-type-rule-operator]')!
        .value as AtlasAgentTypeCondition['operator'];
      const valueText = row
        .querySelector<HTMLInputElement>('[data-type-rule-value]')!
        .value.trim();
      if (!agentTypeIdPattern.test(agentTypeId)) {
        throw new Error(`Rule ${index + 1} needs a valid assigned type.`);
      }
      if (!valueText) throw new Error(`Rule ${index + 1} needs a match value.`);
      const numeric = ['at_least', 'at_most', 'between'].includes(operator);
      const value = numeric ? Number(valueText) : valueText;
      if (numeric && !Number.isFinite(value)) {
        throw new Error(`Rule ${index + 1} needs a numeric value.`);
      }
      const condition: AtlasAgentTypeCondition = { field, operator, value };
      if (operator === 'between') {
        const upperText = row
          .querySelector<HTMLInputElement>('[data-type-rule-upper-value]')!
          .value.trim();
        const upperValue = Number(upperText);
        if (!upperText || !Number.isFinite(upperValue)) {
          throw new Error(`Rule ${index + 1} needs a numeric upper value.`);
        }
        condition.upper_value = upperValue;
      }
      return {
        id: row.dataset.ruleId ?? `rule-${index + 1}`,
        agent_type_ids: [agentTypeId],
        conditions: [condition],
      };
    });
    return {
      status: 'confirmed',
      fallback_agent_type_id: fallbackAgentType,
      rules,
    };
  }

  private renderResult(): void {
    if (!this.result) return;
    const result = this.host.querySelector<HTMLElement>('.atlas-population-result')!;
    const measured = this.result.feature_coverage.filter(
      (feature) => feature.measured_agents > 0,
    );
    const imputed = this.result.feature_coverage.filter(
      (feature) => feature.imputed_agents > 0,
    );
    const unknown = this.result.feature_coverage.filter(
      (feature) => feature.unknown_agents > 0,
    );
    const typeCounts = Object.entries(this.result.agent_type_counts ?? {}).sort(
      ([leftType, leftCount], [rightType, rightCount]) =>
        rightCount - leftCount || leftType.localeCompare(rightType),
    );
    result.innerHTML = `
      <strong>${this.result.materialization.population.agents.length.toLocaleString()} agents generated for ${escapeHtml(this.result.selector.label)}</strong>
      <div><span>${measured.length} measured features</span><span>${imputed.length} imputed features</span><span>${unknown.length} features with unknown values</span></div>
      ${typeCounts.length ? `<small><strong>Deterministic type memberships:</strong> ${typeCounts.map(([agentType, count]) => `${escapeHtml(featureLabel(agentType))} ${count.toLocaleString()}`).join(' · ')}</small>` : ''}
      ${unknown.length ? `<small>Missing: ${unknown.slice(0, 6).map((item) => escapeHtml(featureLabel(item.feature_id))).join(', ')}${unknown.length > 6 ? ` +${unknown.length - 6} more` : ''}</small>` : ''}
      ${this.result.warnings.map((warning) => `<small>${escapeHtml(warning)}</small>`).join('')}`;
    result.hidden = false;
  }

  private feedback(message: string): void {
    const feedback = this.host.querySelector<HTMLElement>('.atlas-population-feedback');
    if (!feedback) return;
    feedback.textContent = message;
    feedback.hidden = !message;
  }

  private setBusy(busy: boolean): void {
    this.host.setAttribute('aria-busy', String(busy));
    this.host.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
      button.disabled = busy;
    });
  }
}
