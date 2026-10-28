import './prompt2-ui.css';
import { escapeHtml, formatPercent, sentenceCase } from './prompt2-ui-utils';

export type SavedRunStatus =
  'queued' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'failed';

export type ConcurrentLaunchPolicy = 'parallel' | 'queue' | 'blocked';

export interface SavedRunHashes {
  protocol?: string | null;
  program?: string | null;
  dsl?: string | null;
  input?: string | null;
  output?: string | null;
}

export interface SavedRunStatusItem {
  id: string;
  name?: string | null;
  status: SavedRunStatus;
  progress: number;
  completedTicks: number;
  totalTicks: number;
  populationSize: number;
  days: number;
  startedAt?: string | null;
  completedAt?: string | null;
  error?: string | null;
  hashes: SavedRunHashes;
}

export interface SavedRunStatusListOptions {
  runs: SavedRunStatusItem[];
  launchPolicy: ConcurrentLaunchPolicy;
  onOpen?: (runId: string) => void;
}

const statusExplanation: Record<SavedRunStatus, string> = {
  queued: 'Waiting for an execution slot. No final output exists yet.',
  running: 'Still executing. Progress is live and its recorded output is not final.',
  cancelling: 'Stopping after the current safe checkpoint. Its output is not final.',
  cancelled: 'Stopped before completion. Recorded partial output remains inspectable.',
  completed: 'Finished. Its recorded output can be opened and inspected.',
  failed: 'Stopped because an error was recorded. Open it to inspect the failure.',
};

const launchPolicyExplanation: Record<ConcurrentLaunchPolicy, string> = {
  parallel: 'Starting another run while one is running starts both in parallel.',
  queue: 'Starting another run while one is running adds the new run to the queue.',
  blocked: 'A new run cannot launch while another run is running. Cancel or finish it first.',
};

const hashLabels: Array<[keyof SavedRunHashes, string, string]> = [
  ['protocol', 'Protocol', 'The wire contract used to exchange run data.'],
  ['program', 'Program', 'The compiled numeric program interpreted by the engine.'],
  ['dsl', 'DSL', 'The exact editable simulation definition used for this run.'],
  ['input', 'Input', 'The normalized run configuration and starting data.'],
  ['output', 'Output', 'The recorded result content for this completed run.'],
];

export class SavedRunStatusList {
  private runs: SavedRunStatusItem[];
  private launchPolicy: ConcurrentLaunchPolicy;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: SavedRunStatusListOptions,
  ) {
    this.runs = [...options.runs];
    this.launchPolicy = options.launchPolicy;
    this.host.addEventListener('click', this.onClick);
    this.render();
  }

  update(runs: SavedRunStatusItem[], launchPolicy = this.launchPolicy): void {
    this.runs = [...runs];
    this.launchPolicy = launchPolicy;
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private readonly onClick = (event: Event): void => {
    const button =
      event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>('[data-open-run]')
        : null;
    const runId = button?.dataset.openRun;
    if (runId) this.options.onOpen?.(runId);
  };

  private render(): void {
    this.host.className = 'prompt2-card saved-run-status-list';
    this.host.innerHTML = `
      <header class="prompt2-card-heading">
        <div><span class="prompt2-eyebrow">SAVED RUNS</span><h3>Recorded simulations</h3></div>
        <span class="saved-run-count">${this.runs.length} ${this.runs.length === 1 ? 'run' : 'runs'}</span>
      </header>
      <p class="saved-run-launch-policy">${escapeHtml(launchPolicyExplanation[this.launchPolicy])}</p>
      <div class="saved-run-status-items">
        ${this.runs.length ? this.runs.map((run) => this.runMarkup(run)).join('') : '<p class="saved-run-zero">No saved runs yet.</p>'}
      </div>
    `;
  }

  private runMarkup(run: SavedRunStatusItem): string {
    const clampedProgress = Math.max(0, Math.min(1, run.progress));
    const heading = run.name?.trim() || `Run ${run.id.slice(0, 8)}`;
    const error = run.error
      ? `<p class="saved-run-error" role="alert">${escapeHtml(run.error)}</p>`
      : '';
    return `
      <article class="saved-run-status-item" data-run-id="${escapeHtml(run.id)}">
        <div class="saved-run-status-main">
          <div>
            <span class="saved-run-status-badge status-${escapeHtml(run.status)}">${escapeHtml(run.status.toUpperCase())}</span>
            <h4>${escapeHtml(heading)}</h4>
            <p>${escapeHtml(statusExplanation[run.status])}</p>
          </div>
          <button type="button" data-open-run="${escapeHtml(run.id)}" aria-label="Open run ${escapeHtml(run.id)}">Open run</button>
        </div>
        <div class="saved-run-facts">
          <span>${run.populationSize.toLocaleString()} agents</span>
          <span>${run.days.toLocaleString()} days</span>
          <span>${run.completedTicks.toLocaleString()} / ${run.totalTicks.toLocaleString()} ticks</span>
          <span>${formatPercent(clampedProgress)} complete</span>
        </div>
        <div class="saved-run-progress" role="progressbar" aria-label="Run progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(clampedProgress * 100)}"><span style="width:${clampedProgress * 100}%"></span></div>
        ${error}
        <details class="saved-run-details">
          <summary>Details and reproducibility hashes</summary>
          <p>Hashes identify the exact definitions, inputs, and recorded output. They are for audit and replay, so they stay behind this disclosure.</p>
          <dl>${hashLabels.map(([key, label, explanation]) => this.hashMarkup(run.hashes[key], label, explanation)).join('')}</dl>
          <dl class="saved-run-dates">
            ${run.startedAt ? `<div><dt>Started</dt><dd>${escapeHtml(run.startedAt)}</dd></div>` : ''}
            ${run.completedAt ? `<div><dt>${escapeHtml(sentenceCase(run.status))}</dt><dd>${escapeHtml(run.completedAt)}</dd></div>` : ''}
          </dl>
        </details>
      </article>
    `;
  }

  private hashMarkup(value: string | null | undefined, label: string, explanation: string): string {
    return `
      <div>
        <dt>${escapeHtml(label)} hash</dt>
        <dd><code>${value ? escapeHtml(value) : 'Not recorded'}</code><small>${escapeHtml(explanation)}</small></dd>
      </div>
    `;
  }
}
