import { api } from '../api';
import type { DSLConfig, DSLValidationResult } from '../contracts.generated';
import { escapeHtml } from '../views';

export class DSLBuilder {
  private dsl?: DSLConfig;
  private validation?: DSLValidationResult;
  private loaded = false;
  private timer?: ReturnType<typeof setTimeout>;
  private featureDraft = false;

  constructor(
    private host: HTMLElement,
    private onRun: (dsl: DSLConfig, seed: number) => Promise<void>,
  ) {
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('input', this.onInput);
  }

  async activate(): Promise<void> {
    if (!this.loaded) {
      this.host.innerHTML = this.shell();
      this.loaded = true;
      try {
        this.dsl = await api.smokeDSL();
        this.textarea().value = JSON.stringify(this.dsl, null, 2);
        await this.validate();
      } catch (error) {
        this.showError(error);
      }
    }
  }

  deactivate(): void {
    clearTimeout(this.timer);
  }

  private shell(): string {
    return `
      <section class="builder-header">
        <div><p class="eyebrow">DSL BUILDER / V1 JSON</p><h1>Define the rules. Prove the numbers.</h1><p>Model hypotheses, coefficient evidence, and population distributions stay separate and visible.</p></div>
        <div class="builder-actions"><label>Seed<input id="dsl-seed" type="number" min="0" max="4294967295" value="42"></label><button class="button primary" data-dsl-action="run">Run validated DSL ↗</button></div>
      </section>
      <div class="builder-grid">
        <section class="builder-column"><span class="small-label">DEMOGRAPHICS / FEATURES</span><h2>Who exists</h2><div id="dsl-features"></div><button class="button secondary" data-dsl-action="add-feature">＋ Add eye colour</button><p class="builder-principle">Distribution data proves a feature exists. Without it, the feature remains label-only.</p></section>
        <section class="builder-column"><span class="small-label">ACTIONS / OUTCOMES</span><h2>What can happen</h2><div id="dsl-actions"></div></section>
        <section class="builder-column"><span class="small-label">RELATIONSHIPS / COEFFICIENTS</span><h2>What predicts what</h2><div id="dsl-coefficients"></div><p class="builder-principle">Joint trait + outcome data proves a predictor. A marginal distribution alone never creates a coefficient.</p></section>
      </div>
      <section class="builder-console">
        <div class="builder-console-heading"><div><span class="small-label">DSL PREVIEW + VALIDATION</span><h2>Single source of truth</h2></div><span id="dsl-validation-badge" class="status-pill">Loading</span></div>
        <div class="builder-console-grid"><label class="dsl-editor-label">JSON<textarea id="dsl-editor" spellcheck="false" aria-label="DSL JSON"></textarea></label><div><div id="dsl-summary" class="dsl-summary"></div><div id="dsl-errors" class="dsl-errors"></div><div id="dsl-sliders" class="dsl-sliders"></div></div></div>
      </section>`;
  }

  private textarea(): HTMLTextAreaElement {
    return this.host.querySelector<HTMLTextAreaElement>('#dsl-editor')!;
  }

  private onInput = (event: Event): void => {
    if ((event.target as HTMLElement).id !== 'dsl-editor') return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.validate(), 250);
  };

  private onClick = (event: MouseEvent): void => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-dsl-action]');
    if (!target) return;
    if (target.dataset.dslAction === 'add-feature') {
      this.featureDraft = true;
      this.renderFeatures();
    }
    if (target.dataset.dslAction === 'run') void this.run();
  };

  private parsed(): DSLConfig {
    return JSON.parse(this.textarea().value) as DSLConfig;
  }

  private async validate(): Promise<void> {
    try {
      this.dsl = this.parsed();
      this.validation = await api.validateDSL(this.dsl);
      const badge = this.host.querySelector<HTMLElement>('#dsl-validation-badge')!;
      badge.textContent = this.validation.valid ? '✓ Valid DSL' : 'Validation failed';
      badge.className = `status-pill ${this.validation.valid ? 'done' : 'failed'}`;
      this.renderModel();
      if (this.validation.valid) {
        const rendered = await api.renderDSL(this.dsl);
        this.host.querySelector<HTMLElement>('#dsl-summary')!.innerHTML = `<h3>Plain-language model</h3><p>${escapeHtml(rendered.plain_language)}</p>`;
        this.host.querySelector<HTMLElement>('#dsl-sliders')!.innerHTML = rendered.sliders
          .map((slider) => `<div><span>${escapeHtml(String(slider.parameter))}</span><strong>${escapeHtml(String(slider.value))}</strong><small>${escapeHtml(String(slider.unit))} · ${escapeHtml(String(slider.evidence_status))}</small></div>`)
          .join('');
      }
    } catch (error) {
      this.dsl = undefined;
      this.validation = undefined;
      this.showError(error);
    }
  }

  private renderModel(): void {
    if (!this.dsl || !this.validation) return;
    this.renderFeatures();
    this.host.querySelector<HTMLElement>('#dsl-actions')!.innerHTML = (this.dsl.actions ?? [])
      .map((action) => `<article><strong>${escapeHtml(action.id)}</strong><span>${action.probability.base} / ${escapeHtml(action.probability.time_unit)}</span><small>Priority ${action.priority} · ${action.duration_minutes} min</small></article>`)
      .join('');
    this.host.querySelector<HTMLElement>('#dsl-coefficients')!.innerHTML = (this.dsl.parameters ?? [])
      .map((parameter) => `<article><strong>${escapeHtml(parameter.id)}</strong><span>${parameter.value ?? 'Unknown'}</span><small>${escapeHtml(parameter.provenance.status)} · uncertainty ${parameter.provenance.uncertainty}</small></article>`)
      .join('');
    const errors = [...this.validation.errors, ...this.validation.warnings];
    this.host.querySelector<HTMLElement>('#dsl-errors')!.innerHTML = errors.length
      ? errors.map((error) => `<p><strong>${escapeHtml(error.path)}</strong> ${escapeHtml(error.message)}</p>`).join('')
      : '<p class="builder-valid">No reference, probability, chain, role, or aggregate errors.</p>';
  }

  private renderFeatures(): void {
    const target = this.host.querySelector<HTMLElement>('#dsl-features');
    if (!target) return;
    const states = this.dsl?.default_states ?? [];
    target.innerHTML = [
      ...states.map((state) => `<article><strong>${escapeHtml(state.id)}</strong><span>Distribution attached</span><small>${escapeHtml(state.distribution.provenance.status)} · ${escapeHtml(state.distribution.provenance.source)}</small></article>`),
      ...(this.featureDraft
        ? ['<article class="label-only"><strong>eye_colour</strong><span>LABEL-ONLY</span><small>No confirmed distribution or joint outcome data. It cannot predict an action.</small><button class="text-button" data-action="data-tab">Open Data organizer</button></article>']
        : []),
    ].join('');
  }

  private showError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    const badge = this.host.querySelector<HTMLElement>('#dsl-validation-badge');
    if (badge) {
      badge.textContent = 'Invalid JSON';
      badge.className = 'status-pill failed';
    }
    const target = this.host.querySelector<HTMLElement>('#dsl-errors');
    if (target) target.innerHTML = `<p>${escapeHtml(message)}</p>`;
  }

  private async run(): Promise<void> {
    if (!this.dsl || !this.validation?.valid) {
      this.showError(new Error('Fix DSL validation errors before running.'));
      return;
    }
    const button = this.host.querySelector<HTMLButtonElement>('[data-dsl-action="run"]')!;
    button.disabled = true;
    button.textContent = 'Launching…';
    try {
      const seed = Number(this.host.querySelector<HTMLInputElement>('#dsl-seed')!.value);
      await this.onRun(this.dsl, seed);
    } catch (error) {
      this.showError(error);
    } finally {
      button.disabled = false;
      button.textContent = 'Run validated DSL ↗';
    }
  }
}
