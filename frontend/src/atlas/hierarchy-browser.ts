import './hierarchy-browser.css';
import { escapeHtml as e } from '../views';

export type HierarchyLevel = 'region' | 'country' | 'city';
export type HierarchyCoverageState =
  | 'no_data'
  | 'partial'
  | 'estimated_only'
  | 'imputed_only'
  | 'complete';
export type ImportWorkflowStage =
  | 'source'
  | 'mapping'
  | 'confirmation'
  | 'validation'
  | 'promotion'
  | 'complete';

export type HierarchyCoverageCounts = {
  present: number;
  inherited: number;
  imputed: number;
  estimated: number;
  missing: number;
};

export type HierarchyBrowserRow = {
  row_id: string;
  parent_id: string | null;
  level: HierarchyLevel;
  label: string;
  country_code: string | null;
  geonameid: number | null;
  population: number;
  city_count: number;
  measured_coverage_percent: number;
  effective_coverage_percent: number;
  counts: HierarchyCoverageCounts;
  status: HierarchyCoverageState;
  missing_fields: string[];
  missing_field_count: number;
  missing_impact: number;
  weight_source: string;
  has_children: boolean;
};

export type HierarchyBreadcrumb = {
  label: string;
  level: HierarchyLevel;
  parent_id: string | null;
};

export type HierarchyBrowserPage = {
  level: HierarchyLevel;
  parent_id: string | null;
  rows: HierarchyBrowserRow[];
  queue: HierarchyBrowserRow[];
  breadcrumbs: HierarchyBreadcrumb[];
  filtered_count: number;
  page: number;
  page_size: number;
  scope: string;
  as_of: string;
  revision: number;
};

export type HierarchyBrowserQuery = {
  level: HierarchyLevel;
  parentId?: string;
  search: string;
  page: number;
  pageSize: number;
  scope: string;
  asOf: string;
  signal: AbortSignal;
};

export type HierarchyBrowserOptions = {
  fetchPage?: (query: HierarchyBrowserQuery) => Promise<HierarchyBrowserPage>;
  openImport?: (row?: HierarchyBrowserRow) => void;
  openCity?: (geonameid: number) => void;
  onError?: (message: string) => void;
  showQueue?: boolean;
};

export type MappingPreviewColumn = {
  column: string;
  target: string | null;
  ambiguous: boolean;
};

const stageOrder: ImportWorkflowStage[] = [
  'source',
  'mapping',
  'confirmation',
  'validation',
  'promotion',
  'complete',
];

const stageLabels: Record<ImportWorkflowStage, string> = {
  source: 'Upload or link',
  mapping: 'Mapping preview',
  confirmation: 'Human confirmation',
  validation: 'Validation',
  promotion: 'Promotion',
  complete: 'Live',
};

const statusLabels: Record<HierarchyCoverageState, string> = {
  no_data: 'No data',
  partial: 'Partial',
  estimated_only: 'Estimated only',
  imputed_only: 'Imputed only',
  complete: 'Complete',
};

const number = new Intl.NumberFormat('en');
const compactNumber = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
const fieldLabels: Record<string, string> = {
  age_sex: 'Age & sex',
  income: 'Income',
  education: 'Education',
  ideology_economic: 'Economic ideology',
  ideology_state: 'State ideology',
  ideology_cultural: 'Cultural ideology',
  household_size: 'Household size',
};

function fieldLabel(field: string): string {
  if (fieldLabels[field]) return fieldLabels[field];
  return field
    .split(/[._-]/)
    .filter(Boolean)
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(' ');
}

function percent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function missingFields(row: HierarchyBrowserRow): string {
  if (!row.missing_fields.length) return '<span class="hierarchy-no-gaps">None</span>';
  const visible = row.missing_fields.slice(0, 3).map(fieldLabel);
  const remainder = row.missing_fields.length - visible.length;
  return `${visible.map((field) => `<span>${e(field)}</span>`).join('')}${
    remainder ? `<strong>+${remainder} more</strong>` : ''
  }`;
}

function countCells(counts: HierarchyCoverageCounts): string {
  return (['present', 'inherited', 'imputed', 'estimated', 'missing'] as const)
    .map(
      (status) =>
        `<span class="hierarchy-count ${status}"><strong>${number.format(counts[status])}</strong>${status}</span>`,
    )
    .join('');
}

function rowActionLabel(row: HierarchyBrowserRow): string {
  if (row.level === 'region') return `Open countries in ${row.label}`;
  if (row.level === 'country') return `Open cities in ${row.label}`;
  return `Open ${row.label} details`;
}

function hierarchyRows(rows: HierarchyBrowserRow[]): string {
  if (!rows.length) {
    return '<tr><td colspan="8" class="hierarchy-empty">No places match this search.</td></tr>';
  }
  return rows
    .map(
      (row) => `<tr>
        <th>
          <button class="hierarchy-place" data-hierarchy-action="drill" data-row-id="${e(row.row_id)}" aria-label="${e(rowActionLabel(row))}">
            <strong>${e(row.label)}</strong>
            <span>${e(row.level)}${row.country_code ? ` · ${e(row.country_code)}` : ''}${
              row.level !== 'city' ? ` · ${number.format(row.city_count)} cities` : ''
            }</span>
          </button>
        </th>
        <td>${number.format(row.population)}</td>
        <td><strong>${percent(row.measured_coverage_percent)}</strong><span>observed here</span></td>
        <td><strong>${percent(row.effective_coverage_percent)}</strong><span>with inheritance</span></td>
        <td><div class="hierarchy-counts">${countCells(row.counts)}</div></td>
        <td><span class="hierarchy-status ${row.status}">${statusLabels[row.status]}</span></td>
        <td><div class="hierarchy-gaps">${missingFields(row)}</div></td>
        <td><button class="button secondary hierarchy-import-button" data-hierarchy-action="import" data-row-id="${e(row.row_id)}">Import</button></td>
      </tr>`,
    )
    .join('');
}

function queueRows(rows: HierarchyBrowserRow[]): string {
  if (!rows.length) {
    return '<div class="hierarchy-queue-empty"><strong>No unresolved gaps</strong><span>Every canonical field has effective coverage.</span></div>';
  }
  return rows
    .map(
      (row, index) => `<article class="hierarchy-queue-row">
        <span class="hierarchy-queue-rank">${String(index + 1).padStart(2, '0')}</span>
        <div class="hierarchy-queue-place">
          <span>${e(row.level)}</span>
          <strong>${e(row.label)}</strong>
          <small>${number.format(row.population)} population · ${e(statusLabels[row.status])}</small>
        </div>
        <div class="hierarchy-queue-gaps">
          <span>Missing</span>
          <div class="hierarchy-gaps">${missingFields(row)}</div>
        </div>
        <div class="hierarchy-impact">
          <span>Population-weighted impact</span>
          <strong>${compactNumber.format(row.missing_impact)}</strong>
          <small>person-field weight</small>
        </div>
        <div class="hierarchy-queue-actions">
          <button class="text-button" data-hierarchy-action="browse" data-row-id="${e(row.row_id)}">Browse</button>
          <button class="button primary" data-hierarchy-action="import" data-row-id="${e(row.row_id)}">Import</button>
        </div>
      </article>`,
    )
    .join('');
}

export function mappingTarget(column: MappingPreviewColumn): string {
  if (column.ambiguous || !column.target) return 'Unknown';
  return fieldLabel(column.target);
}

export function hierarchyBrowserShell(showQueue = true): string {
  return `<section class="hierarchy-browser" aria-labelledby="hierarchy-browser-title">
    ${showQueue ? `<section class="hierarchy-queue-panel" aria-labelledby="hierarchy-queue-title">
      <div class="hierarchy-section-heading">
        <div>
          <p class="eyebrow">IMPORT PRIORITY</p>
          <h2 id="hierarchy-queue-title">What needs importing</h2>
          <p>Unresolved fields ranked by population-weighted impact.</p>
        </div>
        <button class="button primary" data-hierarchy-action="import-general">Import data</button>
      </div>
      <div class="hierarchy-import-flow" data-hierarchy-import-flow></div>
      <div class="hierarchy-queue" data-hierarchy-queue><p class="muted">Loading priorities…</p></div>
    </section>` : ''}
    <section class="hierarchy-table-panel">
      <div class="hierarchy-section-heading hierarchy-browser-heading">
        <div>
          <p class="eyebrow">PLACE HIERARCHY</p>
          <h2 id="hierarchy-browser-title">Browse coverage</h2>
          <nav class="hierarchy-breadcrumbs" data-hierarchy-breadcrumbs aria-label="Place hierarchy"></nav>
        </div>
        <label class="hierarchy-search">Search this level<input type="search" data-hierarchy-search placeholder="Search regions" /></label>
      </div>
      <div class="hierarchy-toolbar">
        <button class="text-button" data-hierarchy-action="back" disabled>← Back</button>
        <span data-hierarchy-count></span>
        <span class="hierarchy-legend"><i class="present"></i>present <i class="inherited"></i>inherited <i class="imputed"></i>imputed <i class="estimated"></i>estimated <i class="missing"></i>missing</span>
      </div>
      <div class="hierarchy-table-scroll">
        <table class="hierarchy-table">
          <thead><tr><th>Place / level</th><th>Population</th><th>Measured</th><th>Effective</th><th>Field-place cells</th><th>Status</th><th>Missing fields</th><th></th></tr></thead>
          <tbody data-hierarchy-rows><tr><td colspan="8" class="hierarchy-empty">Loading hierarchy…</td></tr></tbody>
        </table>
      </div>
      <div class="hierarchy-pagination">
        <span data-hierarchy-page-label></span>
        <div><button class="button secondary" data-hierarchy-action="previous">← Previous</button><button class="button secondary" data-hierarchy-action="next">Next →</button></div>
      </div>
    </section>
  </section>`;
}

async function defaultFetchPage(query: HierarchyBrowserQuery): Promise<HierarchyBrowserPage> {
  const parameters = new URLSearchParams({
    level: query.level,
    search: query.search,
    page: String(query.page),
    page_size: String(query.pageSize),
    scope: query.scope,
    as_of: query.asOf,
  });
  if (query.parentId) parameters.set('parent_id', query.parentId);
  const response = await fetch(`/api/atlas/hierarchy-browser?${parameters}`, {
    signal: query.signal,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => undefined)) as { detail?: string } | undefined;
    throw new Error(body?.detail ?? `Hierarchy request failed (${response.status})`);
  }
  return (await response.json()) as HierarchyBrowserPage;
}

export class HierarchyBrowser {
  private level: HierarchyLevel = 'region';
  private parentId?: string;
  private search = '';
  private page = 1;
  private readonly pageSize = 50;
  private scope = 'shared';
  private asOf = new Date().toISOString().slice(0, 10);
  private generation = 0;
  private requestController?: AbortController;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private current?: HierarchyBrowserPage;
  private importStage: ImportWorkflowStage = 'source';
  private unknownMappings: string[] = [];

  constructor(
    private readonly host: HTMLElement,
    private readonly options: HierarchyBrowserOptions = {},
  ) {
    host.innerHTML = hierarchyBrowserShell(options.showQueue ?? true);
    host.addEventListener('click', this.onClick);
    host.addEventListener('input', this.onInput);
    this.renderImportFlow();
  }

  async load(): Promise<void> {
    await this.refresh();
  }

  async setContext(scope: string, asOf: string): Promise<void> {
    this.scope = scope;
    this.asOf = asOf;
    this.page = 1;
    await this.refresh();
  }

  async importCompleted(): Promise<void> {
    this.setImportProgress('complete');
    await this.refresh();
  }

  suspend(): void {
    this.generation += 1;
    this.requestController?.abort();
  }

  setImportProgress(stage: ImportWorkflowStage, preview: MappingPreviewColumn[] = []): void {
    this.importStage = stage;
    this.unknownMappings = preview
      .filter((column) => mappingTarget(column) === 'Unknown')
      .map((column) => column.column);
    this.renderImportFlow();
  }

  destroy(): void {
    clearTimeout(this.searchTimer);
    this.suspend();
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('input', this.onInput);
  }

  private get<T extends HTMLElement>(selector: string): T {
    const element = this.host.querySelector<T>(selector);
    if (!element) throw new Error(`Missing hierarchy element: ${selector}`);
    return element;
  }

  private readonly onInput = (event: Event): void => {
    const target = event.target as HTMLInputElement;
    if (!target.matches('[data-hierarchy-search]')) return;
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.search = target.value;
      this.page = 1;
      void this.refresh();
    }, 220);
  };

  private readonly onClick = (event: Event): void => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-hierarchy-action]',
    );
    if (!button || !this.host.contains(button)) return;
    const action = button.dataset.hierarchyAction;
    if (action === 'previous' && this.page > 1) {
      this.page -= 1;
      void this.refresh();
      return;
    }
    if (action === 'next' && this.current && this.page * this.pageSize < this.current.filtered_count) {
      this.page += 1;
      void this.refresh();
      return;
    }
    if (action === 'back') {
      this.goBack();
      return;
    }
    if (action === 'breadcrumb') {
      this.navigate(
        button.dataset.level as HierarchyLevel,
        button.dataset.parentId || undefined,
      );
      return;
    }
    const row = this.rowFor(button.dataset.rowId);
    if (action === 'drill' || action === 'browse') {
      if (row) this.openRow(row);
      return;
    }
    if (action === 'import' && row) {
      this.setImportProgress('source');
      this.options.openImport?.(row);
      return;
    }
    if (action === 'import-general') {
      this.setImportProgress('source');
      const firstGap = this.current?.queue[0];
      this.options.openImport?.(firstGap);
    }
  };

  private rowFor(rowId?: string): HierarchyBrowserRow | undefined {
    if (!rowId || !this.current) return undefined;
    return [...this.current.rows, ...this.current.queue].find((row) => row.row_id === rowId);
  }

  private openRow(row: HierarchyBrowserRow): void {
    if (row.level === 'region') this.navigate('country', row.row_id);
    else if (row.level === 'country') this.navigate('city', row.row_id);
    else if (row.geonameid !== null) this.options.openCity?.(row.geonameid);
  }

  private navigate(level: HierarchyLevel, parentId?: string): void {
    this.level = level;
    this.parentId = parentId;
    this.search = '';
    this.page = 1;
    this.get<HTMLInputElement>('[data-hierarchy-search]').value = '';
    void this.refresh();
  }

  private goBack(): void {
    if (this.level === 'city') {
      const regionCrumb = this.current?.breadcrumbs.find((crumb) => crumb.level === 'country');
      this.navigate('country', regionCrumb?.parent_id ?? undefined);
    } else if (this.level === 'country') {
      this.navigate('region');
    }
  }

  private async refresh(): Promise<void> {
    const generation = ++this.generation;
    this.requestController?.abort();
    const controller = new AbortController();
    this.requestController = controller;
    try {
      const current = await (this.options.fetchPage ?? defaultFetchPage)({
        level: this.level,
        parentId: this.parentId,
        search: this.search,
        page: this.page,
        pageSize: this.pageSize,
        scope: this.scope,
        asOf: this.asOf,
        signal: controller.signal,
      });
      if (generation !== this.generation) {
        controller.abort();
        return;
      }
      this.current = current;
      this.render(current);
    } catch (error) {
      if (generation !== this.generation) return;
      const message = error instanceof Error ? error.message : 'Hierarchy request failed';
      this.get('[data-hierarchy-rows]').innerHTML = `<tr><td colspan="8" class="hierarchy-empty">${e(message)}</td></tr>`;
      this.options.onError?.(message);
    }
  }

  private render(current: HierarchyBrowserPage): void {
    const queue = this.host.querySelector<HTMLElement>('[data-hierarchy-queue]');
    if (queue) queue.innerHTML = queueRows(current.queue);
    this.get('[data-hierarchy-rows]').innerHTML = hierarchyRows(current.rows);
    const levelLabel =
      current.filtered_count === 1
        ? current.level
        : current.level === 'country'
          ? 'countries'
          : `${current.level}s`;
    this.get('[data-hierarchy-count]').textContent =
      `${number.format(current.filtered_count)} ${levelLabel}`;
    this.get('[data-hierarchy-page-label]').textContent = current.filtered_count
      ? `${number.format((current.page - 1) * current.page_size + 1)}–${number.format(
          Math.min(current.page * current.page_size, current.filtered_count),
        )} of ${number.format(current.filtered_count)}`
      : '0 places';
    this.get<HTMLButtonElement>('[data-hierarchy-action="back"]').disabled =
      current.level === 'region';
    this.get<HTMLButtonElement>('[data-hierarchy-action="previous"]').disabled = current.page <= 1;
    this.get<HTMLButtonElement>('[data-hierarchy-action="next"]').disabled =
      current.page * current.page_size >= current.filtered_count;
    this.get<HTMLInputElement>('[data-hierarchy-search]').placeholder =
      `Search ${current.level}s`;
    this.get('[data-hierarchy-breadcrumbs]').innerHTML = current.breadcrumbs
      .map((crumb, index) => {
        const active = index === current.breadcrumbs.length - 1;
        if (active) return `<span aria-current="page">${e(crumb.label)}</span>`;
        return `<button data-hierarchy-action="breadcrumb" data-level="${crumb.level}" data-parent-id="${e(crumb.parent_id ?? '')}">${e(crumb.label)}</button><i>›</i>`;
      })
      .join('');
  }

  private renderImportFlow(): void {
    const importFlow = this.host.querySelector<HTMLElement>('[data-hierarchy-import-flow]');
    if (!importFlow) return;
    const activeIndex = stageOrder.indexOf(this.importStage);
    const steps = stageOrder
      .map((stage, index) => {
        const state = index < activeIndex ? 'done' : index === activeIndex ? 'active' : '';
        return `<li class="${state}"><i>${index < activeIndex ? '✓' : index + 1}</i><span>${stageLabels[stage]}</span></li>`;
      })
      .join('');
    const unknown = this.unknownMappings.length
      ? `<p role="status"><strong>Unknown:</strong> ${this.unknownMappings.map(e).join(', ')}. Choose a target or explicitly ignore each column before validation.</p>`
      : '';
    importFlow.innerHTML = `<ol>${steps}</ol><small class="hierarchy-validation-rule">Categorical totals must equal 100% · duplicate place-field cells are blocked · ambiguous columns stay Unknown</small>${unknown}`;
  }
}
