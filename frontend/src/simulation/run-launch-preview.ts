import './run-launch-preview.css';
import {
  runEvidenceMarkup,
  type RunEvidenceSummary,
  type RunEvidenceWarning,
} from './run-evidence';

export interface SimulationRunPreviewConfig {
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

export interface SimulationRunPreview {
  config: SimulationRunPreviewConfig;
  agent_count: number;
  total_ticks: number;
  data_version: string;
  program_version: string;
  default_dsl_version: string | null;
  default_dsl_hash: string | null;
  evidence_summary: RunEvidenceSummary;
  evidence_warnings: RunEvidenceWarning[];
}

export interface SimulationRunPreviewClient {
  preview(config: SimulationRunPreviewConfig): Promise<SimulationRunPreview>;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

function requirePreview(value: unknown): SimulationRunPreview {
  if (
    !isRecord(value) ||
    !isRecord(value.config) ||
    typeof value.agent_count !== 'number' ||
    typeof value.total_ticks !== 'number' ||
    typeof value.data_version !== 'string' ||
    typeof value.program_version !== 'string' ||
    !isRecord(value.evidence_summary) ||
    !Array.isArray(value.evidence_warnings)
  ) {
    throw new Error('The server returned an invalid simulation preview contract.');
  }
  return value as unknown as SimulationRunPreview;
}

async function requestJson(path: string, init: RequestInit): Promise<unknown> {
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
      typeof detail === 'string' ? detail : `Simulation preview failed (${response.status})`,
    );
  }
  return body;
}

export function createSimulationRunPreviewHttpClient(
  path = '/api/simulation/runs/preview',
): SimulationRunPreviewClient {
  return {
    preview: async (config) =>
      requirePreview(
        await requestJson(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        }),
      ),
  };
}

export class SimulationLaunchEvidencePreview {
  private requestVersion = 0;
  private disposed = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: SimulationRunPreviewClient = createSimulationRunPreviewHttpClient(),
  ) {
    this.host.classList.add('simulation-run-launch-preview-host');
  }

  async load(config: SimulationRunPreviewConfig): Promise<boolean> {
    const version = ++this.requestVersion;
    this.renderStatus('Preparing agents and resolving evidence…', 'status');
    try {
      const preview = await this.client.preview(config);
      if (this.disposed || version !== this.requestVersion) return false;
      this.renderPreview(preview);
      return true;
    } catch (error) {
      if (this.disposed || version !== this.requestVersion) return false;
      this.renderStatus(error instanceof Error ? error.message : String(error), 'alert');
      return false;
    }
  }

  clear(): void {
    this.requestVersion += 1;
    this.host.replaceChildren();
  }

  dispose(): void {
    this.disposed = true;
    this.clear();
  }

  private renderStatus(message: string, role: 'status' | 'alert'): void {
    this.host.innerHTML = `<section class="simulation-run-launch-preview is-${role}" role="${role}" aria-label="Simulation launch evidence"><span>${escapeHtml(message)}</span></section>`;
  }

  private renderPreview(preview: SimulationRunPreview): void {
    const identity =
      preview.default_dsl_version && preview.default_dsl_hash
        ? `<strong>Default DSL ${escapeHtml(preview.default_dsl_version)}</strong><span title="${escapeHtml(preview.default_dsl_hash)}">${escapeHtml(preview.default_dsl_hash.slice(0, 19))}…</span>`
        : '<strong>No installed default DSL identity</strong>';
    this.host.innerHTML = `<section class="simulation-run-launch-preview" role="region" aria-label="Simulation launch evidence"><header><div><span class="small-label">Review before launch</span><h3>Resolved run evidence</h3></div><div class="simulation-run-launch-preview-size"><strong>${preview.agent_count.toLocaleString('en')} agents · ${preview.total_ticks.toLocaleString('en')} ticks</strong><span>${escapeHtml(preview.config.place_scope.identifier ?? 'Global')}</span></div></header><div class="simulation-run-launch-preview-identity">${identity}<span>Program ${escapeHtml(preview.program_version)}</span><span>Data ${escapeHtml(preview.data_version)}</span></div>${runEvidenceMarkup(preview.evidence_summary, preview.evidence_warnings)}</section>`;
  }
}
