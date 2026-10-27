import { escapeHtml as e } from '../views';
import type {
  AutoImportAttempt,
  AutoImportBatch,
  AutoImportBatchItem,
  AutoImportClient,
  AutoImportQueueItem,
  AutoImportQueuePage,
  AutoImportQueueQuery,
  AutoImportTarget,
  BatchPromotionRequest,
  BulkSelection,
} from './auto-import-model';

type BulkPanelOptions = {
  client: AutoImportClient;
  context: () => { scope: string; asOf: string };
  openTarget: (target: AutoImportTarget) => void;
  openAttempt: (attemptId: string) => void | Promise<void>;
  onBatchPromoted?: (batch: AutoImportBatch) => void | Promise<void>;
  onError?: (message: string) => void;
  pollIntervalMs: number;
};

const integer = new Intl.NumberFormat('en');
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

function promotionConfirmation(scope: string): string {
  if (scope === 'shared') {
    return 'I confirm the reviewed sources permit redistribution in the shared atlas.';
  }
  return `I confirm these distributions can be added to run ${scope.slice(0, 8)} and remain scoped to that run.`;
}

function blankPage(query: AutoImportQueueQuery): AutoImportQueuePage {
  return {
    items: [],
    filtered_count: 0,
    filtered_population: 0,
    page: query.page,
    page_size: query.page_size,
    primary_count: 0,
    primary_population: 0,
    lower_priority_count: 0,
    lower_priority_population: 0,
  };
}

function shell(): string {
  return `<section class="auto-import-panel" aria-labelledby="auto-import-queue-title">
    <div class="auto-import-panel-heading">
      <div><p class="eyebrow">IMPORT PRIORITY</p><h2 id="auto-import-queue-title">What needs importing</h2><p>One actionable row per missing feature and place.</p></div>
      <button class="button secondary" type="button" data-auto-import-bulk-action="refresh">Refresh</button>
    </div>
    <div class="auto-import-controls">
      <label>Place level<select data-auto-import-filter="level"><option value="all">All levels</option><option value="region">Regions</option><option value="country">Countries</option><option value="city">Cities</option></select></label>
      <label>Feature<select data-auto-import-filter="feature"><option value="">All features</option><option value="age_sex">Age &amp; sex</option><option value="income">Income</option><option value="education">Education</option><option value="ideology_economic">Economic ideology</option><option value="ideology_state">State ideology</option><option value="ideology_cultural">Cultural ideology</option><option value="household_size">Household size</option></select></label>
      <label>Sort<select data-auto-import-filter="sort"><option value="hierarchy_impact">Hierarchy, then impact</option><option value="impact">Missing impact</option><option value="population">Population</option></select></label>
      <label>Search<input type="search" data-auto-import-filter="search" placeholder="Place or feature" /></label>
      <label>Priority city threshold<input type="number" min="0" step="500" value="1000000" data-auto-import-filter="threshold" /></label>
    </div>
    <div class="auto-import-priority-tabs" role="group" aria-label="City priority cohort">
      <button type="button" class="active" data-auto-import-priority="primary" aria-pressed="true"><i data-auto-import-primary-label>Regions, countries, and cities ≥ 1,000,000</i><span data-auto-import-primary-count>0</span></button>
      <button type="button" data-auto-import-priority="lower" aria-pressed="false"><i data-auto-import-lower-label>Lower-priority cities &lt; 1,000,000</i><span data-auto-import-lower-count>0</span></button>
    </div>
    <div class="auto-import-selection-bar">
      <label><input type="checkbox" data-auto-import-select-all />Select all filtered</label>
      <span data-auto-import-filter-summary>Loading…</span>
      <strong data-auto-import-selection-summary>0 selected</strong>
      <label>Concurrency<select data-auto-import-concurrency><option>2</option><option selected>4</option><option>6</option><option>8</option></select></label>
      <button class="button primary" type="button" data-auto-import-bulk-action="start" disabled>Start selected auto-import</button>
    </div>
    <div class="auto-import-queue" data-auto-import-queue role="list"><p class="auto-import-empty">Loading import queue…</p></div>
    <div class="auto-import-pagination"><span data-auto-import-page-label></span><div><button class="button secondary" type="button" data-auto-import-bulk-action="previous">← Previous</button><button class="button secondary" type="button" data-auto-import-bulk-action="next">Next →</button></div></div>
    <div data-auto-import-batch></div>
  </section>`;
}

function queueRow(item: AutoImportQueueItem, selected: boolean): string {
  return `<article class="auto-import-queue-row" role="listitem">
    <label class="auto-import-row-select"><input type="checkbox" data-auto-import-item-select="${e(item.item_id)}"${selected ? ' checked' : ''} /><span class="visually-hidden">Select ${e(item.field_label)} for ${e(item.place_label)}</span></label>
    <div class="auto-import-row-place"><span>${e(item.level)}</span><strong>${e(item.place_label)}</strong><small>${integer.format(item.population)} people${item.country_code ? ` · ${e(item.country_code)}` : ''}</small></div>
    <div class="auto-import-row-feature"><span>Missing feature</span><strong>${e(item.field_label)}</strong><small>${e(item.required_distribution.denominator)} · ${e(item.required_distribution.time_unit)}</small></div>
    <div class="auto-import-row-impact"><span>Missing impact</span><strong>${compact.format(item.missing_impact)}</strong><small>population weight</small></div>
    <button class="button primary" type="button" data-auto-import-field="${e(item.item_id)}">Import ${e(item.field_label)}</button>
  </article>`;
}

function batchProgress(batch: AutoImportBatch): string {
  const summary = batch.summary;
  const complete = summary.completed;
  const percent = summary.total ? Math.min(100, (complete / summary.total) * 100) : 0;
  return `<div class="auto-import-batch-progress" role="status">
    <div><span>Batch ${e(batch.status)}</span><strong>${integer.format(complete)} / ${integer.format(summary.total)}</strong></div>
    <progress max="100" value="${percent}">${percent.toFixed(0)}%</progress>
    <dl><div><dt>Running</dt><dd>${integer.format(summary.running)}</dd></div><div><dt>Ready</dt><dd>${integer.format(summary.ready)}</dd></div><div><dt>Measured</dt><dd>${integer.format(summary.measured)}</dd></div><div><dt>Estimated</dt><dd>${integer.format(summary.estimated)}</dd></div><div><dt>Failed</dt><dd>${integer.format(summary.failed)}</dd></div><div><dt>Promoted</dt><dd>${integer.format(summary.promoted)}</dd></div></dl>
  </div>`;
}

function batchMapping(item: AutoImportBatchItem): string {
  if (!item.mappings.length) return '<span class="auto-import-mapping-empty">Not available</span>';
  const unknown = item.mappings.filter((mapping) => !mapping.target).length;
  const label = unknown
    ? `${integer.format(unknown)} Unknown`
    : `${integer.format(item.mappings.length)} mapped`;
  return `<details class="auto-import-batch-mapping"${unknown ? ' open' : ''}>
    <summary>${label}</summary>
    <dl>${item.mappings
      .map(
        (mapping) =>
          `<div><dt>${e(mapping.column)}</dt><dd>${mapping.target ? e(mapping.target) : '<strong>Unknown</strong>'}</dd></div>`,
      )
      .join('')}</dl>
  </details>`;
}

function batchItem(item: AutoImportBatchItem, selected: boolean): string {
  const evidence = item.evidence_kind ?? 'unresolved';
  const review = item.attempt_id
    ? `<button class="text-button" type="button" data-auto-import-review-attempt="${e(item.attempt_id)}">Review</button>`
    : '';
  const promote = item.can_promote
    ? `<button class="button secondary" type="button" data-auto-import-promote-item="${e(item.item_id)}">Promote</button>`
    : '';
  return `<tr>
    <td><input type="checkbox" data-auto-import-review-select="${e(item.item_id)}"${selected ? ' checked' : ''}${item.can_promote ? '' : ' disabled'} aria-label="Select ${e(item.target.field_label)} for promotion" /></td>
    <th>${e(item.target.place_label)}<small>${e(item.target.level)}</small></th>
    <td>${e(item.target.field_label)}</td>
    <td>${batchMapping(item)}</td>
    <td><span class="auto-import-execution ${e(item.status)}">${e(item.status)}</span></td>
    <td><span class="auto-import-evidence ${e(evidence)}">${e(evidence)}</span></td>
    <td>${item.error ? `<span class="auto-import-item-error">${e(item.error)}</span>` : '—'}</td>
    <td><div class="auto-import-item-actions">${review}${promote}</div></td>
  </tr>`;
}

function batchView(
  batch: AutoImportBatch,
  selected: Set<string>,
  mappingConfirmed: boolean,
  destinationConfirmed: boolean,
  scope: string,
): string {
  const reviewable = batch.items.filter(
    (item) => item.status !== 'queued' && item.status !== 'running',
  );
  return `<section class="auto-import-batch" aria-labelledby="auto-import-batch-title">
    <div class="auto-import-batch-heading"><div><p class="eyebrow">BULK REVIEW</p><h2 id="auto-import-batch-title">Review before promotion</h2><p>Measured and estimated results remain distinct. Nothing is promoted automatically.</p></div><button class="button secondary" type="button" data-auto-import-bulk-action="resume">Resume review</button></div>
    ${batchProgress(batch)}
    <div class="auto-import-table-scroll"><table class="auto-import-batch-table"><thead><tr><th></th><th>Place</th><th>Feature</th><th>Mapping</th><th>Execution</th><th>Evidence</th><th>Issue</th><th></th></tr></thead><tbody>${reviewable.map((item) => batchItem(item, selected.has(item.item_id))).join('') || '<tr><td colspan="8">Results will appear here as each item finishes.</td></tr>'}</tbody></table></div>
    <div class="auto-import-batch-actions">
      <label class="auto-import-check"><input type="checkbox" data-auto-import-batch-mapping-confirmed${mappingConfirmed ? ' checked' : ''} />I reviewed the proposed mappings. Unknown values remain blocked from promotion.</label>
      <label class="auto-import-check"><input type="checkbox" data-auto-import-batch-rights${destinationConfirmed ? ' checked' : ''} />${e(promotionConfirmation(scope))}</label>
      <button class="button secondary" type="button" data-auto-import-bulk-action="retry"${batch.summary.retryable_failed ? '' : ' disabled'}>Retry failed</button>
      <button class="button secondary" type="button" data-auto-import-bulk-action="promote-selected"${selected.size ? '' : ' disabled'}>Promote selected</button>
      <button class="button primary" type="button" data-auto-import-bulk-action="promote-all"${batch.summary.ready ? '' : ' disabled'}>Promote all eligible</button>
    </div>
  </section>`;
}

export class AutoImportBulkPanel {
  private query: AutoImportQueueQuery;
  private page: AutoImportQueuePage;
  private explicitSelection = new Set<string>();
  private allFiltered = false;
  private excluded = new Set<string>();
  private itemCache = new Map<string, AutoImportQueueItem>();
  private reviewSelection = new Set<string>();
  private batchValue?: AutoImportBatch;
  private requestController?: AbortController;
  private batchRequestController?: AbortController;
  private generation = 0;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private pollTimer?: ReturnType<typeof setTimeout>;
  private busy = false;
  private mappingConfirmed = false;
  private destinationConfirmed = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: BulkPanelOptions,
  ) {
    const context = options.context();
    this.query = {
      scope: context.scope,
      as_of: context.asOf,
      level: 'all',
      feature_id: '',
      search: '',
      sort: 'hierarchy_impact',
      priority: 'primary',
      city_population_threshold: 1_000_000,
      page: 1,
      page_size: 50,
    };
    this.page = blankPage(this.query);
    host.innerHTML = shell();
    host.addEventListener('click', this.onClick);
    host.addEventListener('change', this.onChange);
    host.addEventListener('input', this.onInput);
  }

  async load(): Promise<void> {
    await Promise.all([this.refresh(), this.recoverBatch()]);
  }

  async setContext(scope: string, asOf: string): Promise<void> {
    if (scope === this.query.scope && asOf === this.query.as_of) return;
    this.query = { ...this.query, scope, as_of: asOf, page: 1 };
    this.clearSelection();
    this.clearBatch();
    await Promise.all([this.refresh(), this.recoverBatch()]);
  }

  async importCompleted(attempt?: AutoImportAttempt): Promise<void> {
    if (attempt) {
      this.mappingConfirmed = false;
      this.destinationConfirmed = false;
    }
    await Promise.all([this.refresh(), this.refreshBatch(attempt)]);
  }

  async attemptChanged(attempt: AutoImportAttempt): Promise<void> {
    this.mappingConfirmed = false;
    this.destinationConfirmed = false;
    await this.refreshBatch(attempt);
  }

  suspend(): void {
    this.generation += 1;
    this.requestController?.abort();
    this.batchRequestController?.abort();
    clearTimeout(this.pollTimer);
  }

  destroy(): void {
    this.suspend();
    clearTimeout(this.searchTimer);
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('input', this.onInput);
  }

  private clearSelection(): void {
    this.explicitSelection.clear();
    this.excluded.clear();
    this.itemCache.clear();
    this.allFiltered = false;
  }

  private clearBatch(): void {
    clearTimeout(this.pollTimer);
    this.batchValue = undefined;
    this.reviewSelection.clear();
    this.mappingConfirmed = false;
    this.destinationConfirmed = false;
    this.renderBatch();
  }

  private selected(itemId: string): boolean {
    return this.allFiltered ? !this.excluded.has(itemId) : this.explicitSelection.has(itemId);
  }

  private selectedSummary(): { count: number; population: number } {
    if (this.allFiltered) {
      const excludedPlaces = new Map<
        string,
        { count: number; itemCount: number; population: number }
      >();
      this.excluded.forEach((itemId) => {
        const item = this.itemCache.get(itemId);
        if (!item) return;
        const current = excludedPlaces.get(item.place_id) ?? {
          count: 0,
          itemCount: item.place_item_count,
          population: item.population,
        };
        current.count += 1;
        excludedPlaces.set(item.place_id, current);
      });
      const excludedPopulation = [...excludedPlaces.values()]
        .filter((place) => place.count >= place.itemCount)
        .reduce((total, place) => total + place.population, 0);
      return {
        count: Math.max(0, this.page.filtered_count - this.excluded.size),
        population: Math.max(0, this.page.filtered_population - excludedPopulation),
      };
    }
    const items = [...this.explicitSelection]
      .map((id) => this.itemCache.get(id))
      .filter(Boolean) as AutoImportQueueItem[];
    const populations = new Map<string, number>();
    items.forEach((item) =>
      populations.set(
        item.place_id,
        Math.max(item.population, populations.get(item.place_id) ?? 0),
      ),
    );
    return {
      count: this.explicitSelection.size,
      population: [...populations.values()].reduce((sum, population) => sum + population, 0),
    };
  }

  private selection(): BulkSelection {
    if (this.allFiltered) {
      return {
        mode: 'all_filtered',
        query: { ...this.query, page: 1 },
        excluded_item_ids: [...this.excluded],
      };
    }
    return { mode: 'explicit', item_ids: [...this.explicitSelection] };
  }

  private async refresh(): Promise<void> {
    const generation = ++this.generation;
    this.requestController?.abort();
    const controller = new AbortController();
    this.requestController = controller;
    this.setBusy(true);
    try {
      const page = await this.options.client.queue(this.query, controller.signal);
      if (generation !== this.generation) return;
      this.page = page;
      page.items.forEach((item) => this.itemCache.set(item.item_id, item));
      this.renderQueue();
    } catch (error) {
      if (
        generation === this.generation &&
        !(error instanceof DOMException && error.name === 'AbortError')
      )
        this.report(error);
    } finally {
      if (generation === this.generation) this.setBusy(false);
    }
  }

  private async recoverBatch(): Promise<void> {
    this.batchRequestController?.abort();
    const controller = new AbortController();
    this.batchRequestController = controller;
    const scope = this.query.scope;
    try {
      const batch = await this.options.client.latestBatch(scope, controller.signal);
      if (controller.signal.aborted || scope !== this.query.scope) return;
      this.batchValue = batch ?? undefined;
      this.reviewSelection.clear();
      this.mappingConfirmed = false;
      this.destinationConfirmed = false;
      this.renderBatch();
      this.schedulePoll();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) this.report(error);
    }
  }

  private async refreshBatch(attempt?: AutoImportAttempt): Promise<void> {
    if (!this.batchValue) return;
    if (attempt && !this.batchValue.items.some((item) => item.attempt_id === attempt.attempt_id))
      return;
    const scope = this.query.scope;
    try {
      const batch = await this.options.client.batch(this.batchValue.batch_id);
      if (scope !== this.query.scope) return;
      this.batchValue = batch;
      this.reviewSelection = new Set(
        [...this.reviewSelection].filter((itemId) =>
          batch.items.some((item) => item.item_id === itemId && item.can_promote),
        ),
      );
      this.renderBatch();
      this.schedulePoll();
    } catch (error) {
      this.report(error);
    }
  }

  private renderQueue(): void {
    const rows = this.page.items
      .map((item) => queueRow(item, this.selected(item.item_id)))
      .join('');
    this.get('[data-auto-import-queue]').innerHTML =
      rows || '<p class="auto-import-empty">No missing fields match these filters.</p>';
    this.get('[data-auto-import-filter-summary]').textContent =
      `${integer.format(this.page.filtered_count)} fields · ${integer.format(this.page.filtered_population)} people`;
    this.get('[data-auto-import-primary-count]').textContent = integer.format(
      this.page.primary_count,
    );
    this.get('[data-auto-import-lower-count]').textContent = integer.format(
      this.page.lower_priority_count,
    );
    this.get('[data-auto-import-primary-label]').textContent = this.query.city_population_threshold
      ? `Regions, countries, and cities ≥ ${integer.format(this.query.city_population_threshold)}`
      : 'Regions, countries, and all cities';
    this.get('[data-auto-import-lower-label]').textContent = this.query.city_population_threshold
      ? `Lower-priority cities < ${integer.format(this.query.city_population_threshold)}`
      : 'No lower-priority cohort';
    this.get('[data-auto-import-page-label]').textContent = this.page.filtered_count
      ? `${integer.format((this.page.page - 1) * this.page.page_size + 1)}–${integer.format(Math.min(this.page.page * this.page.page_size, this.page.filtered_count))} of ${integer.format(this.page.filtered_count)}`
      : '0 fields';
    this.get<HTMLButtonElement>('[data-auto-import-bulk-action="previous"]').disabled =
      this.page.page <= 1;
    this.get<HTMLButtonElement>('[data-auto-import-bulk-action="next"]').disabled =
      this.page.page * this.page.page_size >= this.page.filtered_count;
    this.host
      .querySelectorAll<HTMLButtonElement>('[data-auto-import-priority]')
      .forEach((button) => {
        const active = button.dataset.autoImportPriority === this.query.priority;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
    this.updateSelectionView();
  }

  private renderBatch(): void {
    this.get('[data-auto-import-batch]').innerHTML = this.batchValue
      ? batchView(
          this.batchValue,
          this.reviewSelection,
          this.mappingConfirmed,
          this.destinationConfirmed,
          this.query.scope,
        )
      : '';
  }

  private updateSelectionView(): void {
    const summary = this.selectedSummary();
    this.get('[data-auto-import-selection-summary]').textContent =
      `${integer.format(summary.count)} selected · ${integer.format(summary.population)} population`;
    const all = this.get<HTMLInputElement>('[data-auto-import-select-all]');
    all.checked = this.allFiltered && this.excluded.size === 0;
    all.indeterminate = this.allFiltered && this.excluded.size > 0;
    this.get<HTMLButtonElement>('[data-auto-import-bulk-action="start"]').disabled =
      this.busy || summary.count === 0;
  }

  private setBusy(busy: boolean): void {
    this.busy = busy;
    this.updateSelectionView();
  }

  private get<T extends HTMLElement = HTMLElement>(selector: string): T {
    const element = this.host.querySelector<T>(selector);
    if (!element) throw new Error(`Missing auto-import element: ${selector}`);
    return element;
  }

  private report(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.options.onError?.(message);
    this.get('[data-auto-import-queue]').insertAdjacentHTML(
      'afterbegin',
      `<div class="auto-import-error" role="alert">${e(message)}</div>`,
    );
  }

  private changeQuery(change: Partial<AutoImportQueueQuery>): void {
    this.query = { ...this.query, ...change, page: 1 };
    this.clearSelection();
    void this.refresh();
  }

  private readonly onInput = (event: Event): void => {
    const input = event.target as HTMLInputElement;
    if (input.dataset.autoImportFilter !== 'search') return;
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.changeQuery({ search: input.value.trim() }), 250);
  };

  private readonly onChange = (event: Event): void => {
    const input = event.target as HTMLInputElement | HTMLSelectElement;
    if (input.dataset.autoImportFilter === 'level')
      this.changeQuery({ level: input.value as AutoImportQueueQuery['level'] });
    if (input.dataset.autoImportFilter === 'feature') this.changeQuery({ feature_id: input.value });
    if (input.dataset.autoImportFilter === 'sort')
      this.changeQuery({ sort: input.value as AutoImportQueueQuery['sort'] });
    if (input.dataset.autoImportFilter === 'threshold')
      this.changeQuery({
        city_population_threshold:
          input.value.trim() === '' ? 0 : Math.max(0, Number(input.value) || 0),
      });
    if (input.hasAttribute('data-auto-import-select-all')) {
      this.allFiltered = (input as HTMLInputElement).checked;
      this.explicitSelection.clear();
      this.excluded.clear();
      this.renderQueue();
    }
    const itemId = input.dataset.autoImportItemSelect;
    if (itemId) {
      if (this.allFiltered) {
        if ((input as HTMLInputElement).checked) this.excluded.delete(itemId);
        else this.excluded.add(itemId);
      } else if ((input as HTMLInputElement).checked) this.explicitSelection.add(itemId);
      else this.explicitSelection.delete(itemId);
      this.updateSelectionView();
    }
    const reviewId = input.dataset.autoImportReviewSelect;
    if (reviewId) {
      if ((input as HTMLInputElement).checked) this.reviewSelection.add(reviewId);
      else this.reviewSelection.delete(reviewId);
      this.renderBatch();
    }
    if (input.hasAttribute('data-auto-import-batch-mapping-confirmed')) {
      this.mappingConfirmed = (input as HTMLInputElement).checked;
    }
    if (input.hasAttribute('data-auto-import-batch-rights')) {
      this.destinationConfirmed = (input as HTMLInputElement).checked;
    }
  };

  private readonly onClick = (event: Event): void => {
    const element = event.target as HTMLElement;
    const priority = element.closest<HTMLButtonElement>('[data-auto-import-priority]');
    if (priority) {
      this.changeQuery({
        priority: priority.dataset.autoImportPriority as AutoImportQueueQuery['priority'],
      });
      return;
    }
    const importButton = element.closest<HTMLButtonElement>('[data-auto-import-field]');
    if (importButton) {
      const item = this.itemCache.get(importButton.dataset.autoImportField ?? '');
      if (item) this.options.openTarget(item);
      return;
    }
    const review = element.closest<HTMLButtonElement>('[data-auto-import-review-attempt]');
    if (review?.dataset.autoImportReviewAttempt) {
      void this.options.openAttempt(review.dataset.autoImportReviewAttempt);
      return;
    }
    const promoteItem = element.closest<HTMLButtonElement>('[data-auto-import-promote-item]');
    if (promoteItem?.dataset.autoImportPromoteItem) {
      void this.promote('selected', [promoteItem.dataset.autoImportPromoteItem]);
      return;
    }
    const button = element.closest<HTMLButtonElement>('[data-auto-import-bulk-action]');
    if (!button) return;
    const action = button.dataset.autoImportBulkAction;
    if (action === 'refresh') void this.refresh();
    if (action === 'previous' && this.query.page > 1) {
      this.query.page -= 1;
      void this.refresh();
    }
    if (action === 'next' && this.query.page * this.query.page_size < this.page.filtered_count) {
      this.query.page += 1;
      void this.refresh();
    }
    if (action === 'start') void this.startBatch();
    if (action === 'retry') void this.retryBatch();
    if (action === 'resume') void this.pollBatch(true);
    if (action === 'promote-selected') void this.promote('selected', [...this.reviewSelection]);
    if (action === 'promote-all') void this.promote('all_eligible', []);
  };

  private async startBatch(): Promise<void> {
    const selected = this.selectedSummary();
    if (!selected.count) return;
    const concurrency = Number(this.get<HTMLSelectElement>('[data-auto-import-concurrency]').value);
    this.setBusy(true);
    try {
      this.batchValue = await this.options.client.createBatch({
        scope: this.query.scope,
        as_of: this.query.as_of,
        concurrency,
        selection: this.selection(),
      });
      this.reviewSelection.clear();
      this.mappingConfirmed = false;
      this.destinationConfirmed = false;
      this.renderBatch();
      this.schedulePoll();
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }

  private schedulePoll(): void {
    clearTimeout(this.pollTimer);
    if (!this.batchValue || !['queued', 'running'].includes(this.batchValue.status)) return;
    this.pollTimer = setTimeout(() => void this.pollBatch(), this.options.pollIntervalMs);
  }

  private async pollBatch(force = false): Promise<void> {
    if (!this.batchValue) return;
    if (!force && !['queued', 'running'].includes(this.batchValue.status)) return;
    try {
      this.batchValue = await this.options.client.batch(this.batchValue.batch_id);
      this.renderBatch();
      this.schedulePoll();
    } catch (error) {
      this.report(error);
    }
  }

  private async retryBatch(): Promise<void> {
    if (!this.batchValue) return;
    try {
      this.batchValue = await this.options.client.retryBatch(this.batchValue.batch_id);
      this.mappingConfirmed = false;
      this.destinationConfirmed = false;
      this.renderBatch();
      this.schedulePoll();
    } catch (error) {
      this.report(error);
    }
  }

  private async promote(mode: BatchPromotionRequest['mode'], itemIds: string[]): Promise<void> {
    if (!this.batchValue) return;
    if (!this.mappingConfirmed) {
      this.report(new Error('Review and confirm the proposed mappings before promotion.'));
      return;
    }
    if (!this.destinationConfirmed) {
      this.report(
        new Error(
          this.query.scope === 'shared'
            ? 'Confirm redistribution rights before promotion.'
            : 'Confirm the run-scoped import before promotion.',
        ),
      );
      return;
    }
    try {
      this.batchValue = await this.options.client.promoteBatch(this.batchValue.batch_id, {
        mode,
        item_ids: itemIds,
        mapping_confirmed: this.mappingConfirmed,
        redistribution_confirmed: this.destinationConfirmed,
      });
      this.reviewSelection.clear();
      this.mappingConfirmed = false;
      this.destinationConfirmed = false;
      this.renderBatch();
      await this.options.onBatchPromoted?.(this.batchValue);
      await this.refresh();
    } catch (error) {
      this.report(error);
    }
  }
}
