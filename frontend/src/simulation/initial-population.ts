import './initial-population.css';

export type PopulationEvidenceStatus =
  | 'measured_joint'
  | 'measured_marginal'
  | 'imputed'
  | 'unknown';

export type PopulationEvidenceReference = {
  evidence_id: string;
  source: string;
  source_version: string;
  observed_at: string;
  licence: string;
  place: string;
  status: PopulationEvidenceStatus;
  fields: string[];
  uncertainty: string;
  url: string | null;
};

export type HouseholdRelationship =
  | 'self'
  | 'spouse'
  | 'child'
  | 'parent'
  | 'sibling'
  | 'other';

export type HouseholdMemberSeed = {
  member_id: string;
  name: string | null;
  age: number;
  sex: string;
  relationship_to_reference: HouseholdRelationship;
  agent_types: string[];
  traits: Record<string, unknown>;
  states: Record<string, string>;
  field_evidence: Record<string, string>;
};

export type HouseholdSeed = {
  template_id: string;
  place: string;
  country: string;
  region: string | null;
  city: string;
  neighbourhood: string | null;
  latitude: number;
  longitude: number;
  weight: number;
  evidence_id: string;
  members: HouseholdMemberSeed[];
};

export type InitialPopulationDraft = {
  population_id: string;
  version: string;
  seed: number;
  target_agents: number;
  household_templates: HouseholdSeed[];
  evidence: PopulationEvidenceReference[];
};

export type InitialPopulationValidationIssue = {
  code: string;
  path: string;
  message: string;
};

export type InitialPopulationValidation = {
  valid: boolean;
  issues: InitialPopulationValidationIssue[];
};

export type InitialPopulationMaterialization = {
  input_hash: string;
  validation: InitialPopulationValidation;
  population: {
    population_id: string;
    version: string;
    seed: number;
    agents: Array<{ agent_id: string; traits: Record<string, unknown> }>;
  };
  provenance: Record<string, unknown>;
};

export type InitialPopulationClient = {
  validate(draft: InitialPopulationDraft): Promise<InitialPopulationValidation>;
  materialize(draft: InitialPopulationDraft): Promise<InitialPopulationMaterialization>;
};

export type InitialPopulationEditorOptions = {
  draft: InitialPopulationDraft;
  client: InitialPopulationClient;
  onSaved?: (result: InitialPopulationMaterialization) => void;
};

const relationships: HouseholdRelationship[] = [
  'self',
  'spouse',
  'child',
  'parent',
  'sibling',
  'other',
];

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function validationIssue(
  code: string,
  path: string,
  message: string,
): InitialPopulationValidationIssue {
  return { code, path, message };
}

function reachablePopulationSize(draft: InitialPopulationDraft): boolean {
  const sizes = new Set(draft.household_templates.map((template) => template.members.length));
  const reachable = Array.from({ length: draft.target_agents + 1 }, () => false);
  reachable[0] = true;
  for (let total = 1; total <= draft.target_agents; total += 1) {
    reachable[total] = [...sizes].some(
      (size) => size <= total && reachable[total - size],
    );
  }
  return reachable[draft.target_agents];
}

export function validateInitialPopulationDraft(
  draft: InitialPopulationDraft,
): InitialPopulationValidation {
  const issues: InitialPopulationValidationIssue[] = [];
  if (!Number.isInteger(draft.seed)) {
    issues.push(validationIssue('invalid_seed', 'seed', 'Seed must be an integer.'));
  }
  if (!Number.isInteger(draft.target_agents) || draft.target_agents < 1) {
    issues.push(
      validationIssue(
        'invalid_target_agents',
        'target_agents',
        'Number of agents must be a positive integer.',
      ),
    );
  }
  if (draft.target_agents > 0 && !reachablePopulationSize(draft)) {
    issues.push(
      validationIssue(
        'population_size_unreachable',
        'target_agents',
        'The requested population cannot be formed without splitting a household.',
      ),
    );
  }
  draft.household_templates.forEach((template, templateIndex) => {
    const path = `household_templates.${templateIndex}`;
    const referenceMembers = template.members.filter(
      (member) => member.relationship_to_reference === 'self',
    );
    if (referenceMembers.length !== 1) {
      issues.push(
        validationIssue(
          'invalid_reference_member',
          `${path}.members`,
          `${template.template_id} requires exactly one reference member.`,
        ),
      );
      return;
    }
    const adults = template.members.filter((member) => member.age >= 18);
    if (adults.length === 0) {
      issues.push(
        validationIssue(
          'household_without_adult',
          `${path}.members`,
          `${template.template_id} has no adult.`,
        ),
      );
    }
    const children = template.members.filter(
      (member) => member.relationship_to_reference === 'child',
    );
    const parents = children.length
      ? template.members.filter((member) =>
          ['self', 'spouse', 'parent'].includes(member.relationship_to_reference),
        )
      : template.members.filter((member) => member.relationship_to_reference === 'parent');
    parents.forEach((parent) => {
      if (parent.age < 16) {
        issues.push(
          validationIssue(
            'parent_too_young',
            `${path}.members.${parent.member_id}.age`,
            `Parent ${parent.name ?? parent.member_id} is younger than 16.`,
          ),
        );
      }
    });
    children.forEach((child) => {
      parents.forEach((parent) => {
        if (child.age >= parent.age) {
          issues.push(
            validationIssue(
              'child_older_than_parent',
              `${path}.members.${child.member_id}.age`,
              `Child ${child.name ?? child.member_id} is not younger than parent ${parent.name ?? parent.member_id}.`,
            ),
          );
        } else if (parent.age - child.age < 12) {
          issues.push(
            validationIssue(
              'parent_age_gap_implausible',
              `${path}.members.${child.member_id}.age`,
              `Parent ${parent.name ?? parent.member_id} is less than 12 years older than child ${child.name ?? child.member_id}.`,
            ),
          );
        }
      });
    });
    const reference = referenceMembers[0];
    template.members
      .filter((member) => member.relationship_to_reference === 'spouse')
      .forEach((spouse) => {
        if (Math.abs(reference.age - spouse.age) > 50) {
          issues.push(
            validationIssue(
              'spouse_age_gap_implausible',
              `${path}.members.${spouse.member_id}.age`,
              `Spouse ages in ${template.template_id} differ by more than 50 years.`,
            ),
          );
        }
      });
  });
  return { valid: issues.length === 0, issues };
}

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : typeof detail?.message === 'string'
          ? detail.message
          : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body as T;
}

export function createInitialPopulationHttpClient(
  endpoint = '/api/simulation/initial-population',
): InitialPopulationClient {
  return {
    async validate(draft) {
      const response = await fetch(`${endpoint}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      return responseBody<InitialPopulationValidation>(response);
    },
    async materialize(draft) {
      const response = await fetch(`${endpoint}/materialize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      return responseBody<InitialPopulationMaterialization>(response);
    },
  };
}

function evidenceLabel(status: PopulationEvidenceStatus): string {
  return status.replace('_', ' ').replace(/^./, (value) => value.toUpperCase());
}

export class InitialPopulationEditor {
  private readonly draft: InitialPopulationDraft;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: InitialPopulationEditorOptions,
  ) {
    this.draft = structuredClone(options.draft);
  }

  mount(): void {
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('change', this.onInput);
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('submit', this.onSubmit);
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('change', this.onInput);
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.replaceChildren();
  }

  value(): InitialPopulationDraft {
    return structuredClone(this.draft);
  }

  private render(): void {
    const evidenceById = new Map(
      this.draft.evidence.map((evidence) => [evidence.evidence_id, evidence]),
    );
    this.host.innerHTML = `
      <section class="initial-population" role="region" aria-label="Initial population setup">
        <header class="initial-population-heading">
          <div>
            <span>INITIAL AGENTS</span>
            <h2>Initial population</h2>
            <p>Households are materialized as linked agents from one joint record.</p>
          </div>
          <strong>${this.draft.household_templates.length} household template${this.draft.household_templates.length === 1 ? '' : 's'}</strong>
        </header>
        <form class="initial-population-form">
          <div class="initial-population-controls">
            <label>Seed<input name="seed" type="number" step="1" value="${this.draft.seed}"></label>
            <label>Number of agents<input name="target_agents" type="number" min="1" step="1" value="${this.draft.target_agents}"></label>
            <p>Complete households only. A target that would split a family is rejected.</p>
          </div>
          <div class="initial-households">
            ${this.draft.household_templates
              .map((template, templateIndex) => {
                const evidence = evidenceById.get(template.evidence_id);
                return this.householdMarkup(template, templateIndex, evidence);
              })
              .join('')}
          </div>
          <div class="initial-population-actions">
            <button type="button" class="button secondary" data-population-action="validate">Validate population</button>
            <button type="submit" class="button primary">Save initial population</button>
          </div>
          <div class="initial-population-errors" role="alert" hidden></div>
          <p class="initial-population-status" role="status" hidden></p>
        </form>
      </section>`;
  }

  private householdMarkup(
    template: HouseholdSeed,
    templateIndex: number,
    evidence: PopulationEvidenceReference | undefined,
  ): string {
    const source = evidence
      ? `<span>${escapeHtml(evidenceLabel(evidence.status))}</span><strong>${escapeHtml(evidence.source)}</strong><small>${escapeHtml(evidence.source_version)} · ${escapeHtml(evidence.observed_at)}</small>`
      : '<span>Unknown evidence</span>';
    return `
      <article class="initial-household" data-household-index="${templateIndex}">
        <header>
          <div><span>HOUSEHOLD TEMPLATE</span><h3>${escapeHtml(template.template_id)}</h3><p>${escapeHtml(template.city)}, ${escapeHtml(template.country)}</p></div>
          <div class="initial-household-evidence">${source}</div>
        </header>
        <div class="initial-household-place">
          <label>Place ID<input data-template-field="place" value="${escapeHtml(template.place)}" required></label>
          <label>Country<input data-template-field="country" value="${escapeHtml(template.country)}" required></label>
          <label>City<input data-template-field="city" value="${escapeHtml(template.city)}" required></label>
          <label>Region<input data-template-field="region" value="${escapeHtml(template.region ?? '')}"></label>
          <label>Latitude<input data-template-field="latitude" type="number" min="-90" max="90" step="any" value="${template.latitude}" required></label>
          <label>Longitude<input data-template-field="longitude" type="number" min="-180" max="180" step="any" value="${template.longitude}" required></label>
        </div>
        <div class="initial-household-member-labels"><span>Name</span><span>Age</span><span>Sex</span><span>Family role</span><span>Agent types</span><span></span></div>
        <div class="initial-household-members">
          ${template.members
            .map((member, memberIndex) =>
              this.memberMarkup(member, templateIndex, memberIndex, template.members.length),
            )
            .join('')}
        </div>
        <button type="button" class="initial-household-add" data-population-action="add-member" data-household-index="${templateIndex}">+ Add household member</button>
      </article>`;
  }

  private memberMarkup(
    member: HouseholdMemberSeed,
    templateIndex: number,
    memberIndex: number,
    memberCount: number,
  ): string {
    const fieldId = `initial-member-${templateIndex}-${memberIndex}`;
    return `
      <div class="initial-household-member" data-household-member data-household-index="${templateIndex}" data-member-index="${memberIndex}">
        <label><span>Name</span><input id="${fieldId}-name" aria-label="Name for ${escapeHtml(member.member_id)}" data-member-field="name" value="${escapeHtml(member.name ?? '')}"></label>
        <label><span>Age</span><input id="${fieldId}-age" aria-label="Age for ${escapeHtml(member.member_id)}" data-member-field="age" type="number" min="0" max="125" step="1" value="${member.age}"></label>
        <label><span>Sex</span><input id="${fieldId}-sex" aria-label="Sex for ${escapeHtml(member.member_id)}" data-member-field="sex" value="${escapeHtml(member.sex)}"></label>
        <label><span>Family role</span><select id="${fieldId}-relationship" aria-label="Family role for ${escapeHtml(member.member_id)}" data-member-field="relationship_to_reference">${relationships.map((value) => `<option value="${value}" ${value === member.relationship_to_reference ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <label><span>Agent types</span><input id="${fieldId}-types" aria-label="Agent types for ${escapeHtml(member.member_id)}" data-member-field="agent_types" value="${escapeHtml(member.agent_types.join(', '))}"></label>
        <button type="button" aria-label="Remove ${escapeHtml(member.name ?? member.member_id)}" data-population-action="remove-member" data-household-index="${templateIndex}" data-member-index="${memberIndex}" ${memberCount === 1 ? 'disabled' : ''}>×</button>
      </div>`;
  }

  private onInput = (event: Event): void => {
    const control = event.target as HTMLInputElement | HTMLSelectElement;
    if (control.name === 'seed' || control.name === 'target_agents') {
      this.draft[control.name] = Number(control.value);
      this.clearFeedback();
      return;
    }
    const templateField = control.dataset.templateField as keyof HouseholdSeed | undefined;
    const templateRow = control.closest<HTMLElement>('[data-household-index]');
    if (templateField && templateRow) {
      const template = this.draft.household_templates[Number(templateRow.dataset.householdIndex)];
      if (!template) return;
      if (templateField === 'latitude' || templateField === 'longitude') {
        template[templateField] = Number(control.value);
      }
      if (templateField === 'place' || templateField === 'country' || templateField === 'city') {
        template[templateField] = control.value.trim();
      }
      if (templateField === 'region') template.region = control.value.trim() || null;
      this.clearFeedback();
      return;
    }
    const field = control.dataset.memberField as keyof HouseholdMemberSeed | undefined;
    const row = control.closest<HTMLElement>('[data-household-member]');
    if (!field || !row) return;
    const templateIndex = Number(row.dataset.householdIndex);
    const memberIndex = Number(row.dataset.memberIndex);
    const member = this.draft.household_templates[templateIndex]?.members[memberIndex];
    if (!member) return;
    if (field === 'age') member.age = Number(control.value);
    if (field === 'name') member.name = control.value.trim() || null;
    if (field === 'sex') member.sex = control.value.trim();
    if (field === 'relationship_to_reference') {
      member.relationship_to_reference = control.value as HouseholdRelationship;
    }
    if (field === 'agent_types') {
      member.agent_types = control.value
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
    }
    this.clearFeedback();
  };

  private onClick = (event: MouseEvent): void => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-population-action]',
    );
    if (!button) return;
    if (button.dataset.populationAction === 'validate') void this.validate();
    if (button.dataset.populationAction === 'add-member') this.addMember(button);
    if (button.dataset.populationAction === 'remove-member') this.removeMember(button);
  };

  private onSubmit = (event: SubmitEvent): void => {
    if (!(event.target as HTMLElement).classList.contains('initial-population-form')) return;
    event.preventDefault();
    void this.save();
  };

  private addMember(button: HTMLButtonElement): void {
    const template = this.draft.household_templates[Number(button.dataset.householdIndex)];
    if (!template) return;
    const previousSize = template.members.length;
    const number = previousSize + 1;
    template.members.push({
      member_id: `member-${number}`,
      name: null,
      age: 18,
      sex: 'unknown',
      relationship_to_reference: 'other',
      agent_types: ['PersonAgent'],
      traits: {},
      states: {},
      field_evidence: {},
    });
    if (this.draft.target_agents === previousSize) this.draft.target_agents = number;
    this.render();
  }

  private removeMember(button: HTMLButtonElement): void {
    const template = this.draft.household_templates[Number(button.dataset.householdIndex)];
    const memberIndex = Number(button.dataset.memberIndex);
    if (!template || template.members.length === 1 || !template.members[memberIndex]) return;
    const previousSize = template.members.length;
    template.members.splice(memberIndex, 1);
    if (this.draft.target_agents === previousSize) this.draft.target_agents = previousSize - 1;
    this.render();
  }

  private async validate(): Promise<InitialPopulationValidation> {
    this.clearFeedback();
    const local = validateInitialPopulationDraft(this.draft);
    if (!local.valid) {
      this.showIssues(local.issues);
      return local;
    }
    this.setBusy(true);
    try {
      const validation = await this.options.client.validate(this.value());
      if (validation.valid) this.showStatus('Population is valid and ready to save.');
      else this.showIssues(validation.issues);
      return validation;
    } catch (error) {
      this.showError(error);
      return {
        valid: false,
        issues: [
          validationIssue(
            'validation_request_failed',
            '',
            error instanceof Error ? error.message : String(error),
          ),
        ],
      };
    } finally {
      this.setBusy(false);
    }
  }

  private async save(): Promise<void> {
    const validation = await this.validate();
    if (!validation.valid) return;
    this.setBusy(true);
    this.clearFeedback();
    try {
      const result = await this.options.client.materialize(this.value());
      if (!result.validation.valid) {
        this.showIssues(result.validation.issues);
        return;
      }
      this.options.onSaved?.(result);
      this.showStatus(`${result.population.agents.length} initial agents saved.`);
    } catch (error) {
      this.showError(error);
    } finally {
      this.setBusy(false);
    }
  }

  private clearFeedback(): void {
    const status = this.host.querySelector<HTMLElement>('.initial-population-status');
    const errors = this.host.querySelector<HTMLElement>('.initial-population-errors');
    if (status) {
      status.hidden = true;
      status.textContent = '';
    }
    if (errors) {
      errors.hidden = true;
      errors.replaceChildren();
    }
  }

  private showStatus(message: string): void {
    const status = this.host.querySelector<HTMLElement>('.initial-population-status');
    if (!status) return;
    status.textContent = message;
    status.hidden = false;
  }

  private showIssues(issues: InitialPopulationValidationIssue[]): void {
    const errors = this.host.querySelector<HTMLElement>('.initial-population-errors');
    if (!errors) return;
    const list = document.createElement('ul');
    issues.forEach((item) => {
      const row = document.createElement('li');
      row.textContent = item.message;
      list.append(row);
    });
    errors.replaceChildren(list);
    errors.hidden = false;
  }

  private showError(error: unknown): void {
    this.showIssues([
      validationIssue(
        'request_failed',
        '',
        error instanceof Error ? error.message : String(error),
      ),
    ]);
  }

  private setBusy(value: boolean): void {
    this.host.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
      button.disabled = value;
    });
    this.host.setAttribute('aria-busy', String(value));
  }
}
