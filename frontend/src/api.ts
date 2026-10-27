import Ajv, { type ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.schema.json';
import type {
  AgentDetail,
  AgentPointList,
  Catalog,
  DailySnapshot,
  DecisionGraph,
  DSLConfig,
  DSLRender,
  DSLValidationResult,
  EnsembleUpdate,
  RunComplete,
  RunConfig,
  RunCreated,
  RunDetail,
  RunFailed,
  RunList,
  StoryDetail,
  StoryList,
} from './contracts.generated';

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addSchema(schema, 'contracts');

export function validator<T>(name: string): ValidateFunction<T> {
  const validate = ajv.getSchema<T>(`contracts#/$defs/${name}`);
  if (!validate) throw new Error(`Missing data contract: ${name}`);
  return validate;
}

const validators = {
  catalog: validator<Catalog>('Catalog'),
  created: validator<RunCreated>('RunCreated'),
  run: validator<RunDetail>('RunDetail'),
  list: validator<RunList>('RunList'),
  snapshot: validator<DailySnapshot>('DailySnapshot'),
  complete: validator<RunComplete>('RunComplete'),
  failed: validator<RunFailed>('RunFailed'),
  ensemble: validator<EnsembleUpdate>('EnsembleUpdate'),
  dsl: validator<DSLConfig>('DSLConfig'),
  dslValidation: validator<DSLValidationResult>('DSLValidationResult'),
  dslRender: validator<DSLRender>('DSLRender'),
  agentPoints: validator<AgentPointList>('AgentPointList'),
  agent: validator<AgentDetail>('AgentDetail'),
  stories: validator<StoryList>('StoryList'),
  story: validator<StoryDetail>('StoryDetail'),
  graph: validator<DecisionGraph>('DecisionGraph'),
};

export function parseContract<T>(data: unknown, validate: ValidateFunction<T>): T {
  if (!validate(data)) {
    throw new Error(
      `The server returned an invalid data contract: ${ajv.errorsText(validate.errors)}`,
    );
  }
  return data;
}

export async function request<T>(
  path: string,
  validate: ValidateFunction<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return parseContract(await response.json(), validate);
}

export const api = {
  catalog: () => request('/catalog', validators.catalog),
  list: () => request('/runs', validators.list),
  get: (id: string) => request(`/runs/${encodeURIComponent(id)}`, validators.run),
  create: (config: RunConfig) =>
    request('/runs', validators.created, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),
  smokeDSL: () => request('/dsl/smoke', validators.dsl),
  validateDSL: (dsl: DSLConfig) =>
    request('/dsl/validate', validators.dslValidation, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dsl),
    }),
  renderDSL: (dsl: DSLConfig) =>
    request('/dsl/render', validators.dslRender, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dsl),
    }),
  staticDecisionGraph: (dsl: DSLConfig, query = new URLSearchParams()) =>
    request(`/dsl/decision-graph?${query}`, validators.graph, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dsl),
    }),
  runDecisionGraph: (runId: string, query = new URLSearchParams()) =>
    request(
      `/runs/${encodeURIComponent(runId)}/decision-graph?${query}`,
      validators.graph,
    ),
  agents: (runId: string, place: string, day: number, limit = 5000) =>
    request(
      `/runs/${encodeURIComponent(runId)}/agents?place=${encodeURIComponent(place)}&day=${day}&limit=${limit}`,
      validators.agentPoints,
    ),
  agent: (agentId: string, runId: string) =>
    request(
      `/agents/${encodeURIComponent(agentId)}?run_id=${encodeURIComponent(runId)}`,
      validators.agent,
    ),
  stories: (runId: string) =>
    request(`/runs/${encodeURIComponent(runId)}/stories`, validators.stories),
  story: (storyId: string, runId: string) =>
    request(
      `/stories/${encodeURIComponent(storyId)}?run_id=${encodeURIComponent(runId)}`,
      validators.story,
    ),
  async delete(id: string): Promise<void> {
    let response: Response;
    try {
      response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch {
      throw new Error('Cannot reach the backend. Reconnect and try deleting again.');
    }
    if (!response.ok && response.status !== 404)
      throw new Error(`Could not delete run (${response.status})`);
  },
};

export type StreamHandlers = {
  snapshot: (snapshot: DailySnapshot, sequence: number) => void;
  ensemble: (update: EnsembleUpdate, sequence: number) => void;
  complete: (result: RunComplete, sequence: number) => void;
  failed: (result: RunFailed, sequence: number) => void;
  connection: (state: 'connected' | 'reconnecting') => void;
  error: (message: string) => void;
};

export class RunStream {
  private source: EventSource | null = null;
  private sequence: number;
  private disposed = false;
  private terminal = false;
  private reconnectTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private runId: string,
    after: number,
    private handlers: StreamHandlers,
  ) {
    this.sequence = after;
    document.addEventListener('visibilitychange', this.onVisibility);
    this.resume();
  }

  private consume<T>(
    event: MessageEvent,
    validate: ValidateFunction<T>,
    callback: (value: T, sequence: number) => void,
  ): void {
    try {
      const sequence = Number(event.lastEventId);
      if (!Number.isInteger(sequence) || sequence < 1)
        throw new Error('Invalid stream sequence ID');
      if (sequence <= this.sequence) return;
      if (sequence !== this.sequence + 1)
        throw new Error('A recorded day is missing. Reopen this run to resync.');
      const value = parseContract(JSON.parse(event.data), validate);
      callback(value, sequence);
      this.sequence = sequence;
    } catch (error) {
      this.source?.close();
      this.source = null;
      this.handlers.error(error instanceof Error ? error.message : 'Invalid stream event');
    }
  }

  private resume(): void {
    if (this.disposed || this.terminal || document.hidden || this.source) return;
    this.source = new EventSource(
      `/api/runs/${encodeURIComponent(this.runId)}/stream?after=${this.sequence}`,
    );
    this.source.onopen = () => this.handlers.connection('connected');
    this.source.onerror = () => {
      if (this.disposed || this.terminal) return;
      this.source?.close();
      this.source = null;
      this.handlers.connection('reconnecting');
      this.reconnectTimer = setTimeout(() => this.resume(), 1500);
    };
    this.source.addEventListener('snapshot', (event) =>
      this.consume(event as MessageEvent, validators.snapshot, this.handlers.snapshot),
    );
    this.source.addEventListener('ensemble_update', (event) =>
      this.consume(event as MessageEvent, validators.ensemble, this.handlers.ensemble),
    );
    this.source.addEventListener('run-complete', (event) => {
      this.consume(event as MessageEvent, validators.complete, this.handlers.complete);
      this.terminal = true;
      this.source?.close();
      this.source = null;
    });
    this.source.addEventListener('run-failed', (event) => {
      this.consume(event as MessageEvent, validators.failed, this.handlers.failed);
      this.terminal = true;
      this.source?.close();
      this.source = null;
    });
  }

  private onVisibility = (): void => {
    if (document.hidden) {
      clearTimeout(this.reconnectTimer);
      this.source?.close();
      this.source = null;
    } else this.resume();
  };

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.reconnectTimer);
    this.source?.close();
    this.source = null;
    document.removeEventListener('visibilitychange', this.onVisibility);
  }
}
