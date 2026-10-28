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
import { autoImportClient, mountAutoImport, type AutoImportSurface } from './auto-import';
import type { AutoImportAttempt, ResearchSource } from './auto-import-model';
import {
  importForm,
  mappingView,
  type ImportFormDefaults,
  validationView,
} from './import_views';
import { choiceEvidenceView } from './evidence_views';
import {
  FeatureCatalogController,
  type CatalogFeature,
  type FeatureCatalogView,
} from './feature-catalog';
import { featureQueryClient, placeOptions } from './feature-query-api';
import { HierarchyBrowser, type HierarchyBrowserRow } from './hierarchy-browser';
import { JoinedFilterPanel, type JoinedFeatureOption } from './joined-filter';
import {
  cityRows,
  coverageRows,
  dataShell,
  detailView,
  historyView,
  sourceCards,
  summaryCards,
} from './views';

function evidenceSource(source: ResearchSource): string {
  const href = (() => {
    if (!source.url) return null;
    try {
      const parsed = new URL(source.url);
      return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
    } catch {
      return null;
    }
  })();
  const title = href
    ? `<a href="${e(href)}" target="_blank" rel="noreferrer">${e(source.title)} ↗</a>`
    : `<strong>${e(source.title)}</strong>`;
  return `<article class="feature-research-source">
    <div>${title}<span class="field-status ${source.accepted ? 'present' : 'missing'}">${source.accepted ? 'accepted' : 'rejected'}</span></div>
    <small>${e(source.publisher)} · ${e(source.language)} · observed ${e(source.source_date ?? 'date not supplied')} · published ${e(source.published_date ?? 'date not supplied')} · ${e(source.version ?? 'version not supplied')} · ${e(source.licence ?? 'licence not supplied')}</small>
    ${source.original_excerpt ? `<p><strong>Original</strong> ${e(source.original_excerpt)}</p>` : ''}
    ${source.translated_excerpt ? `<p><strong>Translation</strong> ${e(source.translated_excerpt)}</p>` : ''}
    ${source.rejection_reason ? `<p>${e(source.rejection_reason)}</p>` : ''}
  </article>`;
}

function featureSearchLog(attempt: AutoImportAttempt): string {
  if (!attempt.search_log.length) return '<p class="muted">No recorded searches for this run.</p>';
  return `<details class="feature-research-log" open>
    <summary>Research search log · ${attempt.search_log.length.toLocaleString()}</summary>
    <div class="auto-import-table-scroll"><table>
      <thead><tr><th>Engine</th><th>Language</th><th>Query / source</th><th>Date</th><th>Results</th><th>Outcome</th><th>Reasons</th></tr></thead>
      <tbody>${attempt.search_log
        .map(
          (entry) => `<tr>
            <td>${e(entry.engine)}</td><td>${e(entry.language)}</td><td>${e(entry.query)}</td><td>${e(entry.searched_at ?? 'date not supplied')}</td>
            <td>${entry.result_count.toLocaleString()}</td><td>${e(entry.outcome)}</td>
            <td>${entry.rejection_reasons.length ? entry.rejection_reasons.map(e).join('<br>') : '—'}</td>
          </tr>`,
        )
        .join('')}</tbody>
    </table></div>
  </details>`;
}

function titleCase(value: string): string {
  const words = value.replaceAll('_', ' ');
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

function resultStateLabel(attempt: AutoImportAttempt): string {
  if (attempt.draft_status === 'editable_draft') return 'Editable draft';
  return `${titleCase(attempt.draft_status)} version`;
}

function featureResearchEvidence(attempts: AutoImportAttempt[]): string {
  if (!attempts.length) {
    return `<section class="feature-catalog-detail-section feature-research-evidence">
      <div><h4>Imported research evidence</h4><span>Research pipeline ready</span></div>
      <p>Import or run research to produce a reviewable draft.</p>
    </section>`;
  }
  return `<section class="feature-catalog-detail-section feature-research-evidence">
    <div><h4>Imported research evidence</h4><span>${attempts.length.toLocaleString()} promoted ${attempts.length === 1 ? 'distribution' : 'distributions'}</span></div>
    <div class="feature-research-attempts">${attempts
      .map((attempt) => {
        const trace = attempt.estimate_trace;
        const distribution = Object.entries(attempt.candidate_values)
          .map(([label, value]) => `${e(label)} ${e(String(value))}%`)
          .join(' · ');
        const languages = Array.from(
          new Set(attempt.search_log.map((entry) => entry.language).filter(Boolean)),
        );
        return `<article class="feature-research-attempt">
          <div class="feature-research-heading">
            <div><strong>${e(attempt.target.place_label)}</strong><small>${e(attempt.target.level)} · ${attempt.target.population.toLocaleString()} people</small></div>
            <span class="field-status ${attempt.evidence_kind === 'measured' ? 'present' : 'estimated'}">${e(attempt.evidence_kind ?? 'estimated draft')}</span>
          </div>
          <p class="feature-research-draft"><strong>${e(resultStateLabel(attempt))}</strong> · ${attempt.usable_in_demo ? 'Executable with this evidence status visible' : 'Review required before execution'}</p>
          <p class="feature-research-distribution">${distribution || 'Draft distribution is being assembled'}</p>
          ${languages.length ? `<small>Searched in ${languages.map(e).join(', ')}</small>` : ''}
          <div class="feature-research-sources">${attempt.sources.map(evidenceSource).join('')}</div>
          ${
            trace
              ? `<dl class="feature-research-estimate">
                  <div><dt>Method</dt><dd>${e(trace.method)}</dd></div>
                  <div><dt>Calculation</dt><dd>${e(trace.calculation)}</dd></div>
                  <div><dt>Inputs</dt><dd>${trace.inputs.map((input) => `${e(input.label)}: ${e(input.value)}`).join('<br>')}</dd></div>
                  <div><dt>Assumptions</dt><dd>${trace.assumptions.map(e).join('<br>')}</dd></div>
                  <div><dt>Wide uncertainty</dt><dd>${e(trace.confidence_interval)}</dd></div>
                  <div><dt>Better data needed</dt><dd>${trace.limitations.map(e).join('<br>')}</dd></div>
                </dl>`
              : ''
          }
          ${featureSearchLog(attempt)}
          ${attempt.promotion_id ? `<p class="auto-import-promotion-record"><strong>Promotion record</strong> <code>${e(attempt.promotion_id)}</code>${attempt.promoted_at ? ` · ${e(attempt.promoted_at)}` : ''}</p>` : ''}
        </article>`;
      })
      .join('')}</div>
  </section>`;
}

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
  private importDefaults: ImportFormDefaults = {};
  private activeTab = 'coverage';
  private activeRunId?: string;
  private promoting?: string;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private readonly hierarchyBrowser: HierarchyBrowser;
  private readonly autoImport: AutoImportSurface;
  private readonly featureCatalog: FeatureCatalogController;
  private joinedPanel?: JoinedFilterPanel;

  constructor(private host: HTMLElement) {
    host.innerHTML = dataShell();
    this.hierarchyBrowser = new HierarchyBrowser(this.get('atlas-hierarchy-browser'), {
      showQueue: false,
      openImport: (row) => this.openHierarchyImport(row),
      openCity: (geonameid) => void this.openCity(geonameid),
      onError: (message) => this.error(new Error(message)),
    });
    this.autoImport = mountAutoImport(this.get('atlas-auto-import'), {
      context: () => ({
        scope: this.get<HTMLSelectElement>('atlas-scope').value,
        asOf: this.get<HTMLInputElement>('atlas-asof').value,
      }),
      onPromoted: async () => {
        await this.hierarchyBrowser.importCompleted();
        await Promise.all([this.refresh(), this.featureCatalog.load()]);
      },
      onBatchPromoted: async () => {
        await this.hierarchyBrowser.importCompleted();
        await Promise.all([this.refresh(), this.featureCatalog.load()]);
      },
      onError: (message) => this.error(new Error(message)),
    });
    this.featureCatalog = new FeatureCatalogController(
      this.get('atlas-feature-catalog'),
      undefined,
      {},
      {
        onImport: (feature) =>
          this.openImport('', { kind: 'marginals', featureId: feature?.id }),
        renderDetailAddon: (target, feature, view) => this.mountFeatureQuery(target, feature, view),
      },
    );
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
        const contextChanged = ['atlas-scope', 'atlas-asof'].includes(
          (event.target as HTMLElement).id,
        );
        if (contextChanged) void Promise.all([this.refresh(), this.featureCatalog.load()]);
        else void this.refresh();
      }
    });
  }

  private get<T extends HTMLElement = HTMLElement>(id: string): T {
    const node = this.host.querySelector<HTMLElement>(`#${id}`);
    if (!node) throw new Error(`Missing data interface element ${id}`);
    return node as T;
  }

  private setTab(tab: string): void {
    this.activeTab = tab;
    this.host.querySelectorAll<HTMLElement>('[data-atlas-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.atlasPanel !== tab;
    });
    this.host.querySelectorAll<HTMLButtonElement>('[data-atlas-tab]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.atlasTab === tab));
    });
  }

  async activate(activeRunId?: string): Promise<void> {
    this.visible = true;
    this.activeRunId = activeRunId;
    this.host.hidden = false;
    this.setTab(this.activeTab);
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
      await Promise.all([this.refresh(), this.featureCatalog.load(), this.autoImport.load()]);
    } catch (error) {
      this.error(error);
    }
  }

  deactivate(): void {
    this.visible = false;
    ++this.generation;
    clearTimeout(this.searchTimer);
    this.hierarchyBrowser.suspend();
    this.autoImport.suspend();
    this.joinedPanel?.dispose();
    this.joinedPanel = undefined;
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
      const [view, history, choices] = await Promise.all([
        atlasApi.overview(query),
        atlasApi.history(query.get('scope')!),
        atlasApi.choices(query.get('scope')!, query.get('as_of')!),
        this.hierarchyBrowser.setContext(query.get('scope')!, query.get('as_of')!),
        this.autoImport.setContext({
          scope: query.get('scope')!,
          asOf: query.get('as_of')!,
        }),
      ]);
      if (!this.visible || generation !== this.generation) return;
      this.get('atlas-summary').innerHTML = summaryCards(view);
      this.get('atlas-choice-evidence').innerHTML = choiceEvidenceView(choices);
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
        `<a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a> · ${e(view.backbone.license)} · source date ${view.backbone.source_date ?? 'not loaded'}<br>${e(view.backbone.selection_policy)}<br><span class="mono">${e(view.backbone.version)} · revision ${view.summary.revision}</span><br>The city audit uses listed GeoNames populations; overlapping urban places are not a national population estimate. The hierarchy queue uses registry population weights, including WPP where installed. ${view.summary.cities_without_population.toLocaleString()} cities without positive source population are excluded from city population-weighted coverage.`;
    } catch (error) {
      if (generation === this.generation) this.error(error);
    }
  }

  private openImport(sourceId = '', defaults: ImportFormDefaults = {}): void {
    if (!this.sources) return;
    this.sourceId = sourceId;
    this.importDefaults = defaults;
    this.preview = undefined;
    this.validation = undefined;
    this.get('atlas-import-body').innerHTML = importForm(
      this.runs,
      this.sources,
      this.activeRunId,
      sourceId,
      defaults,
    );
    this.fillSourceLabel(sourceId);
    this.get<HTMLDialogElement>('atlas-import-dialog').showModal();
  }

  private fillSourceLabel(sourceId: string): void {
    const source = this.sources?.sources.find((source) => source.source_id === sourceId);
    const label = this.host.querySelector<HTMLInputElement>('[name="source"]');
    if (label && source) label.value = source.name;
  }

  private mountFeatureQuery(
    target: HTMLElement,
    feature: CatalogFeature,
    view: FeatureCatalogView,
  ): () => void {
    let disposed = false;
    let panel: JoinedFilterPanel | undefined;
    const evidenceController = new AbortController();
    target.innerHTML =
      '<div data-feature-research-evidence><p class="muted">Loading imported evidence…</p></div><div data-feature-query><p class="muted">Loading place weights…</p></div>';
    const evidenceTarget = target.querySelector<HTMLElement>('[data-feature-research-evidence]')!;
    const queryTarget = target.querySelector<HTMLElement>('[data-feature-query]')!;
    const features: JoinedFeatureOption[] = view.features.map((item) => ({
      id: item.id,
      label: item.name,
      kind: item.type,
      values: item.canonical_values,
      minimum: item.value_range?.minimum,
      maximum: item.value_range?.maximum,
      unit: item.value_range?.unit,
    }));
    const scope = this.get<HTMLSelectElement>('atlas-scope').value;
    const asOf = this.get<HTMLInputElement>('atlas-asof').value;
    void autoImportClient
      .featureEvidence(feature.id, scope, asOf, evidenceController.signal)
      .then((result) => {
        if (!disposed) evidenceTarget.innerHTML = featureResearchEvidence(result.attempts);
      })
      .catch((reason) => {
        if (!disposed && !(reason instanceof DOMException && reason.name === 'AbortError')) {
          evidenceTarget.innerHTML = `<p class="form-error" role="alert">${e(reason instanceof Error ? reason.message : String(reason))}</p>`;
        }
      });
    void placeOptions()
      .then((places) => {
        if (disposed) return;
        if (features.length < 2) {
          queryTarget.innerHTML =
            '<p class="atlas-empty">Add another feature to use joined filters.</p>';
          return;
        }
        panel = new JoinedFilterPanel(
          queryTarget,
          { places, features, initialFeatureId: feature.id },
          featureQueryClient,
        );
        this.joinedPanel = panel;
      })
      .catch((reason) => {
        if (!disposed) this.error(reason);
      });
    return () => {
      disposed = true;
      evidenceController.abort();
      panel?.dispose();
      if (this.joinedPanel === panel) this.joinedPanel = undefined;
    };
  }

  private openHierarchyImport(row?: HierarchyBrowserRow): void {
    this.openImport();
    const country = this.host.querySelector<HTMLInputElement>('[name="country_code"]');
    if (country && row?.country_code) country.value = row.country_code;
  }

  private async openCity(geonameid: number): Promise<void> {
    const detail = await atlasApi.city(geonameid, this.query());
    this.get('atlas-city-detail').innerHTML = detailView(detail);
    this.get<HTMLDialogElement>('atlas-city-dialog').showModal();
  }

  private onSubmit = async (event: SubmitEvent): Promise<void> => {
    const target = event.target as HTMLElement;
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
    const targetFeature = read('target_feature');
    if (targetFeature) metadata.processing_notes.push(`Target feature: ${targetFeature}`);
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
      this.hierarchyBrowser.setImportProgress('mapping', preview.mappings);
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
      this.hierarchyBrowser.setImportProgress('confirmation', mappings.mappings);
      this.validation = await atlasApi.validate(this.preview.import_id, this.importScope, mappings);
      this.hierarchyBrowser.setImportProgress('validation', mappings.mappings);
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
      this.hierarchyBrowser.setImportProgress('promotion');
      await this.refresh();
      await this.featureCatalog.load();
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
      await this.hierarchyBrowser.importCompleted();
      await this.refresh();
      await this.featureCatalog.load();
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
      else if (action === 'tab' && target.dataset.atlasTab) this.setTab(target.dataset.atlasTab);
      else if (action === 'previous') {
        this.page--;
        await this.refresh();
      } else if (action === 'next') {
        this.page++;
        await this.refresh();
      } else if (action === 'city') {
        await this.openCity(Number(target.dataset.id));
      } else if (action === 'hierarchy-country') {
        this.setTab('cities');
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
      else if (action === 'import-evidence') this.openImport('', { kind: 'behaviour' });
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
          this.importDefaults,
        );
      } else if (action === 'validate') await this.validate();
      else if (action === 'commit') await this.commit();
      else if (action === 'resume-import') {
        this.importScope = this.get<HTMLSelectElement>('atlas-scope').value;
        this.preview = await atlasApi.draft(target.dataset.id!, this.importScope);
        this.validation = undefined;
        this.hierarchyBrowser.setImportProgress('mapping', this.preview.mappings);
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
      else if (action?.startsWith('close-'))
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
