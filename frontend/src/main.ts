import './styles.css';
import { api, RunStream } from './api';
import { DataTab } from './atlas/main';
import { InfectionChart, infectedTotal } from './chart';
import type {
  Catalog,
  DailySnapshot,
  RunConfig,
  RunDetail,
  RunSummary,
} from './contracts.generated';
import { Globe } from './globe';
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
  private tab: 'simulation' | 'data' = 'simulation';
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
    for (const id of ['new-run-dialog', 'delete-dialog']) {
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
          this.globe = new Globe(element('globe'), catalog.countries);
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
    this.index = autoplay ? 0 : Math.max(0, run.snapshots.length - 1);
    element('empty-state').hidden = true;
    element('stream-notice').hidden = true;
    text('run-id', `RUN ${run.run_id.slice(0, 10).toUpperCase()}`);
    this.renderStatus();
    this.renderSnapshot();
    this.refreshListView();
    this.attachStream();
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
    text('metric-infected', number(infectedTotal(snapshot)));
    text('metric-day', `Day ${snapshot.day} · ${snapshot.places.length} countries`);
    text(
      'metric-recovered',
      number(snapshot.places.reduce((sum, place) => sum + place.recovered, 0)),
    );
    const population = snapshot.places.reduce(
      (sum, place) => sum + place.susceptible + place.exposed + place.infected + place.recovered,
      0,
    );
    text('metric-population', number(population));
    text('metric-countries', `${snapshot.places.length} fake country compartments`);
    text('metric-peak', this.active?.metrics ? number(this.active.metrics.peak_infected) : '—');
    text(
      'metric-peak-day',
      this.active?.metrics
        ? `Peak recorded on day ${this.active.metrics.peak_day}`
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
    element('snapshot-table').innerHTML = snapshot.places
      .map(
        (place) =>
          `<tr><th scope="row">${this.countryName(place.country)}</th><td>${number(place.susceptible)}</td><td>${number(place.exposed)}</td><td class="infected-cell">${number(place.infected)}</td><td>${number(place.recovered)}</td><td>${number(place.susceptible + place.exposed + place.infected + place.recovered)}</td></tr>`,
      )
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
    element('country-list').innerHTML = snapshot.places
      .map((place) => {
        const population = place.susceptible + place.exposed + place.infected + place.recovered;
        const percentage = (place.infected / population) * 100;
        return `<div class="country-row"><div class="country-row-top"><span><span class="country-code">${place.country}</span>${this.countryName(place.country)}</span><strong>${number(place.infected)}</strong></div><div class="country-bar"><span style="width:${percentage}%"></span></div><div class="country-row-bottom"><span>${percentage.toFixed(2)}% infected</span><span>${number(population)} people</span></div></div>`;
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
      `Pandemic #${run.config.seed} · ${run.config.countries.length} countries · run ${id.slice(0, 8)}`,
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
    element('country-list').innerHTML =
      '<p class="muted empty-country">Launch an experiment to see the country breakdown.</p>';
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
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!target || (target instanceof HTMLButtonElement && target.disabled)) return;
    const action = target.dataset.action;
    if (action === 'data-tab') this.changeTab('data');
    else if (action === 'simulation-tab') this.changeTab('simulation');
    else if (action === 'new') this.showNew();
    else if (action === 'cancel-new') element<HTMLDialogElement>('new-run-dialog').close();
    else if (action === 'cancel-delete') element<HTMLDialogElement>('delete-dialog').close();
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
    clearInterval(this.timer);
    this.stream?.dispose();
    this.globe?.dispose();
    this.chart.dispose();
    document.removeEventListener('click', this.onClick);
  }

  private changeTab(tab: 'simulation' | 'data'): void {
    this.tab = tab;
    text('workspace-breadcrumb', tab === 'data' ? 'Data atlas' : 'Population lab');
    text('workspace-data-notice', tab === 'data' ? 'REAL CITY BACKBONE' : 'FAKE DATA ONLY');
    text(
      'workspace-storage-notice',
      tab === 'data'
        ? 'Atlas versions are saved on the API server. Run records reset on API restart.'
        : 'Runs live in server memory. Restarting the API clears them.',
    );
    document
      .querySelectorAll<HTMLElement>('[role="tab"][data-action]')
      .forEach((button) =>
        button.setAttribute('aria-selected', String(button.dataset.action === `${tab}-tab`)),
      );
    element('simulation-view').hidden = tab !== 'simulation';
    if (tab === 'data') {
      this.suspendView();
      void this.dataTab.activate(this.active?.run_id);
    } else {
      this.dataTab.deactivate();
      this.resumeView();
    }
  }
}

new Lab();
