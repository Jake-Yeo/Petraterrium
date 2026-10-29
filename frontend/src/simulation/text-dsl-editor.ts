import './text-dsl-editor.css';
import { DslGraphView, type ProgramGraph } from './dsl-graph-view';
import { DslOutline } from './dsl-outline';

interface DslDiagnostic {
  code: string;
  line: number;
  column: number;
  message: string;
}

interface DslValidation {
  valid: boolean;
  program_id?: string | null;
  version?: string | null;
  tick_hours?: number | null;
  entities: string[];
  policies: string[];
  roles: string[];
  role_distributions: string[];
  spotlights: string[];
  archetypes: string[];
  composition_archetypes: Array<{ id: string; level: string; child_level: string }>;
  weighted_populations: string[];
  compositions: Array<{ id: string; level: string; cached?: boolean }>;
  composition_populations: string[];
  diagnostics: DslDiagnostic[];
  graph?: ProgramGraph | null;
}

interface DslDocument {
  code: string;
  source_hash: string;
  saved_at?: string | null;
  validation: DslValidation;
}

type ReportValue = number | string | Record<string, number>;

interface ReportColumn {
  id: string;
  label: string;
  format: string;
  metric: unknown;
  line: number;
}

interface ReportRow {
  group_id: string;
  values: Record<string, ReportValue>;
}

interface ReportSnapshot {
  tick: number;
  rows: ReportRow[];
}

interface Report {
  id: string;
  title: string;
  group_by: string;
  display: 'table' | 'cards';
  record: 'tick' | 'daily' | 'final';
  columns: ReportColumn[];
  snapshots: ReportSnapshot[];
}

interface ReportDelta {
  report_id: string;
  group_id: string;
  values: Record<string, ReportValue>;
}

interface DslRunResult {
  run_id: string;
  source_hash: string;
  seed: number;
  days: number;
  ticks: number;
  total_represented_pool: number;
  exemplar_plan: ExemplarSystemPlan;
  cache_stats: ExemplarCacheStats;
  exemplar_cache: Record<string, ExemplarCacheEntry>;
  leader_assignments: Record<string, string>;
  unassigned_required_roles: number;
  results_title: string;
  results_subtitle: string;
  reports: Report[];
  comparison: ReportDelta[];
  engine_version: string;
  created_at: string;
}

interface ExemplarPlan {
  id: string;
  city_id: string;
  stratum: string;
  households: number;
  people: number;
  represented_people: number;
  instances_represented: number;
  city_population_share: number;
  distribution_status: string;
  provenance: string;
}

interface CityExemplarPlan {
  city_id: string;
  represented_people: number;
  represented_households: number;
  distribution_status: string;
  provenance: string;
  strata: string[];
  exemplars: ExemplarPlan[];
  convergence: {
    mean_change: number;
    distribution_distance: number;
    tail_rate_change_points: number;
    converged: boolean;
    cap_hit: boolean;
  };
  mixture_metrics: Record<
    string,
    {
      mean: number;
      standard_deviation: number;
      p10: number;
      p50: number;
      p90: number;
      tail_rate: number;
    }
  >;
}

interface ExemplarSystemPlan {
  total_represented_pool: number;
  total_represented_households: number;
  total_real_neighbourhood_instances: number;
  total_exemplars: number;
  cities: CityExemplarPlan[];
}

interface ExemplarCacheStats {
  cache_hit: boolean;
  mass_agent_ticks: number;
  relearned_exemplars: string[];
  reused_exemplars: string[];
  invalidations: Record<string, string>;
  feedback_iterations: number;
  feedback_final_change: number;
  feedback_inputs: Record<string, Record<string, number>>;
}

interface ExemplarCacheEntry {
  version: number;
  learning_ticks: number;
  learning_seconds: number;
  agents: Array<{
    id: string;
    household_id: string;
    roles: string[];
    residence_path: string[];
    age: number;
    money: number;
    stress: number;
  }>;
  relationships: Array<{ kind: string; source_id: string; target_id: string }>;
}

export interface TextDslEditorOptions {
  onError: (error: unknown) => void;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

const requestJson = async <Value>(path: string, init?: RequestInit): Promise<Value> => {
  const response = await fetch(`/api${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? JSON.stringify((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as Value;
};

const number = (value: number, digits = 2): string =>
  new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);

const signed = (value: number): string => `${value >= 0 ? '+' : ''}${number(value)}`;

const isRates = (value: ReportValue): value is Record<string, number> =>
  typeof value === 'object' && value !== null;

export class TextDslEditor {
  private document?: DslDocument;
  private run?: DslRunResult;
  private loaded = false;
  private dirty = false;
  private resetArmed = false;
  private view: 'code' | 'graph' = 'code';
  private lastRunElapsedMs = 0;
  private selectedRunLabel = 'Petraterrium full system';
  private readonly root = document.createElement('section');
  private readonly textarea = document.createElement('textarea');
  private readonly gutter = document.createElement('pre');
  private readonly status: HTMLElement;
  private readonly diagnostics: HTMLElement;
  private readonly results: HTMLElement;
  private readonly graphView: DslGraphView;
  private readonly outline: DslOutline;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: TextDslEditorOptions,
  ) {
    this.root.className = 'text-dsl-workspace';
    this.root.innerHTML = `
      <header class="text-dsl-heading">
        <div><span class="text-dsl-eyebrow">RUST DSL · SOURCE OF TRUTH</span><h1>Population simulation program</h1><p>Run weighted neighbourhood exemplars across four sector overlays, inspect the exact DSL as code, or explore its validated hierarchy and roles.</p></div>
        <div class="text-dsl-hash" data-dsl-hash>Loading…</div>
      </header>
      <div class="text-dsl-view-toggle" role="tablist" aria-label="DSL view">
        <button type="button" role="tab" aria-selected="true" data-dsl-view="code">Code</button>
        <button type="button" role="tab" aria-selected="false" data-dsl-view="graph">Graph</button>
      </div>
      <div class="text-dsl-source-actions">
        <button type="button" class="button secondary" data-dsl-action="validate">Validate code</button>
        <button type="button" class="button primary" data-dsl-action="save">Save DSL</button>
        <button type="button" class="button secondary" data-dsl-action="reset">Reset shipped DSL</button>
      </div>
      <section class="text-dsl-run-panel">
        <header><div><span class="text-dsl-eyebrow">RUN FULL SYSTEM</span><h2>Petraterrium</h2><p>One pool of people acts across Physical, Media, Conglomerate, and Financial sectors through overlapping roles.</p></div></header>
        <div class="text-dsl-full-summary" data-full-system-summary></div>
        <div class="text-dsl-run-controls">
          <label>Total represented pool <input type="number" min="1" step="1" value="6999999999" data-dsl-total-pool></label>
          <label>Days <input type="number" min="1" max="365" step="1" value="30" data-dsl-days></label>
          <label>Seed <input type="number" min="0" step="1" value="1" data-dsl-seed></label>
          <button type="button" class="button primary text-dsl-run-button" data-dsl-action="run">Run full system</button>
          <details class="text-dsl-advanced"><summary>Advanced</summary><details class="text-dsl-debug-runs"><summary>Debug city</summary><p>Debug city runs still use weighted neighbourhood exemplars.</p><label>Debug target<select data-dsl-population aria-label="Debug target"><option value="">Full system</option></select></label><label>All debug runs<select data-dsl-all-runs aria-label="All debug runs"><option value="">Choose debug run</option></select></label></details></details>
        </div>
      </section>
      <div class="text-dsl-status" role="status" data-dsl-status>Loading Rust DSL…</div>
      <div class="text-dsl-code-view" data-dsl-code-view>
        <aside data-dsl-outline></aside>
        <div class="text-dsl-code-frame" data-dsl-code-frame></div>
      </div>
      <div data-dsl-graph-view hidden></div>
      <div class="text-dsl-diagnostics" data-dsl-diagnostics></div>
      <div class="text-dsl-results" data-dsl-results></div>`;
    const frame = this.root.querySelector<HTMLElement>('[data-dsl-code-frame]')!;
    this.gutter.className = 'text-dsl-gutter';
    this.gutter.setAttribute('aria-hidden', 'true');
    this.textarea.className = 'text-dsl-code';
    this.textarea.setAttribute('aria-label', 'Simulation DSL code');
    this.textarea.spellcheck = false;
    this.textarea.wrap = 'off';
    frame.append(this.gutter, this.textarea);
    this.status = this.root.querySelector<HTMLElement>('[data-dsl-status]')!;
    this.diagnostics = this.root.querySelector<HTMLElement>('[data-dsl-diagnostics]')!;
    this.results = this.root.querySelector<HTMLElement>('[data-dsl-results]')!;
    this.graphView = new DslGraphView(
      this.root.querySelector<HTMLElement>('[data-dsl-graph-view]')!,
      { onViewCode: (line) => this.showCode(line) },
    );
    this.outline = new DslOutline(this.root.querySelector<HTMLElement>('[data-dsl-outline]')!, {
      onSelect: (line) => this.focusLine(line),
    });
    this.host.replaceChildren(this.root);
    this.root.addEventListener('click', this.onClick);
    this.root
      .querySelector<HTMLSelectElement>('[data-dsl-all-runs]')!
      .addEventListener('change', this.onAllRunsChange);
    this.root
      .querySelector<HTMLSelectElement>('[data-dsl-population]')!
      .addEventListener('change', this.onRunSelectionChange);
    this.textarea.addEventListener('input', this.onInput);
    this.textarea.addEventListener('scroll', this.onScroll);
  }

  activate(): void {
    if (!this.loaded) void this.load();
  }

  deactivate(): void {}

  destroy(): void {
    this.root.removeEventListener('click', this.onClick);
    this.textarea.removeEventListener('input', this.onInput);
    this.textarea.removeEventListener('scroll', this.onScroll);
    this.root
      .querySelector<HTMLSelectElement>('[data-dsl-all-runs]')!
      .removeEventListener('change', this.onAllRunsChange);
    this.root
      .querySelector<HTMLSelectElement>('[data-dsl-population]')!
      .removeEventListener('change', this.onRunSelectionChange);
    this.graphView.destroy();
    this.outline.destroy();
    this.root.remove();
  }

  private readonly onInput = (): void => {
    this.dirty = this.textarea.value !== this.document?.code;
    this.resetArmed = false;
    this.renderLines();
    this.status.textContent = this.dirty
      ? 'Unsaved code. Validate and save before running.'
      : 'Saved DSL is ready to run.';
    this.updateButtons();
  };

  private readonly onScroll = (): void => {
    this.gutter.scrollTop = this.textarea.scrollTop;
  };

  private readonly onClick = (event: MouseEvent): void => {
    const view = (event.target as Element).closest<HTMLButtonElement>('[data-dsl-view]');
    if (view) {
      this.setView(view.dataset.dslView === 'graph' ? 'graph' : 'code');
      return;
    }
    const button = (event.target as Element).closest<HTMLButtonElement>('[data-dsl-action]');
    if (!button) return;
    const action = button.dataset.dslAction;
    if (action === 'validate') void this.validate();
    if (action === 'save') void this.save();
    if (action === 'run') void this.runDsl();
    if (action === 'reset') void this.reset(button);
  };

  private readonly onAllRunsChange = (event: Event): void => {
    const select = event.target as HTMLSelectElement;
    if (!select.value) return;
    const primary = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!;
    const selected = select.selectedOptions[0];
    let option = [...primary.options].find((candidate) => candidate.value === select.value);
    if (!option) {
      option = new Option(selected.text, select.value);
      primary.add(option);
    }
    primary.value = select.value;
    this.selectedRunLabel = selected.text;
  };

  private readonly onRunSelectionChange = (event: Event): void => {
    const select = event.target as HTMLSelectElement;
    this.selectedRunLabel = select.value
      ? (select.selectedOptions[0]?.text ?? 'Debug run')
      : 'Petraterrium full system';
  };

  private setView(view: 'code' | 'graph'): void {
    this.view = view;
    const code = this.root.querySelector<HTMLElement>('[data-dsl-code-view]')!;
    const graph = this.root.querySelector<HTMLElement>('[data-dsl-graph-view]')!;
    code.hidden = view !== 'code';
    graph.hidden = view !== 'graph';
    this.root.querySelectorAll<HTMLButtonElement>('[data-dsl-view]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.dslView === view));
    });
    if (view === 'graph') this.graphView.render();
  }

  private showCode(line: number): void {
    this.setView('code');
    this.focusLine(line);
  }

  private async load(): Promise<void> {
    this.status.textContent = 'Loading the DSL source from the API…';
    try {
      this.document = await requestJson<DslDocument>('/simulation/text-dsl');
      this.loaded = true;
      this.textarea.value = this.document.code;
      this.dirty = false;
      this.renderLines();
      this.renderDocument();
      this.renderValidation(this.document.validation);
    } catch (error) {
      this.status.textContent = error instanceof Error ? error.message : String(error);
      this.options.onError(error);
    }
  }

  private async validate(): Promise<DslValidation | null> {
    this.status.textContent = 'Rust is parsing and validating the DSL…';
    try {
      const validation = await requestJson<DslValidation>('/simulation/text-dsl/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: this.textarea.value }),
      });
      this.renderValidation(validation);
      return validation;
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = error instanceof Error ? error.message : String(error);
      return null;
    }
  }

  private async save(): Promise<void> {
    if (!this.document) return;
    const validation = await this.validate();
    if (!validation?.valid) return;
    this.status.textContent = 'Saving the validated DSL source…';
    try {
      this.document = await requestJson<DslDocument>('/simulation/text-dsl', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: this.textarea.value,
          expected_hash: this.document.source_hash,
        }),
      });
      this.textarea.value = this.document.code;
      this.dirty = false;
      this.renderDocument();
      this.renderValidation(this.document.validation);
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = error instanceof Error ? error.message : String(error);
    }
  }

  private async reset(button: HTMLButtonElement): Promise<void> {
    if (!this.resetArmed) {
      this.resetArmed = true;
      button.textContent = 'Click again to reset';
      this.status.textContent = 'Reset will replace the active code with the shipped Rust DSL.';
      return;
    }
    try {
      this.document = await requestJson<DslDocument>('/simulation/text-dsl/reset', {
        method: 'POST',
      });
      this.textarea.value = this.document.code;
      this.dirty = false;
      this.resetArmed = false;
      button.textContent = 'Reset shipped DSL';
      this.renderLines();
      this.renderDocument();
      this.renderValidation(this.document.validation);
    } catch (error) {
      this.options.onError(error);
    }
  }

  private async runDsl(): Promise<void> {
    if (!this.document || this.dirty || !this.document.validation.valid) return;
    const seed = Number(this.root.querySelector<HTMLInputElement>('[data-dsl-seed]')!.value);
    const days = Number(this.root.querySelector<HTMLInputElement>('[data-dsl-days]')!.value);
    const totalRepresentedPool = Number(
      this.root.querySelector<HTMLInputElement>('[data-dsl-total-pool]')!.value,
    );
    const populationId = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!.value;
    const defaultRunId = this.document.validation.graph?.default_run_id ?? null;
    const compositionId = populationId.startsWith('composition:')
      ? populationId.slice('composition:'.length)
      : populationId
        ? null
        : defaultRunId;
    const ticks = Math.round((days * 24) / (this.document.validation.tick_hours || 1));
    const runButton = this.root.querySelector<HTMLButtonElement>('[data-dsl-action="run"]')!;
    runButton.disabled = true;
    runButton.textContent = `Running… ${ticks.toLocaleString()} ticks`;
    this.status.textContent = `Running ${this.selectedRunLabel} for ${days} days…`;
    const started = performance.now();
    try {
      this.run = await requestJson<DslRunResult>('/simulation/text-dsl/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed,
          days,
          total_represented_pool: totalRepresentedPool,
          baseline_run_id: this.run?.run_id ?? null,
          composition_id: compositionId,
        }),
      });
      this.lastRunElapsedMs = performance.now() - started;
      this.graphView.setExemplarPlan(this.run.exemplar_plan, this.run.exemplar_cache);
      this.status.textContent = this.run.cache_stats.cache_hit
        ? 'Completed cached composed run with 0 mass agent ticks.'
        : `Learned ${this.run.cache_stats.relearned_exemplars.length.toLocaleString()} neighbourhood exemplars.`;
      this.renderResults();
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = this.plainError(error, 'The simulation could not run');
    } finally {
      runButton.textContent = 'Run full system';
      this.updateButtons();
    }
  }

  private renderDocument(): void {
    if (!this.document) return;
    this.root.querySelector<HTMLElement>('[data-dsl-hash]')!.textContent =
      `${this.document.validation.program_id ?? 'DSL'} · ${this.document.source_hash.slice(0, 18)}…`;
    this.status.textContent = this.document.validation.valid
      ? 'This exact DSL source is saved and executable.'
      : 'The saved DSL has validation errors.';
    this.updateButtons();
  }

  private renderLines(): void {
    const count = Math.max(1, this.textarea.value.split('\n').length);
    this.gutter.textContent = Array.from({ length: count }, (_, index) => index + 1).join('\n');
  }

  private renderValidation(validation: DslValidation): void {
    this.graphView.setGraph(validation.valid ? validation.graph : null);
    this.outline.setGraph(validation.valid ? validation.graph : null);
    this.renderPopulationOptions(validation.compositions ?? [], validation.graph ?? undefined);
    this.renderFullSystemSummary(validation.graph ?? undefined);
    this.diagnostics.replaceChildren();
    if (validation.valid) {
      this.diagnostics.innerHTML = `<div class="text-dsl-valid"><strong>Valid Rust DSL</strong><span>${escapeHtml(validation.program_id ?? '')} · tick ${number(validation.tick_hours ?? 0)}h · weighted neighbourhood exemplar architecture</span></div>`;
      this.status.textContent = this.dirty
        ? 'Code is valid. Save it to make it the executable source.'
        : 'Saved DSL is valid and ready to run.';
    } else {
      this.diagnostics.innerHTML = `<div class="text-dsl-invalid"><strong>${validation.diagnostics.length} DSL error${validation.diagnostics.length === 1 ? '' : 's'}</strong>${validation.diagnostics
        .map(
          (item) =>
            `<button type="button" data-dsl-error-line="${item.line}"><span>Line ${item.line} · ${escapeHtml(item.code)}</span><strong>${escapeHtml(item.message)}</strong></button>`,
        )
        .join('')}</div>`;
      this.diagnostics
        .querySelectorAll<HTMLButtonElement>('[data-dsl-error-line]')
        .forEach((button) =>
          button.addEventListener('click', () =>
            this.focusLine(Number(button.dataset.dslErrorLine)),
          ),
        );
      this.status.textContent = 'Fix the DSL errors before saving or running.';
    }
    this.updateButtons(validation);
  }

  private renderPopulationOptions(
    compositions: Array<{ id: string; level: string; cached?: boolean }>,
    graph: ProgramGraph | undefined,
  ): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!;
    const allRuns = this.root.querySelector<HTMLSelectElement>('[data-dsl-all-runs]')!;
    const selected = select.value;
    const availableCompositions = compositions;
    const nodeById = new Map((graph?.nodes ?? []).map((node) => [node.id, node]));
    const compositionOption = (composition: {
      id: string;
      level: string;
      cached?: boolean;
    }): HTMLOptionElement => {
      return new Option(
        `${composition.id} — city exemplar debug${composition.cached ? ', cached' : ''}`,
        `composition:${composition.id}`,
      );
    };
    select.replaceChildren(new Option('Full system', ''));
    allRuns.replaceChildren(new Option('Choose debug run', ''));
    const allOptions = [
      ...availableCompositions
        .filter((composition) => {
          const node = nodeById.get(composition.id);
          return (
            composition.id !== graph?.default_run_id &&
            node?.graph_group === 'main' &&
            node.vertical_slice === 'Physical' &&
            ['municipality', 'city'].includes(node.level)
          );
        })
        .map(compositionOption),
    ];
    for (const option of allOptions) {
      allRuns.add(new Option(option.text, option.value));
      select.add(option);
    }
    const values = ['', ...allOptions.map((option) => option.value)];
    select.value = values.includes(selected) ? selected : '';
    this.selectedRunLabel = select.value
      ? (select.selectedOptions[0]?.text ?? 'Debug run')
      : 'Petraterrium full system';
  }

  private renderFullSystemSummary(graph: ProgramGraph | undefined): void {
    const host = this.root.querySelector<HTMLElement>('[data-full-system-summary]')!;
    const root = graph?.nodes.find((node) => node.id === graph.default_run_id);
    if (!graph || !root) {
      host.innerHTML = '<p>Validate the DSL to load the exemplar hierarchy.</p>';
      return;
    }
    const cities = graph.nodes.filter((node) => ['municipality', 'city'].includes(node.level));
    const strata = graph.nodes.filter((node) => node.level === 'neighbourhood');
    host.innerHTML = `<article class="text-dsl-pool-summary"><strong>Logical population</strong><span>6,999,999,999 represented people · ${cities.length.toLocaleString()} cities · adaptive exemplar count</span><small>${strata.length.toLocaleString()} declared strata · each detailed exemplar contains 50–100 households · sector roles overlay the same people</small></article>`;
  }

  private focusLine(line: number): void {
    if (this.view !== 'code') this.setView('code');
    const lines = this.textarea.value.split('\n');
    const start = lines
      .slice(0, Math.max(0, line - 1))
      .reduce((sum, value) => sum + value.length + 1, 0);
    const end = start + (lines[line - 1]?.length ?? 0);
    this.textarea.focus();
    this.textarea.setSelectionRange(start, end);
  }

  private updateButtons(validation = this.document?.validation): void {
    const save = this.root.querySelector<HTMLButtonElement>('[data-dsl-action="save"]')!;
    const run = this.root.querySelector<HTMLButtonElement>('[data-dsl-action="run"]')!;
    save.disabled = !this.dirty;
    run.disabled = this.dirty || !validation?.valid;
  }

  private renderResults(): void {
    if (!this.run) return;
    const deltaByKey = new Map(
      this.run.comparison.map((row) => [`${row.report_id}:${row.group_id}`, row]),
    );
    const plan = this.run.exemplar_plan;
    const poolSummary = `<section class="text-dsl-slice-results"><h3>Weighted neighbourhood exemplars</h3><div><article><strong>${number(plan.total_represented_pool, 0)} represented people</strong><span>${number(plan.total_exemplars, 0)} detailed exemplars · ${number(plan.cities.length, 0)} cities</span><small>${number(plan.total_real_neighbourhood_instances, 0)} real neighbourhood instances · ${number(plan.total_represented_households, 0)} represented households</small></article><article><strong>${this.run.cache_stats.cache_hit ? 'Cache hit' : 'Learning completed'}</strong><span>${number(this.run.cache_stats.mass_agent_ticks, 0)} mass agent ticks</span><small>Unassigned required roles = ${number(this.run.unassigned_required_roles, 0)}</small></article></div></section>`;
    const citySummary = `<section class="text-dsl-result-table"><h3>City convergence</h3><ul>${plan.cities.map((city) => `<li><strong>${escapeHtml(city.city_id)}</strong> · ${number(city.exemplars.length, 0)} exemplars · ${number(city.represented_people, 0)} people · mean Δ ${number(city.convergence.mean_change * 100, 2)}% · distribution ${number(city.convergence.distribution_distance * 100, 2)}% · tail Δ ${number(city.convergence.tail_rate_change_points, 3)}pp · ${city.convergence.converged ? 'converged' : city.convergence.cap_hit ? 'cap hit' : 'not converged'} · ${escapeHtml(city.distribution_status)}</li>`).join('')}</ul></section>`;
    const cacheSummary = `<section class="text-dsl-result-table"><h3>Exemplar cache</h3><p>Relearned ${number(this.run.cache_stats.relearned_exemplars.length, 0)} · reused ${number(this.run.cache_stats.reused_exemplars.length, 0)} · feedback ${number(this.run.cache_stats.feedback_iterations, 0)} iteration(s), final change ${number(this.run.cache_stats.feedback_final_change * 100, 2)}%</p><ul>${Object.entries(
      this.run.cache_stats.invalidations,
    )
      .map(([id, reason]) => `<li>${escapeHtml(id)} · ${escapeHtml(reason)}</li>`)
      .join('')}${Object.entries(this.run.cache_stats.feedback_inputs)
      .map(
        ([city, inputs]) =>
          `<li>${escapeHtml(city)} feedback · ${Object.entries(inputs)
            .map(([input, value]) => `${escapeHtml(input)}=${number(value, 4)}`)
            .join(' · ')}</li>`,
      )
      .join('')}</ul></section>`;
    const leadersSummary = `<section class="text-dsl-result-table"><h3>Leader assignments</h3><ul>${Object.entries(
      this.run.leader_assignments,
    )
      .map(
        ([office, agent]) =>
          `<li><strong>${escapeHtml(office)}</strong> · ${escapeHtml(agent)}</li>`,
      )
      .join('')}</ul></section>`;
    this.results.innerHTML = `
      <header><div><span class="text-dsl-eyebrow">RUN COMPLETE · ${escapeHtml(this.run.results_title)}</span><h2>${escapeHtml(this.run.results_subtitle)}</h2><p>Total pool ${number(this.run.total_represented_pool, 0)} · ${this.run.days} days · seed ${this.run.seed} · ${number(plan.total_exemplars, 0)} exemplars · ${number(plan.total_real_neighbourhood_instances, 0)} real neighbourhoods represented · engine ${escapeHtml(this.run.engine_version)} · ${number(this.lastRunElapsedMs, 1)} ms</p></div><div><span>Run</span><strong>${escapeHtml(this.run.run_id.slice(0, 8))}</strong></div></header>
      ${poolSummary}
      ${citySummary}
      ${cacheSummary}
      ${leadersSummary}
      ${this.run.reports.map((report) => this.report(report, deltaByKey)).join('')}`;
  }

  private plainError(error: unknown, prefix: string): string {
    const raw = error instanceof Error ? error.message : String(error);
    try {
      const parsed = JSON.parse(raw) as { message?: string; code?: string };
      return `${prefix}: ${parsed.message ?? parsed.code ?? raw}`;
    } catch {
      return `${prefix}: ${raw.replace(/^"|"$/g, '')}`;
    }
  }

  private report(report: Report, deltas: Map<string, ReportDelta>): string {
    const snapshot = report.snapshots.at(-1);
    if (!snapshot) {
      return `<section class="text-dsl-result-table"><h3>${escapeHtml(report.title)}</h3><p>No snapshot was scheduled for this run.</p></section>`;
    }
    if (report.display === 'cards') {
      return this.cards(report, snapshot, deltas);
    }
    return this.table(report, snapshot, deltas);
  }

  private table(
    report: Report,
    snapshot: ReportSnapshot,
    deltas: Map<string, ReportDelta>,
  ): string {
    return `<section class="text-dsl-result-table" data-report-id="${escapeHtml(report.id)}"><h3>${escapeHtml(report.title)}</h3><p class="text-dsl-report-meta">Grouped by ${escapeHtml(report.group_by)} · recorded ${escapeHtml(report.record)} · tick ${snapshot.tick}</p><div class="table-scroll"><table><thead><tr><th>Group</th>${report.columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join('')}</tr></thead><tbody>${snapshot.rows
      .map((row) => {
        const delta = deltas.get(`${report.id}:${row.group_id}`);
        return `<tr><th>${escapeHtml(row.group_id)}</th>${report.columns
          .map(
            (column) =>
              `<td>${this.value(row.values[column.id], column.format)}${this.delta(delta?.values[column.id], column.format)}</td>`,
          )
          .join('')}</tr>`;
      })
      .join('')}</tbody></table></div></section>`;
  }

  private cards(
    report: Report,
    snapshot: ReportSnapshot,
    deltas: Map<string, ReportDelta>,
  ): string {
    return `<section class="text-dsl-result-cards" data-report-id="${escapeHtml(report.id)}"><h3>${escapeHtml(report.title)}</h3><p class="text-dsl-report-meta">Grouped by ${escapeHtml(report.group_by)} · recorded ${escapeHtml(report.record)} · tick ${snapshot.tick}</p><div>${snapshot.rows
      .map((row) => {
        const delta = deltas.get(`${report.id}:${row.group_id}`);
        return `<article><h4>${escapeHtml(row.group_id)}</h4>${report.columns
          .map(
            (column) =>
              `<dl><dt>${escapeHtml(column.label)}</dt><dd>${this.value(row.values[column.id], column.format)}${this.delta(delta?.values[column.id], column.format)}</dd></dl>`,
          )
          .join('')}</article>`;
      })
      .join('')}</div></section>`;
  }

  private value(value: ReportValue | undefined, format: string): string {
    if (value === undefined) return '—';
    if (isRates(value)) {
      const values = Object.entries(value)
        .sort((left, right) => right[1] - left[1])
        .slice(0, 6)
        .map(([name, rate]) => `${escapeHtml(name)} ${number(rate)}`)
        .join(' · ');
      return values || '0';
    }
    if (typeof value === 'string') return escapeHtml(value);
    if (format === 'integer') return number(value, 0);
    if (format === 'percent') return `${number(value * 100)}%`;
    return number(value);
  }

  private delta(value: ReportValue | undefined, format: string): string {
    if (value === undefined || typeof value === 'string') return '';
    if (isRates(value)) {
      const summary = Object.entries(value)
        .filter(([, delta]) => delta !== 0)
        .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
        .slice(0, 3)
        .map(([name, delta]) => `${escapeHtml(name)} ${signed(delta)}`)
        .join(' · ');
      return `<small>${summary || '+0'} vs baseline</small>`;
    }
    const scaled = format === 'percent' ? value * 100 : value;
    return `<small>${signed(scaled)}${format === 'percent' ? '%' : ''} vs baseline</small>`;
  }
}
