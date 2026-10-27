import './styles.css';
import { api, RunStream } from './api';
import { DataTab } from './atlas/main';
import { InfectionChart, metricTotal, primaryMetricName } from './chart';
import type {
  AgentDetail,
  Catalog,
  DailySnapshot,
  DSLConfig,
  RunConfig,
  RunDetail,
  RunSummary,
} from './contracts.generated';
import { DSLBuilder } from './dsl-builder/main';
import { Globe } from './globe';
import { StoriesView } from './stories/main';
import { countryOptions, defaults, escapeHtml, savedRunList, shell } from './views';

const element = <T extends HTMLElement = HTMLElement>(id: string): T => {
  const result = document.getElementById(id);
  if (!result) throw new Error(`Missing interface element ${id}`);
  return result as T;
};
const number = (value: number): string => value.toLocaleString('en');
const text = (id: string, value: string): void => {
  element(id).textContent = value;
};

class Lab {
  private dataTab: DataTab;
  private dslBuilder: DSLBuilder;
  private stories: StoriesView;
  private tab: 'simulation' | 'stories' | 'dsl' | 'data' = 'simulation';
  private catalog?: Catalog;
  private runs: RunSummary[] = [];
  private active?: RunDetail;
  private stream?: RunStream;
  private globe?: Globe;
  private chart: InfectionChart;
  private index = 0;
  private timer?: ReturnType<typeof setInterval>;
  private playing = false;
  private generation = 0;
  private deleting?: string;

  constructor() {
    element('app').innerHTML = shell();
    this.dataTab = new DataTab(element('data-view'));
    this.dslBuilder = new DSLBuilder(element('dsl-view'), (dsl, seed) =>
      this.runDSL(dsl, seed),
    );
    this.stories = new StoriesView(
      element('stories-view'),
      (place, day) => void this.openPlace(place, day),
      (agentId) => void this.showAgent(agentId),
    );
    this.chart = new InfectionChart(element<HTMLCanvasElement>('infection-chart'), (index) =>
      this.selectDay(index),
    );
    document.addEventListener('click', this.onClick);
    element('run-form').addEventListener('submit', this.onSubmit);
    element<HTMLInputElement>('timeline').addEventListener('input', (event) =>
      this.selectDay(Number((event.target as HTMLInputElement).value)),
    );
    element('playback-speed').addEventListener('change', () => {
      if (this.playing) this.setPlaying(true);
    });
    for (const id of ['new-run-dialog', 'delete-dialog', 'agent-dialog']) {
      element<HTMLDialogElement>(id).addEventListener('close', () => this.resumeView());
    }
    window.addEventListener('pagehide', () => this.dispose(), { once: true });
    void this.load();
  }

  private async load(): Promise<void> {
    try {
      const [catalog, list] = await Promise.all([api.catalog(), api.list()]);
      this.catalog = catalog;
      this.runs = list.runs;
      text('api-status', 'API connected');
      element('api-status').classList.add('connected');
      element('country-options').innerHTML = countryOptions(catalog);
      document.querySelectorAll<HTMLButtonElement>('[data-action="new"]').forEach((button) => {
        button.disabled = false;
      });
      if (!this.globe) {
        try {
          this.globe = new Globe(element('globe'), catalog.countries, {
            place: (place, day) => void this.openPlace(place, day),
            agent: (agentId) => void this.showAgent(agentId),
          });
        } catch {
          element('globe').innerHTML =
            '<div class="globe-fallback">Globe unavailable in this browser.<br>Every recorded value is available in the table below.</div>';
        }
      }
      this.refreshListView();
      element('error-banner').hidden = true;
      this.renderSnapshot();
    } catch (error) {
      text('api-status', 'API offline');
      element('api-status').classList.remove('connected');
      this.showError(error);
      element('run-list').innerHTML =
        '<li class="sidebar-empty">The backend is offline.<br>Start the API and select Retry.</li>';
    }
  }

  private refreshListView(): void {
    element('run-list').innerHTML = savedRunList(this.runs, this.active?.run_id);
  }

  private async refreshList(): Promise<void> {
    this.runs = (await api.list()).runs;
    this.refreshListView();
  }

  private showError(error: unknown): void {
    text('error-message', error instanceof Error ? error.message : String(error));
    element('error-banner').hidden = false;
  }

  private suspendView(): void {
    this.setPlaying(false);
    this.globe?.setVisible(false);
    this.stream?.dispose();
    this.stream = undefined;
  }

  private resumeView(): void {
    if (this.tab !== 'simulation') return;
    this.globe?.setVisible(true);
    this.attachStream();
  }

  private showNew(): void {
    if (!this.catalog) return;
    this.suspendView();
    element('form-error').hidden = true;
    element<HTMLDialogElement>('new-run-dialog').showModal();
  }

  private onSubmit = async (event: SubmitEvent): Promise<void> => {
    event.preventDefault();
    const form = element<HTMLFormElement>('run-form');
    const fields = new FormData(form);
    const countries = fields.getAll('countries') as RunConfig['countries'];
    const read = (name: string) => Number(fields.get(name));
    const config: RunConfig = {
      ...defaults,
      countries,
      start_day: read('start_day'),
      end_day: read('end_day'),
      seed: read('seed'),
      parameters: {
        transmission: read('transmission'),
        progression: read('progression'),
        recovery: read('recovery'),
        mixing: read('mixing'),
        initial_infected: read('initial_infected'),
      },
    };
    if (
      !countries.length ||
      config.end_day <= config.start_day ||
      config.end_day - config.start_day > 730
    ) {
      text(
        'form-error',
        !countries.length
          ? 'Select at least one country.'
          : 'End day must be 1–730 days after start day.',
      );
      element('form-error').hidden = false;
      return;
    }
    const launch = element<HTMLButtonElement>('launch-button');
    launch.disabled = true;
    launch.textContent = 'Launching…';
    try {
      const run = await api.create(config);
      element<HTMLDialogElement>('new-run-dialog').close();
      this.useRun(run, true);
      if (run.cached) {
        text(
          'stream-message',
          'Identical configuration found. Replaying the existing recorded run.',
        );
        element('stream-notice').hidden = false;
      }
      await this.refreshList();
    } catch (error) {
      text('form-error', error instanceof Error ? error.message : String(error));
      element('form-error').hidden = false;
    } finally {
      launch.disabled = false;
      launch.innerHTML = 'Launch experiment <span>↗</span>';
    }
  };

  private async runDSL(dsl: DSLConfig, seed: number): Promise<void> {
    const durationDays = Math.max(
      1,
      Math.ceil(((dsl.tick.tick_hours ?? 24) * (dsl.tick.total_ticks ?? 30)) / 24),
    );
    const config: RunConfig = {
      scenario: dsl.id,
      countries: [...dsl.population.places],
      start_day: 0,
      end_day: durationDays,
      seed,
      parameters: defaults.parameters,
      dsl,
      population: dsl.population,
      tick: dsl.tick,
      outputs: dsl.outputs,
      evidence_table_version: 'FAKE-evidence-v1',
    };
    const run = await api.create(config);
    this.useRun(run, true);
    if (run.cached) {
      text('stream-message', 'Identical DSL, population, evidence version, and seed found.');
      element('stream-notice').hidden = false;
    }
    await this.refreshList();
  }

  private async openPlace(place: string, day: number): Promise<void> {
    if (!this.active) return;
    this.changeTab('simulation');
    const index = this.active.snapshots.findIndex((snapshot) => snapshot.day === day);
    if (index >= 0) {
      this.index = index;
      this.renderSnapshot();
    }
    try {
      const agents = await api.agents(this.active.run_id, place, day);
      this.globe?.showAgents(agents.agents, place);
      text(
        'agent-lod-status',
        `${agents.returned.toLocaleString()} of ${agents.total.toLocaleString()} representative synthetic agents · click any dot`,
      );
      element('agent-lod-notice').hidden = false;
    } catch (error) {
      this.showError(error);
    }
  }

  private async showAgent(agentId: string): Promise<void> {
    if (!this.active) return;
    try {
      const agent = await api.agent(agentId, this.active.run_id);
      this.renderAgent(agent);
      this.suspendView();
      element<HTMLDialogElement>('agent-dialog').showModal();
    } catch (error) {
      this.showError(error);
    }
  }

  private renderAgent(agent: AgentDetail): void {
    text('agent-title', `Synthetic agent ${agent.agent_id.slice(0, 10)}`);
    text('agent-scope', agent.log_scope);
    element('agent-content').innerHTML = `
      <div class="agent-summary"><span>${escapeHtml(agent.place)}</span><span>${escapeHtml(agent.role)}</span><span>${escapeHtml(agent.log_tier)}</span></div>
      <section><h3>Current states</h3><dl>${Object.entries(agent.states).map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl></section>
      <section><h3>Traits</h3><dl>${Object.entries(agent.traits).map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join('')}</dl></section>
      <section><h3>Timeline and logged causes</h3><ol>${agent.timeline.map((entry) => `<li><span>Day ${entry.day} · tick ${entry.tick}</span><strong>${escapeHtml(entry.action)}</strong><small>${Object.entries(entry.causes).map(([cause, magnitude]) => `${escapeHtml(cause)} ${magnitude >= 0 ? '+' : ''}${magnitude}`).join(' · ') || 'No causal magnitude was logged for this entry.'}</small></li>`).join('')}</ol></section>
      <section><h3>Relationships</h3><ul>${agent.relationships.map((relationship) => `<li>${escapeHtml(relationship.kind)} · ${escapeHtml(relationship.target_id.slice(0, 10))} · weight ${relationship.weight}</li>`).join('') || '<li>No sampled relationship in this representative row.</li>'}</ul></section>`;
  }

  private async openRun(id: string): Promise<void> {
    const generation = ++this.generation;
    this.stream?.dispose();
    this.stream = undefined;
    this.setPlaying(false);
    try {
      const run = await api.get(id);
      if (generation !== this.generation) return;
      this.useRun(run);
      element('error-banner').hidden = true;
    } catch (error) {
      this.showError(error);
    }
  }

  private useRun(run: RunDetail, autoplay = false): void {
    if (this.tab !== 'simulation') this.changeTab('simulation');
    ++this.generation;
    this.stream?.dispose();
    this.stream = undefined;
    this.active = run;
    this.globe?.clearAgents();
    element('agent-lod-notice').hidden = true;
    this.index = autoplay ? 0 : Math.max(0, run.snapshots.length - 1);
    element('empty-state').hidden = true;
    element('stream-notice').hidden = true;
    text('run-id', `RUN ${run.run_id.slice(0, 10).toUpperCase()}`);
    const ensemble = run.ensemble_updates.at(-1);
    text(
      'ensemble-status',
      ensemble
        ? `${ensemble.completed}/${ensemble.total} ensemble samples recorded`
        : 'Ensemble update pending',
    );
    this.renderStatus();
    this.renderSnapshot();
    this.refreshListView();
    this.attachStream();
    void this.stories.setRun(run).catch((error) => this.showError(error));
    this.setPlaying(autoplay);
  }

  private attachStream(): void {
    if (!this.active || this.stream || ['done', 'failed'].includes(this.active.status)) return;
    const run = this.active;
    this.stream = new RunStream(run.run_id, run.last_sequence, {
      snapshot: (snapshot, sequence) => {
        if (snapshot.run_id !== run.run_id || snapshot.seed !== run.config.seed)
          throw new Error('Snapshot provenance does not match this run');
        if (snapshot.day !== run.config.start_day + run.snapshots.length)
          throw new Error('Snapshot day is out of order');
        run.snapshots.push(snapshot);
        run.last_sequence = sequence;
        run.status = 'running';
        this.renderStatus();
        this.renderSnapshot();
      },
      ensemble: (update, sequence) => {
        run.ensemble_updates.push(update);
        run.last_sequence = sequence;
        text('ensemble-status', `${update.completed}/${update.total} ensemble samples recorded`);
      },
      complete: (result, sequence) => {
        if (result.run_id !== run.run_id) throw new Error('Completion does not match this run');
        run.status = 'done';
        run.metrics = result.metrics;
        run.last_sequence = sequence;
        this.stream?.dispose();
        this.stream = undefined;
        element('stream-notice').hidden = true;
        this.renderStatus();
        this.renderSnapshot();
        void api
          .get(run.run_id)
          .then((latest) => {
            this.active = latest;
            return this.stories.setRun(latest);
          })
          .catch((error) => this.showError(error));
        void this.refreshList().catch((error) => this.showError(error));
      },
      failed: (result, sequence) => {
        run.status = 'failed';
        run.error = result.error;
        run.last_sequence = sequence;
        this.stream?.dispose();
        this.stream = undefined;
        this.setPlaying(false);
        this.renderStatus();
        this.showError(new Error(result.error.message));
        void this.refreshList().catch((error) => this.showError(error));
      },
      connection: (state) => {
        element('stream-notice').hidden = state === 'connected';
        if (state === 'reconnecting')
          text(
            'stream-message',
            `Connection lost. Reconnecting after recorded event ${run.last_sequence}.`,
          );
      },
      error: (message) => {
        this.setPlaying(false);
        this.showError(new Error(message));
      },
    });
  }

  private renderStatus(): void {
    const status = this.active?.status;
    const target = element('run-status');
    target.className = `status-pill ${status ?? ''}`;
    target.textContent =
      status === 'done'
        ? '✓ Run complete'
        : status === 'running'
          ? '● Recording days'
          : status === 'queued'
            ? '◷ Queued'
            : status === 'failed'
              ? 'Run failed'
              : 'Ready to explore';
    if (this.active?.error) this.showError(new Error(this.active.error.message));
  }

  private renderSnapshot(): void {
    const snapshots = this.active?.snapshots ?? [];
    const snapshot = snapshots[this.index];
    const timeline = element<HTMLInputElement>('timeline');
    timeline.max = String(Math.max(0, snapshots.length - 1));
    timeline.value = String(this.index);
    timeline.disabled = snapshots.length === 0;
    timeline.style.setProperty(
      '--progress',
      `${snapshots.length > 1 ? (this.index / (snapshots.length - 1)) * 100 : 0}%`,
    );
    element<HTMLButtonElement>('play-button').disabled = snapshots.length === 0;
    text('record-count', `${snapshots.length} DAYS RECORDED`);
    text('timeline-end', snapshots.length ? String(snapshots.at(-1)!.day).padStart(3, '0') : '—');
    this.chart.update(snapshots, this.index);
    this.globe?.update(snapshot);
    if (!snapshot) {
      for (const id of ['metric-infected', 'metric-peak', 'metric-recovered', 'metric-population'])
        text(id, '—');
      text('metric-day', 'Waiting for a recorded day');
      text('metric-peak-day', 'Computed at run completion');
      return;
    }
    const metric = primaryMetricName(snapshot);
    const stateValues = Object.values(snapshot.places[0]?.states ?? {})[0] ?? {};
    const secondary = Object.keys(stateValues).at(-1) ?? metric;
    const population = snapshot.places.reduce((sum, place) => {
      const first = Object.values(place.states)[0];
      return sum + (first ? Object.values(first).reduce((total, value) => total + value, 0) : 0);
    }, 0);
    text('metric-infected', number(metricTotal(snapshot, metric)));
    text('metric-primary-label', metric.replaceAll('_', ' '));
    text('metric-day', `Day ${snapshot.day} · ${snapshot.places.length} places`);
    text('metric-recovered', number(metricTotal(snapshot, secondary)));
    text('metric-secondary-label', secondary.replaceAll('_', ' '));
    text('metric-population', number(population));
    text('metric-countries', `${snapshot.places.length} recorded place compartments`);
    const peak = this.active?.metrics?.metric_peaks[metric];
    text('metric-peak', peak ? number(peak.value) : '—');
    text(
      'metric-peak-day',
      peak
        ? `${metric.replaceAll('_', ' ')} peaked on day ${peak.day}`
        : 'Computed at run completion',
    );
    text('globe-day', `DAY ${String(snapshot.day).padStart(3, '0')}`);
    text('timeline-day', `DAY ${String(snapshot.day).padStart(3, '0')}`);
    text('country-count', String(snapshot.places.length).padStart(2, '0'));
    this.renderCountries(snapshot);
    text(
      'provenance',
      `DAY ${snapshot.day} · SEED ${snapshot.seed} · ENGINE ${snapshot.engine_version} · DATA ${snapshot.data_version}`,
    );
    const columns = Object.entries(snapshot.places[0]?.states ?? {}).flatMap(
      ([state, values]) => Object.keys(values).map((value) => ({ state, value })),
    );
    element('snapshot-head').innerHTML = `<tr><th scope="col">Place</th>${columns.map(({ state, value }) => `<th scope="col">${escapeHtml(state)} · ${escapeHtml(value)}</th>`).join('')}<th scope="col">Population</th></tr>`;
    element('snapshot-table').innerHTML = snapshot.places
      .map((place) => {
        const total = Object.values(Object.values(place.states)[0] ?? {}).reduce(
          (sum, value) => sum + value,
          0,
        );
        return `<tr><th scope="row">${this.countryName(place.country)}</th>${columns.map(({ state, value }) => `<td class="${value === metric ? 'infected-cell' : ''}">${number(place.states[state]?.[value] ?? 0)}</td>`).join('')}<td>${number(total)}</td></tr>`;
      })
      .join('');
    text(
      'config-receipt',
      `CONFIG HASH ${this.active!.config_hash} · CONTRACT ${this.catalog?.contract_version ?? '1'}`,
    );
  }

  private countryName(code: string): string {
    return escapeHtml(
      this.catalog?.countries.find((country) => country.country === code)?.name ?? code,
    );
  }

  private renderCountries(snapshot: DailySnapshot): void {
    const metric = primaryMetricName(snapshot);
    element('country-list').innerHTML = snapshot.places
      .map((place) => {
        const first = Object.values(place.states)[0] ?? {};
        const population = Object.values(first).reduce((sum, value) => sum + value, 0);
        const value = place.metrics[metric] ?? 0;
        const percentage = population ? (value / population) * 100 : 0;
        return `<button class="country-row" data-place="${escapeHtml(place.country)}" data-day="${snapshot.day}"><div class="country-row-top"><span><span class="country-code">${escapeHtml(place.country)}</span>${this.countryName(place.country)}</span><strong>${number(value)}</strong></div><div class="country-bar"><span style="width:${percentage}%"></span></div><div class="country-row-bottom"><span>${percentage.toFixed(2)}% ${escapeHtml(metric)}</span><span>${number(population)} people</span></div></button>`;
      })
      .join('');
  }

  private selectDay(index: number): void {
    this.setPlaying(false);
    this.index = index;
    this.renderSnapshot();
  }

  private setPlaying(playing: boolean): void {
    clearInterval(this.timer);
    this.playing = playing;
    const button = element<HTMLButtonElement>('play-button');
    button.textContent = playing ? 'Ⅱ' : '▶';
    button.setAttribute('aria-label', playing ? 'Pause timeline' : 'Play timeline');
    if (!playing) return;
    if (this.active?.status === 'done' && this.index === this.active.snapshots.length - 1)
      this.index = 0;
    this.timer = setInterval(
      () => {
        if (document.hidden) return;
        const count = this.active?.snapshots.length ?? 0;
        if (this.index + 1 < count) {
          this.index++;
          this.renderSnapshot();
        } else if (this.active?.status === 'done' || this.active?.status === 'failed')
          this.setPlaying(false);
      },
      Number(element<HTMLSelectElement>('playback-speed').value),
    );
  }

  private showDelete(id: string): void {
    const run = this.runs.find((value) => value.run_id === id);
    if (!run) return;
    this.deleting = id;
    this.suspendView();
    text(
      'delete-description',
      `${run.config.scenario} #${run.config.seed} · ${run.config.countries.length} places · run ${id.slice(0, 8)}`,
    );
    element('delete-error').hidden = true;
    element<HTMLDialogElement>('delete-dialog').showModal();
  }

  private async confirmDelete(): Promise<void> {
    if (!this.deleting) return;
    const button = element<HTMLButtonElement>('confirm-delete');
    button.disabled = true;
    try {
      await api.delete(this.deleting);
      if (this.active?.run_id === this.deleting) this.clearRun();
      await this.refreshList();
      element<HTMLDialogElement>('delete-dialog').close();
      this.deleting = undefined;
    } catch (error) {
      text('delete-error', error instanceof Error ? error.message : String(error));
      element('delete-error').hidden = false;
    } finally {
      button.disabled = false;
    }
  }

  private clearRun(): void {
    ++this.generation;
    this.stream?.dispose();
    this.stream = undefined;
    this.setPlaying(false);
    this.active = undefined;
    this.globe?.clearAgents();
    element('agent-lod-notice').hidden = true;
    void this.stories.setRun(undefined);
    this.index = 0;
    element('empty-state').hidden = false;
    element('stream-notice').hidden = true;
    for (const id of ['metric-infected', 'metric-peak', 'metric-recovered', 'metric-population'])
      text(id, '—');
    text('metric-day', 'Waiting for a recorded day');
    text('metric-peak-day', 'Computed at run completion');
    text('metric-countries', '4 available fake countries');
    text('run-id', 'NO ACTIVE RUN');
    text('globe-day', 'DAY —');
    text('timeline-day', 'DAY —');
    text('country-count', '00');
    text('provenance', 'No snapshot selected.');
    text('config-receipt', '');
    text('ensemble-status', 'Ensemble update pending');
    element('country-list').innerHTML =
      '<p class="muted empty-country">Launch an experiment to see the place breakdown.</p>';
    element('snapshot-table').innerHTML = '';
    this.renderStatus();
    this.renderSnapshot();
  }

  private exportRun(format: 'json' | 'csv'): void {
    if (!this.active?.snapshots.length) {
      this.showError(new Error('Create a run before exporting recorded results.'));
      return;
    }
    const run = this.active;
    const contents =
      format === 'json'
        ? JSON.stringify(run, null, 2)
        : [
            'run_id,day,country,susceptible,exposed,infected,recovered,seed,engine_version,data_version',
            ...run.snapshots.flatMap((snapshot) =>
              snapshot.places.map((place) =>
                [
                  snapshot.run_id,
                  snapshot.day,
                  place.country,
                  place.susceptible,
                  place.exposed,
                  place.infected,
                  place.recovered,
                  snapshot.seed,
                  snapshot.engine_version,
                  snapshot.data_version,
                ].join(','),
              ),
            ),
          ].join('\n');
    const url = URL.createObjectURL(
      new Blob([contents], { type: format === 'json' ? 'application/json' : 'text/csv' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `petraterrium-FAKE-${run.run_id.slice(0, 8)}.${format}`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  private onClick = (event: MouseEvent): void => {
    const place = (event.target as HTMLElement).closest<HTMLElement>('[data-place]');
    if (place?.dataset.place) {
      void this.openPlace(place.dataset.place, Number(place.dataset.day));
      return;
    }
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!target || (target instanceof HTMLButtonElement && target.disabled)) return;
    const action = target.dataset.action;
    if (action === 'data-tab') this.changeTab('data');
    else if (action === 'dsl-tab') this.changeTab('dsl');
    else if (action === 'stories-tab') this.changeTab('stories');
    else if (action === 'simulation-tab') this.changeTab('simulation');
    else if (action === 'new') this.showNew();
    else if (action === 'cancel-new') element<HTMLDialogElement>('new-run-dialog').close();
    else if (action === 'cancel-delete') element<HTMLDialogElement>('delete-dialog').close();
    else if (action === 'close-agent') element<HTMLDialogElement>('agent-dialog').close();
    else if (action === 'world-view') {
      this.globe?.clearAgents();
      element('agent-lod-notice').hidden = true;
    }
    else if (action === 'play') this.setPlaying(!this.playing);
    else if (action === 'open' && target.dataset.id) void this.openRun(target.dataset.id);
    else if (action === 'delete' && target.dataset.id) this.showDelete(target.dataset.id);
    else if (action === 'confirm-delete') void this.confirmDelete();
    else if (action === 'dismiss-error') element('error-banner').hidden = true;
    else if (action === 'retry') {
      if (this.active) void this.openRun(this.active.run_id);
      else void this.load();
    } else if (action === 'reconnect' && this.active) void this.openRun(this.active.run_id);
    else if (action === 'refresh') void this.refreshList().catch((error) => this.showError(error));
    else if (action === 'export-json') this.exportRun('json');
    else if (action === 'export-csv') this.exportRun('csv');
  };

  private dispose(): void {
    this.dataTab.deactivate();
    this.dslBuilder.deactivate();
    this.stories.deactivate();
    clearInterval(this.timer);
    this.stream?.dispose();
    this.globe?.dispose();
    this.chart.dispose();
    document.removeEventListener('click', this.onClick);
  }

  private changeTab(tab: 'simulation' | 'stories' | 'dsl' | 'data'): void {
    this.tab = tab;
    const labels = {
      simulation: 'Population lab',
      stories: 'Recorded stories',
      dsl: 'DSL Builder',
      data: 'Data atlas',
    };
    text('workspace-breadcrumb', labels[tab]);
    text(
      'workspace-data-notice',
      tab === 'data' ? 'REAL CITY BACKBONE' : tab === 'dsl' ? 'EVIDENCE-GATED DSL' : 'FAKE SMOKE INPUTS',
    );
    text(
      'workspace-storage-notice',
      tab === 'data'
        ? 'Atlas versions are saved on the API server. Run records reset on API restart.'
        : tab === 'dsl'
          ? 'Every coefficient and distribution keeps provenance and uncertainty.'
          : 'Runs live in server memory. Restarting the API clears them.',
    );
    document
      .querySelectorAll<HTMLElement>('[role="tab"][data-action]')
      .forEach((button) =>
        button.setAttribute('aria-selected', String(button.dataset.action === `${tab}-tab`)),
      );
    element('simulation-view').hidden = tab !== 'simulation';
    element('stories-view').hidden = tab !== 'stories';
    element('dsl-view').hidden = tab !== 'dsl';
    element('data-view').hidden = tab !== 'data';
    if (tab !== 'simulation') {
      this.suspendView();
      this.dataTab.deactivate();
      this.dslBuilder.deactivate();
      this.stories.deactivate();
      if (tab === 'data') void this.dataTab.activate(this.active?.run_id);
      if (tab === 'dsl') void this.dslBuilder.activate();
      if (tab === 'stories')
        void this.stories.activate(this.active).catch((error) => this.showError(error));
    } else {
      this.dataTab.deactivate();
      this.dslBuilder.deactivate();
      this.stories.deactivate();
      this.resumeView();
    }
  }
}

new Lab();
