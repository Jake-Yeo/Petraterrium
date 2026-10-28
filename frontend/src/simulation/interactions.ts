import './interactions.css';

export type InteractionChannel = 'in_person' | 'phone_message' | 'online';
export type InteractionDirection = 'either' | 'initiator' | 'target';

export interface InteractionFactorProvenance {
  source: string;
  version: string;
  status: string;
  uncertainty: number;
}

export interface InteractionFactor {
  id: string;
  label: string;
  value: number;
  provenance: InteractionFactorProvenance;
}

export interface EvaluatedInteractionFactor {
  kind: 'base' | 'relationship' | 'co_location' | 'place' | 'time' | 'context';
  factor: InteractionFactor;
}

export interface AppliedStateDelta {
  agent_id: string;
  state: string;
  before: number;
  delta: number;
  after: number;
}

export interface AppliedRelationshipDelta {
  source_agent_id: string;
  target_agent_id: string;
  field: 'weight' | 'trust' | 'similarity';
  before: number;
  delta: number;
  after: number;
}

export interface InteractionTreePathStep {
  tree_id?: string | null;
  node_id: string;
  transition_id: string;
  outcome: string;
  probability: number;
  draw: number;
  evidence: {
    source: string;
    version: string;
    status: string;
    uncertainty: number;
    source_date?: string | null;
    evidence_id?: string | null;
  };
  factors?: InteractionTreeProbabilityFactorReceipt[];
  outgoing_probabilities?: InteractionTreeBranchReceipt[];
}

export interface InteractionTreeProbabilityFactorReceipt {
  factor_id: string;
  label: string;
  case_id: string;
  multiplier: number;
  inputs: Record<string, string | number | boolean>;
  evidence: InteractionTreePathStep['evidence'];
}

export interface InteractionTreeBranchReceipt {
  transition_id: string;
  outcome: string;
  base_probability: number;
  unnormalized_weight: number;
  probability: number;
  factors: InteractionTreeProbabilityFactorReceipt[];
  evidence: InteractionTreePathStep['evidence'];
}

export interface InteractionTreeTrace {
  tree_id: string;
  tree_version: string;
  outcome_node: string;
  outcome: string;
  path: InteractionTreePathStep[];
}

export interface InteractionListItem {
  event_id: string;
  tick: number;
  hour: number;
  weekday: number;
  rule_id: string;
  interaction_type: string;
  channel: InteractionChannel;
  initiator_id: string;
  target_id: string;
  place_id: string;
  relationship_type: string;
  probability: number;
  effect_count: number;
}

export interface InteractionEventDetail extends InteractionListItem {
  relationship_weight: number;
  trust: number;
  similarity: number;
  factors: EvaluatedInteractionFactor[];
  state_deltas: AppliedStateDelta[];
  relationship_deltas: AppliedRelationshipDelta[];
  interaction_tree: InteractionTreeTrace | null;
}

export interface InteractionFacets {
  agents: string[];
  interaction_types: string[];
  channels: InteractionChannel[];
  relationships: string[];
  places: string[];
}

export interface InteractionBreakdown {
  by_relationship: Record<string, number>;
  by_channel: Record<string, number>;
  by_place: Record<string, number>;
  by_counterparty: Record<string, number>;
}

export interface InteractionQuery {
  search: string;
  agent_id: string;
  direction: InteractionDirection;
  interaction_type: string;
  channel: string;
  relationship_type: string;
  place_id: string;
  page: number;
  page_size: number;
}

export interface InteractionPage {
  items: InteractionListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  facets: InteractionFacets;
  breakdown: InteractionBreakdown;
}

export interface InteractionsClient {
  list(runId: string, query: InteractionQuery): Promise<InteractionPage>;
  detail(runId: string, eventId: string): Promise<InteractionEventDetail>;
}

const emptyQuery = (): InteractionQuery => ({
  search: '',
  agent_id: '',
  direction: 'either',
  interaction_type: '',
  channel: '',
  relationship_type: '',
  place_id: '',
  page: 1,
  page_size: 50,
});

const emptyFacets = (): InteractionFacets => ({
  agents: [],
  interaction_types: [],
  channels: [],
  relationships: [],
  places: [],
});

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const label = (value: string): string =>
  value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const percentage = (value: number): string => `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;

const decimal = (value: number): string =>
  value.toLocaleString('en', { maximumFractionDigits: 4, minimumFractionDigits: 0 });

const hourLabel = (value: number): string => {
  const hours = Math.floor(value) % 24;
  const minutes = Math.round((value - Math.floor(value)) * 60);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isListItem = (value: unknown): value is InteractionListItem =>
  isRecord(value) &&
  typeof value.event_id === 'string' &&
  typeof value.tick === 'number' &&
  typeof value.initiator_id === 'string' &&
  typeof value.target_id === 'string' &&
  typeof value.interaction_type === 'string' &&
  typeof value.probability === 'number';

const isPage = (value: unknown): value is InteractionPage =>
  isRecord(value) &&
  Array.isArray(value.items) &&
  value.items.every(isListItem) &&
  typeof value.total === 'number' &&
  isRecord(value.facets) &&
  isRecord(value.breakdown);

const isDetail = (value: unknown): value is InteractionEventDetail =>
  isListItem(value) &&
  Array.isArray((value as InteractionEventDetail).factors) &&
  Array.isArray((value as InteractionEventDetail).state_deltas) &&
  Array.isArray((value as InteractionEventDetail).relationship_deltas);

async function requestJson(url: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : null;
    throw new Error(detail ?? `Interaction request failed (${response.status})`);
  }
  return body;
}

export function createInteractionsHttpClient(
  basePath = '/api/simulation/runs',
): InteractionsClient {
  return {
    list: async (runId, query) => {
      const parameters = new URLSearchParams({
        search: query.search,
        direction: query.direction,
        page: String(query.page),
        page_size: String(query.page_size),
      });
      for (const [key, value] of Object.entries({
        agent_id: query.agent_id,
        interaction_type: query.interaction_type,
        channel: query.channel,
        relationship_type: query.relationship_type,
        place_id: query.place_id,
      })) {
        if (value) parameters.set(key, value);
      }
      const body = await requestJson(
        `${basePath}/${encodeURIComponent(runId)}/interactions?${parameters}`,
      );
      if (!isPage(body)) throw new Error('The server returned an invalid interaction list.');
      return body;
    },
    detail: async (runId, eventId) => {
      const body = await requestJson(
        `${basePath}/${encodeURIComponent(runId)}/interactions/${encodeURIComponent(eventId)}`,
      );
      if (!isDetail(body)) throw new Error('The server returned an invalid interaction detail.');
      return body;
    },
  };
}

export class InteractionsView {
  private query = emptyQuery();
  private page: InteractionPage | null = null;
  private detail: InteractionEventDetail | null = null;
  private error = '';
  private loading = true;
  private requestSequence = 0;
  private searchTimer: number | null = null;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: InteractionsClient,
    private readonly runId: string,
  ) {
    this.host.classList.add('interactions-view');
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('input', this.onInput);
    this.render();
    void this.load();
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('input', this.onInput);
    if (this.searchTimer !== null) window.clearTimeout(this.searchTimer);
  }

  private async load(): Promise<void> {
    const sequence = ++this.requestSequence;
    this.loading = true;
    this.error = '';
    this.render();
    try {
      const page = await this.client.list(this.runId, { ...this.query });
      if (sequence !== this.requestSequence) return;
      this.page = page;
    } catch (error) {
      if (sequence !== this.requestSequence) return;
      this.error = error instanceof Error ? error.message : 'Could not load interactions.';
    } finally {
      if (sequence === this.requestSequence) {
        this.loading = false;
        this.render();
      }
    }
  }

  private async open(eventId: string): Promise<void> {
    this.loading = true;
    this.error = '';
    this.render();
    try {
      this.detail = await this.client.detail(this.runId, eventId);
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Could not load interaction detail.';
    } finally {
      this.loading = false;
      this.render();
    }
  }

  private render(): void {
    if (this.detail) {
      this.host.innerHTML = this.renderDetail(this.detail);
      return;
    }
    const facets = this.page?.facets ?? emptyFacets();
    this.host.innerHTML = `
      <header class="interactions-heading">
        <div><span class="small-label">RECORDED EVENTS</span><h2>Interactions</h2><p>Inspect who acted on whom, the conditions that allowed it, and the state changes delivered to the next tick.</p></div>
        <strong>${this.page?.total.toLocaleString('en') ?? '—'} events</strong>
      </header>
      ${this.renderFilters(facets)}
      ${this.renderBody()}
    `;
  }

  private renderFilters(facets: InteractionFacets): string {
    return `<section class="interaction-filters" aria-label="Interaction filters">
      <label class="interaction-search">Search<input type="search" data-interaction-filter="search" value="${escapeHtml(this.query.search)}" placeholder="Agent, action, place…"></label>
      <label>Agent<select data-interaction-filter="agent_id">${this.options(facets.agents.map((agentId) => [agentId, agentId]), this.query.agent_id, 'All agents')}</select></label>
      <label>Direction<select data-interaction-filter="direction"${this.query.agent_id ? '' : ' disabled'}>${this.options(
        [
          ['either', 'Sent or received'],
          ['initiator', 'Sent'],
          ['target', 'Received'],
        ],
        this.query.direction,
        '',
      )}</select></label>
      <label>Action<select data-interaction-filter="interaction_type">${this.options(
        facets.interaction_types.map((value) => [value, label(value)]),
        this.query.interaction_type,
        'All actions',
      )}</select></label>
      <label>Relationship<select data-interaction-filter="relationship_type">${this.options(
        facets.relationships.map((value) => [value, label(value)]),
        this.query.relationship_type,
        'All relationships',
      )}</select></label>
      <label>Channel<select data-interaction-filter="channel">${this.options(
        facets.channels.map((value) => [value, label(value)]),
        this.query.channel,
        'All channels',
      )}</select></label>
      <label>Place<select data-interaction-filter="place_id">${this.options(
        facets.places.map((value) => [value, label(value)]),
        this.query.place_id,
        'All places',
      )}</select></label>
      <button type="button" class="ghost-btn" data-interaction-action="reset">Reset filters</button>
    </section>`;
  }

  private options(entries: [string, string][], selected: string, emptyLabel: string): string {
    const empty = emptyLabel ? `<option value="">${escapeHtml(emptyLabel)}</option>` : '';
    return `${empty}${entries
      .map(
        ([value, text]) =>
          `<option value="${escapeHtml(value)}"${value === selected ? ' selected' : ''}>${escapeHtml(text)}</option>`,
      )
      .join('')}`;
  }

  private renderBody(): string {
    if (this.loading && !this.page) {
      return '<div class="interaction-state" role="status">Loading recorded interactions…</div>';
    }
    if (this.error) {
      return `<div class="interaction-state interaction-error" role="alert"><strong>${escapeHtml(this.error)}</strong><button type="button" class="ghost-btn" data-interaction-action="retry">Retry</button></div>`;
    }
    if (!this.page || this.page.items.length === 0) {
      return '<div class="interaction-state">No recorded interactions match these filters.</div>';
    }
    return `${this.renderBreakdowns(this.page.breakdown)}
      <div class="interaction-column-labels"><span>Time</span><span>Directed event</span><span>Context</span><span>Probability</span><span>Effects</span><span></span></div>
      <section class="interaction-list" aria-label="Recorded interactions">
        ${this.page.items.map((event) => this.renderRow(event)).join('')}
      </section>
      <footer class="interaction-pagination"><span>Page ${this.page.page} of ${Math.max(1, this.page.pages)}</span><button type="button" class="ghost-btn" data-interaction-action="previous"${this.page.page <= 1 ? ' disabled' : ''}>Previous</button><button type="button" class="ghost-btn" data-interaction-action="next"${this.page.page >= this.page.pages ? ' disabled' : ''}>Next</button></footer>`;
  }

  private renderBreakdowns(breakdown: InteractionBreakdown): string {
    const groups: [string, Record<string, number>][] = [
      ['Relationship', breakdown.by_relationship],
      ['Channel', breakdown.by_channel],
      ['Place', breakdown.by_place],
    ];
    if (this.query.agent_id) groups.push(['Counterparty', breakdown.by_counterparty]);
    return `<section class="interaction-breakdowns" aria-label="Interaction breakdowns">${groups
      .map(
        ([title, values]) =>
          `<article><span>${escapeHtml(title)}</span><div>${
            Object.entries(values)
              .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
              .slice(0, 5)
              .map(([name, count]) => `<b>${escapeHtml(label(name))}<i>${count}</i></b>`)
              .join('') || '<small>No events</small>'
          }</div></article>`,
      )
      .join('')}</section>`;
  }

  private renderRow(event: InteractionListItem): string {
    return `<button type="button" class="interaction-row" data-interaction-action="open" data-event-id="${escapeHtml(event.event_id)}" aria-label="Open ${escapeHtml(event.initiator_id)} to ${escapeHtml(event.target_id)} ${escapeHtml(label(event.interaction_type))} interaction">
      <span><strong>Tick ${event.tick}</strong><small>${hourLabel(event.hour)} · day ${event.weekday + 1}</small></span>
      <span class="interaction-direction"><strong>${escapeHtml(event.initiator_id)} <i>→</i> ${escapeHtml(event.target_id)}</strong><small>${escapeHtml(label(event.interaction_type))} · ${escapeHtml(label(event.channel))}</small></span>
      <span><strong>${escapeHtml(label(event.place_id))}</strong><small>${escapeHtml(label(event.relationship_type))}</small></span>
      <span><strong>${percentage(event.probability)}</strong><small>recorded formula</small></span>
      <span><strong>${event.effect_count}</strong><small>state changes</small></span><b>›</b>
    </button>`;
  }

  private renderDetail(event: InteractionEventDetail): string {
    return `<button type="button" class="interaction-back" data-interaction-action="back">← Back to interactions</button>
      <header class="interaction-detail-heading"><div><span class="small-label">${escapeHtml(label(event.channel))} · TICK ${event.tick}</span><h2>${escapeHtml(event.initiator_id)} <i>→</i> ${escapeHtml(event.target_id)}</h2><p>${escapeHtml(label(event.interaction_type))} at ${escapeHtml(label(event.place_id))}, ${hourLabel(event.hour)}</p></div><strong>${percentage(event.probability)}</strong></header>
      <section class="interaction-facts" aria-label="Interaction context">
        ${this.fact('Relationship', label(event.relationship_type))}${this.fact('Weight', decimal(event.relationship_weight))}${this.fact('Trust', decimal(event.trust))}${this.fact('Similarity', decimal(event.similarity))}${this.fact('Rule', event.rule_id)}
      </section>
      <section class="interaction-detail-section" aria-labelledby="interaction-formula-heading"><header><span class="small-label">PROBABILITY</span><h3 id="interaction-formula-heading">Factor formula</h3></header><div class="interaction-equation">${event.factors.map(({ factor }) => `P(${escapeHtml(factor.label)})`).join('<i>×</i>')}<b>= ${percentage(event.probability)}</b></div><div class="interaction-factor-list">${event.factors.map((factor) => this.renderFactor(factor)).join('')}</div></section>
      ${this.renderTreePath(event)}
      <section class="interaction-detail-section" aria-labelledby="interaction-effects-heading"><header><span class="small-label">NEXT TICK</span><h3 id="interaction-effects-heading">Applied effects</h3></header>${this.renderEffects(event)}</section>`;
  }

  private fact(name: string, value: string): string {
    return `<article><span>${escapeHtml(name)}</span><strong>${escapeHtml(value)}</strong></article>`;
  }

  private renderFactor(item: EvaluatedInteractionFactor): string {
    const { factor } = item;
    return `<article><div><span>${escapeHtml(label(item.kind))}</span><strong>${escapeHtml(factor.label)}</strong></div><b>${percentage(factor.value)}</b><p>${escapeHtml(factor.provenance.source)} · ${escapeHtml(factor.provenance.version)}</p><small>${escapeHtml(label(factor.provenance.status))} · uncertainty ${decimal(factor.provenance.uncertainty)}</small></article>`;
  }

  private renderEffects(event: InteractionEventDetail): string {
    const stateEffects = event.state_deltas.map(
      (effect) =>
        `<article><span>Agent state</span><strong>${escapeHtml(effect.agent_id)} · ${escapeHtml(label(effect.state))}</strong><p>${decimal(effect.before)} <i>→</i> ${decimal(effect.after)} <small>(${effect.delta >= 0 ? '+' : ''}${decimal(effect.delta)})</small></p></article>`,
    );
    const relationshipEffects = event.relationship_deltas.map(
      (effect) =>
        `<article><span>Directed relationship</span><strong>${escapeHtml(effect.source_agent_id)} → ${escapeHtml(effect.target_agent_id)} · ${escapeHtml(label(effect.field))}</strong><p>${decimal(effect.before)} <i>→</i> ${decimal(effect.after)} <small>(${effect.delta >= 0 ? '+' : ''}${decimal(effect.delta)})</small></p></article>`,
    );
    const effects = [...stateEffects, ...relationshipEffects];
    return `<div class="interaction-effect-list">${effects.join('') || '<p class="interaction-no-effects">This event recorded no state change.</p>'}</div>`;
  }

  private renderTreePath(event: InteractionEventDetail): string {
    const trace = event.interaction_tree;
    if (!trace) return '';
    const path = trace.path
      .map((step) => {
        const factors = (step.factors ?? [])
          .map((factor) => {
            const inputs = Object.entries(factor.inputs)
              .map(([input, value]) => `${label(input.replaceAll('.', ' '))} = ${String(value)}`)
              .join(' · ');
            return `<li><strong>${escapeHtml(factor.label)} ×${decimal(factor.multiplier)}</strong><span>${escapeHtml(inputs)}</span><small>${escapeHtml(factor.evidence.source)} · ${escapeHtml(factor.evidence.version)}</small></li>`;
          })
          .join('');
        const branches = (step.outgoing_probabilities ?? [])
          .map(
            (branch) =>
              `<li${branch.transition_id === step.transition_id ? ' class="is-selected"' : ''}><strong>${escapeHtml(label(branch.outcome))}</strong><span>${percentage(branch.probability)}</span><small>base ${percentage(branch.base_probability)} · weight ${decimal(branch.unnormalized_weight)}</small></li>`,
          )
          .join('');
        return `<article>
          <span>${escapeHtml(label(step.node_id))} → ${escapeHtml(label(step.outcome))}</span>
          <strong>${escapeHtml(step.transition_id)} · ${percentage(step.probability)}</strong>
          <p>${escapeHtml(step.evidence.source)} · ${escapeHtml(step.evidence.version)}</p>
          <small>${escapeHtml(label(step.evidence.status))} · uncertainty ${decimal(step.evidence.uncertainty)}</small>
          ${branches ? `<h4>Evaluated branches</h4><ul>${branches}</ul>` : ''}
          ${factors ? `<h4>Selected factor inputs</h4><ul>${factors}</ul>` : ''}
        </article>`;
      })
      .join('');
    return `<section class="interaction-detail-section" aria-labelledby="interaction-tree-path-heading">
      <header><span class="small-label">DECISION PATH</span><h3 id="interaction-tree-path-heading">${escapeHtml(label(trace.tree_id))}</h3></header>
      <p>Outcome: <strong>${escapeHtml(label(trace.outcome))}</strong></p>
      <div class="interaction-factor-list">${path}</div>
    </section>`;
  }

  private readonly onClick = (event: MouseEvent): void => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-interaction-action]');
    if (!target) return;
    const action = target.dataset.interactionAction;
    if (action === 'open' && target.dataset.eventId) void this.open(target.dataset.eventId);
    if (action === 'back') {
      this.detail = null;
      this.error = '';
      this.render();
    }
    if (action === 'retry') void this.load();
    if (action === 'reset') {
      this.query = emptyQuery();
      void this.load();
    }
    if (action === 'previous' && this.query.page > 1) {
      this.query.page -= 1;
      void this.load();
    }
    if (action === 'next' && this.page && this.query.page < this.page.pages) {
      this.query.page += 1;
      void this.load();
    }
  };

  private readonly onChange = (event: Event): void => {
    const target = (event.target as HTMLElement).closest<HTMLSelectElement>(
      '[data-interaction-filter]',
    );
    if (!target) return;
    const key = target.dataset.interactionFilter as keyof InteractionQuery;
    if (key === 'direction') this.query.direction = target.value as InteractionDirection;
    else if (key !== 'search' && key !== 'page' && key !== 'page_size')
      this.query[key] = target.value;
    if (key === 'agent_id' && !target.value) this.query.direction = 'either';
    this.query.page = 1;
    void this.load();
  };

  private readonly onInput = (event: Event): void => {
    const input = (event.target as HTMLElement).closest<HTMLInputElement>(
      '[data-interaction-filter="search"]',
    );
    if (!input) return;
    this.query.search = input.value;
    this.query.page = 1;
    if (this.searchTimer !== null) window.clearTimeout(this.searchTimer);
    this.searchTimer = window.setTimeout(() => void this.load(), 180);
  };
}
