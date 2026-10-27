import './styles.css';
import { api } from '../api';
import type {
  ImportMetadata,
  ImportPreview,
  MappingConfirmation,
  RunSummary,
  SourceCatalog,
  ValidationReport,
} from '../contracts.generated';
import { escapeHtml as e } from '../views';
import { atlasApi } from './api';
import { importForm, mappingView, validationView } from './import_views';
import { choiceEvidenceView, hierarchyView, universalFeatureView } from './evidence_views';
import {
  distributionTemplate,
  featureDraftCards,
  featureForm,
  featureGrid,
  jointTemplate,
  loadFeatureDrafts,
  priorityList,
  saveFeatureDrafts,
  type FeatureDraft,
} from './features';
import {
  cityRows,
  coverageRows,
  dataShell,
  detailView,
  historyView,
  labels,
  sourceCards,
  summaryCards,
} from './views';

export class DataTab {
  private visible = false;
  private generation = 0;
  private page = 1;
  private runs: RunSummary[] = [];
  private sources?: SourceCatalog;
  private preview?: ImportPreview;
  private validation?: ValidationReport;
  private importScope = '';
  private sourceId = '';
  private featureDrafts: FeatureDraft[] = loadFeatureDrafts();
  private activeRunId?: string;
  private promoting?: string;
  private searchTimer?: ReturnType<typeof setTimeout>;

  constructor(private host: HTMLElement) {
    host.innerHTML = dataShell();
    host.addEventListener('click', this.onClick);
    host.addEventListener('submit', this.onSubmit);
    host.addEventListener('input', (event) => {
      const target = event.target as HTMLElement;
      if (target.id === 'atlas-search') {
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => {
          this.page = 1;
          void this.refresh();
        }, 250);
      }
      if (target.hasAttribute('data-mapping-index')) {
        this.validation = undefined;
        this.get<HTMLButtonElement>('atlas-commit-button').disabled = true;
      }
    });
    host.addEventListener('change', (event) => {
      const input = event.target as HTMLInputElement;
      if (input.name === 'source_id') this.fillSourceLabel(input.value);
      if (input.name === 'kind') this.updateFeatureKind(input.value);
      if (
        [
          'atlas-country',
          'atlas-tier',
          'atlas-status',
          'atlas-missing',
          'atlas-scope',
          'atlas-asof',
        ].includes((event.target as HTMLElement).id)
      ) {
        this.page = 1;
        void this.refresh();
      }
    });
  }

  private get<T extends HTMLElement = HTMLElement>(id: string): T {
    const node = this.host.querySelector<HTMLElement>(`#${id}`);
    if (!node) throw new Error(`Missing data interface element ${id}`);
    return node as T;
  }

  async activate(activeRunId?: string): Promise<void> {
    this.visible = true;
    this.activeRunId = activeRunId;
    this.host.hidden = false;
    try {
      const [runs, sources, scopes] = await Promise.all([
        api.list(),
        atlasApi.sources(),
        atlasApi.scopes(),
      ]);
      this.runs = runs.runs;
      this.sources = sources;
      const scope = this.get<HTMLSelectElement>('atlas-scope');
      const previous = scope.value;
      scope.innerHTML =
        '<option value="shared">Shared atlas</option>' +
        scopes.scopes
          .map(
            (run) =>
              `<option value="${e(run.run_id)}">${e(run.label)} · ${run.run_id.slice(0, 8)}</option>`,
          )
          .join('');
      scope.value = Array.from(scope.options).some((option) => option.value === previous)
        ? previous
        : 'shared';
      await this.refresh();
    } catch (error) {
      this.error(error);
    }
  }

  deactivate(): void {
    this.visible = false;
    ++this.generation;
    clearTimeout(this.searchTimer);
    this.host
      .querySelectorAll<HTMLDialogElement>('dialog[open]')
      .forEach((dialog) => dialog.close());
    this.host.hidden = true;
  }

  private query(): URLSearchParams {
    return new URLSearchParams({
      scope: this.get<HTMLSelectElement>('atlas-scope').value,
      as_of: this.get<HTMLInputElement>('atlas-asof').value,
      search: this.get<HTMLInputElement>('atlas-search').value,
      country: this.get<HTMLSelectElement>('atlas-country').value,
      tier: this.get<HTMLSelectElement>('atlas-tier').value,
      status: this.get<HTMLSelectElement>('atlas-status').value,
      missing_field: this.get<HTMLSelectElement>('atlas-missing').value,
      page: String(this.page),
      page_size: '25',
    });
  }

  private error(error: unknown, id = 'atlas-error'): void {
    const target = this.get(id);
    target.hidden = false;
    target.textContent = error instanceof Error ? error.message : String(error);
  }

  private async refresh(): Promise<void> {
    const generation = ++this.generation;
    this.get('atlas-error').hidden = true;
    try {
      const query = this.query();
      const [view, history, features, hierarchy, choices] = await Promise.all([
        atlasApi.overview(query),
        atlasApi.history(query.get('scope')!),
        atlasApi.features(),
        atlasApi.hierarchy(query.get('scope')!, query.get('as_of')!),
        atlasApi.choices(),
      ]);
      if (!this.visible || generation !== this.generation) return;
      this.get('atlas-summary').innerHTML = summaryCards(view);
      this.get('atlas-universal-features').innerHTML = universalFeatureView(features);
      this.get('atlas-hierarchy').innerHTML = hierarchyView(hierarchy);
      this.get('atlas-choice-evidence').innerHTML = choiceEvidenceView(choices);
      this.get('atlas-feature-grid').innerHTML = featureGrid(view);
      this.get('atlas-priorities').innerHTML = priorityList(view);
      this.renderFeatureDrafts();
      this.get('atlas-coverage').innerHTML = coverageRows(view);
      this.get('atlas-cities').innerHTML = cityRows(view.cities);
      this.get('atlas-filter-count').textContent =
        ` / ${view.filtered_count.toLocaleString()} matches`;
      this.get('atlas-page-label').textContent = view.filtered_count
        ? `${((view.page - 1) * view.page_size + 1).toLocaleString()}–${Math.min(view.page * view.page_size, view.filtered_count).toLocaleString()} of ${view.filtered_count.toLocaleString()} · ${view.page_size} rows per page`
        : '0 matching cities';
      this.get('atlas-page-number').textContent =
        `${view.page} / ${Math.max(1, Math.ceil(view.filtered_count / view.page_size))}`;
      this.host.querySelector<HTMLButtonElement>('[data-atlas-action="previous"]')!.disabled =
        view.page === 1;
      this.host.querySelector<HTMLButtonElement>('[data-atlas-action="next"]')!.disabled =
        view.page * view.page_size >= view.filtered_count;
      const country = this.get<HTMLSelectElement>('atlas-country');
      const selected = country.value;
      country.innerHTML =
        '<option value="">All countries</option>' +
        view.countries
          .map(
            (c) =>
              `<option value="${c.country_code}">${e(c.name)} (${c.cities.toLocaleString()})</option>`,
          )
          .join('');
      country.value = selected;
      this.get('atlas-gaps').innerHTML =
        view.gaps
          .map(
            (gap) =>
              `<tr><th><button class="atlas-city-link" data-atlas-action="city" data-id="${gap.geonameid}">${e(gap.city)}</button></th><td>${gap.country_code}</td><td>${labels[gap.field]}</td><td><span class="field-status ${gap.status}">${gap.status}</span></td><td>${gap.population.toLocaleString()}</td><td>${e(gap.suggested_source)}</td></tr>`,
          )
          .join('') ||
        '<tr><td colspan="6" class="atlas-empty">No city observation gaps in this scope.</td></tr>';
      this.get('atlas-history').innerHTML = historyView(history, query.get('scope')!);
      if (
        query.get('scope') !== 'shared' &&
        history.versions.some((version) => version.scope === query.get('scope'))
      ) {
        this.get<HTMLDetailsElement>('atlas-history-panel').open = true;
      }
      this.get('atlas-load').hidden = view.backbone.loaded;
      this.get('atlas-backbone-note').textContent = view.backbone.loaded
        ? `${view.backbone.retained_rows.toLocaleString()} retained from ${view.backbone.original_rows.toLocaleString()} source records · ${view.backbone.excluded_rows.toLocaleString()} excluded · ${view.backbone.duplicate_rows} duplicate IDs`
        : 'Load the complete source once. Empty marginal fields never remove a city.';
      this.get('atlas-attribution').innerHTML =
        `<a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a> · ${e(view.backbone.license)} · source date ${view.backbone.source_date ?? 'not loaded'}<br>${e(view.backbone.selection_policy)}<br><span class="mono">${e(view.backbone.version)} · revision ${view.summary.revision}</span><br>Population weights use listed city populations; overlapping urban places are not a national population estimate. ${view.summary.cities_without_population.toLocaleString()} cities without positive source population are excluded from the population denominator. Tier assignments do not activate city simulation in the current fake-data engine.`;
    } catch (error) {
      if (generation === this.generation) this.error(error);
    }
  }

  private openImport(sourceId = ''): void {
    if (!this.sources) return;
    this.sourceId = sourceId;
    this.preview = undefined;
    this.validation = undefined;
    this.get('atlas-import-body').innerHTML = importForm(
      this.runs,
      this.sources,
      this.activeRunId,
      sourceId,
    );
    this.fillSourceLabel(sourceId);
    this.get<HTMLDialogElement>('atlas-import-dialog').showModal();
  }

  private fillSourceLabel(sourceId: string): void {
    const source = this.sources?.sources.find((source) => source.source_id === sourceId);
    const label = this.host.querySelector<HTMLInputElement>('[name="source"]');
    if (label && source) label.value = source.name;
  }

  private renderFeatureDrafts(): void {
    this.get('atlas-feature-drafts').innerHTML = featureDraftCards(this.featureDrafts);
  }

  private featureDraftById(id: string): FeatureDraft | undefined {
    return this.featureDrafts.find((draft) => draft.id === id);
  }

  private openFeature(): void {
    this.get('atlas-feature-body').innerHTML = featureForm();
    this.updateFeatureKind('continuous');
    this.get<HTMLDialogElement>('atlas-feature-dialog').showModal();
  }

  private updateFeatureKind(kind: string): void {
    this.host.querySelectorAll<HTMLElement>('[data-kind-fields]').forEach((field) => {
      field.hidden = field.dataset.kindFields !== kind;
    });
  }

  private saveFeature(form: HTMLFormElement): void {
    const values = new FormData(form);
    const read = (name: string): string => String(values.get(name) ?? '').trim();
    const error = this.get('atlas-feature-error');
    const name = read('name').toLowerCase();
    if (!/^[a-z][a-z0-9_]*$/.test(name)) {
      error.hidden = false;
      error.textContent = 'Use a snake_case name starting with a letter: endurance, tiktok_use.';
      return;
    }
    if (this.featureDrafts.some((draft) => draft.name === name)) {
      error.hidden = false;
      error.textContent = `A feature plan named ${name} already exists.`;
      return;
    }
    const label = read('label');
    const definition = read('definition');
    if (!label || !definition) {
      error.hidden = false;
      error.textContent = 'Add a display label and a precise measurement definition.';
      return;
    }
    const kind = read('kind') as FeatureDraft['kind'];
    const unit = read('unit');
    const minimum = read('minimum');
    const maximum = read('maximum');
    const categories = read('categories')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    const outcomes = read('outcomes')
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean);
    if (outcomes.some((outcome) => !/^[a-z][a-z0-9_]*$/.test(outcome))) {
      error.hidden = false;
      error.textContent = 'Outcome keys must use lowercase snake_case.';
      return;
    }
    if (kind === 'continuous') {
      const lower = Number(minimum);
      const upper = Number(maximum);
      if (
        !unit ||
        !minimum ||
        !maximum ||
        !Number.isFinite(lower) ||
        !Number.isFinite(upper) ||
        lower >= upper
      ) {
        error.hidden = false;
        error.textContent =
          'Continuous features need a unit and a numeric minimum below the maximum.';
        return;
      }
    }
    const uniqueCategories = Array.from(new Set(categories));
    if (kind === 'categorical' && uniqueCategories.length < 2) {
      error.hidden = false;
      error.textContent = 'Categorical features need at least two distinct categories.';
      return;
    }
    this.featureDrafts = [
      ...this.featureDrafts,
      {
        id:
          typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : `feature-${Date.now()}`,
        name,
        label,
        kind,
        definition,
        unit: kind === 'continuous' ? unit : '',
        minimum: kind === 'continuous' ? minimum : '',
        maximum: kind === 'continuous' ? maximum : '',
        categories: kind === 'binary' ? ['no', 'yes'] : uniqueCategories,
        coverageLevel: read('coverage_level') as FeatureDraft['coverageLevel'],
        outcomes: Array.from(new Set(outcomes)),
        createdAt: new Date().toISOString(),
      },
    ];
    saveFeatureDrafts(this.featureDrafts);
    this.get<HTMLDialogElement>('atlas-feature-dialog').close();
    this.renderFeatureDrafts();
    document
      .getElementById('atlas-feature-drafts')
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  private downloadFeatureTemplate(draft: FeatureDraft, kind: 'distribution' | 'joint'): void {
    const content = kind === 'distribution' ? distributionTemplate(draft) : jointTemplate(draft);
    const blob = new Blob([content], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${draft.name}-${kind}-template.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  private onSubmit = async (event: SubmitEvent): Promise<void> => {
    const target = event.target as HTMLElement;
    if (target.id === 'atlas-feature-form') {
      event.preventDefault();
      this.saveFeature(target as HTMLFormElement);
      return;
    }
    if (target.id !== 'atlas-import-form') return;
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const values = new FormData(form);
    const read = (name: string): string => String(values.get(name) ?? '');
    const sourceId = read('source_id');
    const source = this.sources?.sources.find((source) => source.source_id === sourceId);
    const metadata: ImportMetadata = {
      run_id: read('run_id'),
      kind: read('kind') as ImportMetadata['kind'],
      source: source?.name ?? read('source'),
      source_date: read('source_date'),
      published_date: read('published_date'),
      version: read('version'),
      uploader: read('uploader'),
      source_id: sourceId || null,
      country_code: read('country_code') || null,
      unit: read('unit'),
      redistribution_allowed: values.has('redistribution_allowed'),
      processing_notes: [],
    };
    const button = form.querySelector<HTMLButtonElement>('[type="submit"]')!;
    button.disabled = true;
    button.textContent = 'Reading and proposing mappings…';
    try {
      const sourceUrl = read('source_url');
      let preview: ImportPreview;
      if (sourceUrl) {
        if (!sourceId) throw new Error('Select the canonical source loader for this URL.');
        preview = await atlasApi.fetchSource(sourceId, {
          url: sourceUrl,
          metadata,
          access_confirmed: values.has('access_confirmed'),
        });
      } else {
        const file = values.get('file');
        if (!(file instanceof File) || !file.size)
          throw new Error('Choose a data file or an approved source URL.');
        preview = await atlasApi.preview(file, metadata, values.has('use_llm'));
      }
      this.preview = preview;
      this.importScope = metadata.run_id;
      this.get('atlas-import-body').innerHTML = mappingView(preview);
    } catch (error) {
      this.error(error, 'atlas-import-error');
      button.disabled = false;
      button.textContent = 'Preview & map';
    }
  };

  private async validate(): Promise<void> {
    if (!this.preview) return;
    const mappings: MappingConfirmation = {
      confirmed: this.get<HTMLInputElement>('atlas-mapping-confirmed').checked,
      mappings: this.preview.mappings.map((mapping, index) => {
        const value = this.host
          .querySelector<HTMLInputElement>(`[data-mapping-index="${index}"]`)!
          .value.trim();
        return {
          ...mapping,
          target: value && value !== '?' ? value : null,
          ambiguous: value === '?',
        };
      }),
    };
    try {
      this.validation = await atlasApi.validate(this.preview.import_id, this.importScope, mappings);
      this.get('atlas-validation').innerHTML = validationView(this.validation);
      this.get<HTMLButtonElement>('atlas-commit-button').disabled = !this.validation.valid;
      this.get('atlas-import-error').hidden = true;
    } catch (error) {
      this.error(error, 'atlas-import-error');
    }
  }

  private async commit(): Promise<void> {
    if (!this.preview || !this.validation?.valid) return;
    const button = this.get<HTMLButtonElement>('atlas-commit-button');
    button.disabled = true;
    try {
      await atlasApi.commit(this.preview.import_id, this.importScope, {
        confirmed: true,
        mapping_hash: this.validation.mapping_hash,
      });
      this.get<HTMLDialogElement>('atlas-import-dialog').close();
      this.get<HTMLSelectElement>('atlas-scope').value = this.importScope;
      this.page = 1;
      await this.refresh();
    } catch (error) {
      this.error(error, 'atlas-import-error');
      button.disabled = false;
    }
  }

  private async promote(): Promise<void> {
    if (!this.promoting) return;
    try {
      await atlasApi.promote(this.promoting, this.get<HTMLSelectElement>('atlas-scope').value, {
        confirmed: true,
        redistribution_confirmed: this.get<HTMLInputElement>('atlas-promotion-rights').checked,
      });
      this.get<HTMLDialogElement>('atlas-promotion-dialog').close();
      await this.refresh();
    } catch (error) {
      this.error(error, 'atlas-promotion-error');
    }
  }

  private onClick = async (event: MouseEvent): Promise<void> => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-atlas-action]');
    if (!target || (target instanceof HTMLButtonElement && target.disabled)) return;
    const action = target.dataset.atlasAction;
    try {
      if (action === 'refresh') await this.refresh();
      else if (action === 'previous') {
        this.page--;
        await this.refresh();
      } else if (action === 'next') {
        this.page++;
        await this.refresh();
      } else if (action === 'city') {
        const detail = await atlasApi.city(Number(target.dataset.id), this.query());
        this.get('atlas-city-detail').innerHTML = detailView(detail);
        this.get<HTMLDialogElement>('atlas-city-dialog').showModal();
      } else if (action === 'hierarchy-country') {
        this.get<HTMLSelectElement>('atlas-country').value = target.dataset.country ?? '';
        this.page = 1;
        await this.refresh();
        this.get('atlas-city-browser').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (action === 'load') {
        target.textContent = 'Loading the complete dump…';
        (target as HTMLButtonElement).disabled = true;
        await atlasApi.backbone();
        await this.refresh();
      } else if (action === 'import') this.openImport();
      else if (action === 'sources' && this.sources) {
        this.get('atlas-sources-list').innerHTML = sourceCards(this.sources);
        this.get<HTMLDialogElement>('atlas-sources-dialog').showModal();
      } else if (action === 'source-import') {
        this.get<HTMLDialogElement>('atlas-sources-dialog').close();
        this.openImport(target.dataset.source);
      } else if (action === 'restart-import' && this.sources) {
        this.get('atlas-import-body').innerHTML = importForm(
          this.runs,
          this.sources,
          this.activeRunId,
          this.sourceId,
        );
      } else if (action === 'validate') await this.validate();
      else if (action === 'commit') await this.commit();
      else if (action === 'resume-import') {
        this.importScope = this.get<HTMLSelectElement>('atlas-scope').value;
        this.preview = await atlasApi.draft(target.dataset.id!, this.importScope);
        this.validation = undefined;
        this.get('atlas-import-body').innerHTML = mappingView(this.preview);
        this.get<HTMLDialogElement>('atlas-import-dialog').showModal();
      } else if (action === 'promote') {
        this.promoting = target.dataset.id;
        this.get<HTMLInputElement>('atlas-promotion-rights').checked = false;
        this.get('atlas-promotion-error').hidden = true;
        this.get<HTMLDialogElement>('atlas-promotion-dialog').showModal();
      } else if (action === 'confirm-promotion') await this.promote();
      else if (action === 'cancel-promotion')
        this.get<HTMLDialogElement>('atlas-promotion-dialog').close();
      else if (action === 'add-feature') this.openFeature();
      else if (action === 'close-feature')
        this.get<HTMLDialogElement>('atlas-feature-dialog').close();
      else if (action === 'delete-feature') {
        this.featureDrafts = this.featureDrafts.filter((draft) => draft.id !== target.dataset.id);
        saveFeatureDrafts(this.featureDrafts);
        this.renderFeatureDrafts();
      } else if (action === 'download-distribution' || action === 'download-joint') {
        const draft = this.featureDraftById(target.dataset.id!);
        if (draft) {
          this.downloadFeatureTemplate(
            draft,
            action === 'download-distribution' ? 'distribution' : 'joint',
          );
        }
      } else if (action === 'import-for-feature') {
        this.openImport();
        const kind = this.host.querySelector<HTMLSelectElement>('[name="kind"]');
        if (kind) kind.value = 'behaviour';
      } else if (action === 'filter-feature') {
        this.get<HTMLSelectElement>('atlas-missing').value = target.dataset.field ?? '';
        this.get<HTMLInputElement>('atlas-search').value = '';
        this.get<HTMLSelectElement>('atlas-country').value = '';
        this.page = 1;
        await this.refresh();
        this.get('atlas-city-browser').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (action?.startsWith('close-'))
        this.get<HTMLDialogElement>(`atlas-${action.slice(6)}-dialog`).close();
    } catch (error) {
      this.error(error);
      if (action === 'load') {
        target.textContent = 'Retry full backbone load';
        (target as HTMLButtonElement).disabled = false;
      }
    }
  };
}
