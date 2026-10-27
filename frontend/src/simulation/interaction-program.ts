import './interaction-program.css';

type EvidenceStatus =
  | 'measured_joint'
  | 'fitted_model'
  | 'approved_estimate'
  | 'unknown'
  | 'label_only'
  | 'ambiguous'
  | 'legacy';

interface FactorProvenance {
  source: string;
  version: string;
  source_date: string | null;
  evidence_id: string | null;
  licence: string | null;
  status: EvidenceStatus;
  uncertainty: number;
  user_approved: boolean;
}

interface InteractionFactor {
  id: string;
  label: string;
  value: number;
  provenance: FactorProvenance;
}

interface RelationshipEvidence {
  kind: string;
  weight: number;
  trust: number;
  similarity: number;
  provenance: FactorProvenance;
}

interface TimeFactor {
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  factor: InteractionFactor;
}

interface InteractionRule {
  id: string;
  source_action: string;
  interaction_type: string;
  channel: 'in_person' | 'phone_message' | 'online';
  max_targets_per_initiator: number;
  allowed_relationships: string[];
  allowed_place_kinds: string[];
  base_factor: InteractionFactor;
  relationship_factors: Record<string, InteractionFactor>;
  colocation_factors: Record<string, InteractionFactor>;
  place_factors: Record<string, InteractionFactor>;
  time_factors: TimeFactor[];
  context_factors: InteractionFactor[];
  unrelated_relationship: {
    kind: string;
    weight: number;
    trust: number;
    similarity: number;
  } | null;
  agent_effects: unknown[];
  relationship_effects: unknown[];
  interaction_tree_id: string | null;
  interaction_tree_context: Record<string, string | number | boolean>;
}

interface InteractionProgram {
  version: string;
  status: 'draft' | 'confirmed';
  relationship_evidence: RelationshipEvidence[];
  rules: InteractionRule[];
}

interface InteractionProgramView {
  configured: boolean;
  program: InteractionProgram;
}

interface ValidationIssue {
  path: string;
  message: string;
}

interface InteractionProgramValidation {
  valid: boolean;
  issues: ValidationIssue[];
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

async function responseBody<T>(response: Response): Promise<T> {
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (typeof value === 'object' && value !== null && 'detail' in value) {
      const detail = value.detail;
      if (typeof detail === 'string') throw new Error(detail);
      if (Array.isArray(detail)) {
        throw new Error(
          detail
            .map((item) =>
              typeof item === 'object' && item !== null && 'message' in item
                ? String(item.message)
                : JSON.stringify(item),
            )
            .join('; '),
        );
      }
    }
    throw new Error(`Request failed (${response.status})`);
  }
  return value as T;
}

function factorRows(rule: InteractionRule): Array<[string, InteractionFactor]> {
  return [
    ['Channel baseline', rule.base_factor],
    ...Object.entries(rule.relationship_factors).map(
      ([key, factor]) => [`Relationship · ${key}`, factor] as [string, InteractionFactor],
    ),
    ...Object.entries(rule.colocation_factors).map(
      ([key, factor]) => [`Co-location · ${key}`, factor] as [string, InteractionFactor],
    ),
    ...Object.entries(rule.place_factors).map(
      ([key, factor]) => [`Place · ${key}`, factor] as [string, InteractionFactor],
    ),
    ...rule.time_factors.map(
      (window) =>
        [
          `Time · days ${window.weekdays.join(', ')} · ${window.start_hour}:00–${window.end_hour}:00`,
          window.factor,
        ] as [string, InteractionFactor],
    ),
    ...rule.context_factors.map(
      (factor) => [`Context · ${factor.label}`, factor] as [string, InteractionFactor],
    ),
  ];
}

function factorReceipt(label: string, factor: InteractionFactor): string {
  const provenance = factor.provenance;
  return `
    <li>
      <div><strong>${escapeHtml(label)}</strong><span>× ${factor.value.toLocaleString('en', { maximumFractionDigits: 6 })}</span></div>
      <p>${escapeHtml(provenance.source)} · ${escapeHtml(provenance.version)}</p>
      <small>${escapeHtml(provenance.status.replaceAll('_', ' '))} · ${escapeHtml(provenance.source_date ?? 'date missing')} · uncertainty ±${provenance.uncertainty.toLocaleString('en', { maximumFractionDigits: 6 })}</small>
      <small>${escapeHtml(provenance.evidence_id ?? 'evidence id missing')}${provenance.licence ? ` · ${escapeHtml(provenance.licence)}` : ''}</small>
    </li>`;
}

function programPreview(program: InteractionProgram): string {
  const relationshipEvidence = program.relationship_evidence.length
    ? program.relationship_evidence
        .map(
          (item) => `
            <article>
              <div><span>${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.provenance.status.replaceAll('_', ' '))}</strong></div>
              <p>Weight ${item.weight.toLocaleString('en')} · trust ${item.trust.toLocaleString('en')} · similarity ${item.similarity.toLocaleString('en')}</p>
              <p>Network edge ${(
                item.weight *
                Math.abs(item.trust) *
                Math.abs(item.similarity)
              ).toLocaleString('en', { maximumFractionDigits: 6 })} = weight × |trust| × |similarity|</p>
              <small>${escapeHtml(item.provenance.source)} · ${escapeHtml(item.provenance.version)} · ${escapeHtml(item.provenance.source_date ?? 'date missing')}</small>
              <small>Uncertainty ±${item.provenance.uncertainty.toLocaleString('en')} · ${escapeHtml(item.provenance.evidence_id ?? 'evidence id missing')}</small>
            </article>`,
        )
        .join('')
    : '<p class="interaction-program-empty">No relationship evidence is registered. Relationship weights, trust, and similarity remain blocked.</p>';
  const rules = program.rules.length
    ? program.rules
        .map(
          (rule) => `
            <article class="interaction-program-rule">
              <header>
                <div><span>${escapeHtml(rule.channel.replaceAll('_', ' '))}</span><h3>${escapeHtml(rule.id)}</h3></div>
                <strong>${escapeHtml(rule.interaction_type)}</strong>
              </header>
              <p class="interaction-program-formula">P(${escapeHtml(rule.interaction_type)} | ${escapeHtml(rule.source_action)}) = channel baseline × relationship × co-location × place × time${rule.context_factors.length ? ' × context' : ''}</p>
              <dl>
                <div><dt>Trigger</dt><dd>${escapeHtml(rule.source_action)}</dd></div>
                <div><dt>Relationships</dt><dd>${escapeHtml(rule.allowed_relationships.join(', ') || 'Any evidenced kind')}</dd></div>
                <div><dt>Places</dt><dd>${escapeHtml(rule.allowed_place_kinds.join(', ') || 'Any evidenced place')}</dd></div>
                <div><dt>Outcome tree</dt><dd>${escapeHtml(rule.interaction_tree_id ?? 'Direct effects')}</dd></div>
              </dl>
              <ul>${factorRows(rule).map(([label, factor]) => factorReceipt(label, factor)).join('')}</ul>
            </article>`,
        )
        .join('')
    : '<p class="interaction-program-empty">No rules are authored. A confirmed program requires at least one fully evidenced rule.</p>';
  return `
    <section class="interaction-program-preview" aria-label="Interaction program evidence">
      <div><span class="small-label">RELATIONSHIP EVIDENCE</span><h3>Weights and affinity</h3></div>
      <div class="interaction-program-relationships">${relationshipEvidence}</div>
      <div><span class="small-label">EXECUTION RULES</span><h3>Probability formulas</h3></div>
      <div class="interaction-program-rules">${rules}</div>
    </section>`;
}

export class InteractionProgramEditor {
  private input?: HTMLTextAreaElement;
  private validation?: InteractionProgramValidation;
  private confirmed = false;
  private disposed = false;

  constructor(private readonly host: HTMLElement) {}

  async mount(): Promise<void> {
    this.host.innerHTML = '<div class="simulation-tree-loading" role="status">Loading interaction program…</div>';
    try {
      const view = await responseBody<InteractionProgramView>(
        await fetch('/api/simulation/interaction-program'),
      );
      if (this.disposed) return;
      const draft: InteractionProgram = { ...view.program, status: 'draft' };
      this.render(draft, view.configured ? view.program.status : 'draft');
    } catch (error) {
      if (this.disposed) return;
      this.host.innerHTML = `<div class="simulation-tree-loading error" role="alert">${escapeHtml(error instanceof Error ? error.message : String(error))}</div>`;
    }
  }

  destroy(): void {
    this.disposed = true;
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('input', this.onInput);
    this.host.replaceChildren();
  }

  private render(program: InteractionProgram, persistedStatus: string): void {
    this.host.innerHTML = `
      <div class="interaction-program-heading">
        <div><span class="small-label">EVIDENCE-GATED INTERACTIONS</span><h2>Interaction program</h2><p>Author relationship, channel, place, and time factors. Validation blocks unknown evidence and unreachable rules before Rust execution.</p></div>
        <strong data-interaction-program-persisted>${escapeHtml(persistedStatus)}</strong>
      </div>
      <div class="interaction-program-layout">
        <section class="interaction-program-editor" aria-label="Interaction program editor">
          <label for="interaction-program-json">Program JSON</label>
          <textarea id="interaction-program-json" spellcheck="false"></textarea>
          <div class="interaction-program-actions">
            <button type="button" class="button secondary" data-interaction-program-action="format">Format</button>
            <button type="button" class="button secondary" data-interaction-program-action="validate">Validate</button>
          </div>
          <div data-interaction-program-validation role="status"></div>
          <label class="interaction-program-confirm"><input type="checkbox" data-interaction-program-confirm> <span>I reviewed every probability, evidence source, and effect.</span></label>
          <button type="button" class="button primary" data-interaction-program-action="confirm" disabled>Confirm and save</button>
        </section>
        <div data-interaction-program-preview>${programPreview(program)}</div>
      </div>`;
    this.input = this.host.querySelector<HTMLTextAreaElement>('#interaction-program-json')!;
    this.input.value = JSON.stringify(program, null, 2);
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('input', this.onInput);
  }

  private parse(): InteractionProgram {
    if (!this.input) throw new Error('Interaction program editor is not mounted');
    const value: unknown = JSON.parse(this.input.value);
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      throw new Error('The program must be a JSON object');
    }
    return value as InteractionProgram;
  }

  private async validate(): Promise<InteractionProgramValidation> {
    const program = { ...this.parse(), status: 'draft' as const };
    const response = await fetch('/api/simulation/interaction-program/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(program),
    });
    this.validation = await responseBody<InteractionProgramValidation>(response);
    this.renderValidation();
    this.updatePreview(program);
    return this.validation;
  }

  private renderValidation(error?: unknown): void {
    const host = this.host.querySelector<HTMLElement>('[data-interaction-program-validation]')!;
    if (error) {
      host.className = 'interaction-program-validation blocked';
      host.innerHTML = `<strong>Blocked</strong><p>${escapeHtml(error instanceof Error ? error.message : String(error))}</p>`;
      return;
    }
    if (!this.validation) {
      host.className = '';
      host.replaceChildren();
      return;
    }
    if (this.validation.valid) {
      host.className = 'interaction-program-validation ready';
      host.innerHTML = '<strong>Ready to confirm</strong><p>All probability and relationship evidence is executable.</p>';
      return;
    }
    host.className = 'interaction-program-validation blocked';
    host.innerHTML = `<strong>Blocked reasons</strong><ul>${this.validation.issues.map((issue) => `<li><span>${escapeHtml(issue.path || 'program')}</span>${escapeHtml(issue.message)}</li>`).join('')}</ul>`;
  }

  private updatePreview(program: InteractionProgram): void {
    this.host.querySelector<HTMLElement>('[data-interaction-program-preview]')!.innerHTML =
      programPreview(program);
  }

  private updateConfirmButton(): void {
    const button = this.host.querySelector<HTMLButtonElement>(
      '[data-interaction-program-action="confirm"]',
    );
    if (button) button.disabled = !(this.confirmed && this.validation?.valid);
  }

  private onInput = (event: Event): void => {
    if (event.target === this.input) {
      this.validation = undefined;
      this.confirmed = false;
      const checkbox = this.host.querySelector<HTMLInputElement>(
        '[data-interaction-program-confirm]',
      );
      if (checkbox) checkbox.checked = false;
      this.renderValidation();
      this.updateConfirmButton();
      return;
    }
    const checkbox = (event.target as HTMLElement).closest<HTMLInputElement>(
      '[data-interaction-program-confirm]',
    );
    if (checkbox) {
      this.confirmed = checkbox.checked;
      this.updateConfirmButton();
    }
  };

  private onClick = (event: MouseEvent): void => {
    const action = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-interaction-program-action]',
    )?.dataset.interactionProgramAction;
    if (action === 'format') {
      try {
        const program = this.parse();
        if (this.input) this.input.value = JSON.stringify(program, null, 2);
        this.updatePreview(program);
        this.renderValidation();
      } catch (error) {
        this.renderValidation(error);
      }
    }
    if (action === 'validate') {
      void this.validate().catch((error) => this.renderValidation(error));
    }
    if (action === 'confirm') void this.confirmProgram();
  };

  private async confirmProgram(): Promise<void> {
    try {
      const validation = await this.validate();
      if (!validation.valid || !this.confirmed) return;
      const program = { ...this.parse(), status: 'confirmed' as const };
      const view = await responseBody<InteractionProgramView>(
        await fetch('/api/simulation/interaction-program/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ program, user_confirmed: true }),
        }),
      );
      if (this.input) this.input.value = JSON.stringify({ ...view.program, status: 'draft' }, null, 2);
      this.host.querySelector<HTMLElement>('[data-interaction-program-persisted]')!.textContent =
        'confirmed';
      const status = this.host.querySelector<HTMLElement>(
        '[data-interaction-program-validation]',
      )!;
      status.className = 'interaction-program-validation saved';
      status.innerHTML = `<strong>Confirmed and saved</strong><p>Version ${escapeHtml(view.program.version)} is now eligible for Rust run preparation.</p>`;
      this.confirmed = false;
      this.validation = undefined;
      const checkbox = this.host.querySelector<HTMLInputElement>(
        '[data-interaction-program-confirm]',
      )!;
      checkbox.checked = false;
      this.updateConfirmButton();
      this.updatePreview(view.program);
    } catch (error) {
      this.renderValidation(error);
    }
  }
}
