import type { Catalog, RunConfig, RunSummary } from './contracts.generated';

export const defaults: RunConfig = {
  scenario: 'pandemic',
  countries: ['ITA', 'FRA', 'DEU', 'ESP'],
  start_day: 0,
  end_day: 160,
  seed: 42,
  parameters: {
    transmission: 0.38,
    progression: 0.2,
    recovery: 0.09,
    mixing: 0.04,
    initial_infected: 40,
  },
  dsl: null,
  population: null,
  tick: null,
  outputs: null,
  evidence_table_version: 'FAKE-evidence-v1',
};

export const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!,
  );

export const scenarioLabel = (scenario: string): string =>
  scenario
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ''}${part.slice(1)}`)
    .join(' ');

export function shell(): string {
  return `
    <aside class="sidebar">
      <a class="brand" href="/" aria-label="Petraterrium home"
        ><span class="brand-mark">◎</span
        ><span>Petraterrium<span class="brand-subtitle">POPULATION DYNAMICS LAB</span></span></a
      >
      <div class="workspace-label">
        <span class="status-dot"></span> SANDBOX WORKSPACE <span class="version">V0.1</span>
      </div>
      <button class="button primary new-run-button" data-action="new" disabled>
        <span>＋</span> New experiment <span class="button-arrow">↗</span>
      </button>
      <div class="workspace-tabs" role="tablist" aria-label="Workspace view">
        <button role="tab" aria-selected="true" aria-controls="simulation-view" data-action="simulation-tab">Simulation</button>
        <button role="tab" aria-selected="false" aria-controls="stories-view" data-action="stories-tab">Stories</button>
        <button role="tab" aria-selected="false" aria-controls="dsl-view" data-action="dsl-tab">DSL</button>
        <button role="tab" aria-selected="false" aria-controls="data-view" data-action="data-tab">Data</button>
      </div>
      <div class="sidebar-section-title">
        <span>SAVED RUNS</span
        ><button class="icon-button" data-action="refresh" aria-label="Refresh saved runs">↻</button>
      </div>
      <nav aria-label="Saved runs">
        <ul id="run-list" class="run-list">
          <li class="sidebar-empty">Connecting to your session…</li>
        </ul>
      </nav>
      <div class="sidebar-footer">
        <span class="small-label">THE DSL SIMULATION FRAMEWORK</span>
        <p>One engine.<br />Every number has a receipt.</p>
        <div class="fake-tag" id="workspace-data-notice">FAKE DATA ONLY</div>
        <p class="muted" id="workspace-storage-notice">Runs live in server memory.<br />Restarting the API clears them.</p>
      </div>
    </aside>
    <main>
      <header class="topbar">
        <span class="breadcrumb">Workspace <span>/</span> <span id="workspace-breadcrumb">Population lab</span></span>
        <div class="topbar-right">
          <span id="api-status" class="api-status">Connecting</span
          ><span class="avatar" aria-hidden="true">P</span>
        </div>
      </header>
      <div class="lab" id="simulation-view">
        <div id="error-banner" class="notice error-notice" role="alert" hidden>
          <span id="error-message"></span><button class="text-button" data-action="retry">Retry</button
          ><button class="icon-button" data-action="dismiss-error" aria-label="Dismiss error">×</button>
        </div>
        <section class="hero">
          <div>
            <p class="eyebrow">
              <span class="tiny-globe">⊕</span> DSL SYSTEM <span class="slash">/</span> RECORDED RUN
            </p>
            <h1>Trace the state.</h1>
            <p class="hero-copy">A world of connections. A record of every change.</p>
          </div>
          <div class="hero-status">
            <span id="run-status" class="status-pill">Ready to explore</span
            ><span id="run-id" class="mono muted">NO ACTIVE RUN</span>
          </div>
        </section>
        <div class="model-notice">
          <span class="fake-tag">FAKE</span
          ><span>Bundled smoke inputs · explicit uncertainty · deterministic engine</span
          ><span class="notice-end">A conditional simulation, never a prophecy.</span>
        </div>
        <section class="metrics" aria-label="Run metrics">
          <div>
            <span class="metric-label"><i class="legend-dot orange"></i><span id="metric-primary-label">Primary state</span> on selected day</span
            ><strong id="metric-infected">—</strong
            ><span id="metric-day" class="metric-caption">Waiting for a recorded day</span>
          </div>
          <div>
            <span class="metric-label">Peak primary state</span><strong id="metric-peak">—</strong
            ><span id="metric-peak-day" class="metric-caption">Computed at run completion</span>
          </div>
          <div>
            <span class="metric-label"><span id="metric-secondary-label">Terminal state</span> on selected day</span
            ><strong id="metric-recovered">—</strong
            ><span class="metric-caption">Recorded compartment count</span>
          </div>
          <div>
            <span class="metric-label">Selected population</span
            ><strong id="metric-population">—</strong
            ><span id="metric-countries" class="metric-caption">4 available fake countries</span>
          </div>
        </section>
        <div id="stream-notice" class="notice" role="status" hidden>
          <span id="stream-message"></span
          ><button class="text-button" data-action="reconnect">Reconnect</button>
        </div>
        <div id="agent-lod-notice" class="notice agent-lod-notice" role="status" hidden>
          <span id="agent-lod-status"></span><button class="text-button" data-action="world-view">Return to clusters</button>
        </div>
        <section class="world-section" aria-label="Globe and place results">
          <div class="globe-panel">
            <div class="panel-heading globe-heading">
              <span><span class="status-dot"></span> GLOBAL VIEW</span
              ><span class="muted">01 / WORLD</span>
            </div>
            <div id="globe" class="globe"></div>
            <div id="empty-state" class="empty-state">
              <span class="small-label">YOUR NEXT EXPERIMENT</span>
              <h2>Start with a small world.</h2>
              <p>Four places. One seeded model.<br />Watch the recorded days unfold.</p>
              <button class="button primary" data-action="new" disabled>
                Create your first run <span>↗</span>
              </button>
            </div>
            <div class="globe-caption">
              <span id="globe-day" class="mono">DAY —</span
              ><span>DRAG TO ROTATE <span class="caption-divider">/</span> SCROLL TO ZOOM</span>
            </div>
            <div class="map-label">ILLUSTRATIVE GEOGRAPHY</div>
          </div>
          <aside class="country-panel">
            <div class="panel-heading">
              <span>PLACE PULSE</span><span id="country-count" class="muted">00</span>
            </div>
            <p class="country-panel-caption">Primary state · selected recorded day</p>
            <div id="country-list" class="country-list">
              <p class="muted empty-country">Launch an experiment to see the place breakdown.</p>
            </div>
            <div class="marker-legend">
              <span class="marker-example"></span>
              <p>Marker size and warmth<br />reflect the recorded primary state.</p>
            </div>
          </aside>
        </section>
        <section class="timeline-panel" aria-label="Timeline and recorded metric chart">
          <div class="chart-heading">
            <div>
              <span class="small-label">RECORDED STATE OVER TIME</span
              ><span class="chart-subtitle"
                ><i class="legend-dot orange"></i>All selected places</span
              >
            </div>
            <div class="chart-actions">
              <span id="record-count" class="mono muted">0 DAYS RECORDED</span>
              <details class="export-menu">
                <summary class="text-button">Export ↓</summary>
                <div>
                  <button data-action="export-json">Run as JSON</button
                  ><button data-action="export-csv">Snapshots as CSV</button>
                </div>
              </details>
            </div>
          </div>
          <p id="ensemble-status" class="mono muted">Ensemble update pending</p>
          <canvas
            id="infection-chart"
            class="infection-chart"
            role="img"
            aria-label="Recorded primary state values over time. Use the timeline or snapshot table to inspect exact values."
          ></canvas>
          <div class="playback">
            <button
              id="play-button"
              class="play-button"
              data-action="play"
              disabled
              aria-label="Play timeline"
            >
              ▶</button
            ><span id="timeline-day" class="mono timeline-day">DAY —</span
            ><input
              id="timeline"
              type="range"
              min="0"
              max="0"
              value="0"
              aria-label="Recorded day"
              disabled
            /><span id="timeline-end" class="mono muted">—</span
            ><select id="playback-speed" aria-label="Playback speed">
              <option value="240">0.5×</option>
              <option value="120" selected>1×</option>
              <option value="40">3×</option>
            </select>
          </div>
        </section>
        <details class="receipt">
          <summary>
            <span>↳ Snapshot receipt</span
            ><span class="muted">Inspect the recorded numbers and provenance</span>
          </summary>
          <div class="receipt-content">
            <p id="provenance" class="mono muted">No snapshot selected.</p>
            <div class="table-scroll">
              <table>
                <thead id="snapshot-head"><tr><th scope="col">Place</th><th scope="col">Waiting for state schema</th></tr></thead>
                <tbody id="snapshot-table"></tbody>
              </table>
            </div>
            <p id="config-receipt" class="mono muted"></p>
          </div>
        </details>
        <footer class="lab-footer">
          <span>PETRATERRIUM <span class="muted">/ A SMALL WORLD, MADE CHECKABLE</span></span
          ><span class="muted">CONDITIONAL OUTPUT · VERSIONED RECEIPTS</span>
        </footer>
      </div>
      <div id="stories-view" class="stories-view" hidden></div>
      <div id="dsl-view" class="dsl-view" hidden></div>
      <div id="data-view" class="atlas-view" hidden></div>
    </main>
    <dialog id="new-run-dialog" class="run-dialog" aria-labelledby="new-run-title">
      <form id="run-form">
        <div class="dialog-top">
          <span class="small-label">NEW EXPERIMENT / 01</span
          ><button
            type="button"
            class="icon-button"
            data-action="cancel-new"
            aria-label="Close new experiment"
          >
            ×
          </button>
        </div>
        <h2 id="new-run-title">Set the world in motion.</h2>
        <p class="dialog-subtitle">Choose the places. Set the seed. Follow every day.</p>
        <div class="scenario-field">
          <span class="small-label">SCENARIO</span
          ><span>◉ Pandemic <span class="muted">/ placeholder SEIR</span></span>
        </div>
        <fieldset class="country-fieldset">
          <legend class="small-label">COUNTRIES <span class="muted">/ FAKE POPULATIONS</span></legend>
          <div id="country-options" class="country-options"></div>
        </fieldset>
        <div class="form-row">
          <label
            >Start day<input
              name="start_day"
              type="number"
              value="0"
              min="0"
              max="10000"
              required /></label
          ><label
            >End day<input
              name="end_day"
              type="number"
              value="160"
              min="1"
              max="10730"
              required /></label
          ><label
            >Random seed<input name="seed" type="number" value="42" min="0" max="4294967295" required
          /></label>
        </div>
        <p class="field-hint">Days are inclusive. Choose a window of 1–730 transitions.</p>
        <details class="parameter-details">
          <summary>Model parameters <span class="muted">Unfitted defaults</span></summary>
          <div class="parameter-grid">
            <label
              >Transmission / day<input
                name="transmission"
                type="number"
                min="0"
                max="3"
                step="0.01"
                value="0.38"
                required /></label
            ><label
              >Progression / day<input
                name="progression"
                type="number"
                min="0"
                max="3"
                step="0.01"
                value="0.20"
                required /></label
            ><label
              >Recovery / day<input
                name="recovery"
                type="number"
                min="0"
                max="3"
                step="0.01"
                value="0.09"
                required /></label
            ><label
              >Country mixing<input
                name="mixing"
                type="number"
                min="0"
                max="1"
                step="0.01"
                value="0.04"
                required /></label
            ><label
              >Initial infected<input
                name="initial_infected"
                type="number"
                min="1"
                max="10000"
                step="1"
                value="40"
                required
            /></label>
          </div>
          <p class="field-hint">
            Initial infections start in Italy when selected, otherwise the first country in code order.
          </p>
        </details>
        <div class="form-notice">
          <span class="fake-tag">FAKE</span
          ><span>Invented counts and unfitted rates. This experiment is a plumbing demonstration.</span>
        </div>
        <p id="form-error" class="form-error" role="alert" hidden></p>
        <div class="dialog-footer">
          <button type="button" class="button secondary" data-action="cancel-new">Cancel</button
          ><button type="submit" id="launch-button" class="button primary">
            Launch experiment <span>↗</span>
          </button>
        </div>
      </form>
    </dialog>
    <dialog id="delete-dialog" class="delete-dialog" aria-labelledby="delete-title">
      <div class="dialog-top">
        <span class="small-label">MANAGE RUN</span
        ><button class="icon-button" data-action="cancel-delete" aria-label="Cancel deletion">×</button>
      </div>
      <h2 id="delete-title">Delete this experiment?</h2>
      <p id="delete-description" class="dialog-subtitle"></p>
      <p class="muted">This removes the run and its recorded results from this server session.</p>
      <p id="delete-error" class="form-error" role="alert" hidden></p>
      <div class="dialog-footer">
        <button class="button secondary" data-action="cancel-delete">Keep run</button
        ><button id="confirm-delete" class="button danger" data-action="confirm-delete">
          Delete run
        </button>
      </div>
    </dialog>
    <dialog id="agent-dialog" class="agent-dialog" aria-labelledby="agent-title">
      <div class="dialog-top"><span class="small-label">SYNTHETIC AGENT / LOG RECEIPT</span><button class="icon-button" data-action="close-agent" aria-label="Close agent detail">×</button></div>
      <h2 id="agent-title">Synthetic agent</h2><p id="agent-scope" class="dialog-subtitle"></p><div id="agent-content"></div>
      <div class="dialog-footer"><button class="button secondary" data-action="close-agent">Return to globe</button></div>
    </dialog>
  `;
}

export function countryOptions(catalog: Catalog): string {
  return catalog.countries
    .map(
      (country) =>
        `<label class="country-option"><input type="checkbox" name="countries" value="${country.country}" checked /><span><strong>${escapeHtml(country.name)}</strong><span>${country.population.toLocaleString()} fake people</span></span><span class="country-check">✓</span></label>`,
    )
    .join('');
}

export function savedRunList(runs: RunSummary[], activeId?: string): string {
  if (!runs.length)
    return '<li class="sidebar-empty"><span class="empty-runs-icon">⊞</span>No experiments yet.<br>Your next question starts here.</li>';
  return runs
    .map(
      (run) =>
        `<li class="saved-run ${run.run_id === activeId ? 'selected' : ''}"><button class="run-open" data-action="open" data-id="${run.run_id}" ${run.run_id === activeId ? 'aria-current="true"' : ''}><span class="run-item-icon">◉</span><span><strong>${escapeHtml(scenarioLabel(run.config.scenario))} <span class="run-seed">#${run.config.seed}</span></strong><span class="run-item-caption">${run.config.countries.length} places · ${run.config.end_day - run.config.start_day} days</span><span class="run-item-status"><i class="status-dot status-${run.status}"></i>${run.status} <span class="mono">${run.run_id.slice(0, 6)}</span></span></span></button><button class="run-delete" data-action="delete" data-id="${run.run_id}" aria-label="Delete run with seed ${run.config.seed}">×</button></li>`,
    )
    .join('');
}
