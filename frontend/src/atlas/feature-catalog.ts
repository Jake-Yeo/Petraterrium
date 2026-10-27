import './feature-catalog.css';
import { escapeHtml as e } from '../views';

export type FeatureCatalogStatus = 'pending' | 'awaiting_data' | 'ready';
export type FeatureKind = 'categorical' | 'continuous' | 'binary';
export type FeatureUsageMode = 'predictive' | 'label_only';

export interface FeatureRange {
  minimum: number;
  maximum: number;
  unit: string;
}

export interface FeatureEvidence {
  source: string;
  version: string;
  status: string;
  uncertainty: number;
  source_date: string | null;
}

export interface FeatureDistribution {
  feature_id: string;
  level: 'global' | 'region' | 'subregion' | 'country' | 'city';
  place: string;
  population: string;
  population_count: number | null;
  coverage_percent: number;
  values: Record<string, number>;
  mean: number | null;
  standard_deviation: number | null;
  provenance: FeatureEvidence;
  method: 'measured' | 'compositional' | 'fallback';
}

export interface FeatureUsage {
  name: string;
  mode: FeatureUsageMode;
  reason: string;
  population: string | null;
  provenance: FeatureEvidence | null;
}

export interface CatalogFeature {
  id: string;
  name: string;
  type: FeatureKind;
  canonical_values: string[];
  value_range: FeatureRange | null;
  description: string;
  provenance_placeholder: string;
  status: FeatureCatalogStatus;
  predictor_blocked: boolean;
  distributions: FeatureDistribution[];
  usages: FeatureUsage[];
  custom: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface FeatureCatalogView {
  version: string;
  features: CatalogFeature[];
}

export interface FeatureCreateRequest {
  id: string;
  name: string;
  type: FeatureKind;
  canonical_values: string[];
  value_range: FeatureRange | null;
  description: string;
  provenance_placeholder: string;
  status: 'pending' | 'awaiting_data';
}

export interface FeatureCatalogState {
  place: string;
  search: string;
  status: '' | FeatureCatalogStatus;
}

export interface FeatureCatalogApi {
  list(): Promise<FeatureCatalogView>;
  detail(featureId: string): Promise<CatalogFeature>;
  create(request: FeatureCreateRequest): Promise<CatalogFeature>;
  updateDescription(featureId: string, description: string): Promise<CatalogFeature>;
}

export interface FeatureCatalogControllerOptions {
  onImport?: (feature?: CatalogFeature) => void;
  renderDetailAddon?: (
    host: HTMLElement,
    feature: CatalogFeature,
    view: FeatureCatalogView,
  ) => (() => void) | void;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

function isEvidence(value: unknown): value is FeatureEvidence {
  return (
    isRecord(value) &&
    typeof value.source === 'string' &&
    typeof value.version === 'string' &&
    typeof value.status === 'string' &&
    typeof value.uncertainty === 'number' &&
    (value.source_date === null || typeof value.source_date === 'string')
  );
}

function isDistribution(value: unknown): value is FeatureDistribution {
  if (!isRecord(value)) return false;
  return (
    typeof value.feature_id === 'string' &&
    typeof value.level === 'string' &&
    typeof value.place === 'string' &&
    typeof value.population === 'string' &&
    (value.population_count === null || typeof value.population_count === 'number') &&
    typeof value.coverage_percent === 'number' &&
    isRecord(value.values) &&
    (value.mean === null || typeof value.mean === 'number') &&
    (value.standard_deviation === null || typeof value.standard_deviation === 'number') &&
    isEvidence(value.provenance) &&
    typeof value.method === 'string'
  );
}

function isUsage(value: unknown): value is FeatureUsage {
  if (!isRecord(value)) return false;
  return (
    typeof value.name === 'string' &&
    (value.mode === 'predictive' || value.mode === 'label_only') &&
    typeof value.reason === 'string' &&
    (value.population === null || typeof value.population === 'string') &&
    (value.provenance === null || isEvidence(value.provenance))
  );
}

function isRange(value: unknown): value is FeatureRange {
  return (
    isRecord(value) &&
    typeof value.minimum === 'number' &&
    typeof value.maximum === 'number' &&
    typeof value.unit === 'string'
  );
}

function isCatalogFeature(value: unknown): value is CatalogFeature {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    (value.type === 'categorical' || value.type === 'continuous' || value.type === 'binary') &&
    typeof value.description === 'string' &&
    typeof value.provenance_placeholder === 'string' &&
    (value.status === 'pending' || value.status === 'awaiting_data' || value.status === 'ready') &&
    typeof value.predictor_blocked === 'boolean' &&
    Array.isArray(value.canonical_values) &&
    value.canonical_values.every((item) => typeof item === 'string') &&
    (value.value_range === null || isRange(value.value_range)) &&
    Array.isArray(value.distributions) &&
    value.distributions.every(isDistribution) &&
    Array.isArray(value.usages) &&
    value.usages.every(isUsage)
  );
}

function isCatalogView(value: unknown): value is FeatureCatalogView {
  return (
    isRecord(value) &&
    typeof value.version === 'string' &&
    Array.isArray(value.features) &&
    value.features.every(isCatalogFeature)
  );
}

async function catalogRequest<T>(
  path: string,
  validate: (value: unknown) => value is T,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) ? body.detail : null;
    if (typeof detail === 'string') throw new Error(detail);
    if (Array.isArray(detail) && isRecord(detail[0]) && typeof detail[0].msg === 'string') {
      throw new Error(detail[0].msg);
    }
    throw new Error(`Request failed (${response.status})`);
  }
  if (!validate(body)) throw new Error('The server returned an invalid feature catalog contract.');
  return body;
}

const jsonRequest = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const featureCatalogApi: FeatureCatalogApi = {
  list: () => catalogRequest('/atlas/feature-catalog', isCatalogView),
  detail: (featureId) =>
    catalogRequest(`/atlas/feature-catalog/${encodeURIComponent(featureId)}`, isCatalogFeature),
  create: (request) =>
    catalogRequest('/atlas/feature-catalog', isCatalogFeature, jsonRequest(request)),
  updateDescription: (featureId, description) =>
    catalogRequest(
      `/atlas/feature-catalog/${encodeURIComponent(featureId)}/description`,
      isCatalogFeature,
      { ...jsonRequest({ description }), method: 'PATCH' },
    ),
};

const words = (value: string): string => value.replaceAll('_', ' ');
const percent = (value: number): string => `${value.toFixed(1)}%`;
const DISTRIBUTIONS_PER_PAGE = 12;

function schemaSummary(feature: CatalogFeature): string {
  if (feature.value_range) {
    return `${feature.value_range.minimum}–${feature.value_range.maximum} ${feature.value_range.unit}`;
  }
  return feature.canonical_values.join(' · ');
}

function statusText(feature: CatalogFeature): string {
  if (feature.status === 'ready') return 'Distribution attached';
  if (feature.status === 'awaiting_data') return 'Awaiting data';
  return 'Pending';
}

function placeOptions(view: FeatureCatalogView, selected: string): string {
  const places = Array.from(
    new Set(view.features.flatMap((feature) => feature.distributions.map((item) => item.place))),
  ).sort((left, right) => left.localeCompare(right));
  return [
    '<option value="">All places</option>',
    ...places.map(
      (place) =>
        `<option value="${e(place)}"${selected === place ? ' selected' : ''}>${e(place)}</option>`,
    ),
  ].join('');
}

function rowMarkup(feature: CatalogFeature, place: string): string {
  const distributions = place
    ? feature.distributions.filter((distribution) => distribution.place === place)
    : feature.distributions;
  const description = feature.description || 'No description yet';
  const usage = feature.predictor_blocked ? 'Label-only' : 'Predictive evidence attached';
  return `
    <button class="feature-catalog-row" type="button" data-feature-action="open" data-feature-id="${e(feature.id)}" aria-label="Open ${e(feature.name)} feature details">
      <span class="feature-catalog-identity"><strong>${e(feature.name)}</strong><small class="mono">${e(feature.id)} · ${e(feature.type)}</small><span>${e(description)}</span></span>
      <span class="feature-catalog-schema"><small>Values</small><b>${e(schemaSummary(feature))}</b></span>
      <span class="feature-catalog-distribution-count"><b>${distributions.length}</b><small>${place ? `in ${e(place)}` : 'place distributions'}</small></span>
      <span class="feature-catalog-usage"><small>${e(usage)}</small><b>${feature.usages.length} use${feature.usages.length === 1 ? '' : 's'}</b></span>
      <span class="field-status ${feature.status === 'ready' ? 'present' : 'missing'}">${e(statusText(feature))}</span>
      <span class="feature-catalog-open" aria-hidden="true">→</span>
    </button>`;
}

function valueLabel(feature: CatalogFeature, label: string): string {
  if (feature.id === 'age') return `Age ${label}`;
  return words(label);
}

function distributionValues(
  feature: CatalogFeature,
  distribution: FeatureDistribution,
): string {
  const values = Object.entries(distribution.values);
  if (values.length) {
    const ordered = values.sort(([left], [right]) => {
      const leftNumber = Number(left.replace('+', ''));
      const rightNumber = Number(right.replace('+', ''));
      if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) return leftNumber - rightNumber;
      return left.localeCompare(right);
    });
    return `<div class="feature-value-table-scroll"><table class="feature-value-table"><thead><tr><th>Value</th><th>Share</th><th>Estimated agents</th></tr></thead><tbody>${ordered
      .map(([label, probability]) => {
        const count =
          distribution.population_count === null
            ? 'Population unavailable'
            : `${Math.round(probability * distribution.population_count).toLocaleString()} agents`;
        return `<tr><th>${e(valueLabel(feature, label))}</th><td>${percent(probability * 100)}</td><td>${e(count)}</td></tr>`;
      })
      .join('')}</tbody></table></div>`;
  }
  if (distribution.mean !== null) {
    return `<p class="feature-distribution-moments">Mean ${distribution.mean.toLocaleString()} · SD ${distribution.standard_deviation?.toLocaleString() ?? 'unknown'}</p>`;
  }
  return '<p class="feature-distribution-moments">No distribution values</p>';
}

function distributionMarkup(
  feature: CatalogFeature,
  distribution: FeatureDistribution,
): string {
  const sourceDate = distribution.provenance.source_date ?? 'Undated';
  return `
    <article class="feature-catalog-distribution">
      <div class="feature-catalog-distribution-heading">
        <div><strong>${e(distribution.place)}</strong><small>${e(distribution.level)} · ${e(distribution.method)}</small></div>
        <span class="field-status ${distribution.provenance.status === 'present' ? 'present' : 'imputed'}">${e(distribution.provenance.status)}</span>
      </div>
      ${distributionValues(feature, distribution)}
      <dl>
        <div><dt>Population</dt><dd>${e(distribution.population)}</dd></div>
        <div><dt>Coverage</dt><dd>${percent(distribution.coverage_percent)}</dd></div>
        <div><dt>Source</dt><dd>${e(distribution.provenance.source)}</dd></div>
        <div><dt>Date / version</dt><dd>${e(sourceDate)} · ${e(distribution.provenance.version)}</dd></div>
        <div><dt>Uncertainty</dt><dd>${distribution.provenance.uncertainty.toFixed(2)}</dd></div>
      </dl>
    </article>`;
}

function usageMarkup(usage: FeatureUsage): string {
  const provenance = usage.provenance
    ? `${e(usage.provenance.source)} · ${e(usage.provenance.version)} · ${e(usage.provenance.source_date ?? 'undated')}`
    : 'No joint evidence attached';
  return `
    <article class="feature-catalog-use">
      <div><strong>${e(usage.name)}</strong><span class="field-status ${usage.mode === 'predictive' ? 'present' : 'missing'}">${e(words(usage.mode))}</span></div>
      <p>${e(usage.reason)}</p>
      <small>${usage.population ? `${e(usage.population)} · ` : ''}${provenance}</small>
    </article>`;
}

function createFormMarkup(): string {
  return `
    <dialog class="atlas-dialog feature-catalog-dialog" data-feature-create-dialog aria-labelledby="feature-catalog-create-title">
      <div class="dialog-top"><span class="small-label">FEATURE REGISTRY</span><button class="icon-button" type="button" data-feature-action="cancel-create" aria-label="Close feature form">×</button></div>
      <h2 id="feature-catalog-create-title">Add agent feature</h2>
      <p class="dialog-subtitle">Create the schema now and attach measured distributions later. Until then, the feature remains label-only.</p>
      <form data-feature-create-form>
        <div class="feature-catalog-form-grid">
          <label>Name<input name="name" required maxlength="120" placeholder="Endurance" /></label>
          <label>Feature ID<input name="id" required pattern="[a-z][a-z0-9_-]*" maxlength="80" placeholder="endurance" /></label>
          <label>Type<select name="type"><option value="continuous">Continuous</option><option value="categorical">Categorical</option><option value="binary">Binary</option></select></label>
        </div>
        <label class="feature-catalog-wide">Description<textarea name="description" rows="3" maxlength="2000" placeholder="What this feature measures and how to interpret it"></textarea></label>
        <label class="feature-catalog-wide">Provenance placeholder<input name="provenance_placeholder" required maxlength="500" value="Representative source required" /></label>
        <label class="feature-catalog-wide" data-feature-values hidden>Canonical values<textarea name="canonical_values" rows="2" placeholder="low, medium, high"></textarea><small>Enter two or more comma-separated values. Binary features require exactly two.</small></label>
        <div class="feature-catalog-form-grid" data-feature-range>
          <label>Minimum<input name="minimum" type="number" step="any" required value="0" /></label>
          <label>Maximum<input name="maximum" type="number" step="any" required value="1" /></label>
          <label>Unit<input name="unit" required value="score" maxlength="80" /></label>
        </div>
        <p class="form-error" data-feature-create-error role="alert" hidden></p>
        <div class="dialog-footer"><button class="button secondary" type="button" data-feature-action="cancel-create">Cancel</button><button class="button primary" type="submit">Create feature</button></div>
      </form>
    </dialog>`;
}

export function featureCatalogShell(): string {
  return `
    <section class="feature-catalog" aria-labelledby="feature-catalog-title">
      <div class="atlas-evidence-heading feature-catalog-heading">
        <div><p class="eyebrow">UNIVERSAL FEATURE REGISTRY</p><h2 id="feature-catalog-title">Features and evidence</h2><p>Open any feature to inspect its schema, data by place, provenance, and predictor eligibility.</p></div>
        <div class="feature-catalog-heading-actions"><button class="button secondary" type="button" data-feature-action="import">Import feature data</button><button class="button primary" type="button" data-feature-action="create">Add feature</button></div>
      </div>
      <div data-feature-catalog-content><p class="muted">Loading feature registry…</p></div>
      ${createFormMarkup()}
    </section>`;
}

export class FeatureCatalogController {
  private view?: FeatureCatalogView;
  private detail?: CatalogFeature;
  private editingDescription = false;
  private distributionSearch = '';
  private distributionPage = 1;
  private state: FeatureCatalogState;
  private disposeDetailAddon?: () => void;
  private createIdManuallyEdited = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly api: FeatureCatalogApi = featureCatalogApi,
    initialState: Partial<FeatureCatalogState> = {},
    private readonly options: FeatureCatalogControllerOptions = {},
  ) {
    this.state = { place: '', search: '', status: '', ...initialState };
    this.host.innerHTML = featureCatalogShell();
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('submit', this.onSubmit);
  }

  async load(): Promise<void> {
    this.view = await this.api.list();
    this.render();
  }

  destroy(): void {
    this.disposeDetailAddon?.();
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('submit', this.onSubmit);
  }

  setPlace(place: string): void {
    this.state.place = place;
    if (!this.detail) this.render();
  }

  getState(): FeatureCatalogState {
    return { ...this.state };
  }

  private content(): HTMLElement {
    return this.host.querySelector<HTMLElement>('[data-feature-catalog-content]')!;
  }

  private render(): void {
    if (!this.view) return;
    this.disposeDetailAddon?.();
    this.disposeDetailAddon = undefined;
    this.content().innerHTML = this.detail ? this.detailMarkup(this.detail) : this.listMarkup();
    if (this.detail && this.options.renderDetailAddon) {
      const target = this.content().querySelector<HTMLElement>('[data-feature-detail-addon]')!;
      this.disposeDetailAddon =
        this.options.renderDetailAddon(target, this.detail, this.view) ?? undefined;
    }
  }

  private listMarkup(): string {
    const view = this.view!;
    const query = this.state.search.toLowerCase();
    const features = view.features.filter((feature) => {
      const matchesSearch =
        !query ||
        feature.id.toLowerCase().includes(query) ||
        feature.name.toLowerCase().includes(query) ||
        feature.description.toLowerCase().includes(query);
      const matchesStatus = !this.state.status || feature.status === this.state.status;
      const matchesPlace =
        !this.state.place ||
        feature.distributions.some((distribution) => distribution.place === this.state.place);
      return matchesSearch && matchesStatus && matchesPlace;
    });
    return `
      <div class="feature-catalog-toolbar">
        <label>Search features<input type="search" data-feature-filter="search" value="${e(this.state.search)}" placeholder="Name, ID, or description" /></label>
        <label>Place<select data-feature-filter="place">${placeOptions(view, this.state.place)}</select></label>
        <label>Status<select data-feature-filter="status"><option value="">All statuses</option><option value="pending"${this.state.status === 'pending' ? ' selected' : ''}>Pending</option><option value="awaiting_data"${this.state.status === 'awaiting_data' ? ' selected' : ''}>Awaiting data</option><option value="ready"${this.state.status === 'ready' ? ' selected' : ''}>Ready</option></select></label>
        <span>${features.length.toLocaleString()} of ${view.features.length.toLocaleString()} features</span>
      </div>
      <div class="feature-catalog-rows">${features.map((feature) => rowMarkup(feature, this.state.place)).join('') || '<p class="atlas-empty">No features match these filters.</p>'}</div>`;
  }

  private detailMarkup(feature: CatalogFeature): string {
    const description = feature.description || 'No description yet';
    return `
      <section class="feature-catalog-detail" aria-labelledby="feature-detail-title">
        <button class="text-button feature-catalog-back" type="button" data-feature-action="back">← Back to features</button>
        <div class="feature-catalog-detail-heading">
          <div><p class="eyebrow">${feature.custom ? 'CUSTOM FEATURE' : 'CANONICAL FEATURE'} / ${e(feature.id)}</p><h3 id="feature-detail-title">${e(feature.name)}</h3></div>
          <div><button class="button secondary" type="button" data-feature-action="import" aria-label="Import data for ${e(feature.name)}">Import data</button><span class="field-status ${feature.status === 'ready' ? 'present' : 'missing'}">${e(statusText(feature))}</span><span class="field-status ${feature.predictor_blocked ? 'missing' : 'present'}">${feature.predictor_blocked ? 'Label-only' : 'Predictive'}</span></div>
        </div>
        <section class="feature-catalog-description">
          <div><h4>Description</h4><button class="text-button" type="button" data-feature-action="edit-description">Edit</button></div>
          ${this.editingDescription ? `<form data-feature-description-form><textarea name="description" rows="4" maxlength="2000">${e(feature.description)}</textarea><p class="form-error" data-feature-description-error role="alert" hidden></p><div><button class="button secondary" type="button" data-feature-action="cancel-description">Cancel</button><button class="button primary" type="submit">Save description</button></div></form>` : `<p class="${feature.description ? '' : 'muted'}">${e(description)}</p>`}
        </section>
        <dl class="feature-catalog-facts">
          <div><dt>Type</dt><dd>${e(feature.type)}</dd></div>
          <div><dt>Canonical values / range</dt><dd>${e(schemaSummary(feature))}</dd></div>
          <div><dt>Provenance needed</dt><dd>${e(feature.provenance_placeholder)}</dd></div>
          <div><dt>Status</dt><dd>${e(statusText(feature))}${feature.predictor_blocked ? ' · predictor blocked' : ''}</dd></div>
        </dl>
        <section class="feature-catalog-detail-section"><div><h4>Distributions by place</h4><span>${feature.distributions.length.toLocaleString()} attached</span></div><div data-feature-distribution-browser>${this.distributionBrowserMarkup(feature)}</div></section>
        <section class="feature-catalog-detail-section"><div><h4>What uses it</h4><span>Predictive use requires joint trait and outcome evidence.</span></div><div class="feature-catalog-uses">${feature.usages.map(usageMarkup).join('')}</div></section>
        <div data-feature-detail-addon></div>
      </section>`;
  }

  private async openFeature(featureId: string): Promise<void> {
    this.detail = await this.api.detail(featureId);
    this.editingDescription = false;
    this.distributionSearch = this.state.place;
    this.distributionPage = 1;
    this.render();
    this.host.querySelector<HTMLElement>('#feature-detail-title')?.focus();
  }

  private matchingDistributions(feature: CatalogFeature): FeatureDistribution[] {
    const query = this.distributionSearch.trim().toLowerCase();
    return feature.distributions
      .filter((distribution) => {
        if (!query) return true;
        return [
          distribution.place,
          distribution.level,
          distribution.method,
          distribution.provenance.source,
          distribution.provenance.version,
        ].some((value) => value.toLowerCase().includes(query));
      })
      .sort(
        (left, right) =>
          left.level.localeCompare(right.level) || left.place.localeCompare(right.place),
      );
  }

  private distributionBrowserMarkup(feature: CatalogFeature): string {
    if (!feature.distributions.length) {
      return '<p class="atlas-empty">No distribution attached. This feature remains label-only.</p>';
    }
    const distributions = this.matchingDistributions(feature);
    const pageCount = Math.max(1, Math.ceil(distributions.length / DISTRIBUTIONS_PER_PAGE));
    this.distributionPage = Math.min(this.distributionPage, pageCount);
    const start = (this.distributionPage - 1) * DISTRIBUTIONS_PER_PAGE;
    const visible = distributions.slice(start, start + DISTRIBUTIONS_PER_PAGE);
    const range = distributions.length
      ? `${(start + 1).toLocaleString()}–${Math.min(start + DISTRIBUTIONS_PER_PAGE, distributions.length).toLocaleString()} of ${distributions.length.toLocaleString()}`
      : '0 matching distributions';
    return `
      <div class="feature-catalog-distribution-toolbar">
        <label>Find a place or source<input type="search" data-feature-distribution-search value="${e(this.distributionSearch)}" placeholder="Country, region, city, or source" /></label>
        <span>${range}</span>
      </div>
      <div class="feature-catalog-distributions" data-feature-distribution-list>${visible.map((item) => distributionMarkup(feature, item)).join('') || '<p class="atlas-empty">No distributions match this search.</p>'}</div>
      <div class="feature-catalog-distribution-pagination">
        <span>Page ${this.distributionPage.toLocaleString()} of ${pageCount.toLocaleString()}</span>
        <div><button class="button secondary" type="button" data-feature-action="distribution-previous"${this.distributionPage === 1 ? ' disabled' : ''}>← Previous</button><button class="button secondary" type="button" data-feature-action="distribution-next"${this.distributionPage === pageCount ? ' disabled' : ''}>Next →</button></div>
      </div>`;
  }

  private renderDistributionBrowser(): void {
    if (!this.detail) return;
    const browser = this.content().querySelector<HTMLElement>('[data-feature-distribution-browser]');
    if (!browser) return;
    browser.innerHTML = this.distributionBrowserMarkup(this.detail);
  }

  private openCreate(): void {
    const dialog = this.host.querySelector<HTMLDialogElement>('[data-feature-create-dialog]')!;
    const form = dialog.querySelector<HTMLFormElement>('[data-feature-create-form]')!;
    form.reset();
    this.createIdManuallyEdited = false;
    this.updateCreateType(form, 'continuous');
    dialog.showModal();
  }

  private updateCreateType(form: HTMLFormElement, type: FeatureKind): void {
    const values = form.querySelector<HTMLElement>('[data-feature-values]')!;
    const range = form.querySelector<HTMLElement>('[data-feature-range]')!;
    values.hidden = type === 'continuous';
    range.hidden = type !== 'continuous';
    values.querySelector<HTMLTextAreaElement>('textarea')!.required = type !== 'continuous';
    range.querySelectorAll<HTMLInputElement>('input').forEach((input) => {
      input.required = type === 'continuous';
    });
  }

  private createRequest(form: HTMLFormElement): FeatureCreateRequest {
    const data = new FormData(form);
    const read = (name: string): string => String(data.get(name) ?? '').trim();
    const type = read('type') as FeatureKind;
    const canonicalValues = Array.from(
      new Set(
        read('canonical_values')
          .split(/[\n,]/)
          .map((value) => value.trim())
          .filter(Boolean),
      ),
    );
    const minimum = Number(read('minimum'));
    const maximum = Number(read('maximum'));
    if (type === 'continuous' && (!Number.isFinite(minimum) || !Number.isFinite(maximum))) {
      throw new Error('Continuous features need numeric minimum and maximum values.');
    }
    if (type === 'continuous' && minimum >= maximum) {
      throw new Error('The maximum must be greater than the minimum.');
    }
    if (type === 'categorical' && canonicalValues.length < 2) {
      throw new Error('Categorical features need at least two canonical values.');
    }
    if (type === 'binary' && canonicalValues.length !== 2) {
      throw new Error('Binary features need exactly two canonical values.');
    }
    return {
      id: read('id'),
      name: read('name'),
      type,
      canonical_values: type === 'continuous' ? [] : canonicalValues,
      value_range: type === 'continuous' ? { minimum, maximum, unit: read('unit') } : null,
      description: read('description'),
      provenance_placeholder: read('provenance_placeholder'),
      status: 'awaiting_data',
    };
  }

  private replaceFeature(feature: CatalogFeature): void {
    if (!this.view) return;
    const index = this.view.features.findIndex((item) => item.id === feature.id);
    if (index === -1) this.view.features.push(feature);
    else this.view.features[index] = feature;
    this.view.features.sort((left, right) => left.id.localeCompare(right.id));
  }

  private onClick = (event: MouseEvent): void => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-feature-action]');
    if (!target) return;
    const action = target.dataset.featureAction;
    if (action === 'open' && target.dataset.featureId)
      void this.openFeature(target.dataset.featureId);
    else if (action === 'back') {
      this.detail = undefined;
      this.editingDescription = false;
      this.render();
    } else if (action === 'distribution-previous') {
      this.distributionPage = Math.max(1, this.distributionPage - 1);
      this.renderDistributionBrowser();
    } else if (action === 'distribution-next') {
      this.distributionPage++;
      this.renderDistributionBrowser();
    } else if (action === 'create') this.openCreate();
    else if (action === 'import') this.options.onImport?.(this.detail);
    else if (action === 'cancel-create')
      this.host.querySelector<HTMLDialogElement>('[data-feature-create-dialog]')!.close();
    else if (action === 'edit-description') {
      this.editingDescription = true;
      this.render();
      this.host
        .querySelector<HTMLTextAreaElement>('[data-feature-description-form] textarea')
        ?.focus();
    } else if (action === 'cancel-description') {
      this.editingDescription = false;
      this.render();
    }
  };

  private onInput = (event: Event): void => {
    const target = event.target as HTMLInputElement;
    if (target.form?.matches('[data-feature-create-form]')) {
      if (target.name === 'id') this.createIdManuallyEdited = target.value.length > 0;
      if (target.name === 'name' && !this.createIdManuallyEdited) {
        const id = target.form.elements.namedItem('id') as HTMLInputElement;
        id.value = target.value
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '_')
          .replace(/^_+|_+$/g, '');
      }
    }
    if (target.hasAttribute('data-feature-distribution-search')) {
      this.distributionSearch = target.value;
      this.distributionPage = 1;
      this.renderDistributionBrowser();
      const input = this.host.querySelector<HTMLInputElement>('[data-feature-distribution-search]');
      input?.focus();
      input?.setSelectionRange(input.value.length, input.value.length);
      return;
    }
    if (target.dataset.featureFilter !== 'search') return;
    this.state.search = target.value;
    this.render();
    this.host.querySelector<HTMLInputElement>('[data-feature-filter="search"]')?.focus();
  };

  private onChange = (event: Event): void => {
    const target = event.target as HTMLSelectElement;
    if (target.name === 'type') {
      this.updateCreateType(target.form!, target.value as FeatureKind);
      return;
    }
    if (target.dataset.featureFilter === 'place') this.state.place = target.value;
    else if (target.dataset.featureFilter === 'status')
      this.state.status = target.value as FeatureCatalogState['status'];
    else return;
    this.render();
  };

  private onSubmit = async (event: SubmitEvent): Promise<void> => {
    const form = event.target as HTMLFormElement;
    if (form.matches('[data-feature-create-form]')) {
      event.preventDefault();
      const error = form.querySelector<HTMLElement>('[data-feature-create-error]')!;
      try {
        const feature = await this.api.create(this.createRequest(form));
        this.replaceFeature(feature);
        this.detail = feature;
        this.host.querySelector<HTMLDialogElement>('[data-feature-create-dialog]')!.close();
        this.render();
      } catch (reason) {
        error.hidden = false;
        error.textContent = reason instanceof Error ? reason.message : String(reason);
      }
      return;
    }
    if (!form.matches('[data-feature-description-form]') || !this.detail) return;
    event.preventDefault();
    const description = new FormData(form).get('description');
    const error = form.querySelector<HTMLElement>('[data-feature-description-error]')!;
    try {
      const feature = await this.api.updateDescription(this.detail.id, String(description ?? ''));
      this.replaceFeature(feature);
      this.detail = feature;
      this.editingDescription = false;
      this.render();
    } catch (reason) {
      error.hidden = false;
      error.textContent = reason instanceof Error ? reason.message : String(reason);
    }
  };
}
