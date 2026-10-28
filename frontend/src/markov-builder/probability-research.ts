import './probability-research.css';
import { escapeHtml as e } from '../views';
import type {
  ChainDraft,
  ChainTransitionDraft,
  MarkovBuilderApi,
  PipelineEstimateSource,
  PipelineTransitionEstimate,
  TransitionProbabilityResearchRequest,
  TransitionResearchPlaceLevel,
  TransitionResearchTimeUnit,
} from './types';

interface ProbabilityResearchContext {
  level: TransitionResearchPlaceLevel;
  placeId: string;
  placeLabel: string;
  countryCode: string;
  population: string;
  languages: string;
  localNames: string;
  timeUnit: TransitionResearchTimeUnit;
}

interface ProbabilityResearchReceipt {
  estimate: PipelineTransitionEstimate;
  applied: boolean;
}

interface ProbabilityResearchCallbacks {
  changed(): void;
  render(): void;
  setFeedback(message: string, error: string): void;
}

const percentage = (value: number): string => `${(value * 100).toFixed(2).replace(/\.00$/, '')}%`;

const option = (value: string, label: string, selected: string): string =>
  `<option value="${e(value)}" ${value === selected ? 'selected' : ''}>${e(label)}</option>`;

const slug = (value: string, fallback: string): string => {
  let identity = value
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
  if (!identity) identity = fallback;
  if (!/^[a-z]/.test(identity)) identity = `${fallback}_${identity}`;
  return identity.slice(0, 80).replace(/_+$/g, '');
};

const sourceKindLabel = (value: string): string =>
  value.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());

const externalUrl = (value: string | null): string | null => {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
};

const commaSeparated = (value: string): string[] =>
  [...new Set(value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean))];

const localNameMap = (value: string): { names: Record<string, string>; error: string | null } => {
  const names: Record<string, string> = {};
  const entries = value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  for (const entry of entries) {
    const separator = entry.indexOf('=');
    const language = separator >= 0 ? entry.slice(0, separator).trim() : '';
    const name = separator >= 0 ? entry.slice(separator + 1).trim() : '';
    if (language.length < 2 || !name) {
      return { names: {}, error: 'Use language=name pairs, such as zh=中国.' };
    }
    names[language] = name;
  }
  return { names, error: null };
};

export class ProbabilityResearchPanel {
  private researching = false;
  private progress = '';
  private readonly receipts = new Map<string, ProbabilityResearchReceipt>();
  private readonly errors = new Map<string, string>();
  private readonly context: ProbabilityResearchContext = {
    level: 'country',
    placeId: '',
    placeLabel: '',
    countryCode: '',
    population: '',
    languages: '',
    localNames: '',
    timeUnit: 'event',
  };

  constructor(
    private readonly api: MarkovBuilderApi,
    private readonly callbacks: ProbabilityResearchCallbacks,
  ) {}

  get busy(): boolean {
    return this.researching;
  }

  render(draft: ChainDraft): string {
    const missingCount = draft.transitions.filter((edge) => edge.probability === null).length;
    const contextProblem = this.contextProblem();
    const disabled = this.researching || missingCount === 0 || contextProblem !== null;
    const state = this.researching
      ? this.progress
      : missingCount === 0
        ? 'Every edge already has a probability.'
        : contextProblem ?? `${missingCount} unresolved ${missingCount === 1 ? 'edge' : 'edges'} ready for research.`;
    return `
      <section class="markov-research" role="region" aria-label="Probability research">
        <div class="markov-section-heading">
          <div><p class="eyebrow">PIPELINE EVIDENCE</p><h3>Research missing probabilities</h3></div>
          <span>${missingCount} unresolved</span>
        </div>
        <p class="markov-research-intro">Set the population and local-language context used by the in-app research pipeline. Results arrive as estimated drafts with wide uncertainty and stay separate from the chain until you apply them.</p>
        <div class="markov-research-context">
          <label>Place level<select data-research-field="level" aria-label="Place level">
            ${option('region', 'Region', this.context.level)}
            ${option('country', 'Country', this.context.level)}
            ${option('city', 'City', this.context.level)}
          </select></label>
          <label>Place id<input data-research-field="placeId" aria-label="Place id" value="${e(this.context.placeId)}" placeholder="CHN"></label>
          <label>Place label<input data-research-field="placeLabel" aria-label="Place label" value="${e(this.context.placeLabel)}" placeholder="China"></label>
          <label>Country code<input data-research-field="countryCode" aria-label="Country code" value="${e(this.context.countryCode)}" placeholder="CN" maxlength="2"></label>
          <label>Population<input data-research-field="population" aria-label="Population" type="number" min="0" step="1" value="${e(this.context.population)}" placeholder="1409000000"></label>
          <label>Research languages<input data-research-field="languages" aria-label="Research languages" value="${e(this.context.languages)}" placeholder="zh, en"></label>
          <label class="markov-research-wide">Local labels<input data-research-field="localNames" aria-label="Local labels" value="${e(this.context.localNames)}" placeholder="zh=中国, en=China"></label>
          <label>Time unit<select data-research-field="timeUnit" aria-label="Time unit">
            ${option('event', 'Per event', this.context.timeUnit)}
            ${option('hour', 'Hourly', this.context.timeUnit)}
            ${option('day', 'Daily', this.context.timeUnit)}
            ${option('friday', 'Friday', this.context.timeUnit)}
            ${option('week', 'Weekly', this.context.timeUnit)}
            ${option('year', 'Yearly', this.context.timeUnit)}
          </select></label>
        </div>
        <div class="markov-research-actions">
          <div><strong>Local search first</strong><span data-research-context-state>${e(state)}</span></div>
          <button class="button secondary" data-markov-action="research-probabilities" ${disabled ? 'disabled' : ''}>${this.researching ? 'Researching probabilities…' : 'Research missing probabilities'}</button>
        </div>
        <div class="markov-research-results" aria-live="polite">
          ${this.resultContent(draft)}
        </div>
      </section>`;
  }

  captureContext(field: string, value: string, draft: ChainDraft, host: HTMLElement): void {
    if (field === 'level' && ['region', 'country', 'city'].includes(value)) {
      this.context.level = value as TransitionResearchPlaceLevel;
    }
    if (field === 'placeId') this.context.placeId = value;
    if (field === 'placeLabel') this.context.placeLabel = value;
    if (field === 'countryCode') this.context.countryCode = value;
    if (field === 'population') this.context.population = value;
    if (field === 'languages') this.context.languages = value;
    if (field === 'localNames') this.context.localNames = value;
    if (field === 'timeUnit' && ['event', 'hour', 'day', 'friday', 'week', 'year'].includes(value)) {
      this.context.timeUnit = value as TransitionResearchTimeUnit;
    }
    this.refreshAction(draft, host);
  }

  handleAction(action: string, edgeId: string, draft: ChainDraft): boolean {
    if (action === 'research-probabilities') {
      void this.researchMissing(draft);
      return true;
    }
    if (action === 'apply-research-probability') {
      this.apply(edgeId, draft);
      return true;
    }
    return false;
  }

  clearResults(): void {
    this.receipts.clear();
    this.errors.clear();
    this.progress = '';
  }

  invalidate(edgeId: string): void {
    this.receipts.delete(edgeId);
    this.errors.delete(edgeId);
  }

  invalidateAll(): void {
    this.receipts.clear();
    this.errors.clear();
  }

  updateAppliedState(edgeId: string, probability: number | null): void {
    const receipt = this.receipts.get(edgeId);
    if (receipt) receipt.applied = probability === receipt.estimate.probability;
  }

  private resultContent(draft: ChainDraft): string {
    const rows = draft.transitions.flatMap((edge) => {
      const receipt = this.receipts.get(edge.id);
      const error = this.errors.get(edge.id);
      if (receipt) return [this.receipt(draft, edge, receipt)];
      if (error) {
        return [
          `<article class="markov-research-failure"><strong>${e(this.edgeLabel(draft, edge))}</strong><p>${e(error)}</p><span>Keep this edge unresolved and retry the pipeline.</span></article>`,
        ];
      }
      return [];
    });
    if (rows.length) return rows.join('');
    return '<p class="markov-research-empty">Research receipts will appear here before any draft probability can be used.</p>';
  }

  private receipt(
    draft: ChainDraft,
    edge: ChainTransitionDraft,
    receipt: ProbabilityResearchReceipt,
  ): string {
    const estimate = receipt.estimate;
    const selected = new Set(estimate.selected_source_ids);
    const sources = estimate.sources
      .map((source) => this.source(source, selected.has(source.id)))
      .join('');
    const log = estimate.search_log
      .map(
        (entry) => `<tr><td>${entry.sequence}</td><td><strong>${e(entry.engine)}</strong><span>${e(entry.language)} · ${e(sourceKindLabel(entry.source_kind))}</span></td><td>${e(entry.query_or_source)}</td><td><span class="markov-search-outcome ${e(entry.outcome)}">${e(sourceKindLabel(entry.outcome))}</span></td></tr>`,
      )
      .join('');
    const assumptions = estimate.assumptions.map((item) => `<li>${e(item)}</li>`).join('');
    const appliedState = receipt.applied
      ? '<span class="markov-research-applied">Applied to this chain draft</span>'
      : '<span>Not applied to the chain</span>';
    return `
      <article class="markov-research-receipt" data-probability-research-receipt data-edge-id="${e(edge.id)}">
        <header>
          <div><span class="markov-research-badge">Estimated draft</span><h4>${e(this.edgeLabel(draft, edge))}</h4><p>${e(edge.id)}</p></div>
          <div class="markov-research-rate"><strong>${percentage(estimate.probability)}</strong><span>Wide CI ${percentage(estimate.ci_low)}–${percentage(estimate.ci_high)}</span></div>
        </header>
        <div class="markov-research-meta">
          <span>${e(estimate.population)}</span>
          <span>${estimate.sample_size === null ? 'Sample size not reported' : `n=${estimate.sample_size.toLocaleString()}`}</span>
          <span>${e(estimate.pipeline_provider)} · ${e(estimate.pipeline_model)}</span>
          <span>${e(estimate.prompt_version)}</span>
        </div>
        <section><h5>Reasoning</h5><p>${e(estimate.reasoning)}</p></section>
        <section><h5>Assumptions</h5><ul>${assumptions}</ul></section>
        <section><h5>Sources</h5><div class="markov-research-sources">${sources}</div></section>
        <section class="markov-search-log">
          <h5>Ordered search log</h5>
          <div class="markov-search-log-scroll"><table><thead><tr><th>#</th><th>Engine</th><th>Query or source</th><th>Result</th></tr></thead><tbody>${log}</tbody></table></div>
        </section>
        <footer>
          ${appliedState}
          <button class="button secondary" data-markov-action="apply-research-probability" data-edge-id="${e(edge.id)}" ${receipt.applied ? 'disabled' : ''}>${receipt.applied ? 'Draft applied' : `Use ${percentage(estimate.probability)} draft`}</button>
        </footer>
      </article>`;
  }

  private source(source: PipelineEstimateSource, selected: boolean): string {
    const url = externalUrl(source.url);
    const title = url
      ? `<a href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(source.title)}</a>`
      : `<strong>${e(source.title)}</strong>`;
    const date = source.observation_date ?? source.published_date ?? source.retrieved_date ?? 'Date unavailable';
    return `
      <article class="markov-research-source ${selected ? 'selected' : ''}">
        <div>${title}${selected ? '<span>Used</span>' : ''}</div>
        <p>${e(sourceKindLabel(source.source_kind))} · ${e(source.language)} · ${e(date)} · ${e(source.source_version)}</p>
        <blockquote>${e(source.excerpt)}</blockquote>
        <small>${e(source.license)}</small>
      </article>`;
  }

  private edgeLabel(draft: ChainDraft, edge: ChainTransitionDraft): string {
    const source = draft.nodes.find((node) => node.id === edge.from_node)?.label ?? edge.from_node;
    const target = draft.nodes.find((node) => node.id === edge.to_node)?.label ?? edge.to_node;
    return `${source} → ${target}`;
  }

  private contextProblem(): string | null {
    if (!this.context.placeId.trim()) return 'Add the place id used by the Atlas.';
    if (!this.context.placeLabel.trim()) return 'Add the place label shown in provenance.';
    const population = Number(this.context.population);
    if (!Number.isSafeInteger(population) || population < 0) {
      return 'Add a whole-number population for this research context.';
    }
    const languages = commaSeparated(this.context.languages);
    if (!languages.length || languages.some((language) => language.length < 2)) {
      return 'Add local research languages in priority order.';
    }
    const countryCode = this.context.countryCode.trim();
    if (this.context.level !== 'region' && !/^[a-z]{2}$/i.test(countryCode)) {
      return 'Add the two-letter country code for country or city research.';
    }
    if (countryCode && !/^[a-z]{2}$/i.test(countryCode)) {
      return 'Country code must contain two letters.';
    }
    const parsedNames = localNameMap(this.context.localNames);
    if (parsedNames.error) return parsedNames.error;
    const primaryLanguage = languages[0]!;
    if (primaryLanguage !== 'en' && !parsedNames.names[primaryLanguage]) {
      return `Add the ${primaryLanguage} local place label so local-language research runs first.`;
    }
    return null;
  }

  private refreshAction(draft: ChainDraft, host: HTMLElement): void {
    const missingCount = draft.transitions.filter((edge) => edge.probability === null).length;
    const contextProblem = this.contextProblem();
    const button = host.querySelector<HTMLButtonElement>(
      '[data-markov-action="research-probabilities"]',
    );
    if (button) button.disabled = this.researching || missingCount === 0 || contextProblem !== null;
    const state = host.querySelector<HTMLElement>('[data-research-context-state]');
    if (state) {
      state.textContent = contextProblem ?? `${missingCount} unresolved ${missingCount === 1 ? 'edge' : 'edges'} ready for research.`;
    }
  }

  private async researchMissing(draft: ChainDraft): Promise<void> {
    const contextProblem = this.contextProblem();
    if (contextProblem) {
      this.callbacks.setFeedback('', contextProblem);
      this.callbacks.render();
      return;
    }
    const edges = draft.transitions.filter((edge) => edge.probability === null);
    if (!edges.length) return;
    this.researching = true;
    this.callbacks.setFeedback('', '');
    this.progress = `Starting research for ${edges.length} ${edges.length === 1 ? 'edge' : 'edges'}…`;
    edges.forEach((edge) => {
      this.receipts.delete(edge.id);
      this.errors.delete(edge.id);
    });
    this.callbacks.render();
    let completed = 0;
    for (const edge of edges) {
      try {
        const estimate = await this.api.researchProbability(this.researchRequest(draft, edge));
        this.receipts.set(edge.id, { estimate, applied: false });
      } catch (error) {
        this.errors.set(edge.id, error instanceof Error ? error.message : String(error));
      }
      completed += 1;
      this.progress = `Researched ${completed} of ${edges.length} ${edges.length === 1 ? 'edge' : 'edges'}…`;
      this.callbacks.render();
    }
    this.researching = false;
    const ready = edges.filter((edge) => this.receipts.has(edge.id)).length;
    const retry = edges.length - ready;
    const message = retry
      ? `${ready} draft ${ready === 1 ? 'receipt is' : 'receipts are'} ready. ${retry} ${retry === 1 ? 'edge needs' : 'edges need'} a pipeline retry.`
      : `${ready} estimated ${ready === 1 ? 'draft is' : 'drafts are'} ready for review. Apply each rate explicitly; totals are never normalized.`;
    this.callbacks.setFeedback(message, '');
    this.callbacks.render();
  }

  private researchRequest(
    draft: ChainDraft,
    edge: ChainTransitionDraft,
  ): TransitionProbabilityResearchRequest {
    const outgoing = draft.transitions.filter((candidate) => candidate.from_node === edge.from_node);
    const source = draft.nodes.find((node) => node.id === edge.from_node);
    const target = draft.nodes.find((node) => node.id === edge.to_node);
    const population = Number(this.context.population);
    const outcomeDescription = `${target?.label ?? edge.to_node}${edge.condition ? ` when ${edge.condition}` : ''}`;
    return {
      transition_id: edge.id,
      outcome_id: edge.id,
      outcome_description: outcomeDescription,
      outcomes: outgoing.map((candidate) => {
        const candidateTarget = draft.nodes.find((node) => node.id === candidate.to_node);
        return {
          id: candidate.id,
          description: `${candidateTarget?.label ?? candidate.to_node}${candidate.condition ? ` when ${candidate.condition}` : ''}`,
          localized_descriptions: {},
        };
      }),
      conditioning_id: slug(`${draft.id}_${edge.from_node}_${this.context.timeUnit}`, 'decision_context'),
      conditioning_description: `People in ${source?.label ?? edge.from_node} choosing among the listed outgoing transitions`,
      localized_conditioning_descriptions: {},
      localized_search_terms: {},
      place: {
        level: this.context.level,
        place_id: this.context.placeId.trim(),
        place_label: this.context.placeLabel.trim(),
        population,
        country_code: this.context.countryCode.trim().toUpperCase() || null,
        local_names: localNameMap(this.context.localNames).names,
        dominant_languages: commaSeparated(this.context.languages),
      },
      time_unit: this.context.timeUnit,
      predictor_values: {},
      condition_values: edge.condition ? { condition: edge.condition } : {},
      population_basis: `${this.context.placeLabel.trim()} population (${population})`,
    };
  }

  private apply(edgeId: string, draft: ChainDraft): void {
    const edge = draft.transitions.find((candidate) => candidate.id === edgeId);
    const receipt = this.receipts.get(edgeId);
    if (!edge || !receipt) return;
    edge.probability = receipt.estimate.probability;
    edge.origin = 'manual_edit';
    receipt.applied = true;
    this.callbacks.changed();
  }
}
