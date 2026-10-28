import './text-dsl-editor.css';

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
  archetypes: string[];
  weighted_populations: string[];
  aggregate_functions: AggregateFunctionDefinition[];
  neighbourhoods: string[];
  neighbourhood_populations: string[];
  diagnostics: DslDiagnostic[];
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
  private readonly root = document.createElement('section');
  private readonly textarea = document.createElement('textarea');
  private readonly gutter = document.createElement('pre');
  private readonly status: HTMLElement;
  private readonly diagnostics: HTMLElement;
  private readonly results: HTMLElement;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: TextDslEditorOptions,
  ) {
    this.root.className = 'text-dsl-workspace';
    this.root.innerHTML = `
      <header class="text-dsl-heading">
        <div><span class="text-dsl-eyebrow">RUST DSL · SOURCE OF TRUTH</span><h1>Small-town simulation program</h1><p>Edit the exact Python-like DSL that the Rust engine parses and runs. Town coefficients retain their placeholder labels; archetype values are explicit estimates.</p></div>
        <div class="text-dsl-hash" data-dsl-hash>Loading…</div>
      </header>
      <div class="text-dsl-toolbar">
        <button type="button" class="button secondary" data-dsl-action="validate">Validate code</button>
        <button type="button" class="button primary" data-dsl-action="save">Save DSL</button>
        <button type="button" class="button secondary" data-dsl-action="reset">Reset shipped DSL</button>
        <label>Population<select data-dsl-population><option value="">Town</option></select></label>
        <label>Seed<input type="number" min="0" step="1" value="1" data-dsl-seed></label>
        <label>Days<input type="number" min="1" max="365" step="1" value="30" data-dsl-days></label>
        <button type="button" class="button primary" data-dsl-action="run">Run saved DSL</button>
      </div>
      <div class="text-dsl-aggregate-toolbar">
        <label>Aggregate function<select data-aggregate-function><option value="">Select archetype</option></select></label>
        <div class="text-dsl-aggregate-inputs" data-aggregate-inputs></div>
        <label>Evaluation day<input type="number" min="0" step="1" value="0" data-aggregate-day></label>
        <label>Events<input type="text" placeholder="disaster, pandemic" data-aggregate-events></label>
        <button type="button" class="button secondary" data-dsl-action="aggregate-cached">Evaluate cached</button>
        <button type="button" class="button secondary" data-dsl-action="aggregate-relearn">Relearn detailed</button>
      </div>
      <div class="text-dsl-status" role="status" data-dsl-status>Loading Rust DSL…</div>
      <div class="text-dsl-code-frame" data-dsl-code-frame></div>
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
    this.host.replaceChildren(this.root);
    this.root.addEventListener('click', this.onClick);
    this.root
      .querySelector<HTMLSelectElement>('[data-aggregate-function]')!
      .addEventListener('change', this.onAggregateFunctionChange);
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
    const neighbourhoodId = populationId.startsWith('neighbourhood:')
      ? populationId.slice('neighbourhood:'.length)
      : null;
    const neighbourhoodPopulationId = populationId.startsWith('neighbourhood_population:')
      ? populationId.slice('neighbourhood_population:'.length)
      : null;
    const weightedPopulationId =
      neighbourhoodId || neighbourhoodPopulationId ? null : populationId || null;
    this.status.textContent = `Running ${days} days in the Rust DSL engine…`;
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
          neighbourhood_id: neighbourhoodId,
          neighbourhood_population_id: neighbourhoodPopulationId,
        }),
      });
      this.status.textContent = `Completed ${this.run.ticks.toLocaleString()} Rust ticks.`;
      this.renderResults();
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = error instanceof Error ? error.message : String(error);
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
            events,
            force_relearn: forceRelearn,
          }),
        },
      );
      this.status.textContent = `${result.cache_hit ? 'Cache hit' : 'Detailed relearn'} · ${result.agent_ticks.toLocaleString()} agent ticks · ${number(result.elapsed_seconds * 1000, 1)} ms.`;
      this.renderAggregateResults(result, days);
    } catch (error) {
      this.options.onError(error);
      this.status.textContent = error instanceof Error ? error.message : String(error);
    }
  }

  private renderAggregateResults(result: AggregateEvaluationResult, days: number): void {
    const deltas = new Map<string, ReportDelta>();
    const outputIds = Object.keys(result.time_series.at(-1)?.outputs ?? {});
    this.results.innerHTML = `
      <header><div><span class="text-dsl-eyebrow">${result.cache_hit ? 'CACHED FAST-FORWARD' : 'DETAILED RELEARN'}</span><h2>${escapeHtml(result.function_id)}</h2><p>${days} days · cache v${result.cache_version} · ${number(result.elapsed_seconds * 1000, 1)} ms · ${result.agent_ticks.toLocaleString()} agent ticks</p></div></header>
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
    this.renderPopulationOptions(
      validation.weighted_populations ?? [],
      validation.neighbourhoods ?? [],
      validation.neighbourhood_populations ?? [],
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
    neighbourhoods: string[],
    neighbourhoodPopulations: string[],
  ): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-dsl-population]')!;
    const selected = select.value;
    select.replaceChildren(new Option('Town', ''));
    for (const population of populations) {
      select.add(new Option(population, population));
    }
    for (const neighbourhood of neighbourhoods) {
      select.add(new Option(`Neighbourhood · ${neighbourhood}`, `neighbourhood:${neighbourhood}`));
    }
    for (const population of neighbourhoodPopulations) {
      select.add(
        new Option(
          `Neighbourhood population · ${population}`,
          `neighbourhood_population:${population}`,
        ),
      );
    }
    const values = [
      ...populations,
      ...neighbourhoods.map((neighbourhood) => `neighbourhood:${neighbourhood}`),
      ...neighbourhoodPopulations.map((population) => `neighbourhood_population:${population}`),
    ];
    select.value = values.includes(selected) ? selected : '';
  }

  private renderAggregateOptions(functions: AggregateFunctionDefinition[]): void {
    const select = this.root.querySelector<HTMLSelectElement>('[data-aggregate-function]')!;
    const selected = select.value;
    select.replaceChildren(new Option('Select archetype', ''));
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
          `<label>${escapeHtml(input.id.replaceAll('_', ' '))}<input type="number" min="${input.minimum}" max="${input.maximum}" step="any" value="${input.default}" data-aggregate-input="${escapeHtml(input.id)}"><small>invalidate ±${number(input.invalidate_threshold)}</small></label>`,
      )
      .join('');
  }

  private focusLine(line: number): void {
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
  }

  private renderResults(): void {
    if (!this.run) return;
    const deltaByKey = new Map(
      this.run.comparison.map((row) => [`${row.report_id}:${row.group_id}`, row]),
    );
    this.results.innerHTML = `
      <header><div><span class="text-dsl-eyebrow">${escapeHtml(this.run.results_title)}</span><h2>${escapeHtml(this.run.results_subtitle)}</h2><p>Run ${escapeHtml(this.run.run_id.slice(0, 8))} · seed ${this.run.seed} · ${this.run.days} days · ${this.run.engine_version}</p></div></header>
      ${this.run.reports.map((report) => this.report(report, deltaByKey)).join('')}`;
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
