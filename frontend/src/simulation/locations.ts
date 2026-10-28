import './locations.css';

export type LocationLevel =
  'country' | 'region' | 'state' | 'city' | 'district' | 'building' | 'room';

export interface LocationEvidence {
  source_title: string;
  source_version: string;
  source_date: string;
  licence: string;
  evidence_id: string;
  status: 'measured' | 'user_defined';
  uncertainty: number;
}

export interface LocationDecisionTreeAvailability {
  tree_id: string;
  tree_name: string;
  available: boolean;
  required_place_kinds: string[];
  reason: string | null;
}

export interface LocationPlaceSummary {
  id: string;
  name: string;
  level: LocationLevel;
  parent_id: string | null;
  child_ids: string[];
  current_agent_count: number;
  accepts_arrivals: boolean;
  allows_in_person: boolean;
  capacity: number | null;
  state: Record<string, number>;
  state_source?: 'rust_numeric_core' | 'location_registry';
  runtime_place_id?: string | null;
  runtime_place_kind?: string | null;
  evidence: LocationEvidence | null;
  decision_trees: LocationDecisionTreeAvailability[];
}

export interface LocationAgentSummary {
  agent_id: string;
  current_location_id: string;
}

export interface LocationHistoryRecord {
  tick: number;
  agent_id: string;
  from_location_id: string;
  to_location_id: string;
  route_location_ids: string[];
}

export interface LocationRunSnapshot {
  run_id: string;
  tick: number;
  root_location_ids: string[];
  places: LocationPlaceSummary[];
  agents: LocationAgentSummary[];
}

export interface LocationAgentDetail {
  agent_id: string;
  current_location: LocationPlaceSummary;
  ancestry: LocationPlaceSummary[];
  history: LocationHistoryRecord[];
  co_located_agents: LocationAgentSummary[];
  elsewhere_agents: LocationAgentSummary[];
  effective_place_state: Record<string, number>;
}

export interface LocationsClient {
  snapshot(): Promise<LocationRunSnapshot>;
  agentDetail(agentId: string): Promise<LocationAgentDetail>;
}

export interface LocationsViewOptions {
  initialPlaceId?: string;
  initialAgentId?: string;
}

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const titleCase = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isNumberRecord = (value: unknown): value is Record<string, number> =>
  isRecord(value) && Object.values(value).every((item) => typeof item === 'number');

function isEvidence(value: unknown): value is LocationEvidence {
  if (!isRecord(value)) return false;
  return (
    typeof value.source_title === 'string' &&
    typeof value.source_version === 'string' &&
    typeof value.source_date === 'string' &&
    typeof value.licence === 'string' &&
    typeof value.evidence_id === 'string' &&
    (value.status === 'measured' || value.status === 'user_defined') &&
    typeof value.uncertainty === 'number'
  );
}

function isDecisionTreeAvailability(value: unknown): value is LocationDecisionTreeAvailability {
  if (!isRecord(value)) return false;
  return (
    typeof value.tree_id === 'string' &&
    typeof value.tree_name === 'string' &&
    typeof value.available === 'boolean' &&
    Array.isArray(value.required_place_kinds) &&
    value.required_place_kinds.every((item) => typeof item === 'string') &&
    (value.reason === null || typeof value.reason === 'string')
  );
}

function isPlace(value: unknown): value is LocationPlaceSummary {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.level === 'string' &&
    (value.parent_id === null || typeof value.parent_id === 'string') &&
    Array.isArray(value.child_ids) &&
    value.child_ids.every((item) => typeof item === 'string') &&
    typeof value.current_agent_count === 'number' &&
    typeof value.accepts_arrivals === 'boolean' &&
    typeof value.allows_in_person === 'boolean' &&
    (value.capacity === null || typeof value.capacity === 'number') &&
    isNumberRecord(value.state) &&
    (value.state_source === undefined ||
      value.state_source === 'rust_numeric_core' ||
      value.state_source === 'location_registry') &&
    (value.runtime_place_id === undefined ||
      value.runtime_place_id === null ||
      typeof value.runtime_place_id === 'string') &&
    (value.runtime_place_kind === undefined ||
      value.runtime_place_kind === null ||
      typeof value.runtime_place_kind === 'string') &&
    (value.evidence === null || isEvidence(value.evidence)) &&
    Array.isArray(value.decision_trees) &&
    value.decision_trees.every(isDecisionTreeAvailability)
  );
}

function isAgentSummary(value: unknown): value is LocationAgentSummary {
  if (!isRecord(value)) return false;
  return (
    typeof value.agent_id === 'string' &&
    typeof value.current_location_id === 'string'
  );
}

function isHistory(value: unknown): value is LocationHistoryRecord {
  if (!isRecord(value)) return false;
  return (
    typeof value.tick === 'number' &&
    typeof value.agent_id === 'string' &&
    typeof value.from_location_id === 'string' &&
    typeof value.to_location_id === 'string' &&
    Array.isArray(value.route_location_ids) &&
    value.route_location_ids.every((item) => typeof item === 'string')
  );
}

function isSnapshot(value: unknown): value is LocationRunSnapshot {
  if (!isRecord(value)) return false;
  return (
    typeof value.run_id === 'string' &&
    typeof value.tick === 'number' &&
    Array.isArray(value.root_location_ids) &&
    value.root_location_ids.every((item) => typeof item === 'string') &&
    Array.isArray(value.places) &&
    value.places.every(isPlace) &&
    Array.isArray(value.agents) &&
    value.agents.every(isAgentSummary)
  );
}

function isAgentDetail(value: unknown): value is LocationAgentDetail {
  if (!isRecord(value)) return false;
  return (
    typeof value.agent_id === 'string' &&
    isPlace(value.current_location) &&
    Array.isArray(value.ancestry) &&
    value.ancestry.every(isPlace) &&
    Array.isArray(value.history) &&
    value.history.every(isHistory) &&
    Array.isArray(value.co_located_agents) &&
    value.co_located_agents.every(isAgentSummary) &&
    Array.isArray(value.elsewhere_agents) &&
    value.elsewhere_agents.every(isAgentSummary) &&
    isNumberRecord(value.effective_place_state)
  );
}

async function request<T>(url: string, validate: (value: unknown) => value is T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : null;
    throw new Error(detail ?? `Locations request failed (${response.status})`);
  }
  if (!validate(body)) throw new Error('The server returned an invalid locations contract.');
  return body;
}

export function createLocationsHttpClient(runId: string): LocationsClient {
  const basePath = `/api/simulation/runs/${encodeURIComponent(runId)}/locations`;
  return {
    snapshot: () => request(basePath, isSnapshot),
    agentDetail: (agentId) =>
      request(`${basePath}/agents/${encodeURIComponent(agentId)}`, isAgentDetail),
  };
}

function formatStateValue(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString('en');
  return value.toLocaleString('en', { maximumFractionDigits: 4 });
}

function stateRows(state: Record<string, number>, emptyMessage: string): string {
  const entries = Object.entries(state).sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) return `<p class="locations-empty-copy">${escapeHtml(emptyMessage)}</p>`;
  return `<dl class="locations-state-list">${entries
    .map(
      ([name, value]) =>
        `<div><dt>${escapeHtml(titleCase(name))}</dt><dd>${escapeHtml(formatStateValue(value))}</dd></div>`,
    )
    .join('')}</dl>`;
}

function evidenceMarkup(evidence: LocationEvidence | null): string {
  if (!evidence) {
    return '<p class="locations-empty-copy">No measured or user-confirmed place profile is attached.</p>';
  }
  return `<dl class="locations-evidence"><div><dt>Source</dt><dd>${escapeHtml(evidence.source_title)}</dd></div><div><dt>Version</dt><dd>${escapeHtml(evidence.source_version)}</dd></div><div><dt>Date</dt><dd>${escapeHtml(evidence.source_date)}</dd></div><div><dt>Status</dt><dd>${escapeHtml(titleCase(evidence.status))}</dd></div><div><dt>Uncertainty</dt><dd>${escapeHtml(evidence.uncertainty.toLocaleString('en', { style: 'percent' }))}</dd></div><div><dt>Licence</dt><dd>${escapeHtml(evidence.licence)}</dd></div></dl>`;
}

function decisionTreeMarkup(decisions: LocationDecisionTreeAvailability[]): string {
  if (!decisions.length) {
    return '<p class="locations-empty-copy">No place-specific decision trees are registered here.</p>';
  }
  return `<div class="locations-decision-list">${decisions
    .map(
      (decision) =>
        `<article class="${decision.available ? 'is-available' : 'is-unavailable'}"><span>${decision.available ? 'Available' : 'Unavailable'}</span><div><strong>${escapeHtml(decision.tree_name)}</strong><small>${decision.available ? `Runs at ${decision.required_place_kinds.map(titleCase).join(' / ')}` : escapeHtml(decision.reason ?? 'Unavailable at this place')}</small></div></article>`,
    )
    .join('')}</div>`;
}

export class LocationsView {
  private snapshotValue: LocationRunSnapshot | null = null;
  private selectedPlaceId: string | null = null;
  private selectedAgent: LocationAgentDetail | null = null;
  private expanded = new Set<string>();
  private requestVersion = 0;
  private disposed = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: LocationsClient,
    private readonly options: LocationsViewOptions = {},
  ) {
    this.host.classList.add('locations-view');
    this.host.addEventListener('click', this.onClick);
    this.renderStatus('Loading recorded locations…');
    void this.load();
  }

  dispose(): void {
    this.disposed = true;
    this.requestVersion += 1;
    this.host.removeEventListener('click', this.onClick);
  }

  refresh(): Promise<void> {
    return this.load();
  }

  private async load(): Promise<void> {
    const version = ++this.requestVersion;
    this.renderStatus('Loading recorded locations…');
    try {
      const snapshot = await this.client.snapshot();
      if (this.disposed || version !== this.requestVersion) return;
      this.snapshotValue = snapshot;
      this.selectedPlaceId =
        (this.options.initialPlaceId &&
        snapshot.places.some((place) => place.id === this.options.initialPlaceId)
          ? this.options.initialPlaceId
          : snapshot.root_location_ids[0]) ??
        snapshot.places[0]?.id ??
        null;
      snapshot.root_location_ids.forEach((placeId) => this.expanded.add(placeId));
      if (this.options.initialAgentId) {
        await this.loadAgent(this.options.initialAgentId, version);
        return;
      }
      this.render();
    } catch (error) {
      if (this.disposed || version !== this.requestVersion) return;
      this.renderError(error);
    }
  }

  private async loadAgent(agentId: string, parentVersion?: number): Promise<void> {
    const version = parentVersion ?? ++this.requestVersion;
    this.host.setAttribute('aria-busy', 'true');
    try {
      const detail = await this.client.agentDetail(agentId);
      if (this.disposed || version !== this.requestVersion) return;
      this.selectedAgent = detail;
      this.selectedPlaceId = detail.current_location.id;
      detail.ancestry.forEach((place) => this.expanded.add(place.id));
      this.render();
    } catch (error) {
      if (this.disposed || version !== this.requestVersion) return;
      this.renderError(error);
    } finally {
      if (!this.disposed && version === this.requestVersion) {
        this.host.removeAttribute('aria-busy');
      }
    }
  }

  private renderStatus(message: string): void {
    this.host.innerHTML = `<div class="locations-status" role="status">${escapeHtml(message)}</div>`;
  }

  private renderError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.host.innerHTML = `<div class="locations-status locations-error" role="alert"><strong>Locations unavailable</strong><span>${escapeHtml(message)}</span><button type="button" class="button secondary" data-location-action="retry">Retry</button></div>`;
  }

  private render(): void {
    const snapshot = this.snapshotValue;
    if (!snapshot) return;
    const places = new Map(snapshot.places.map((place) => [place.id, place]));
    const selectedPlace = this.selectedPlaceId ? places.get(this.selectedPlaceId) : null;
    this.host.innerHTML = `
      <header class="locations-heading">
        <div><span class="small-label">RECORDED AT TICK ${snapshot.tick.toLocaleString('en')}</span><h2>Locations</h2><p>Inspect the place hierarchy, current occupancy, and recorded travel.</p></div>
        <div class="locations-counts"><strong>${snapshot.places.length.toLocaleString('en')}</strong><span>places</span><strong>${snapshot.agents.length.toLocaleString('en')}</strong><span>agents</span></div>
      </header>
      <div class="locations-layout">
        <section class="locations-panel locations-tree-panel" aria-label="Place hierarchy">
          <div class="locations-panel-heading"><div><span class="small-label">PLACE TREE</span><h3>Country to room</h3></div></div>
          <div class="locations-tree" role="tree" aria-label="Location hierarchy">
            ${snapshot.root_location_ids.map((placeId) => this.renderTreeBranch(placeId, 0, places)).join('')}
          </div>
        </section>
        ${this.selectedAgent ? this.renderAgentDetail(this.selectedAgent, places) : this.renderPlaceDetail(selectedPlace, snapshot)}
      </div>`;
  }

  private renderTreeBranch(
    placeId: string,
    depth: number,
    places: Map<string, LocationPlaceSummary>,
  ): string {
    const place = places.get(placeId);
    if (!place) return '';
    const hasChildren = place.child_ids.length > 0;
    const isExpanded = this.expanded.has(place.id);
    const isSelected = place.id === this.selectedPlaceId;
    const children =
      hasChildren && isExpanded
        ? `<div role="group">${place.child_ids
            .map((childId) => this.renderTreeBranch(childId, depth + 1, places))
            .join('')}</div>`
        : '';
    return `<div class="locations-tree-branch">
      <div class="locations-tree-row${isSelected ? ' is-selected' : ''}" role="treeitem" aria-level="${depth + 1}"${hasChildren ? ` aria-expanded="${isExpanded}"` : ''}>
        <button type="button" class="locations-tree-toggle" data-location-toggle="${escapeHtml(place.id)}" aria-label="${hasChildren ? `${isExpanded ? 'Collapse' : 'Expand'} ${place.name}` : `${place.name} has no child locations`}" ${hasChildren ? '' : 'disabled'} style="--location-depth:${depth}">${hasChildren ? (isExpanded ? '−' : '+') : '·'}</button>
        <button type="button" class="locations-tree-select" data-location-place="${escapeHtml(place.id)}" aria-pressed="${isSelected}" style="--location-depth:${depth}"><span><strong>${escapeHtml(place.name)}</strong><small>${escapeHtml(place.level)}</small></span><b>${place.current_agent_count.toLocaleString('en')}</b></button>
      </div>${children}
    </div>`;
  }

  private renderPlaceDetail(
    place: LocationPlaceSummary | null | undefined,
    snapshot: LocationRunSnapshot,
  ): string {
    if (!place) {
      return '<section class="locations-panel locations-detail-panel"><div class="locations-status">Select a place.</div></section>';
    }
    const occupants = snapshot.agents.filter((agent) => agent.current_location_id === place.id);
    const liveState = place.state_source === 'rust_numeric_core';
    const stateTitle = liveState ? 'Live Rust place state' : 'Place state';
    const stateReceipt = liveState
      ? `${place.runtime_place_kind ?? 'place'} · ${place.runtime_place_id ?? place.id}`
      : `${Object.keys(place.state).length} registry values`;
    return `<section class="locations-panel locations-detail-panel" aria-label="${escapeHtml(place.name)} location detail">
      <div class="locations-panel-heading"><div><span class="small-label">${escapeHtml(place.level.toUpperCase())}</span><h3>${escapeHtml(place.name)}</h3></div><span class="locations-status-pill ${place.accepts_arrivals ? 'is-open' : 'is-closed'}">${place.accepts_arrivals ? 'Arrivals open' : 'Arrivals blocked'}</span></div>
      <div class="locations-facts"><div><small>Current agents</small><strong>${place.current_agent_count.toLocaleString('en')}</strong></div><div><small>Capacity</small><strong>${place.capacity === null ? 'Unspecified' : place.capacity.toLocaleString('en')}</strong></div><div><small>In-person contact</small><strong>${place.allows_in_person ? 'Allowed when co-located' : 'Blocked'}</strong></div></div>
      <div class="locations-detail-scroll">
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>${stateTitle}</h4><span>${escapeHtml(stateReceipt)}</span></div>${stateRows(place.state, 'No state values are recorded directly at this place.')}</section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Place profile evidence</h4><span>${place.evidence ? escapeHtml(place.evidence.status) : 'unknown'}</span></div>${evidenceMarkup(place.evidence)}</section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Decision trees here</h4><span>${place.decision_trees.filter((item) => item.available).length} available</span></div>${decisionTreeMarkup(place.decision_trees)}</section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Agents here</h4><span>${occupants.length}</span></div>
          ${occupants.length ? `<div class="locations-agent-list">${occupants.map((agent) => `<button type="button" data-location-agent="${escapeHtml(agent.agent_id)}"><span><strong>${escapeHtml(agent.agent_id)}</strong><small>Synthetic agent ID</small></span><b>Open</b></button>`).join('')}</div>` : '<p class="locations-empty-copy">No agent currently occupies this exact location.</p>'}
        </section>
      </div>
    </section>`;
  }

  private renderAgentDetail(
    detail: LocationAgentDetail,
    places: Map<string, LocationPlaceSummary>,
  ): string {
    const placeName = (placeId: string): string => places.get(placeId)?.name ?? placeId;
    const history = [...detail.history].reverse();
    const stateTitle =
      detail.current_location.state_source === 'rust_numeric_core'
        ? 'Live Rust state at current place'
        : 'Effective place state';
    return `<section class="locations-panel locations-detail-panel" aria-label="${escapeHtml(detail.agent_id)} location detail">
      <button type="button" class="locations-back" data-location-action="back-to-place">← Back to ${escapeHtml(detail.current_location.name)}</button>
      <div class="locations-panel-heading"><div><span class="small-label">SYNTHETIC AGENT ID</span><h3>${escapeHtml(detail.agent_id)}</h3></div><span class="locations-status-pill is-open">${escapeHtml(titleCase(detail.current_location.level))}</span></div>
      <nav class="locations-breadcrumbs" aria-label="Current location path">${detail.ancestry.map((place, index) => `${index ? '<i>›</i>' : ''}<button type="button" data-location-place="${escapeHtml(place.id)}">${escapeHtml(place.name)}</button>`).join('')}</nav>
      <div class="locations-detail-scroll">
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>${stateTitle}</h4><span>Most specific recorded value wins</span></div>${stateRows(detail.effective_place_state, 'No place state is recorded for this location path.')}</section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Decision availability</h4><span>${detail.current_location.decision_trees.filter((item) => item.available).length} available here</span></div>${decisionTreeMarkup(detail.current_location.decision_trees)}</section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Co-located agents</h4><span>${detail.co_located_agents.length}</span></div>
          ${detail.co_located_agents.length ? `<div class="locations-agent-list">${detail.co_located_agents.map((agent) => `<button type="button" data-location-agent="${escapeHtml(agent.agent_id)}"><span><strong>${escapeHtml(agent.agent_id)}</strong><small>${escapeHtml(agent.current_location_id)}</small></span><b>Open</b></button>`).join('')}</div>` : '<p class="locations-empty-copy">No other agents are available for face-to-face interaction here.</p>'}
        </section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Elsewhere</h4><span>${detail.elsewhere_agents.length} unavailable in person</span></div>
          ${detail.elsewhere_agents.length ? `<div class="locations-agent-list locations-elsewhere-list">${detail.elsewhere_agents.map((agent) => `<button type="button" data-location-agent="${escapeHtml(agent.agent_id)}"><span><strong>${escapeHtml(agent.agent_id)}</strong><small>${escapeHtml(placeName(agent.current_location_id))}</small></span><b>Elsewhere</b></button>`).join('')}</div>` : '<p class="locations-empty-copy">Every other recorded agent is currently co-located.</p>'}
        </section>
        <section class="locations-subsection"><div class="locations-subsection-heading"><h4>Location history</h4><span>${history.length} moves</span></div>
          ${history.length ? `<ol class="locations-history">${history.map((record) => `<li><time>Tick ${record.tick.toLocaleString('en')}</time><div><strong>${escapeHtml(placeName(record.from_location_id))} → ${escapeHtml(placeName(record.to_location_id))}</strong><small>${record.route_location_ids.map(placeName).map(escapeHtml).join(' › ')}</small></div></li>`).join('')}</ol>` : '<p class="locations-empty-copy">No movement has been recorded for this agent.</p>'}
        </section>
      </div>
    </section>`;
  }

  private readonly onClick = (event: Event): void => {
    const target = event.target as HTMLElement;
    const action = target.closest<HTMLElement>('[data-location-action]')?.dataset.locationAction;
    if (action === 'retry') {
      void this.load();
      return;
    }
    if (action === 'back-to-place') {
      this.selectedAgent = null;
      this.render();
      return;
    }
    const toggle = target.closest<HTMLElement>('[data-location-toggle]')?.dataset.locationToggle;
    if (toggle) {
      if (this.expanded.has(toggle)) this.expanded.delete(toggle);
      else this.expanded.add(toggle);
      this.render();
      return;
    }
    const placeId = target.closest<HTMLElement>('[data-location-place]')?.dataset.locationPlace;
    if (placeId) {
      this.selectedPlaceId = placeId;
      this.selectedAgent = null;
      this.expanded.add(placeId);
      this.render();
      return;
    }
    const agentId = target.closest<HTMLElement>('[data-location-agent]')?.dataset.locationAgent;
    if (agentId) void this.loadAgent(agentId);
  };
}

export function mountLocationsView(
  host: HTMLElement,
  client: LocationsClient,
  options: LocationsViewOptions = {},
): LocationsView {
  return new LocationsView(host, client, options);
}
