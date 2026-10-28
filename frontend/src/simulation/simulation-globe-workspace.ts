import {
  simulationGlobeRecordsFromRunStatistics,
  type SimulationRunAggregateApiRecord,
} from './run-globe-adapter';
import type {
  SimulationGlobeAgentViewportRequest,
  SimulationGlobeAgentViewportResponse,
  SimulationGlobeAggregateEvidence,
} from './run-globe-types';
import { SimulationRunGlobe } from './simulation-run-globe';

interface GlobeRunSummary {
  run_id: string;
  status: string;
  aggregate_statistics_version?: string | null;
  total_ticks: number;
  config: {
    population_size: number;
    days: number;
    start_date: string;
    tick_interval_hours: number;
  };
}

interface GlobeStatisticsPage {
  items: Array<
    SimulationRunAggregateApiRecord & {
    latitude: number | null;
    longitude: number | null;
    parent_place_id: string | null;
    }
  >;
  total: number;
}

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

async function requestJson<Value>(path: string, init?: RequestInit): Promise<Value> {
  const response = await fetch(`/api${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as Value;
}

const aggregateEvidence = (programVersion: string): SimulationGlobeAggregateEvidence => ({
  population: {
    status: 'estimated',
    source: 'Recorded representative population weights',
    source_version: programVersion,
  },
  employment: {
    status: 'estimated',
    source: 'Recorded DSL employment predicates and agent states',
    source_version: programVersion,
  },
  agent_type_mix: {
    status: 'estimated',
    source: 'Recorded synthetic initial population',
    source_version: programVersion,
  },
  action_rates: {
    status: 'estimated',
    source: 'Recorded DSL action counters',
    source_version: programVersion,
  },
});

export class SimulationGlobeWorkspace {
  private globe?: SimulationRunGlobe;
  private runs: GlobeRunSummary[] = [];
  private selectedRunId = '';
  private requestVersion = 0;
  private active = false;

  constructor(private readonly host: HTMLElement) {
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('click', this.onClick);
    this.renderLoading('Loading recorded global runs…');
  }

  activate(): void {
    this.active = true;
    this.globe?.setVisible(true);
    void this.loadRuns();
  }

  deactivate(): void {
    this.active = false;
    this.globe?.setVisible(false);
  }

  dispose(): void {
    this.requestVersion += 1;
    this.globe?.dispose();
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private readonly onChange = (event: Event): void => {
    const select = event.target instanceof HTMLSelectElement ? event.target : null;
    if (select?.name !== 'simulation-globe-run') return;
    this.selectedRunId = select.value;
    void this.loadStatistics();
  };

  private readonly onClick = (event: Event): void => {
    const action =
      event.target instanceof Element
        ? event.target.closest<HTMLElement>('[data-globe-workspace-action]')?.dataset
            .globeWorkspaceAction
        : undefined;
    if (action === 'retry') void this.loadRuns();
  };

  private async loadRuns(): Promise<void> {
    const version = ++this.requestVersion;
    try {
      const runs = await requestJson<GlobeRunSummary[]>('/simulation/runs');
      if (version !== this.requestVersion) return;
      this.runs = runs.filter(
        (run) => run.status === 'completed' && Boolean(run.aggregate_statistics_version),
      );
      if (!this.runs.length) {
        this.globe?.dispose();
        this.globe = undefined;
        this.host.innerHTML =
          '<section class="simulation-globe-workspace-empty"><h2>Simulation globe</h2><p>Complete a run with aggregate statistics to explore it here.</p></section>';
        return;
      }
      if (!this.runs.some((run) => run.run_id === this.selectedRunId)) {
        this.selectedRunId = this.runs[0]!.run_id;
      }
      await this.loadStatistics(version);
    } catch (error) {
      if (version !== this.requestVersion) return;
      this.renderError(error);
    }
  }

  private async loadStatistics(parentVersion?: number): Promise<void> {
    const version = parentVersion ?? ++this.requestVersion;
    const selected = this.runs.find((run) => run.run_id === this.selectedRunId);
    if (!selected) return;
    this.renderLoading('Loading recorded country and region statistics…');
    try {
      const page = await requestJson<GlobeStatisticsPage>(
        `/simulation/runs/${encodeURIComponent(selected.run_id)}/statistics?page_size=1000`,
      );
      if (version !== this.requestVersion) return;
      const geographicRows = page.items.filter(
        (
          row,
        ): row is typeof row & {
          place_level: 'country' | 'region';
          latitude: number;
          longitude: number;
        } => row.place_level !== 'global' && row.latitude !== null && row.longitude !== null,
      );
      if (!geographicRows.length) {
        throw new Error('This run has no recorded geographic aggregate coordinates.');
      }
      const metadata = geographicRows.map((row) => ({
        place_level: row.place_level,
        place_id: row.place_id,
        latitude: row.latitude,
        longitude: row.longitude,
        parent_place_id: row.parent_place_id,
        evidence: aggregateEvidence(row.program_version),
      }));
      const records = simulationGlobeRecordsFromRunStatistics(page.items, metadata);
      this.globe?.dispose();
      this.host.innerHTML = `<div class="simulation-globe-workspace-run"><label>Saved run<select name="simulation-globe-run">${this.runs.map((run) => `<option value="${escapeHtml(run.run_id)}"${run.run_id === selected.run_id ? ' selected' : ''}>${run.config.population_size.toLocaleString()} agents · ${run.config.days} days · ${escapeHtml(run.config.start_date)}</option>`).join('')}</select></label><span>${page.total.toLocaleString()} place/day records</span></div><div data-simulation-run-globe></div>`;
      this.globe = new SimulationRunGlobe(
        this.host.querySelector<HTMLElement>('[data-simulation-run-globe]')!,
        {
          records,
          total_ticks: selected.total_ticks,
          ticks_per_day: Math.round(24 / selected.config.tick_interval_hours),
          load_agent_points: (request) => this.loadAgentPoints(request),
        },
      );
      this.globe.setVisible(this.active);
    } catch (error) {
      if (version !== this.requestVersion) return;
      this.renderError(error);
    }
  }

  private loadAgentPoints(
    request: SimulationGlobeAgentViewportRequest,
  ): Promise<SimulationGlobeAgentViewportResponse> {
    const query = new URLSearchParams({
      day: String(request.day),
      tick: String(request.tick),
      detail_level: request.detail_level,
      north: String(request.bounds.north),
      east: String(request.bounds.east),
      south: String(request.bounds.south),
      west: String(request.bounds.west),
    });
    request.visible_city_ids.forEach((cityId) => query.append('city_id', cityId));
    return requestJson<SimulationGlobeAgentViewportResponse>(
      `/simulation/runs/${encodeURIComponent(request.run_id)}/spatial-points?${query}`,
    );
  }

  private renderLoading(message: string): void {
    this.host.innerHTML = `<div class="simulation-tree-loading" role="status">${escapeHtml(message)}</div>`;
  }

  private renderError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.host.innerHTML = `<div class="simulation-tree-loading error" role="alert"><span>${escapeHtml(message)}</span><button class="button secondary" type="button" data-globe-workspace-action="retry">Retry</button></div>`;
  }
}
