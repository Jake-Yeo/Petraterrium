import './joined-filter.css';

export type PlaceLevel = 'global' | 'region' | 'subregion' | 'country' | 'city';
export type FilterOperator = 'eq' | 'in' | 'gt' | 'gte' | 'lt' | 'lte' | 'between';

export interface PlaceSelector {
  level: PlaceLevel;
  place: string;
  label: string;
}

export interface JoinedFeatureOption {
  id: string;
  label: string;
  kind: 'categorical' | 'binary' | 'continuous';
  values: string[];
  minimum?: number;
  maximum?: number;
  unit?: string;
}

export interface FeatureFilter {
  feature_id: string;
  operator: FilterOperator;
  values: Array<string | number>;
}

export interface DistributionSource {
  place: string;
  level: PlaceLevel;
  status: string;
  source: string;
  version: string;
  source_date: string | null;
  population: string;
  coverage_percent: number;
  uncertainty: number;
  applied_population: number;
  estimated_count: number;
  agent_percent: number;
}

export interface InheritedValue {
  value: string;
  agent_percent: number;
  estimated_count: number;
  sources: DistributionSource[];
}

export interface FeatureInheritanceView {
  feature_id: string;
  selector: PlaceSelector;
  selected_population: number;
  represented_population: number;
  unresolved_population: number;
  values: InheritedValue[];
  sources: DistributionSource[];
  continuous_mean: number | null;
  continuous_standard_deviation: number | null;
}

export interface JointSourceApplication {
  place: string;
  level: PlaceLevel;
  source: string;
  version: string;
  source_date: string;
  sample_size: number;
  population: string;
  ci_low: number;
  ci_high: number;
  coverage_percent: number;
  uncertainty: number;
  applied_population: number;
}

export interface JoinedFilterEstimate {
  selector: PlaceSelector;
  filters: FeatureFilter[];
  method: 'measured_joint' | 'independence_estimate' | 'mixed';
  method_label: string;
  probability: number;
  agent_percent: number;
  estimated_count: number;
  selected_population: number;
  represented_population: number;
  unresolved_population: number;
  measured_population_percent: number;
  ci_low: number;
  ci_high: number;
  sources: JointSourceApplication[];
  coefficient_fit_eligible: boolean;
  missing_requirement: string | null;
  missing_md_entry: string | null;
}

export interface JoinedFilterClient {
  featureInheritance(selector: PlaceSelector, featureId: string): Promise<FeatureInheritanceView>;
  estimateJoinedFilters(
    selector: PlaceSelector,
    filters: FeatureFilter[],
  ): Promise<JoinedFilterEstimate>;
  searchPlaces?(query: string): Promise<PlaceSelector[]>;
}

export interface JoinedFilterOptions {
  places: PlaceSelector[];
  features: JoinedFeatureOption[];
  initialPlace?: PlaceSelector;
  initialFeatureId?: string;
}

const html = (value: unknown): string =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const count = (value: number): string => Math.round(value).toLocaleString('en');
const percent = (value: number): string => `${value.toFixed(2)}%`;
const probabilityPercent = (value: number): string => percent(value * 100);

function selectorIdentity(selector: PlaceSelector): string {
  return `${selector.level}:${selector.place}`;
}

function featureOperators(feature: JoinedFeatureOption): FilterOperator[] {
  return feature.kind === 'continuous' ? ['gte', 'lte', 'gt', 'lt', 'between'] : ['eq', 'in'];
}

function operatorLabel(operator: FilterOperator): string {
  return {
    eq: 'is',
    in: 'is one of',
    gt: 'is greater than',
    gte: 'is at least',
    lt: 'is less than',
    lte: 'is at most',
    between: 'is between',
  }[operator];
}

function sourceLabel(source: DistributionSource): string {
  const inherited = source.status === 'present' ? 'direct' : source.status;
  return `${source.place} · ${inherited} · ${source.source} · ${source.version} · ${source.coverage_percent.toFixed(1)}% source coverage`;
}

function emptyState(message: string): string {
  return `<p class="joined-empty">${html(message)}</p>`;
}

export class JoinedFilterPanel {
  private readonly selectors: PlaceSelector[];
  private readonly features: JoinedFeatureOption[];
  private generation = 0;
  private filterCount = 2;
  private placeSearchTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private readonly host: HTMLElement,
    options: JoinedFilterOptions,
    private readonly client: JoinedFilterClient,
  ) {
    if (!options.places.length) throw new Error('Joined filters need at least one place');
    if (options.features.length < 2) throw new Error('Joined filters need at least two features');
    this.selectors = options.places;
    this.features = options.features;
    this.host.innerHTML = this.shell(options.initialPlace, options.initialFeatureId);
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('click', this.onClick);
    this.renderFilterRows();
    void this.refresh();
  }

  dispose(): void {
    this.generation++;
    clearTimeout(this.placeSearchTimer);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private shell(initialPlace?: PlaceSelector, initialFeatureId?: string): string {
    const selectedPlace = initialPlace
      ? selectorIdentity(initialPlace)
      : selectorIdentity(this.selectors[0]);
    const selectedFeature = initialFeatureId ?? this.features[0].id;
    return `
      <section class="joined-filter-panel" aria-labelledby="joined-filter-title">
        <div class="joined-filter-heading">
          <div><p class="eyebrow">AGENT INHERITANCE</p><h3 id="joined-filter-title">Place distribution and joined filters</h3></div>
          <label>Place<select data-joined-place>${this.selectors
            .map(
              (selector) =>
                `<option value="${html(selectorIdentity(selector))}"${selectorIdentity(selector) === selectedPlace ? ' selected' : ''}>${html(selector.label)} · ${html(selector.level)}</option>`,
            )
            .join('')}</select></label>
        </div>
        <div class="joined-city-search">
          <label>Find a city<input type="search" data-joined-city-search placeholder="Type at least 2 characters" autocomplete="off" /></label>
          <div data-joined-city-results></div>
        </div>
        <div class="joined-inheritance-heading">
          <label>Feature distribution<select data-inheritance-feature>${this.features
            .map(
              (feature) =>
                `<option value="${html(feature.id)}"${feature.id === selectedFeature ? ' selected' : ''}>${html(feature.label)}</option>`,
            )
            .join('')}</select></label>
          <span data-inheritance-population></span>
        </div>
        <div class="joined-inheritance" data-inheritance-result aria-live="polite">${emptyState('Loading distribution…')}</div>
        <div class="joined-query-heading">
          <div><p class="eyebrow">AND QUERY</p><h4>Estimate a joined group</h4></div>
          <button type="button" class="button secondary" data-joined-action="add">Add filter</button>
        </div>
        <div class="joined-filter-rows" data-joined-rows></div>
        <div class="joined-result" data-joined-result aria-live="polite">${emptyState('Choose two filters to estimate their overlap.')}</div>
      </section>`;
  }

  private selectedPlace(): PlaceSelector {
    const value = this.host.querySelector<HTMLSelectElement>('[data-joined-place]')?.value;
    const selected = this.selectors.find((selector) => selectorIdentity(selector) === value);
    if (!selected) throw new Error('Selected place is unavailable');
    return selected;
  }

  private addPlace(selector: PlaceSelector): void {
    const identity = selectorIdentity(selector);
    if (!this.selectors.some((item) => selectorIdentity(item) === identity)) {
      this.selectors.push(selector);
    }
    const select = this.host.querySelector<HTMLSelectElement>('[data-joined-place]')!;
    if (!Array.from(select.options).some((option) => option.value === identity)) {
      const option = document.createElement('option');
      option.value = identity;
      option.textContent = `${selector.label} · ${selector.level}`;
      select.append(option);
    }
    select.value = identity;
  }

  private async searchPlaces(query: string): Promise<void> {
    const target = this.host.querySelector<HTMLElement>('[data-joined-city-results]')!;
    if (!this.client.searchPlaces || query.trim().length < 2) {
      target.replaceChildren();
      return;
    }
    target.textContent = 'Searching…';
    try {
      const places = (await this.client.searchPlaces(query)).filter(
        (selector) => selector.level === 'city',
      );
      target.innerHTML = places.length
        ? places
            .map(
              (selector) =>
                `<button type="button" data-joined-action="choose-place" data-place-level="${html(selector.level)}" data-place-id="${html(selector.place)}" data-place-label="${html(selector.label)}">${html(selector.label)}</button>`,
            )
            .join('')
        : '<span>No cities found</span>';
    } catch (reason) {
      target.textContent = reason instanceof Error ? reason.message : String(reason);
    }
  }

  private selectedInheritanceFeature(): string {
    return (
      this.host.querySelector<HTMLSelectElement>('[data-inheritance-feature]')?.value ??
      this.features[0].id
    );
  }

  private renderFilterRows(preserved?: FeatureFilter[]): void {
    const rows = this.host.querySelector<HTMLElement>('[data-joined-rows]');
    if (!rows) return;
    rows.innerHTML = Array.from({ length: this.filterCount }, (_, index) => {
      const prior = preserved?.[index];
      const feature =
        this.features.find((candidate) => candidate.id === prior?.feature_id) ??
        this.features[index % this.features.length];
      const operators = featureOperators(feature);
      const operator = prior && operators.includes(prior.operator) ? prior.operator : operators[0];
      return this.filterRow(index, feature, operator, prior?.values);
    }).join('');
  }

  private filterRow(
    index: number,
    feature: JoinedFeatureOption,
    operator: FilterOperator,
    values?: Array<string | number>,
  ): string {
    return `
      <div class="joined-filter-row" data-joined-row="${index}">
        <span class="joined-and">${index ? 'AND' : 'WHERE'}</span>
        <label><span>Feature</span><select data-filter-feature>${this.features
          .map(
            (candidate) =>
              `<option value="${html(candidate.id)}"${candidate.id === feature.id ? ' selected' : ''}>${html(candidate.label)}</option>`,
          )
          .join('')}</select></label>
        <label><span>Condition</span><select data-filter-operator>${featureOperators(feature)
          .map(
            (candidate) =>
              `<option value="${candidate}"${candidate === operator ? ' selected' : ''}>${html(operatorLabel(candidate))}</option>`,
          )
          .join('')}</select></label>
        ${this.valueControl(feature, operator, values)}
        <button type="button" class="icon-button" data-joined-action="remove" data-index="${index}" aria-label="Remove ${html(feature.label)} filter"${this.filterCount <= 2 ? ' disabled' : ''}>×</button>
      </div>`;
  }

  private valueControl(
    feature: JoinedFeatureOption,
    operator: FilterOperator,
    values?: Array<string | number>,
  ): string {
    if (feature.kind !== 'continuous') {
      if (operator === 'in') {
        return `<label class="joined-value"><span>Values</span><select data-filter-values multiple size="${Math.min(4, Math.max(2, feature.values.length))}">${feature.values
          .map(
            (value) =>
              `<option value="${html(value)}"${values?.map(String).includes(value) ? ' selected' : ''}>${html(value)}</option>`,
          )
          .join('')}</select></label>`;
      }
      return `<label class="joined-value"><span>Value</span><select data-filter-value>${feature.values
        .map(
          (value) =>
            `<option value="${html(value)}"${String(values?.[0] ?? '') === value ? ' selected' : ''}>${html(value)}</option>`,
        )
        .join('')}</select></label>`;
    }
    const limits = `${feature.minimum == null ? '' : ` min="${feature.minimum}"`}${feature.maximum == null ? '' : ` max="${feature.maximum}"`}`;
    const unit = feature.unit ? ` ${html(feature.unit)}` : '';
    if (operator === 'between') {
      return `<div class="joined-value joined-range"><label><span>Minimum${unit}</span><input type="number" step="any" data-filter-value value="${html(values?.[0] ?? feature.minimum ?? '')}"${limits}></label><label><span>Maximum${unit}</span><input type="number" step="any" data-filter-value-two value="${html(values?.[1] ?? feature.maximum ?? '')}"${limits}></label></div>`;
    }
    return `<label class="joined-value"><span>Value${unit}</span><input type="number" step="any" data-filter-value value="${html(values?.[0] ?? feature.minimum ?? '')}"${limits}></label>`;
  }

  private readFilters(): FeatureFilter[] | null {
    const filters: FeatureFilter[] = [];
    for (const row of this.host.querySelectorAll<HTMLElement>('[data-joined-row]')) {
      const featureId = row.querySelector<HTMLSelectElement>('[data-filter-feature]')?.value;
      const operator = row.querySelector<HTMLSelectElement>('[data-filter-operator]')
        ?.value as FilterOperator;
      const feature = this.features.find((candidate) => candidate.id === featureId);
      if (!feature || !operator) return null;
      let values: Array<string | number>;
      if (operator === 'in') {
        values = Array.from(
          row.querySelector<HTMLSelectElement>('[data-filter-values]')?.selectedOptions ?? [],
        ).map((option) => option.value);
      } else {
        const first = row.querySelector<HTMLInputElement | HTMLSelectElement>(
          '[data-filter-value]',
        )?.value;
        const second = row.querySelector<HTMLInputElement>('[data-filter-value-two]')?.value;
        if (first == null || first === '') return null;
        values = feature.kind === 'continuous' ? [Number(first)] : [first];
        if (operator === 'between') {
          if (second == null || second === '') return null;
          values.push(Number(second));
        }
      }
      if (
        !values.length ||
        values.some((value) => typeof value === 'number' && !Number.isFinite(value))
      )
        return null;
      filters.push({ feature_id: feature.id, operator, values });
    }
    return new Set(filters.map((filter) => filter.feature_id)).size >= 2 ? filters : null;
  }

  private async refresh(): Promise<void> {
    const generation = ++this.generation;
    const selector = this.selectedPlace();
    const inheritanceFeature = this.selectedInheritanceFeature();
    const filters = this.readFilters();
    const inheritanceTarget = this.host.querySelector<HTMLElement>('[data-inheritance-result]');
    const resultTarget = this.host.querySelector<HTMLElement>('[data-joined-result]');
    if (!inheritanceTarget || !resultTarget) return;
    inheritanceTarget.innerHTML = emptyState('Loading distribution…');
    resultTarget.innerHTML = filters
      ? emptyState('Calculating overlap…')
      : emptyState('Use at least two different features with complete values.');
    const inheritancePromise = this.client.featureInheritance(selector, inheritanceFeature);
    const estimatePromise = filters
      ? this.client.estimateJoinedFilters(selector, filters)
      : Promise.resolve(null);
    const [inheritanceResult, estimateResult] = await Promise.allSettled([
      inheritancePromise,
      estimatePromise,
    ]);
    if (generation !== this.generation) return;
    if (inheritanceResult.status === 'fulfilled') {
      inheritanceTarget.innerHTML = this.inheritanceResult(inheritanceResult.value);
      const population = this.host.querySelector<HTMLElement>('[data-inheritance-population]');
      if (population)
        population.textContent = `${count(inheritanceResult.value.selected_population)} agents`;
    } else {
      inheritanceTarget.innerHTML = emptyState(
        inheritanceResult.reason instanceof Error
          ? inheritanceResult.reason.message
          : String(inheritanceResult.reason),
      );
    }
    if (estimateResult.status === 'fulfilled' && estimateResult.value) {
      resultTarget.innerHTML = this.estimateResult(estimateResult.value);
    } else if (estimateResult.status === 'rejected') {
      resultTarget.innerHTML = emptyState(
        estimateResult.reason instanceof Error
          ? estimateResult.reason.message
          : String(estimateResult.reason),
      );
    }
  }

  private inheritanceResult(view: FeatureInheritanceView): string {
    const unresolved = view.unresolved_population
      ? `<p class="joined-warning">${count(view.unresolved_population)} agents have no resolved distribution.</p>`
      : '';
    if (view.values.length) {
      return `${unresolved}<div class="joined-value-list">${view.values
        .map(
          (value) => `
            <article>
              <div><strong>${html(value.value)}</strong><span>${percent(value.agent_percent)} · ${count(value.estimated_count)} agents</span></div>
              <small>${value.sources.map((source) => html(sourceLabel(source))).join('<br>')}</small>
            </article>`,
        )
        .join('')}</div>`;
    }
    if (view.continuous_mean != null && view.continuous_standard_deviation != null) {
      return `${unresolved}<article class="joined-continuous"><div><strong>Mean ${view.continuous_mean.toLocaleString('en', { maximumFractionDigits: 3 })}</strong><span>SD ${view.continuous_standard_deviation.toLocaleString('en', { maximumFractionDigits: 3 })}</span></div><small>${view.sources.map((source) => html(sourceLabel(source))).join('<br>')}</small></article>`;
    }
    return unresolved || emptyState('No resolved distribution for this place.');
  }

  private estimateResult(estimate: JoinedFilterEstimate): string {
    const sourceRows = estimate.sources.length
      ? `<dl class="joined-sources">${estimate.sources
          .map(
            (source) =>
              `<div><dt>${html(source.place)} · measured joint</dt><dd>${html(source.source)} · ${html(source.version)} · ${html(source.source_date)} · ${html(source.population)} · n=${count(source.sample_size)} · CI ${probabilityPercent(source.ci_low)}–${probabilityPercent(source.ci_high)} · ${source.coverage_percent.toFixed(1)}% coverage</dd></div>`,
          )
          .join('')}</dl>`
      : '';
    const missing = estimate.missing_requirement
      ? `<div class="joined-missing"><strong>Joint data needed</strong><p>${html(estimate.missing_requirement)}</p></div>`
      : '';
    const unresolved = estimate.unresolved_population
      ? `<p class="joined-warning">${count(estimate.unresolved_population)} agents are excluded because a marginal is unresolved.</p>`
      : '';
    return `
      <div class="joined-answer">
        <div><span class="joined-method ${estimate.method}">${html(estimate.method_label)}</span><strong>${percent(estimate.agent_percent)}</strong><span>${count(estimate.estimated_count)} estimated agents</span></div>
        <div class="joined-ci"><span>Uncertainty ${probabilityPercent(estimate.ci_low)}–${probabilityPercent(estimate.ci_high)}</span><span>${percent(estimate.measured_population_percent)} of population uses measured joint data</span></div>
      </div>
      ${unresolved}${sourceRows}${missing}`;
  }

  private onChange = (event: Event): void => {
    const target = event.target as HTMLElement;
    if (target.matches('[data-filter-feature], [data-filter-operator]')) {
      const preserved = this.readFilters() ?? undefined;
      const row = target.closest<HTMLElement>('[data-joined-row]');
      const index = Number(row?.dataset.joinedRow ?? -1);
      if (index >= 0) {
        const featureId = row?.querySelector<HTMLSelectElement>('[data-filter-feature]')?.value;
        const operator = row?.querySelector<HTMLSelectElement>('[data-filter-operator]')
          ?.value as FilterOperator;
        const feature = this.features.find((candidate) => candidate.id === featureId);
        if (feature) {
          const replacement = document.createElement('div');
          replacement.innerHTML = this.filterRow(
            index,
            feature,
            featureOperators(feature).includes(operator) ? operator : featureOperators(feature)[0],
            preserved?.[index]?.values,
          );
          row?.replaceWith(replacement.firstElementChild!);
        }
      }
    }
    void this.refresh();
  };

  private onInput = (event: Event): void => {
    const target = event.target as HTMLElement;
    if (target.matches('[data-joined-city-search]')) {
      clearTimeout(this.placeSearchTimer);
      this.placeSearchTimer = setTimeout(
        () => void this.searchPlaces((target as HTMLInputElement).value),
        220,
      );
      return;
    }
    if (target.matches('[data-filter-value], [data-filter-value-two]')) void this.refresh();
  };

  private onClick = (event: MouseEvent): void => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-joined-action]');
    if (!target) return;
    if (target.dataset.joinedAction === 'choose-place') {
      this.addPlace({
        level: target.dataset.placeLevel as PlaceLevel,
        place: target.dataset.placeId!,
        label: target.dataset.placeLabel!,
      });
      this.host.querySelector<HTMLElement>('[data-joined-city-results]')!.replaceChildren();
      const search = this.host.querySelector<HTMLInputElement>('[data-joined-city-search]');
      if (search) search.value = '';
      void this.refresh();
      return;
    }
    const filters = this.readFilters() ?? undefined;
    if (target.dataset.joinedAction === 'add') {
      this.filterCount++;
      this.renderFilterRows(filters);
      void this.refresh();
      return;
    }
    if (target.dataset.joinedAction === 'remove' && this.filterCount > 2) {
      const removeIndex = Number(target.dataset.index);
      const remaining = filters?.filter((_, index) => index !== removeIndex);
      this.filterCount--;
      this.renderFilterRows(remaining);
      void this.refresh();
    }
  };
}
