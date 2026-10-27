import type {
  AtlasCity,
  AtlasOverview,
  CityDetail,
  ImportHistory,
  ImportVersion,
  SourceCatalog,
} from '../contracts.generated';
import { escapeHtml as e } from '../views';
import { plannerSection } from './features';

export const labels: Record<string, string> = {
  age_sex: 'Age & sex',
  income: 'Income',
  education: 'Education',
  ideology: 'Ideology / alignment',
  household_size: 'Household size',
};
const n = (number: number): string => number.toLocaleString('en');
const pct = (number: number): string => `${number.toFixed(2)}%`;
const localDate = (): string => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
};

export function dataShell(): string {
  return `
    <section class="atlas-heading">
      <div>
        <p class="eyebrow">ATLAS / DATA ORGANIZER</p>
        <h1>Data coverage</h1>
        <p class="atlas-heading-copy">Find observed data, fallback data, and the highest-impact gaps across the city backbone.</p>
      </div>
      <div class="atlas-heading-actions">
        <button class="button secondary" data-atlas-action="sources">Source loaders</button
        ><button class="button primary" data-atlas-action="import">Import data ↗</button>
      </div>
    </section>
    <div id="atlas-error" class="notice error-notice" role="alert" hidden></div>
    <div class="atlas-context">
      <label
        >Data scope<select id="atlas-scope" aria-label="Data scope">
          <option value="shared">Shared atlas</option>
        </select></label
      ><label
        >Available on or before<input id="atlas-asof" type="date" value="${localDate()}"
      /></label>
      <p>Run uploads stay in their run.<br />Only explicit promotion changes the shared atlas.</p>
      <button class="text-button" data-atlas-action="refresh">Refresh ↻</button>
    </div>
    <div id="atlas-summary" class="atlas-summary"><p class="muted">Loading the atlas…</p></div>
    ${plannerSection()}
    <section class="atlas-section atlas-evidence-section" id="atlas-universal-features"><p class="muted">Loading feature registry…</p></section>
    <section class="atlas-section atlas-evidence-section" id="atlas-hierarchy"><p class="muted">Loading hierarchy…</p></section>
    <section class="atlas-section atlas-evidence-section" id="atlas-choice-evidence"><p class="muted">Loading choice evidence…</p></section>
    <section class="atlas-section" id="atlas-gap-list">
      <div class="atlas-section-heading">
        <div>
          <p class="eyebrow">CITY OBSERVATIONS</p>
          <h2>Highest-impact city gaps</h2>
          <p>Individual city-field gaps sorted by city population.</p>
        </div>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>City</th>
              <th>Country</th>
              <th>Field to gather</th>
              <th>Current status</th>
              <th>Population weight</th>
              <th>Source that could fill it</th>
            </tr>
          </thead>
          <tbody id="atlas-gaps"></tbody>
        </table>
      </div>
    </section>
    <section class="atlas-section" id="atlas-city-browser">
      <div class="atlas-section-heading">
        <div>
          <p class="eyebrow">225K CITY BACKBONE</p>
          <h2>Browse cities <span id="atlas-filter-count" class="muted"></span></h2>
          <p id="atlas-backbone-note">GeoNames cities500 · all retained populated places</p>
        </div>
        <button id="atlas-load" class="button secondary" data-atlas-action="load">
          Load full GeoNames backbone
        </button>
      </div>
      <div class="atlas-filters">
        <label
          >Search cities<input
            id="atlas-search"
            type="search"
            placeholder="Name, ASCII name or GeoNames ID" /></label
        ><label
          >Country<select id="atlas-country" aria-label="Country">
            <option value="">All countries</option>
          </select></label
        ><label
          >Simulation tier<select id="atlas-tier" aria-label="Simulation tier">
            <option value="">All tiers</option>
            <option value="simulated">Simulated tier</option>
            <option value="disaggregated">Disaggregated tier</option>
          </select></label
        ><label
          >City status<select id="atlas-status" aria-label="City status">
            <option value="">All statuses</option>
            <option value="present">Present</option>
            <option value="inherited">Inherited</option>
            <option value="imputed">Imputed</option>
            <option value="missing">Missing</option>
          </select></label
        ><label
          >Missing field<select id="atlas-missing" aria-label="Missing field">
            <option value="">Any field</option>
            ${Object.entries(labels)
              .map(([key, value]) => `<option value="${key}">${value}</option>`)
              .join('')}
          </select></label
        >
      </div>
      <div class="table-scroll atlas-table-scroll">
        <table class="atlas-city-table">
          <thead>
            <tr>
              <th>City / country</th>
              <th>Population</th>
              <th>Coordinates</th>
              <th>Simulation tier</th>
              ${Object.values(labels)
                .map((label) => `<th>${label}</th>`)
                .join('')}
              <th>Country behaviour</th>
              <th>Coverage</th>
              <th>City status</th>
            </tr>
          </thead>
          <tbody id="atlas-cities"></tbody>
        </table>
      </div>
      <div class="atlas-pagination">
        <span id="atlas-page-label"></span>
        <div>
          <button class="button secondary" data-atlas-action="previous">← Previous</button
          ><span id="atlas-page-number" class="mono"></span
          ><button class="button secondary" data-atlas-action="next">Next →</button>
        </div>
      </div>
    </section>
    <details class="atlas-section atlas-collapsible" id="atlas-coverage-panel">
      <summary>
        <div><span class="eyebrow">AUDIT TABLE</span><strong>Coverage calculations</strong></div>
        <span>City counts and population-weighted percentages for every canonical field</span>
      </summary>
      <div class="table-scroll">
        <table class="coverage-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Direct cities</th>
              <th>Direct + inherited cities</th>
              <th>Direct population</th>
              <th>Direct + inherited population</th>
              <th>Imputed cities</th>
              <th>Missing cities</th>
            </tr>
          </thead>
          <tbody id="atlas-coverage"></tbody>
        </table>
      </div>
    </details>
    <details class="atlas-section atlas-collapsible" id="atlas-history-panel">
      <summary>
        <div><span class="eyebrow">PROVENANCE</span><strong>Import versions</strong></div>
        <span>Latest live and draft source versions; older versions remain available below each source.</span>
      </summary>
      <div id="atlas-history"></div>
    </details>
    <footer id="atlas-attribution" class="atlas-attribution"></footer>
    <dialog id="atlas-city-dialog" class="atlas-dialog" aria-labelledby="atlas-city-title">
      <div id="atlas-city-detail"></div>
      <div class="dialog-footer">
        <button class="button secondary" data-atlas-action="close-city">Close</button>
      </div>
    </dialog>
    <dialog id="atlas-import-dialog" class="atlas-dialog" aria-labelledby="atlas-import-title">
      <div class="dialog-top">
        <span class="small-label">IMPORT / REVIEW BEFORE WRITE</span
        ><button class="icon-button" data-atlas-action="close-import" aria-label="Close import">
          ×
        </button>
      </div>
      <h2 id="atlas-import-title">Bring evidence into the atlas.</h2>
      <div id="atlas-import-body"></div>
    </dialog>
    <dialog id="atlas-sources-dialog" class="atlas-dialog" aria-labelledby="atlas-sources-title">
      <div class="dialog-top">
        <span class="small-label">CANONICAL DATA SOURCES</span
        ><button
          class="icon-button"
          data-atlas-action="close-sources"
          aria-label="Close source loaders"
        >
          ×
        </button>
      </div>
      <h2 id="atlas-sources-title">Load from the source.</h2>
      <div id="atlas-sources-list"></div>
    </dialog>
    <dialog id="atlas-promotion-dialog" class="delete-dialog" aria-labelledby="atlas-promotion-title">
      <h2 id="atlas-promotion-title">Promote to shared atlas?</h2>
      <label class="atlas-checkbox"
        ><input id="atlas-promotion-rights" type="checkbox" />I confirm this source permits
        redistribution to the shared atlas.</label
      >
      <p id="atlas-promotion-error" class="form-error" role="alert" hidden></p>
      <div class="dialog-footer">
        <button class="button secondary" data-atlas-action="cancel-promotion">Keep private</button
        ><button class="button primary" data-atlas-action="confirm-promotion">Promote version</button>
      </div>
    </dialog>
  `;
}

export function summaryCards(view: AtlasOverview): string {
  const s = view.summary;
  const directCities = s.direct.full + s.direct.partial;
  const usableCities = s.total_cities - s.direct_plus_inherited.none;
  const missingCells = s.fields.reduce((total, field) => total + field.missing, 0);
  const imputedCells = s.fields.reduce((total, field) => total + field.imputed, 0);
  return `
    <div>
      <span class="metric-label">Cities tracked</span><strong>${n(s.total_cities)}</strong
      ><span>${n(s.simulated_cities)} simulated tier · ${n(s.disaggregated_cities)} disaggregated</span>
    </div>
    <div>
      <span class="metric-label">Cities with direct data</span><strong>${n(directCities)}</strong
      ><span>${n(s.direct.full)} full · ${n(s.direct.partial)} partial · ${n(s.direct.none)} none</span>
    </div>
    <div>
      <span class="metric-label">Usable after inheritance</span><strong>${n(usableCities)}</strong
      ><span>${n(s.direct_plus_inherited.full)} full · ${n(s.direct_plus_inherited.partial)} partial · ${n(s.direct_plus_inherited.none)} none</span>
    </div>
    <div>
      <span class="metric-label">Unresolved field-place cells</span><strong>${n(missingCells)}</strong
      ><span>${n(imputedCells)} additional cells use regional estimates</span>
    </div>
  `;
}

export function coverageRows(view: AtlasOverview): string {
  return view.summary.fields
    .map(
      (f) =>
        `
    <tr>
      <th>${labels[f.field]}</th>
      <td>${pct(f.direct_percent)} <small>${n(f.present)}</small></td>
      <td>${pct(f.direct_plus_inherited_percent)} <small>${n(f.present + f.inherited)}</small></td>
      <td>${pct(f.direct_population_percent)}</td>
      <td>${pct(f.direct_plus_inherited_population_percent)}</td>
      <td>${n(f.imputed)}</td>
      <td>${n(f.missing)}</td>
    </tr>
  `,
    )
    .join('');
}

export function cityRows(cities: AtlasCity[]): string {
  if (!cities.length)
    return '<tr><td colspan="12" class="atlas-empty">No cities match these filters. Adjust your search or load the full backbone.</td></tr>';
  return cities
    .map(
      (city) =>
        `
    <tr>
      <th>
        <button class="atlas-city-link" data-atlas-action="city" data-id="${city.geonameid}">
          ${e(city.name)}</button
        ><small>${e(city.country_name)} · ${city.country_code} · ${city.geonameid}</small>
      </th>
      <td>${city.population_status === 'missing' ? 'Unknown (source: 0)' : n(city.population)}</td>
      <td class="mono">${city.latitude.toFixed(4)}<br />${city.longitude.toFixed(4)}</td>
      <td>
        <span class="atlas-tier" title="${e(city.tier_reason)}">${city.simulation_tier}</span
        ><small>Assigned tier · engine pending</small>
      </td>
      ${city.fields.map((field) => `<td><span class="field-status ${field.status}" title="${e(field.provenance ? `${field.provenance.source} · ${field.provenance.source_date} · ${field.provenance.version}` : field.suggested_source)}">${field.status}</span>${field.provenance ? `<small>${e(field.provenance.source)}<br>${field.provenance.source_date} · ${e(field.provenance.version)}</small>` : ''}</td>`).join('')}
      <td>${city.behaviour.length ? city.behaviour.map((model) => `<span class="field-status ${model.fitted ? 'present' : 'missing'}">${model.fitted ? 'Fitted' : 'Label-only'}</span><small>${e(model.behaviour)} · ${e(model.provenance.source)} · ${model.provenance.source_date}</small>`).join('') : '<span class="field-status missing">No fitted model</span>'}</td>
      <td>
        <strong>${pct(city.coverage_percent)}</strong><small>${pct(city.inherited_coverage_percent)} incl. inherited</small>
      </td>
      <td><span class="field-status ${city.status}">${city.status}</span></td>
    </tr>
  `,
    )
    .join('');
}

export function detailView(detail: CityDetail): string {
  const c = detail.city;
  return `
    <p class="eyebrow">GEONAMES ${c.geonameid} / ${e(c.country_name)}</p>
    <h2 id="atlas-city-title">${e(c.name)}</h2>
    <p class="dialog-subtitle">
      ${n(c.population)} people · ${c.latitude}, ${c.longitude} ·
      ${e(c.timezone)}<br />Admin1 ${e(c.admin1) || '—'} / Admin2 ${e(c.admin2) || '—'} · ASCII
      ${e(c.asciiname)}
    </p>
    <p class="atlas-detail-note">${e(detail.simulation_note)}<br />Density: ${c.density_per_km2 === null ? 'missing — load a WorldPop or GPW grid' : `${n(c.density_per_km2)} people/km² · imputed grid-cell sample · ${e(c.density_provenance?.source ?? '')}`}</p>
    <div class="table-scroll">
      <table class="atlas-detail-table">
        <thead>
          <tr>
            <th>Field / status</th>
            <th>Recorded value</th>
            <th>Source / date / version</th>
          </tr>
        </thead>
        <tbody>
          ${c.fields.map((f) => `<tr><th>${labels[f.field]}<br><span class="field-status ${f.status}">${f.status}</span></th><td><pre>${e(f.value === null ? 'Missing' : typeof f.value === 'number' ? String(f.value) : JSON.stringify(f.value, null, 2))}</pre>${f.unit ? `<small>${e(f.unit)}</small>` : ''}</td><td>${f.provenance ? `${e(f.provenance.source)}<small>Data ${f.provenance.source_date}<br>Published ${f.provenance.published_date}<br>Version ${e(f.provenance.version)}<br>Scope ${e(f.provenance.scope)}<br>Uploader ${e(f.provenance.uploader)}</small>` : `<a href="${e(f.source_url)}" target="_blank" rel="noreferrer">${e(f.suggested_source)} ↗</a>`}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
    <h3>Still missing</h3>
    <p class="atlas-detail-note">${detail.missing_fields.length ? detail.missing_fields.map((field) => labels[field]).join(', ') : 'No unresolved fields.'}</p>
    <h3>Still needs a city observation</h3>
    <p class="atlas-detail-note">${detail.direct_observation_gaps.length ? detail.direct_observation_gaps.map((field) => `${labels[field]}: ${c.fields.find((f) => f.field === field)!.suggested_source}`).join('<br>') : 'Every field has city-specific observed data.'}</p>
    <h3>Country behaviour</h3>
    <p class="atlas-detail-note">${c.behaviour.length ? c.behaviour.map((model) => `${e(model.behaviour)}: ${model.fitted ? 'fitted classical logit' : 'label-only; no fitted coefficient'} · ${e(model.provenance.source)} · ${e(model.provenance.version)}${model.heldout_loss !== null ? `<br>Held-out log loss ${model.heldout_loss.toFixed(5)} vs baseline ${model.baseline_loss?.toFixed(5)} · ${model.training_rows} train / ${model.heldout_rows} held out · traits ${model.traits.map(e).join(', ')}` : ''}`).join('<br>') : 'No fitted model for this country. Import a survey with an explicit trait-to-action link.'}</p>
    <h3>Source history</h3>
    <p class="atlas-detail-note">${detail.history.map((p) => `${e(p.source)} · ${p.source_date} · ${e(p.version)} · ${e(p.scope)}`).join('<br>') || 'No marginal versions yet.'}</p>
  `;
}

export function historyView(history: ImportHistory, scope: string): string {
  if (!history.versions.length) return '<p class="atlas-empty">No imports in this scope.</p>';
  const grouped = new Map<string, ImportVersion[]>();
  history.versions.forEach((version) => {
    const key =
      version.status === 'committed'
        ? `${version.source}|${version.scope}|${version.kind}`
        : version.import_id;
    grouped.set(key, [...(grouped.get(key) ?? []), version]);
  });
  return Array.from(grouped.values())
    .map((versions) => {
      const ordered = versions
        .slice()
        .sort((a, b) =>
          `${b.source_date}|${b.published_date}`.localeCompare(
            `${a.source_date}|${a.published_date}`,
          ),
        );
      const latest = ordered[0];
      const action =
        latest.scope === scope && scope !== 'shared' && latest.status === 'committed'
          ? `<button class="button secondary" data-atlas-action="promote" data-id="${latest.import_id}">Promote…</button>`
          : latest.scope === scope && scope !== 'shared' && latest.status !== 'committed'
            ? `<button class="button secondary" data-atlas-action="resume-import" data-id="${latest.import_id}">Resume review</button>`
            : '';
      return `
        <article class="atlas-history-group">
          <div class="atlas-version">
            <div>
              <div class="atlas-history-title"><strong>${e(latest.source)}</strong><span class="field-status ${latest.status === 'committed' ? 'present' : 'missing'}">${e(latest.status)}</span><span class="field-status inherited">${e(latest.kind)}</span></div>
              <p><span class="mono">${e(latest.version)}</span> · data ${latest.source_date} · published ${latest.published_date} · ${n(latest.rows)} rows</p>
              <p>${e(latest.uploader)} · ${latest.live_fields} live fields · ${latest.scope === 'shared' ? 'shared atlas' : `run ${latest.scope.slice(0, 8)}`}${latest.promoted_from ? ' · explicitly promoted' : ''}</p>
              ${latest.models.map((model) => `<p>${e(model.behaviour)} · ${model.fitted ? `fitted · held-out loss ${model.heldout_loss?.toFixed(5)}` : 'label-only · no fitted coefficient'}</p>`).join('')}
            </div>
            ${action}
          </div>
          ${
            ordered.length > 1
              ? `<details class="atlas-older-versions"><summary>${n(ordered.length - 1)} older versions</summary><ul>${ordered
                  .slice(1)
                  .map(
                    (version) =>
                      `<li><div><span class="mono">${e(version.version)}</span><span>data ${version.source_date} · published ${version.published_date} · ${e(version.uploader)} · ${n(version.rows)} rows · ${version.live_fields} live fields</span></div>${version.scope === scope && scope !== 'shared' ? `<button class="text-button" data-atlas-action="promote" data-id="${version.import_id}">Promote this version…</button>` : ''}</li>`,
                  )
                  .join('')}</ul></details>`
              : ''
          }
        </article>`;
    })
    .join('');
}

export function sourceCards(catalog: SourceCatalog): string {
  return catalog.sources
    .map(
      (source) =>
        `
    <article class="atlas-source">
      <div>
        <h3>
          <a href="${e(source.url)}" target="_blank" rel="noreferrer">${e(source.name)} ↗</a>
        </h3>
        <span class="field-status ${source.access === 'public' ? 'present' : 'inherited'}">${source.access}</span>
      </div>
      <p>${e(source.license)}</p>
      <p>${e(source.instructions)}</p>
      <small>${e(source.adapter)} · ${source.fields.map((field) => labels[field] ?? field).join(', ')}</small
      ><button
        class="button secondary"
        data-atlas-action="source-import"
        data-source="${source.source_id}"
      >
        Load authorized source file / URL
      </button>
    </article>
  `,
    )
    .join('');
}
