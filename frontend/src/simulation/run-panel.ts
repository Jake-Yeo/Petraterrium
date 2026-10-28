import './run-panel.css';
import { createInteractionsHttpClient, InteractionsView } from './interactions';
import { createLocationsHttpClient, LocationsView } from './locations';
import {
  GlobalDemoSummaryView,
  isGlobalDemoSummaryData,
  type GlobalDemoSummaryData,
} from './global-demo-summary';
import {
  SimulationLaunchEvidencePreview,
  type SimulationRunPreviewClient,
} from './run-launch-preview';
import {
  runEvidenceMarkup,
  type RunEvidenceSummary,
  type RunEvidenceWarning,
} from './run-evidence';

export type SimulationRunStatus =
  'queued' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'failed';

export interface SimulationRunConfig {
  population_size: number;
  seed: number;
  days: number;
  tick_interval_hours: number;
  start_date: string;
  place_scope: {
    level: 'global' | 'region' | 'country' | 'city';
    identifier: string | null;
  };
  agent_type_mix: Record<string, number>;
}

export interface SimulationSnapshot {
  day: number;
  date: string;
  tick: number;
  elapsed_hours: number;
  state_counts: Record<string, number>;
  place_counts: Record<string, number>;
  transition_counts: Record<string, unknown>[];
  interaction_outcome_counts?: Record<string, number>;
  event_count: number;
  interaction_count: number;
}

export interface SimulationResult {
  source: 'rust';
  protocol_version: string;
  engine_version: string;
  data_version: string;
  program_version: string;
  default_dsl_version?: string | null;
  default_dsl_hash?: string | null;
  input_hash: string;
  output_hash: string;
  snapshots: SimulationSnapshot[];
}

export interface SimulationRun {
  run_id: string;
  config: SimulationRunConfig;
  status: SimulationRunStatus;
  progress: number;
  completed_ticks: number;
  total_ticks: number;
  result: SimulationResult | null;
  error: string | null;
  default_dsl_version?: string | null;
  default_dsl_hash?: string | null;
  evidence_summary?: RunEvidenceSummary;
  evidence_warnings?: RunEvidenceWarning[];
  global_demo_summary?: GlobalDemoSummaryData;
}

export interface RunAgentSummary {
  agent_id: string;
  final_module: string;
  final_state: string;
  final_location: string;
}

export interface RunAgentPage {
  items: RunAgentSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AgentTimelinePoint {
  day: number;
  date: string;
  tick: number;
  elapsed_hours: number;
  module: string;
  state: string;
  location: string;
  memory?: Record<string, number>;
  state_receipts?: StateTickReceipt[];
  action_receipts?: ActionReceipt[];
  actions: string[];
  routine_actions: string[];
  interactions: string[];
  interaction_details?: AgentInteractionDetail[];
  decision_path: DecisionPathStep[];
  location_transitions: LocationTransitionStep[];
}

export interface StateTickReceipt {
  tick: number;
  event_counts: Record<string, number>;
  state_rules: Array<{
    rule_index?: number;
    target_state_id: string;
    input_state_ids: string[];
    formula: string;
    evidence: {
      status: string;
      source: string;
      source_version: string;
      uncertainty: number;
    };
  }>;
  event_effects?: Array<{
    event: string;
    agent_index: number;
    target_state_id: string;
    operation: string;
    configured_value: number;
    delta: number;
    evidence: {
      status: string;
      source: string;
      source_version: string;
      uncertainty: number;
    };
  }>;
  agent_state_changes?: Array<{
    agent_index: number;
    target_state_id: string;
    rule_index: number;
    before: number;
    event_delta: number;
    equation_delta: number;
    after: number;
  }>;
  finance_changes?: Array<{
    agent_index: number;
    currency: string;
    provenance: {
      status: string;
      source: string;
    };
    flows: Record<string, number>;
    ledger_changes: Array<{
      ledger: string;
      before: number | null;
      flow_delta: number;
      after: number | null;
    }>;
  }>;
  finance_formula?: string | null;
}

export interface ActionReceipt {
  tick: number;
  action: string;
  rule_index: number;
  probability: number;
  draw: number;
  provenance: {
    source: string;
    version: string;
    status: string;
    uncertainty: number;
  };
}

export interface InteractionPathStep {
  tree_id: string | null;
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
    source_date: string | null;
    evidence_id: string | null;
  };
}

export interface AgentInteractionDetail {
  tick: number;
  role: 'initiator' | 'target';
  interaction_type: string;
  channel: string;
  other_agent_id: string;
  place: string;
  state_deltas: Array<{
    agent_id: string;
    state: string;
    before: number;
    delta: number;
    after: number;
  }>;
  relationship_deltas: Array<{
    source_agent_id: string;
    target_agent_id: string;
    field: string;
    before: number;
    delta: number;
    after: number;
  }>;
  interaction_tree: {
    tree_id: string;
    tree_version: string;
    outcome_node: string;
    outcome: string;
    path: InteractionPathStep[];
  } | null;
}

export interface DecisionPathStep {
  tick: number;
  module: string;
  transition: string;
  from_state: string;
  to_state: string;
  probability: number;
  provenance: Record<string, unknown>;
}

export interface LocationTransitionStep {
  tick: number;
  kind: string;
  source: string;
  schedule: string | null;
  from_location: string;
  to_location: string;
  destination_location: string;
  provenance: Record<string, unknown>;
}

export interface RunAgentDetail extends RunAgentSummary {
  initial_module: string;
  initial_state: string;
  initial_location: string;
  traits: Record<string, string | number>;
  memory: Record<string, number>;
  initial_profile: Record<string, unknown>;
  timeline: AgentTimelinePoint[];
}

export interface RunEvent {
  day: number;
  date: string;
  tick: number;
  kind:
    | 'action'
    | 'routine'
    | 'transition'
    | 'location'
    | 'availability'
    | 'synchronization'
    | 'interaction';
  label: string;
  agent_ids: string[];
  location: string | null;
  details: Record<string, unknown>;
}

export interface RunEventPage {
  items: RunEvent[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SimulationRunClient {
  launch(config: SimulationRunConfig): Promise<SimulationRun>;
  list(): Promise<SimulationRun[]>;
  get(runId: string): Promise<SimulationRun>;
  cancel(runId: string): Promise<SimulationRun>;
  delete(runId: string, confirmation: string): Promise<void>;
  agents(runId: string, search?: string, page?: number): Promise<RunAgentPage>;
  agent(runId: string, agentId: string): Promise<RunAgentDetail>;
  events(runId: string, kind?: string, page?: number): Promise<RunEventPage>;
}

export interface SimulationRunPanelOptions {
  pollIntervalMs?: number;
  launchPreviewClient?: SimulationRunPreviewClient | null;
}

interface InitialPopulationDefaults {
  configured: boolean;
  seed: number | null;
  agent_count: number;
  agent_type_mix: Record<string, number>;
}

type ResultView = 'overview' | 'agents' | 'events' | 'interactions' | 'locations';

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const display = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) ? body.detail : null;
    throw new Error(
      typeof detail === 'string' ? detail : `Simulation request failed (${response.status})`,
    );
  }
  return body;
}

function requireRun(value: unknown): SimulationRun {
  if (
    !isRecord(value) ||
    typeof value.run_id !== 'string' ||
    !isRecord(value.config) ||
    typeof value.status !== 'string' ||
    typeof value.progress !== 'number' ||
    typeof value.completed_ticks !== 'number' ||
    typeof value.total_ticks !== 'number' ||
    (value.global_demo_summary != null && !isGlobalDemoSummaryData(value.global_demo_summary))
  ) {
    throw new Error('The server returned an invalid simulation run contract.');
  }
  return value as unknown as SimulationRun;
}

function requireRuns(value: unknown): SimulationRun[] {
  if (!Array.isArray(value)) {
    throw new Error('The server returned an invalid saved simulation list.');
  }
  return value.map(requireRun);
}

function requireAgentPage(value: unknown): RunAgentPage {
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
    throw new Error('The server returned an invalid simulation agent list.');
  }
  return value as unknown as RunAgentPage;
}

function requireAgent(value: unknown): RunAgentDetail {
  if (!isRecord(value) || typeof value.agent_id !== 'string' || !Array.isArray(value.timeline)) {
    throw new Error('The server returned an invalid simulation agent timeline.');
  }
  return value as unknown as RunAgentDetail;
}

function requireEvents(value: unknown): RunEventPage {
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
    throw new Error('The server returned an invalid simulation event list.');
  }
  return value as unknown as RunEventPage;
}

export function createSimulationRunHttpClient(
  basePath = '/api/simulation/runs',
): SimulationRunClient {
  return {
    launch: async (config) =>
      requireRun(
        await requestJson(basePath, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        }),
      ),
    list: async () => requireRuns(await requestJson(basePath)),
    get: async (runId) => requireRun(await requestJson(`${basePath}/${encodeURIComponent(runId)}`)),
    cancel: async (runId) =>
      requireRun(
        await requestJson(`${basePath}/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }),
      ),
    delete: async (runId, confirmation) => {
      const query = new URLSearchParams({ confirm_run_id: confirmation });
      await requestJson(`${basePath}/${encodeURIComponent(runId)}?${query}`, { method: 'DELETE' });
    },
    agents: async (runId, search = '', page = 1) => {
      const query = new URLSearchParams({ search, page: String(page), page_size: '100' });
      return requireAgentPage(
        await requestJson(`${basePath}/${encodeURIComponent(runId)}/agents?${query}`),
      );
    },
    agent: async (runId, agentId) =>
      requireAgent(
        await requestJson(
          `${basePath}/${encodeURIComponent(runId)}/agents/${encodeURIComponent(agentId)}`,
        ),
      ),
    events: async (runId, kind = '', page = 1) => {
      const query = new URLSearchParams({ page: String(page), page_size: '100' });
      if (kind) query.set('kind', kind);
      return requireEvents(
        await requestJson(`${basePath}/${encodeURIComponent(runId)}/events?${query}`),
      );
    },
  };
}

export class SimulationRunPanel {
  private run: SimulationRun | null = null;
  private savedRuns: SimulationRun[] = [];
  private savedRunsLoading = true;
  private savedRunsError = '';
  private pendingDeleteRunId: string | null = null;
  private view: ResultView = 'overview';
  private snapshotIndex = -1;
  private agentPage: RunAgentPage | null = null;
  private agentDetail: RunAgentDetail | null = null;
  private eventPage: RunEventPage | null = null;
  private agentSearch = '';
  private eventKind = '';
  private interactionsView: InteractionsView | null = null;
  private locationsView: LocationsView | null = null;
  private globalDemoSummaryView: GlobalDemoSummaryView | null = null;
  private launchEvidencePreview: SimulationLaunchEvidencePreview | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private requestVersion = 0;
  private disposed = false;
  private active = true;
  private draftConfig: SimulationRunConfig = {
    population_size: 1000,
    seed: 1,
    days: 30,
    tick_interval_hours: 1,
    start_date: new Date().toISOString().slice(0, 10),
    place_scope: { level: 'global', identifier: null },
    agent_type_mix: {},
  };
  private readonly pollIntervalMs: number;
  private readonly launchPreviewClient: SimulationRunPreviewClient | null | undefined;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: SimulationRunClient = createSimulationRunHttpClient(),
    options: SimulationRunPanelOptions = {},
  ) {
    this.pollIntervalMs = options.pollIntervalMs ?? 350;
    this.launchPreviewClient = options.launchPreviewClient;
    this.host.classList.add('simulation-run-panel');
    this.host.addEventListener('submit', this.onSubmit);
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
    this.render();
    void this.loadInitialPopulationDefaults();
    void this.loadSavedRuns();
  }

  dispose(): void {
    this.disposed = true;
    this.requestVersion += 1;
    if (this.timer) clearTimeout(this.timer);
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
    this.interactionsView?.destroy();
    this.locationsView?.dispose();
    this.globalDemoSummaryView?.destroy();
    this.launchEvidencePreview?.dispose();
  }

  activate(): void {
    if (this.disposed) return;
    this.active = true;
    this.render();
    this.schedulePoll();
  }

  deactivate(): void {
    this.active = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  refreshDefaults(): Promise<void> {
    return this.loadInitialPopulationDefaults();
  }

  private onSubmit = (event: SubmitEvent): void => {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    if (form.matches('[data-run-config]')) void this.launch(form);
    if (form.matches('[data-run-agent-search]')) {
      const data = new FormData(form);
      this.agentSearch = String(data.get('search') ?? '').trim();
      void this.loadAgents(1);
    }
  };

  private onClick = (event: MouseEvent): void => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-run-action]');
    if (!button) return;
    const action = button.dataset.runAction;
    if (action === 'cancel') void this.cancel();
    if (action === 'retry') this.reset();
    if (action === 'refresh-runs') void this.loadSavedRuns();
    if (action === 'open-run' && button.dataset.runId) void this.openSavedRun(button.dataset.runId);
    if (action === 'request-delete' && button.dataset.runId) {
      this.pendingDeleteRunId = button.dataset.runId;
      this.render();
    }
    if (action === 'cancel-delete') {
      this.pendingDeleteRunId = null;
      this.render();
    }
    if (action === 'confirm-delete' && button.dataset.runId)
      void this.deleteSavedRun(button.dataset.runId);
    if (action === 'overview') this.openView('overview');
    if (action === 'agents') this.openView('agents');
    if (action === 'events') this.openView('events');
    if (action === 'interactions') this.openView('interactions');
    if (action === 'locations') this.openView('locations');
    if (action === 'open-agent' && button.dataset.agentId)
      void this.loadAgent(button.dataset.agentId);
    if (action === 'close-agent') {
      this.agentDetail = null;
      this.render();
    }
    if (action === 'agents-previous' && this.agentPage)
      void this.loadAgents(this.agentPage.page - 1);
    if (action === 'agents-next' && this.agentPage) void this.loadAgents(this.agentPage.page + 1);
    if (action === 'events-previous' && this.eventPage)
      void this.loadEvents(this.eventPage.page - 1);
    if (action === 'events-next' && this.eventPage) void this.loadEvents(this.eventPage.page + 1);
  };

  private onChange = (event: Event): void => {
    const input = event.target as HTMLInputElement | HTMLSelectElement;
    if (input.matches('[data-run-snapshot]')) {
      this.snapshotIndex = Number(input.value);
      this.render();
    }
    if (input.matches('[data-run-event-kind]')) {
      this.eventKind = input.value;
      void this.loadEvents(1);
    }
  };

  private async launch(form: HTMLFormElement): Promise<void> {
    const data = new FormData(form);
    const scopeLevel = String(data.get('place_scope_level')) as
      'global' | 'region' | 'country' | 'city';
    let agentTypeMix: Record<string, number>;
    try {
      agentTypeMix = this.parseAgentTypeMix(String(data.get('agent_type_mix') ?? ''));
    } catch (error) {
      this.renderMessage(error instanceof Error ? error.message : String(error));
      return;
    }
    const config: SimulationRunConfig = {
      population_size: Number(data.get('population_size')),
      seed: Number(data.get('seed')),
      days: Number(data.get('days')),
      tick_interval_hours: Number(data.get('tick_interval_hours')),
      start_date: String(data.get('start_date')),
      place_scope: {
        level: scopeLevel,
        identifier:
          scopeLevel === 'global' ? null : String(data.get('place_scope_identifier') ?? '').trim(),
      },
      agent_type_mix: agentTypeMix,
    };
    const error = this.validateConfig(config);
    if (error) {
      this.renderMessage(error);
      return;
    }
    if (!(await this.prepareLaunchEvidence(config))) return;
    const version = ++this.requestVersion;
    this.renderMessage('Preparing the Rust run…');
    try {
      this.run = await this.client.launch(config);
      if (this.disposed || version !== this.requestVersion) return;
      this.view = 'overview';
      this.snapshotIndex = -1;
      this.upsertSavedRun(this.run);
      this.render();
      this.schedulePoll();
    } catch (errorValue) {
      if (this.disposed || version !== this.requestVersion) return;
      this.renderRequestError(errorValue);
    }
  }

  private async prepareLaunchEvidence(config: SimulationRunConfig): Promise<boolean> {
    while (this.launchEvidencePreview) {
      const preview = this.launchEvidencePreview;
      const ready = await preview.load(config);
      if (ready) return true;
      if (preview === this.launchEvidencePreview) return false;
    }
    return true;
  }

  private validateConfig(config: SimulationRunConfig): string | null {
    if (!Number.isInteger(config.population_size) || config.population_size < 1)
      return 'Population must be a positive whole number.';
    if (!Number.isSafeInteger(config.seed) || config.seed < 0)
      return 'Seed must be a non-negative whole number.';
    if (!Number.isInteger(config.days) || config.days < 1)
      return 'Days must be a positive whole number.';
    if (config.tick_interval_hours <= 0 || !Number.isInteger(24 / config.tick_interval_hours))
      return 'Tick interval must divide a 24-hour day exactly.';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(config.start_date)) return 'Choose a start date.';
    if (config.place_scope.level !== 'global' && !config.place_scope.identifier)
      return `Enter the ${config.place_scope.level} to simulate.`;
    return null;
  }

  private parseAgentTypeMix(value: string): Record<string, number> {
    const normalized = value.trim();
    if (!normalized) return {};
    const result: Record<string, number> = {};
    for (const row of normalized.split(/\n|,/)) {
      const [rawName, rawShare, ...extra] = row.split(':');
      const name = rawName?.trim();
      const share = Number(rawShare?.trim());
      if (!name || extra.length || !Number.isFinite(share) || share <= 0 || share > 1) {
        throw new Error('Agent type mix must use one Type: share entry per line.');
      }
      result[name] = share;
    }
    const total = Object.values(result).reduce((sum, share) => sum + share, 0);
    if (Math.abs(total - 1) > 1e-9) throw new Error('Agent type mix shares must sum to 1.');
    return result;
  }

  private schedulePoll(): void {
    if (!this.active) return;
    if (!this.run || !['queued', 'running', 'cancelling'].includes(this.run.status)) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.poll(), this.pollIntervalMs);
  }

  private async poll(): Promise<void> {
    if (!this.run || this.disposed || !this.active) return;
    const runId = this.run.run_id;
    try {
      const run = await this.client.get(runId);
      if (this.disposed || this.run?.run_id !== runId) return;
      this.run = run;
      this.upsertSavedRun(run);
      if (run.status === 'completed' && run.result) {
        this.snapshotIndex = run.result.snapshots.length - 1;
      }
      if (this.active) {
        this.render();
        this.schedulePoll();
      }
    } catch (error) {
      if (!this.disposed) this.renderRequestError(error);
    }
  }

  private async cancel(): Promise<void> {
    if (!this.run) return;
    const runId = this.run.run_id;
    try {
      this.run = await this.client.cancel(runId);
      this.upsertSavedRun(this.run);
      this.render();
      this.schedulePoll();
    } catch (error) {
      this.renderRequestError(error);
    }
  }

  private reset(): void {
    this.requestVersion += 1;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.run = null;
    this.agentPage = null;
    this.agentDetail = null;
    this.eventPage = null;
    this.pendingDeleteRunId = null;
    this.render();
  }

  private async loadSavedRuns(): Promise<void> {
    this.savedRunsLoading = true;
    this.savedRunsError = '';
    this.render();
    try {
      this.savedRuns = await this.client.list();
      this.savedRunsLoading = false;
      this.render();
    } catch (error) {
      this.savedRunsLoading = false;
      this.savedRunsError = error instanceof Error ? error.message : String(error);
      this.render();
    }
  }

  private async openSavedRun(runId: string): Promise<void> {
    const version = ++this.requestVersion;
    try {
      const run = await this.client.get(runId);
      if (this.disposed || version !== this.requestVersion) return;
      this.run = run;
      this.view = 'overview';
      this.snapshotIndex = run.result ? run.result.snapshots.length - 1 : -1;
      this.agentPage = null;
      this.agentDetail = null;
      this.eventPage = null;
      this.pendingDeleteRunId = null;
      this.upsertSavedRun(run);
      this.render();
      this.schedulePoll();
    } catch (error) {
      if (!this.disposed && version === this.requestVersion) this.renderRequestError(error);
    }
  }

  private async deleteSavedRun(runId: string): Promise<void> {
    try {
      await this.client.delete(runId, runId);
      this.savedRuns = this.savedRuns.filter((run) => run.run_id !== runId);
      this.pendingDeleteRunId = null;
      if (this.run?.run_id === runId) {
        this.requestVersion += 1;
        this.run = null;
        this.agentPage = null;
        this.agentDetail = null;
        this.eventPage = null;
      }
      this.render();
    } catch (error) {
      this.savedRunsError = error instanceof Error ? error.message : String(error);
      this.pendingDeleteRunId = null;
      this.render();
    }
  }

  private upsertSavedRun(run: SimulationRun): void {
    this.savedRuns = [run, ...this.savedRuns.filter((item) => item.run_id !== run.run_id)];
  }

  private openView(view: ResultView): void {
    this.view = view;
    this.agentDetail = null;
    this.render();
    if (view === 'agents' && !this.agentPage) void this.loadAgents(1);
    if (view === 'events' && !this.eventPage) void this.loadEvents(1);
  }

  private async loadAgents(page: number): Promise<void> {
    if (!this.run || page < 1) return;
    const version = ++this.requestVersion;
    try {
      const result = await this.client.agents(this.run.run_id, this.agentSearch, page);
      if (this.disposed || version !== this.requestVersion) return;
      this.agentPage = result;
      this.render();
    } catch (error) {
      if (!this.disposed && version === this.requestVersion) this.renderRequestError(error);
    }
  }

  private async loadAgent(agentId: string): Promise<void> {
    if (!this.run) return;
    const version = ++this.requestVersion;
    try {
      const result = await this.client.agent(this.run.run_id, agentId);
      if (this.disposed || version !== this.requestVersion) return;
      this.agentDetail = result;
      this.render();
    } catch (error) {
      if (!this.disposed && version === this.requestVersion) this.renderRequestError(error);
    }
  }

  private async loadEvents(page: number): Promise<void> {
    if (!this.run || page < 1) return;
    const version = ++this.requestVersion;
    try {
      const result = await this.client.events(this.run.run_id, this.eventKind, page);
      if (this.disposed || version !== this.requestVersion) return;
      this.eventPage = result;
      this.render();
    } catch (error) {
      if (!this.disposed && version === this.requestVersion) this.renderRequestError(error);
    }
  }

  private render(): void {
    this.interactionsView?.destroy();
    this.interactionsView = null;
    this.locationsView?.dispose();
    this.locationsView = null;
    this.globalDemoSummaryView?.destroy();
    this.globalDemoSummaryView = null;
    this.launchEvidencePreview?.dispose();
    this.launchEvidencePreview = null;
    this.host.innerHTML = `${this.renderConfig()}${this.renderSavedRuns()}<div class="simulation-run-body">${this.renderRun()}</div>`;
    const launchPreviewHost = this.host.querySelector<HTMLElement>('[data-run-launch-preview]');
    if (launchPreviewHost && this.launchPreviewClient !== null) {
      this.launchEvidencePreview = this.launchPreviewClient
        ? new SimulationLaunchEvidencePreview(launchPreviewHost, this.launchPreviewClient)
        : new SimulationLaunchEvidencePreview(launchPreviewHost);
    }
    const interactionHost = this.host.querySelector<HTMLElement>('[data-run-interactions]');
    if (interactionHost && this.run) {
      this.interactionsView = new InteractionsView(
        interactionHost,
        createInteractionsHttpClient(),
        this.run.run_id,
      );
    }
    const locationsHost = this.host.querySelector<HTMLElement>('[data-run-locations]');
    if (locationsHost && this.run) {
      this.locationsView = new LocationsView(
        locationsHost,
        createLocationsHttpClient(this.run.run_id),
      );
    }
    const populationEvidenceHost = this.host.querySelector<HTMLElement>(
      '[data-run-population-evidence]',
    );
    if (populationEvidenceHost && this.run?.global_demo_summary) {
      this.globalDemoSummaryView = new GlobalDemoSummaryView(
        populationEvidenceHost,
        this.run.global_demo_summary,
      );
    }
  }

  private renderConfig(): string {
    const config = this.run?.config ?? this.draftConfig;
    const locked = this.run && ['queued', 'running', 'cancelling'].includes(this.run.status);
    const typeMix = Object.entries(config.agent_type_mix)
      .map(([name, share]) => `${name}: ${share}`)
      .join('\n');
    return `
      <header class="simulation-run-heading">
        <div><span class="small-label">RUST NUMERIC CORE</span><h2>Run simulation</h2><p>Configure the confirmed population and decision modules, then inspect recorded engine output.</p></div>
      </header>
      <form class="simulation-run-config" data-run-config>
        <label>Population<input name="population_size" type="number" min="1" step="1" value="${config.population_size}" ${locked ? 'disabled' : ''} /></label>
        <label>Days<input name="days" type="number" min="1" step="1" value="${config.days}" ${locked ? 'disabled' : ''} /></label>
        <label>Seed<input name="seed" type="number" min="0" step="1" value="${config.seed}" ${locked ? 'disabled' : ''} /></label>
        <label>Start date<input name="start_date" type="date" value="${escapeHtml(config.start_date)}" ${locked ? 'disabled' : ''} /></label>
        <label>Tick interval (hours)<input name="tick_interval_hours" type="number" min="0.0001" step="any" value="${config.tick_interval_hours}" ${locked ? 'disabled' : ''} /></label>
        <label>Place scope<select name="place_scope_level" ${locked ? 'disabled' : ''}>${['global', 'region', 'country', 'city'].map((level) => `<option value="${level}"${config.place_scope.level === level ? ' selected' : ''}>${display(level)}</option>`).join('')}</select></label>
        <label>Place<input name="place_scope_identifier" type="text" value="${escapeHtml(config.place_scope.identifier ?? '')}" placeholder="Required for region, country, or city" ${locked ? 'disabled' : ''} /></label>
        <label class="simulation-run-type-mix">Agent type mix<textarea name="agent_type_mix" rows="2" placeholder="Blank uses Initial Agents mix" ${locked ? 'disabled' : ''}>${escapeHtml(typeMix)}</textarea></label>
        <button class="button" type="submit" ${locked ? 'disabled' : ''}>Launch Rust simulation</button>
      </form>
      <div data-run-launch-preview></div>`;
  }

  private async loadInitialPopulationDefaults(): Promise<void> {
    try {
      const value = await requestJson('/api/simulation/initial-population');
      if (
        this.disposed ||
        !isRecord(value) ||
        value.configured !== true ||
        typeof value.agent_count !== 'number' ||
        !isRecord(value.agent_type_mix)
      )
        return;
      const typeMix = Object.fromEntries(
        Object.entries(value.agent_type_mix).filter(
          (entry): entry is [string, number] => typeof entry[1] === 'number',
        ),
      );
      const defaults = value as unknown as InitialPopulationDefaults;
      this.draftConfig = {
        ...this.draftConfig,
        population_size: defaults.agent_count,
        seed: typeof defaults.seed === 'number' ? defaults.seed : this.draftConfig.seed,
        agent_type_mix: typeMix,
      };
      if (!this.run) this.render();
    } catch {
      return;
    }
  }

  private renderSavedRuns(): string {
    let content = '';
    if (this.savedRunsLoading) {
      content = '<div class="simulation-saved-empty" role="status">Loading saved runs…</div>';
    } else if (this.savedRunsError) {
      content = `<div class="simulation-saved-error" role="alert"><span>${escapeHtml(this.savedRunsError)}</span><button class="button secondary" type="button" data-run-action="refresh-runs">Retry</button></div>`;
    } else if (!this.savedRuns.length) {
      content = '<div class="simulation-saved-empty">No saved runs yet.</div>';
    } else {
      content = `<div class="simulation-saved-list">${this.savedRuns
        .map((run) => this.renderSavedRun(run))
        .join('')}</div>`;
    }
    return `<section class="simulation-saved-runs" aria-label="Saved simulation runs"><header><div><span class="small-label">RECORDED OUTPUT</span><h3>Saved runs</h3></div><button class="button secondary" type="button" data-run-action="refresh-runs" ${this.savedRunsLoading ? 'disabled' : ''}>Refresh</button></header>${content}</section>`;
  }

  private renderSavedRun(run: SimulationRun): string {
    const selected = this.run?.run_id === run.run_id;
    const deleting = this.pendingDeleteRunId === run.run_id;
    const place = run.config.place_scope.identifier ?? 'Global';
    if (deleting) {
      return `<article class="simulation-saved-row simulation-saved-confirm"><div><strong>Delete this recorded run?</strong><small>${escapeHtml(run.run_id)}</small></div><span>This removes its snapshots, timelines, and events.</span><div><button class="button secondary" type="button" data-run-action="cancel-delete">Keep run</button><button class="button danger" type="button" data-run-action="confirm-delete" data-run-id="${escapeHtml(run.run_id)}">Delete permanently</button></div></article>`;
    }
    return `<article class="simulation-saved-row${selected ? ' is-selected' : ''}"><button type="button" data-run-action="open-run" data-run-id="${escapeHtml(run.run_id)}" aria-label="Open run ${escapeHtml(run.run_id)}"><span class="simulation-run-status">${escapeHtml(display(run.status))}</span><span><strong>${run.config.population_size.toLocaleString()} agents · ${run.config.days.toLocaleString()} days</strong><small>${escapeHtml(place)} · seed ${run.config.seed} · starts ${escapeHtml(run.config.start_date)}</small></span><b>›</b></button><button class="simulation-saved-delete" type="button" data-run-action="request-delete" data-run-id="${escapeHtml(run.run_id)}" aria-label="Delete run ${escapeHtml(run.run_id)}" ${['queued', 'running', 'cancelling'].includes(run.status) ? 'disabled title="Cancel the active run before deleting it"' : ''}>Delete</button></article>`;
  }

  private renderRun(): string {
    if (!this.run)
      return '<div class="simulation-run-empty">Launch a simulation or open a saved run.</div>';
    const evidence = runEvidenceMarkup(this.run.evidence_summary, this.run.evidence_warnings);
    const populationEvidence = this.run.global_demo_summary
      ? '<div class="simulation-run-population-evidence" data-run-population-evidence></div>'
      : '';
    if (['queued', 'running', 'cancelling'].includes(this.run.status))
      return `${populationEvidence}${evidence}${this.renderProgress()}`;
    if (this.run.status === 'failed') {
      return `${evidence}<div class="simulation-run-state simulation-run-error" role="alert"><strong>Run failed</strong><span>${escapeHtml(this.run.error ?? 'The Rust engine failed.')}</span><button class="button secondary" type="button" data-run-action="retry">Edit configuration</button></div>`;
    }
    if (this.run.status === 'cancelled') {
      return `${evidence}<div class="simulation-run-state"><strong>Cancelled</strong><span>The engine stopped before the next recorded tick.</span><button class="button secondary" type="button" data-run-action="retry">Start another run</button></div>`;
    }
    if (!this.run.result)
      return `${populationEvidence}${evidence}<div class="simulation-run-state" role="alert">Completed run has no result.</div>`;
    if (this.agentDetail)
      return `${populationEvidence}${evidence}${this.renderAgentDetail(this.agentDetail)}`;
    return `${this.renderResultHeader()}${populationEvidence}${evidence}${this.renderResultNavigation()}${
      this.view === 'agents'
        ? this.renderAgents()
        : this.view === 'locations'
          ? '<section data-run-locations></section>'
          : this.view === 'interactions'
            ? '<section data-run-interactions></section>'
            : this.view === 'events'
              ? this.renderEvents()
              : this.renderOverview()
    }`;
  }

  private renderProgress(): string {
    if (!this.run) return '';
    const percent = Math.round(this.run.progress * 100);
    return `<div class="simulation-run-progress" role="status">
      <div><span class="simulation-run-status">${escapeHtml(display(this.run.status))}</span><strong>${percent}%</strong></div>
      <div class="simulation-run-progress-track" role="progressbar" aria-label="Simulation progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><i style="width:${percent}%"></i></div>
      <p>${this.run.completed_ticks.toLocaleString()} of ${this.run.total_ticks.toLocaleString()} Rust ticks completed</p>
      <button class="button secondary" type="button" data-run-action="cancel">Cancel run</button>
    </div>`;
  }

  private renderResultHeader(): string {
    const result = this.run?.result;
    if (!result) return '';
    const defaultDsl =
      result.default_dsl_version && result.default_dsl_hash
        ? `<small>Default DSL ${escapeHtml(result.default_dsl_version)} · <span title="${escapeHtml(result.default_dsl_hash)}">${escapeHtml(result.default_dsl_hash.slice(0, 18))}…</span></small>`
        : '';
    return `<div class="simulation-result-heading">
      <div><span class="simulation-run-status">Completed</span><strong>Rust ${escapeHtml(result.engine_version)}</strong><small>Protocol ${escapeHtml(result.protocol_version)} · data ${escapeHtml(result.data_version)} · program ${escapeHtml(result.program_version)}</small>${defaultDsl}</div>
      <div class="simulation-run-hashes"><span title="${escapeHtml(result.input_hash)}">Input ${escapeHtml(result.input_hash.slice(0, 10))}</span><span title="${escapeHtml(result.output_hash)}">Output ${escapeHtml(result.output_hash.slice(0, 10))}</span></div>
    </div>`;
  }

  private renderResultNavigation(): string {
    return `<nav class="simulation-result-nav" aria-label="Simulation results">
      ${this.resultButton('overview', 'Overview')}
      ${this.resultButton('agents', 'Agents')}
      ${this.resultButton('locations', 'Locations')}
      ${this.resultButton('events', 'Events')}
      ${this.resultButton('interactions', 'Interactions')}
    </nav>`;
  }

  private resultButton(view: ResultView, label: string): string {
    return `<button type="button" data-run-action="${view}" aria-pressed="${this.view === view}">${label}</button>`;
  }

  private renderOverview(): string {
    const snapshots = this.run?.result?.snapshots ?? [];
    if (!snapshots.length)
      return '<div class="simulation-run-empty">No Rust snapshots were recorded.</div>';
    const index = this.snapshotIndex >= 0 ? this.snapshotIndex : snapshots.length - 1;
    const snapshot = snapshots[Math.min(index, snapshots.length - 1)];
    return `<section class="simulation-run-overview" aria-label="Recorded Rust snapshot">
      <div class="simulation-snapshot-toolbar"><label>Recorded day<select data-run-snapshot>${snapshots.map((item, snapshotIndex) => `<option value="${snapshotIndex}"${snapshotIndex === index ? ' selected' : ''}>Day ${item.day} · ${escapeHtml(item.date)}</option>`).join('')}</select></label><span>${snapshot.event_count} events · ${snapshot.interaction_count} interactions</span></div>
      <div class="simulation-result-columns">
        ${this.renderCounts('Agent states', snapshot.state_counts, 'agents')}
        ${this.renderCounts('Locations', snapshot.place_counts, 'agents')}
      </div>
      ${this.renderDecisionOutcomes(snapshot)}
    </section>`;
  }

  private renderDecisionOutcomes(snapshot: SimulationSnapshot): string {
    const outcomes = new Map<string, { count: number; unit: string }>();
    for (const item of snapshot.transition_counts) {
      const module = typeof item.module === 'string' ? item.module : 'module';
      const transition = typeof item.transition === 'string' ? item.transition : 'transition';
      const count = typeof item.count === 'number' ? item.count : 0;
      const key = `${module} / ${transition}`;
      outcomes.set(key, { count: (outcomes.get(key)?.count ?? 0) + count, unit: 'agent' });
    }
    for (const [outcome, count] of Object.entries(snapshot.interaction_outcome_counts ?? {})) {
      outcomes.set(`Interaction / ${display(outcome)}`, { count, unit: 'interaction' });
    }
    return `<section class="simulation-decision-outcomes"><h3>Decision and interaction outcomes</h3>${
      [...outcomes.entries()]
        .sort((left, right) => right[1].count - left[1].count)
        .map(
          ([label, outcome]) =>
            `<div><span>${escapeHtml(label)}</span><strong>${outcome.count.toLocaleString()} ${outcome.unit}${outcome.count === 1 ? '' : 's'}</strong></div>`,
        )
        .join('') || '<p>No decision or interaction outcomes occurred on this day.</p>'
    }</section>`;
  }

  private renderCounts(title: string, counts: Record<string, number>, suffix: string): string {
    const rows = Object.entries(counts).sort((left, right) => right[1] - left[1]);
    return `<section class="simulation-counts"><h3>${title}</h3>${rows.map(([label, count]) => `<div><span>${escapeHtml(label)}</span><strong>${count.toLocaleString()} ${suffix}</strong></div>`).join('') || '<p>No values recorded.</p>'}</section>`;
  }

  private renderAgents(): string {
    if (!this.agentPage)
      return '<div class="simulation-run-state" role="status">Loading recorded agents…</div>';
    return `<section class="simulation-run-agents">
      <form data-run-agent-search><label>Search recorded agents<input type="search" name="search" value="${escapeHtml(this.agentSearch)}" placeholder="Agent ID, state, or location" /></label><button class="button secondary" type="submit">Search</button></form>
      <div class="simulation-agent-list">${this.agentPage.items.map((agent) => `<button type="button" data-run-action="open-agent" data-agent-id="${escapeHtml(agent.agent_id)}" aria-label="Open ${escapeHtml(agent.agent_id)}"><span><strong>${escapeHtml(agent.agent_id)}</strong><small>Synthetic agent ID</small></span><span>${escapeHtml(agent.final_module)} / ${escapeHtml(agent.final_state)}</span><span>${escapeHtml(agent.final_location)}</span><b>›</b></button>`).join('') || '<div class="simulation-run-empty">No recorded agents match.</div>'}</div>
      ${this.renderPagination(this.agentPage.page, this.agentPage.pages, 'agents')}
    </section>`;
  }

  private renderAgentDetail(agent: RunAgentDetail): string {
    return `<section class="simulation-agent-detail">
      <button class="simulation-run-back" type="button" data-run-action="close-agent">← Back to results</button>
      <header><div><span class="small-label">RECORDED AGENT</span><h2>${escapeHtml(agent.agent_id)}</h2><p>Synthetic agent ID</p></div><span>${escapeHtml(agent.final_location)}</span></header>
      <div class="simulation-agent-state-pair"><div><small>Initial state</small><strong>${escapeHtml(agent.initial_module)} / ${escapeHtml(agent.initial_state)}</strong><span>${escapeHtml(agent.initial_location)}</span></div><b>→</b><div><small>Final state</small><strong>${escapeHtml(agent.final_module)} / ${escapeHtml(agent.final_state)}</strong><span>${escapeHtml(agent.final_location)}</span></div></div>
      ${this.renderInitialProfile(agent.initial_profile ?? {})}
      <div class="simulation-agent-data">${this.renderRecord('Final traits', agent.traits)}${this.renderRecord('Final memory', agent.memory)}</div>
      <section class="simulation-agent-timeline" aria-label="${escapeHtml(agent.agent_id)} timeline"><h3>Daily state, decisions, and locations</h3><div class="simulation-timeline-table"><div class="simulation-timeline-labels"><span>Day</span><span>State</span><span>Location</span><span>Recorded activity</span></div>${agent.timeline.map((point) => this.renderTimelinePoint(point)).join('')}</div></section>
    </section>`;
  }

  private renderInitialProfile(profile: Record<string, unknown>): string {
    const labels: Record<string, string> = {
      agent_types: 'Agent types',
      geography: 'Geography and location',
      household: 'Household and family',
      traits: 'Age, sex, occupation, income, education, health, and traits',
      states: 'Initial states',
      relationships: 'Relationships',
      routines: 'Routines',
      decision_trees: 'Decision trees',
      provenance: 'Data provenance',
    };
    const entries = Object.entries(labels).filter(([key]) => key in profile);
    if (!entries.length) return '';
    return `<section class="simulation-initial-profile"><h3>Full initial state</h3><div>${entries
      .map(([key, label]) => {
        const value = profile[key];
        const summary = Array.isArray(value) ? `${value.length} recorded` : 'Recorded detail';
        return `<details><summary><span>${escapeHtml(label)}</span><small>${escapeHtml(summary)}</small></summary><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;
      })
      .join('')}</div></section>`;
  }

  private renderTimelinePoint(point: AgentTimelinePoint): string {
    const activity = [...point.routine_actions, ...point.actions, ...point.interactions].join(
      ' · ',
    );
    return `<div class="simulation-timeline-row"><span><strong>${point.day}</strong><small>${escapeHtml(point.date)}</small></span><span>${escapeHtml(point.module)} / ${escapeHtml(point.state)}</span><span>${escapeHtml(point.location)}</span><span>${escapeHtml(activity || 'None')}${this.renderTimelineMemory(point.memory ?? {})}${this.renderActionReceipts(point.action_receipts ?? [])}${this.renderStateReceipts(point.state_receipts ?? [])}${this.renderLocationTransitions(point.location_transitions ?? [])}${this.renderDecisionPath(point.decision_path ?? [])}${this.renderInteractionDetails(point.interaction_details ?? [])}</span></div>`;
  }

  private renderTimelineMemory(memory: Record<string, number>): string {
    const entries = Object.entries(memory).sort(([left], [right]) => left.localeCompare(right));
    if (!entries.length) return '';
    return `<details class="simulation-state-receipts"><summary>Recorded state vector</summary><dl>${entries.map(([state, value]) => `<div><dt>${escapeHtml(display(state))}</dt><dd>${this.number(value)}</dd></div>`).join('')}</dl></details>`;
  }

  private renderActionReceipts(receipts: ActionReceipt[]): string {
    if (!receipts.length) return '';
    return `<details class="simulation-state-receipts"><summary>${receipts.length} causal action ${receipts.length === 1 ? 'receipt' : 'receipts'}</summary>${receipts
      .map(
        (receipt) =>
          `<article><strong>${escapeHtml(display(receipt.action))} · ${this.number(receipt.probability * 100)}%</strong><code>P=${this.number(receipt.probability)} · draw ${this.number(receipt.draw)} · rule ${receipt.rule_index}</code><small>${escapeHtml(display(receipt.provenance.status))} · ${escapeHtml(receipt.provenance.source)} ${escapeHtml(receipt.provenance.version)} · uncertainty ${Math.round(receipt.provenance.uncertainty * 100)}% · tick ${receipt.tick}</small></article>`,
      )
      .join('')}</details>`;
  }

  private renderStateReceipts(receipts: StateTickReceipt[]): string {
    if (!receipts.length) return '';
    const rules = new Map<number | string, StateTickReceipt['state_rules'][number]>();
    const changes = receipts.flatMap((receipt) => {
      receipt.state_rules.forEach((rule, index) => {
        rules.set(rule.rule_index ?? `${rule.target_state_id}:${index}`, rule);
      });
      return receipt.agent_state_changes ?? [];
    });
    const financeFormulas = [
      ...new Set(
        receipts
          .map((receipt) => receipt.finance_formula)
          .filter((formula): formula is string => Boolean(formula)),
      ),
    ];
    const financeChanges = receipts.flatMap((receipt) => receipt.finance_changes ?? []);
    return `<details class="simulation-state-receipts"><summary>State formulas and receipts</summary>${changes
      .map(
        (change) =>
          `<article><strong>${escapeHtml(display(change.target_state_id))} ${this.number(change.before)} ${this.signedNumber(change.event_delta)} ${this.signedNumber(change.equation_delta)} → ${this.number(change.after)}</strong><small>event delta ${this.signedNumber(change.event_delta)} · equation delta ${this.signedNumber(change.equation_delta)} · rule ${change.rule_index}</small></article>`,
      )
      .join(
        '',
      )}${[...rules.values()].map((rule) => `<article><strong>${escapeHtml(display(rule.target_state_id))}</strong><code>${escapeHtml(rule.formula)}</code><small>${escapeHtml(display(rule.evidence.status))} · ${escapeHtml(rule.evidence.source)} ${escapeHtml(rule.evidence.source_version)} · uncertainty ${Math.round(rule.evidence.uncertainty * 100)}%</small></article>`).join('')}${financeChanges.map((change) => this.renderFinanceChange(change)).join('')}${financeFormulas.map((formula) => `<article><strong>Finance equation</strong><code>${escapeHtml(formula)}</code></article>`).join('')}</details>`;
  }

  private renderFinanceChange(
    change: NonNullable<StateTickReceipt['finance_changes']>[number],
  ): string {
    const currency = escapeHtml(change.currency);
    const ledgers = change.ledger_changes
      .map(
        (ledger) =>
          `<strong>${escapeHtml(display(ledger.ledger))} ${this.number(ledger.before ?? 0)} ${this.signedNumber(ledger.flow_delta)} → ${this.number(ledger.after ?? 0)} ${currency}</strong>`,
      )
      .join('');
    const flows = Object.entries(change.flows)
      .filter(([, value]) => value !== 0)
      .map(
        ([name, value]) => `<span>${escapeHtml(display(name))} ${this.signedNumber(value)}</span>`,
      )
      .join(' · ');
    return `<article>${ledgers}<small>${flows || 'No cash flows'} · ${escapeHtml(display(change.provenance.status))} · ${escapeHtml(change.provenance.source)}</small></article>`;
  }

  private renderInteractionDetails(interactions: AgentInteractionDetail[]): string {
    if (!interactions.length) return '';
    return `<details class="simulation-interaction-path"><summary>${interactions.length} interaction ${interactions.length === 1 ? 'detail' : 'details'}</summary>${interactions
      .map((interaction) => {
        const stateDeltas = interaction.state_deltas
          .map(
            (delta) =>
              `<div><strong>${escapeHtml(display(delta.state))} ${this.number(delta.before)} ${this.signedNumber(delta.delta)} → ${this.number(delta.after)}</strong><small>${escapeHtml(delta.agent_id)}</small></div>`,
          )
          .join('');
        const relationshipDeltas = interaction.relationship_deltas
          .map(
            (delta) =>
              `<div><strong>${escapeHtml(display(delta.field))} ${escapeHtml(delta.source_agent_id)} → ${escapeHtml(delta.target_agent_id)} ${this.number(delta.before)} ${this.signedNumber(delta.delta)} → ${this.number(delta.after)}</strong></div>`,
          )
          .join('');
        const tree = interaction.interaction_tree;
        const treePath = tree
          ? `<div class="simulation-interaction-tree"><strong>${escapeHtml(display(tree.tree_id.replaceAll('-', '_')))} ${escapeHtml(tree.tree_version)} · ${escapeHtml(display(tree.outcome))}</strong>${tree.path
              .map((step) => {
                const treeLabel = step.tree_id
                  ? `${display(step.tree_id.replaceAll('-', '_'))} · `
                  : '';
                return `<div><span>${escapeHtml(treeLabel)}${escapeHtml(display(step.node_id))} → ${escapeHtml(display(step.outcome))}</span><small>P=${step.probability.toFixed(4)} · draw ${step.draw.toFixed(4)} · ${escapeHtml(step.evidence.source)} ${escapeHtml(step.evidence.version)}</small></div>`;
              })
              .join('')}</div>`
          : '';
        return `<article><h4>${escapeHtml(display(interaction.interaction_type))} · ${escapeHtml(display(interaction.channel))} with ${escapeHtml(interaction.other_agent_id)}</h4><p>${escapeHtml(interaction.place)} · ${escapeHtml(display(interaction.role))} · tick ${interaction.tick}</p>${treePath}${stateDeltas}${relationshipDeltas}</article>`;
      })
      .join('')}</details>`;
  }

  private number(value: number): string {
    return value.toLocaleString('en', {
      maximumFractionDigits: 6,
      useGrouping: true,
    });
  }

  private signedNumber(value: number): string {
    return `${value >= 0 ? '+' : ''}${this.number(value)}`;
  }

  private renderLocationTransitions(transitions: LocationTransitionStep[]): string {
    if (!transitions.length) return '';
    return `<details class="simulation-location-path"><summary>${transitions.length} location ${transitions.length === 1 ? 'change' : 'changes'}</summary>${transitions
      .map((transition) => {
        const recordedBy =
          typeof transition.provenance.recorded_by === 'string'
            ? display(transition.provenance.recorded_by)
            : typeof transition.provenance.source === 'string'
              ? transition.provenance.source
              : 'Provenance unavailable';
        const source = transition.schedule ?? transition.source;
        const destination =
          transition.destination_location !== transition.to_location
            ? ` · destination ${transition.destination_location}`
            : '';
        return `<div><strong>${escapeHtml(transition.from_location)} → ${escapeHtml(transition.to_location)}</strong><span>${escapeHtml(display(transition.kind))} · ${escapeHtml(source)}</span><small>${escapeHtml(recordedBy)}${escapeHtml(destination)} · tick ${transition.tick}</small></div>`;
      })
      .join('')}</details>`;
  }

  private renderDecisionPath(path: DecisionPathStep[]): string {
    if (!path.length) return '';
    return `<details class="simulation-decision-path"><summary>${path.length} decision ${path.length === 1 ? 'step' : 'steps'}</summary>${path
      .map((step) => {
        const source =
          typeof step.provenance.source === 'string' ? step.provenance.source : 'Unknown source';
        return `<div><strong>${escapeHtml(step.from_state)} → ${escapeHtml(step.to_state)}</strong><span>${escapeHtml(step.module)} · ${escapeHtml(step.transition)} · P=${step.probability.toFixed(4)}</span><small>${escapeHtml(source)} · tick ${step.tick}</small></div>`;
      })
      .join('')}</details>`;
  }

  private renderRecord(title: string, values: Record<string, string | number>): string {
    const rows = Object.entries(values);
    return `<section><h3>${title}</h3>${rows.map(([name, value]) => `<div><span>${escapeHtml(display(name))}</span><strong>${escapeHtml(value)}</strong></div>`).join('') || '<p>None recorded.</p>'}</section>`;
  }

  private renderEvents(): string {
    if (!this.eventPage)
      return '<div class="simulation-run-state" role="status">Loading recorded events…</div>';
    const options = [
      '',
      'action',
      'routine',
      'transition',
      'location',
      'availability',
      'interaction',
      'synchronization',
    ];
    return `<section class="simulation-run-events">
      <label>Event type<select data-run-event-kind>${options.map((value) => `<option value="${value}"${value === this.eventKind ? ' selected' : ''}>${value ? display(value) : 'All events'}</option>`).join('')}</select></label>
      <div class="simulation-event-list">${this.eventPage.items.map((event) => this.renderEvent(event)).join('') || '<div class="simulation-run-empty">No recorded events match.</div>'}</div>
      ${this.renderPagination(this.eventPage.page, this.eventPage.pages, 'events')}
    </section>`;
  }

  private renderEvent(event: RunEvent): string {
    return `<article><span class="simulation-event-kind">${escapeHtml(display(event.kind))}</span><div><strong>${escapeHtml(event.label)}</strong><p>${escapeHtml(event.agent_ids.join(' → ') || 'System')} ${event.location ? `· ${escapeHtml(event.location)}` : ''}</p>${this.renderEventDetails(event)}</div><time>Day ${event.day} · tick ${event.tick}<br />${escapeHtml(event.date)}</time></article>`;
  }

  private renderEventDetails(event: RunEvent): string {
    if (event.kind === 'availability') {
      const module =
        typeof event.details.decision_module === 'string'
          ? display(event.details.decision_module.replaceAll('-', '_'))
          : 'Decision tree';
      const schedule =
        typeof event.details.schedule === 'string'
          ? display(event.details.schedule.replaceAll('-', '_'))
          : 'Schedule unavailable';
      return `<small class="simulation-event-details">${escapeHtml(module)} · ${escapeHtml(schedule)} · blocked at the agent's actual place</small>`;
    }
    if (event.kind !== 'location') return '';
    const kind = typeof event.details.kind === 'string' ? display(event.details.kind) : 'Location';
    const source =
      typeof event.details.schedule === 'string'
        ? event.details.schedule
        : typeof event.details.source === 'string'
          ? event.details.source
          : 'Source unavailable';
    const provenance = isRecord(event.details.provenance)
      ? event.details.provenance.recorded_by
      : null;
    const recordedBy =
      typeof provenance === 'string' ? display(provenance) : 'Provenance unavailable';
    return `<small class="simulation-event-details">${escapeHtml(kind)} · ${escapeHtml(source)} · ${escapeHtml(recordedBy)}</small>`;
  }

  private renderPagination(page: number, pages: number, kind: 'agents' | 'events'): string {
    if (pages <= 1) return '';
    return `<div class="simulation-run-pagination"><button class="button secondary" type="button" data-run-action="${kind}-previous" ${page <= 1 ? 'disabled' : ''}>Previous</button><span>Page ${page} of ${pages}</span><button class="button secondary" type="button" data-run-action="${kind}-next" ${page >= pages ? 'disabled' : ''}>Next</button></div>`;
  }

  private renderMessage(message: string): void {
    const body = this.host.querySelector<HTMLElement>('.simulation-run-body');
    if (body)
      body.innerHTML = `<div class="simulation-run-state" role="status">${escapeHtml(message)}</div>`;
  }

  private renderRequestError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    const body = this.host.querySelector<HTMLElement>('.simulation-run-body');
    if (body)
      body.innerHTML = `<div class="simulation-run-state simulation-run-error" role="alert"><strong>Simulation unavailable</strong><span>${escapeHtml(message)}</span><button class="button secondary" type="button" data-run-action="retry">Edit configuration</button></div>`;
  }
}
