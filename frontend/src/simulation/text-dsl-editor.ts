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
  adult_population?: number | null;
  entities: string[];
  policies: string[];
  roles: string[];
  role_distributions: string[];
  spotlights: string[];
  archetypes: string[];
  composition_archetypes: Array<{ id: string; level: string; child_level: string }>;
  weighted_populations: string[];
  aggregate_functions: AggregateFunctionDefinition[];
  compositions: Array<{ id: string; level: string; cached?: boolean }>;
  composition_populations: string[];
  neighbourhoods: string[];
  neighbourhood_populations: string[];
  diagnostics: DslDiagnostic[];
  graph?: ProgramGraph | null;
}

interface AggregateInputDefinition {
  id: string;
  default: number;
  minimum: number;
  maximum: number;
  invalidate_threshold: number;
}

interface AggregateFunctionDefinition {
  id: string;
  inputs: AggregateInputDefinition[];
  time_days: number;
  time_points: number[];
  cache: { valid_for_days: number };
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
  adult_population: number;
  total_agents: number;
  generated_children: number;
  population_id?: string | null;
  results_title: string;
  results_subtitle: string;
  reports: Report[];
  comparison: ReportDelta[];
  engine_version: string;
  created_at: string;
}

interface AggregateEvaluationResult {
  function_id: string;
  cache_hit: boolean;
  invalidation_reason?: string | null;
  agent_ticks: number;
  inputs_hash: string;
  valid_from: number;
  valid_until: number;
  dsl_source_hash: string;
  cache_version: number;
  time_series: Array<{
    day: number;
    outputs: Record<string, { mean: number; standard_deviation: number }>;
  }>;
  reports: Report[];
  elapsed_seconds: number;
  feedback_iterations?: number;
  feedback_change_percent?: number;
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

const assignments = (source: string): Array<[string, string, number]> =>
  source
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => {
      const [path, encoded] = value.split('=');
      const separator = path.lastIndexOf('.');
      if (separator <= 0 || encoded === undefined || !Number.isFinite(Number(encoded))) {
        throw new Error(`Invalid assignment ${value}`);
      }
      return [path.slice(0, separator), path.slice(separator + 1), Number(encoded)];
    });

const branchInputs = (source: string): Record<string, Record<string, number>> =>
  assignments(source).reduce<Record<string, Record<string, number>>>(
    (result, [branch, input, value]) => {
      (result[branch] ??= {})[input] = value;
      return result;
    },
    {},
  );

const inputSchedule = (source: string): Array<{ day: number; values: Record<string, number> }> => {
  const grouped = assignments(source).reduce<Map<number, Record<string, number>>>(
    (result, [encodedDay, input, value]) => {
      const day = Number(encodedDay);
      if (!Number.isInteger(day) || day < 1) throw new Error(`Invalid schedule day ${encodedDay}`);
      (result.get(day) ?? (result.set(day, {}), result.get(day)!))[input] = value;
      return result;
    },
    new Map(),
  );
  return [...grouped].map(([day, values]) => ({ day, values }));
};

export class TextDslEditor {
  private document?: DslDocument;
  private run?: DslRunResult;
  private loaded = false;
  private dirty = false;
  private resetArmed = false;
  private view: 'code' | 'graph' = 'code';
  private lastRunElapsedMs = 0;
  private selectedRunLabel = 'Town';
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
        <div><span class="text-dsl-eyebrow">RUST DSL · SOURCE OF TRUTH</span><h1>Population simulation program</h1><p>Run the default Town in one click, inspect the exact DSL as code, or explore its validated composition and coupling graph.</p></div>
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
        <header><div><span class="text-dsl-eyebrow">RUN SIMULATION</span><h2>Choose a run</h2><p>Town is ready by default. Change only what matters, then run the saved DSL.</p></div></header>
        <div class="text-dsl-run-controls">
          <label>What to run <span class="dsl-help" title="Choose a population or composition; Town is the default detailed demo.">?</span><select data-dsl-population aria-label="What to run"><option value="">Town — default detailed demo</option></select></label>
          <label>Days <span class="dsl-help" title="Days controls how long the simulation runs; the default is 30.">?</span><input type="number" min="1" max="365" step="1" value="30" data-dsl-days></label>
          <details class="text-dsl-all-runs"><summary>All runs</summary><label>Population or composition <span class="dsl-help" title="A population samples agents; a composition combines reusable hierarchy branches.">?</span><select data-dsl-all-runs aria-label="All runs"><option value="">Choose another run</option></select></label></details>
          <details class="text-dsl-advanced"><summary>Advanced</summary><label>Seed <span class="dsl-help" title="Seed = the same number gives the same random results; change it to get a different run.">?</span><input type="number" min="0" step="1" value="1" data-dsl-seed></label></details>
          <button type="button" class="button primary text-dsl-run-button" data-dsl-action="run">Run simulation</button>
        </div>
      </section>
      <details class="text-dsl-fast-forward" data-fast-forward>
        <summary><div><span class="text-dsl-eyebrow">FAST-FORWARD · CACHED · ADVANCED</span><strong>You do not need this to run a simulation.</strong><p>Fast-forward uses a learned aggregate function to estimate a cohort instantly, with 0 agent ticks, instead of simulating agents again. Example: change unemployment and see mean income in 30 days.</p></div></summary>
        <div class="text-dsl-aggregate-toolbar">
          <label>Learned aggregate function <span class="dsl-help" title="A learned aggregate function estimates cohort outputs without rerunning individual agents.">?</span><select data-aggregate-function><option value="">Select aggregate</option></select></label>
          <div class="text-dsl-aggregate-inputs" data-aggregate-inputs></div>
          <label>Evaluation day <span class="dsl-help" title="Evaluation day = which day to evaluate to.">?</span><input type="number" min="0" step="1" value="0" data-aggregate-day></label>
          <label>Events <span class="dsl-help" title="Events = e.g. disaster, pandemic, comma-separated.">?</span><input type="text" placeholder="disaster, pandemic" data-aggregate-events></label>
          <label>Branch inputs <span class="dsl-help" title="Branch inputs = e.g. NorthOne.unemployment=0.8, changing one branch only.">?</span><input type="text" placeholder="NorthOne.unemployment=0.8" data-aggregate-branch-inputs></label>
          <label>Input schedule <span class="dsl-help" title="Input schedule = e.g. 30.unemployment=0.8, changing an input from day 30.">?</span><input type="text" placeholder="30.unemployment=0.8" data-aggregate-input-schedule></label>
          <button type="button" class="button secondary" data-dsl-action="aggregate-cached">Evaluate cached</button>
          <button type="button" class="button secondary" data-dsl-action="aggregate-relearn">Relearn detailed</button>
          <p class="text-dsl-fast-reason" data-fast-forward-reason></p>
        </div>
      </details>
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
      .querySelector<HTMLSelectElement>('[data-aggregate-function]')!
      .addEventListener('change', this.onAggregateFunctionChange);
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
      .querySelector<HTMLSelectElement>('[data-aggregate-function]')!
      .removeEventListener('change', this.onAggregateFunctionChange);
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
    if (action === 'aggregate-cached') void this.evaluateAggregate(false);
    if (action === 'aggregate-relearn') void this.evaluateAggregate(true);
  };

  private readonly onAggregateFunctionChange = (): void => {
    this.renderAggregateInputs();
    this.updateButtons();
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
    this.root.querySelector<HTMLDetailsElement>('.text-dsl-all-runs')!.open = false;
  };

  private readonly onRunSelectionChange = (event: Event): void => {
    const select = event.target as HTMLSelectElement;
    this.selectedRunLabel = select.selectedOptions[0]?.text ?? 'Town';
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
    requestAnimationFrame(() => this.focusLine(line));
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
    const populationId = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!.value;
    const compositionId = populationId.startsWith('composition:')
      ? populationId.slice('composition:'.length)
      : null;
    const compositionPopulationId = populationId.startsWith('composition_population:')
      ? populationId.slice('composition_population:'.length)
      : null;
    const neighbourhoodId = populationId.startsWith('neighbourhood:')
      ? populationId.slice('neighbourhood:'.length)
      : null;
    const neighbourhoodPopulationId = populationId.startsWith('neighbourhood_population:')
      ? populationId.slice('neighbourhood_population:'.length)
      : null;
    const weightedPopulationId =
      compositionId || compositionPopulationId || neighbourhoodId || neighbourhoodPopulationId
        ? null
        : populationId || null;
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
          baseline_run_id:
            this.run?.population_id === (populationId || null) ? this.run.run_id : null,
          population_id: weightedPopulationId,
          composition_id: compositionId,
          composition_population_id: compositionPopulationId,
          neighbourhood_id: neighbourhoodId,
          neighbourhood_population_id: neighbourhoodPopulationId,
        }),
      });
      this.lastRunElapsedMs = performance.now() - started;
      this.status.textContent = `Completed ${this.run.ticks.toLocaleString()} Rust ticks.`;
      this.renderResults();
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = this.plainError(error, 'The simulation could not run');
    } finally {
      runButton.textContent = 'Run simulation';
      this.updateButtons();
    }
  }

  private async evaluateAggregate(forceRelearn: boolean): Promise<void> {
    if (!this.document || this.dirty || !this.document.validation.valid) return;
    const functionId = this.root.querySelector<HTMLSelectElement>(
      '[data-aggregate-function]',
    )!.value;
    if (!functionId) return;
    const inputs = Object.fromEntries(
      [...this.root.querySelectorAll<HTMLInputElement>('[data-aggregate-input]')].map((input) => [
        input.dataset.aggregateInput!,
        Number(input.value),
      ]),
    );
    const events = this.root
      .querySelector<HTMLInputElement>('[data-aggregate-events]')!
      .value.split(',')
      .map((event) => event.trim())
      .filter(Boolean);
    const days = Number(this.root.querySelector<HTMLInputElement>('[data-dsl-days]')!.value);
    const evaluatedAtDay = Number(
      this.root.querySelector<HTMLInputElement>('[data-aggregate-day]')!.value,
    );
    this.status.textContent = forceRelearn
      ? `Relearning ${functionId} from detailed cohorts…`
      : `Evaluating cached ${functionId}…`;
    const buttons = this.root.querySelectorAll<HTMLButtonElement>(
      '[data-dsl-action^="aggregate-"]',
    );
    buttons.forEach((button) => {
      button.disabled = true;
    });
    try {
      const result = await requestJson<AggregateEvaluationResult>(
        '/simulation/text-dsl/aggregate/evaluate',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            function_id: functionId,
            seed: Number(this.root.querySelector<HTMLInputElement>('[data-dsl-seed]')!.value),
            days,
            evaluated_at_day: evaluatedAtDay,
            inputs,
            branch_inputs: branchInputs(
              this.root.querySelector<HTMLInputElement>('[data-aggregate-branch-inputs]')!.value,
            ),
            input_schedule: inputSchedule(
              this.root.querySelector<HTMLInputElement>('[data-aggregate-input-schedule]')!.value,
            ),
            events,
            force_relearn: forceRelearn,
          }),
        },
      );
      const evaluation = result.cache_hit
        ? 'Cache hit'
        : result.agent_ticks > 0
          ? 'Branch relearn'
          : 'Hierarchy updated';
      this.status.textContent = `${evaluation} · ${result.agent_ticks.toLocaleString()} agent ticks · ${number(result.elapsed_seconds * 1000, 1)} ms · ${result.feedback_iterations ?? 0} feedback iterations.`;
      this.graphView.setCacheStatus(
        functionId,
        `${evaluation.toLowerCase()} · ${result.agent_ticks.toLocaleString()} agent ticks · ${number(result.elapsed_seconds * 1000, 1)} ms`,
      );
      this.renderAggregateResults(result, days);
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = this.plainError(error, 'Fast-forward could not finish');
    } finally {
      this.updateButtons();
    }
  }

  private renderAggregateResults(result: AggregateEvaluationResult, days: number): void {
    const deltas = new Map<string, ReportDelta>();
    const outputIds = Object.keys(result.time_series.at(-1)?.outputs ?? {});
    this.results.innerHTML = `
      <header><div><span class="text-dsl-eyebrow">${result.cache_hit ? 'CACHED FAST-FORWARD' : result.agent_ticks > 0 ? 'BRANCH RELEARN' : 'HIERARCHY UPDATED'}</span><h2>${escapeHtml(result.function_id)}</h2><p>${days} days · cache_hit=${result.cache_hit} · cache v${result.cache_version} · ${number(result.elapsed_seconds * 1000, 1)} ms · ${result.agent_ticks.toLocaleString()} agent ticks · ${result.feedback_iterations ?? 0} feedback iterations · ${number(result.feedback_change_percent ?? 0, 3)}% final change</p></div></header>
      <section class="text-dsl-result-table" data-report-id="aggregate_time_series"><h3>Fast-forward time series</h3><div class="table-scroll"><table><thead><tr><th>Day</th>${outputIds.map((id) => `<th>${escapeHtml(id.replaceAll('_', ' '))}</th><th>${escapeHtml(id.replaceAll('_', ' '))} sd</th>`).join('')}</tr></thead><tbody>${result.time_series
        .map(
          (point) =>
            `<tr><th>${point.day}</th>${outputIds.map((id) => `<td>${number(point.outputs[id]?.mean ?? 0)}</td><td>${number(point.outputs[id]?.standard_deviation ?? 0)}</td>`).join('')}</tr>`,
        )
        .join('')}</tbody></table></div></section>
      ${result.reports.map((report) => this.report(report, deltas)).join('')}`;
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
    this.renderPopulationOptions(
      validation.weighted_populations ?? [],
      validation.compositions ?? [],
      validation.composition_populations ?? [],
      validation.neighbourhoods ?? [],
      validation.neighbourhood_populations ?? [],
      validation.graph ?? undefined,
      validation.adult_population ?? 0,
    );
    this.renderAggregateOptions(validation.aggregate_functions ?? []);
    this.diagnostics.replaceChildren();
    if (validation.valid) {
      this.diagnostics.innerHTML = `<div class="text-dsl-valid"><strong>Valid Rust DSL</strong><span>${escapeHtml(validation.program_id ?? '')} · tick ${number(validation.tick_hours ?? 0)}h · ${number(validation.adult_population ?? 0, 0)} adults before generated children</span></div>`;
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
    populations: string[],
    compositions: Array<{ id: string; level: string; cached?: boolean }>,
    compositionPopulations: string[],
    neighbourhoods: string[],
    neighbourhoodPopulations: string[],
    graph: ProgramGraph | undefined,
    adultPopulation: number,
  ): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!;
    const allRuns = this.root.querySelector<HTMLSelectElement>('[data-dsl-all-runs]')!;
    const selected = select.value;
    const availableCompositions =
      compositions.length > 0
        ? compositions
        : neighbourhoods.map((id) => ({ id, level: 'neighbourhood' }));
    const availableCompositionPopulations =
      compositionPopulations.length > 0 ? compositionPopulations : neighbourhoodPopulations;
    const nodeById = new Map((graph?.nodes ?? []).map((node) => [node.id, node]));
    const compositionOption = (composition: {
      id: string;
      level: string;
      cached?: boolean;
    }): HTMLOptionElement => {
      const node = nodeById.get(composition.id);
      const counts = node
        ? `${node.simulated_count?.toLocaleString() ?? '—'} simulated${node.represented_count ? ` representing ${node.represented_count.toLocaleString()}` : ''}`
        : composition.level.replaceAll('_', ' ');
      return new Option(
        `${composition.id} — ${counts}${composition.cached ? ', detailed + cached' : ', detailed'}`,
        `composition:${composition.id}`,
      );
    };
    const quickLevels = ['world', 'platform', 'coupled_corporate_financial'];
    const quick = quickLevels
      .map((level) => availableCompositions.find((composition) => composition.level === level))
      .filter((composition): composition is { id: string; level: string; cached?: boolean } =>
        Boolean(composition),
      );
    select.replaceChildren(
      new Option(
        `Town — ${adultPopulation.toLocaleString()} adults plus generated children, detailed, 30 days, the default demo`,
        '',
      ),
    );
    for (const composition of quick) select.add(compositionOption(composition));
    allRuns.replaceChildren(new Option('Choose another run', ''));
    const allOptions = [
      ...populations.map(
        (population) => new Option(`Weighted population — ${population}`, population),
      ),
      ...availableCompositions.map(compositionOption),
      ...availableCompositionPopulations.map(
        (population) =>
          new Option(
            `Composition population — ${population}`,
            `composition_population:${population}`,
          ),
      ),
    ];
    for (const option of allOptions) {
      allRuns.add(option);
      if (![...select.options].some((candidate) => candidate.value === option.value)) {
        const hidden = new Option(option.text, option.value);
        hidden.hidden = true;
        select.add(hidden);
      }
    }
    const values = ['', ...allOptions.map((option) => option.value)];
    select.value = values.includes(selected) ? selected : '';
    this.selectedRunLabel = select.selectedOptions[0]?.text ?? 'Town';
  }

  private renderAggregateOptions(functions: AggregateFunctionDefinition[]): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-aggregate-function]')!;
    const selected = select.value;
    select.replaceChildren(new Option('Select aggregate', ''));
    for (const definition of functions) {
      const option = new Option(definition.id, definition.id);
      option.dataset.definition = JSON.stringify(definition);
      select.add(option);
    }
    select.value = functions.some((definition) => definition.id === selected) ? selected : '';
    this.renderAggregateInputs();
  }

  private renderAggregateInputs(): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-aggregate-function]')!;
    const option = select.selectedOptions[0];
    const definition = option?.dataset.definition
      ? (JSON.parse(option.dataset.definition) as AggregateFunctionDefinition)
      : undefined;
    const host = this.root.querySelector<HTMLElement>('[data-aggregate-inputs]')!;
    host.innerHTML = (definition?.inputs ?? [])
      .map(
        (input) =>
          `<label>${escapeHtml(input.id.replaceAll('_', ' '))} <span class="dsl-help" title="Allowed range ${number(input.minimum)} to ${number(input.maximum)}; changing by ±${number(input.invalidate_threshold)} invalidates the learned branch.">?</span><input type="number" min="${input.minimum}" max="${input.maximum}" step="any" value="${input.default}" data-aggregate-input="${escapeHtml(input.id)}"><small>range ${number(input.minimum)}–${number(input.maximum)} · invalidate ±${number(input.invalidate_threshold)}</small></label>`,
      )
      .join('');
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
    const aggregateButtons = this.root.querySelectorAll<HTMLButtonElement>(
      '[data-dsl-action^="aggregate-"]',
    );
    save.disabled = !this.dirty;
    run.disabled = this.dirty || !validation?.valid;
    const aggregateSelected = Boolean(
      this.root.querySelector<HTMLSelectElement>('[data-aggregate-function]')!.value,
    );
    aggregateButtons.forEach((button) => {
      button.disabled = this.dirty || !validation?.valid || !aggregateSelected;
    });
    const reason = this.root.querySelector<HTMLElement>('[data-fast-forward-reason]')!;
    reason.textContent =
      this.dirty || !validation?.valid
        ? 'Save valid DSL before fast-forwarding.'
        : aggregateSelected
          ? 'Ready to evaluate the selected learned aggregate.'
          : 'Choose a learned aggregate function to enable fast-forward.';
  }

  private renderResults(): void {
    if (!this.run) return;
    const deltaByKey = new Map(
      this.run.comparison.map((row) => [`${row.report_id}:${row.group_id}`, row]),
    );
    const selected = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!.value;
    const compositionId = selected.startsWith('composition:')
      ? selected.slice('composition:'.length)
      : undefined;
    const node = this.document?.validation.graph?.nodes.find(
      (candidate) => candidate.id === compositionId,
    );
    const represented = node?.represented_count ?? this.run.total_agents;
    this.results.innerHTML = `
      <header><div><span class="text-dsl-eyebrow">RUN COMPLETE · ${escapeHtml(this.run.results_title)}</span><h2>${escapeHtml(this.run.results_subtitle)}</h2><p>What to run: ${escapeHtml(this.selectedRunLabel)} · ${this.run.days} days · seed ${this.run.seed} · ${this.run.ticks.toLocaleString()} ticks <span class="dsl-help" title="Ticks are the engine's fixed simulation steps across the selected days.">?</span> · ${this.run.total_agents.toLocaleString()} simulated <span class="dsl-help" title="Simulated agents are computed directly; represented agents are the real population their weighted sample stands for.">?</span> · ${represented.toLocaleString()} represented · engine ${escapeHtml(this.run.engine_version)} · ${number(this.lastRunElapsedMs, 1)} ms · detailed run</p><p>Deltas below compare this run to the previous run of the same What to run, if any.</p></div><div><span>Run</span><strong>${escapeHtml(this.run.run_id.slice(0, 8))}</strong></div></header>
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
