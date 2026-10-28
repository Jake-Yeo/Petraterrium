import type {
  AISourceProvenance,
  AtlasCity,
  AtlasOverview,
  CityDetail,
  ImportHistory,
  ImportVersion,
  SourceCatalog,
} from '../contracts.generated';
import { escapeHtml as e } from '../views';

export const labels: Record<string, string> = {
  age_sex: 'Age & sex',
  income: 'Income',
  education: 'Education',
  ideology_economic: 'Economic ideology',
  ideology_state: 'State ideology',
  ideology_cultural: 'Cultural ideology',
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

type StoredResearchSource = {
  title: string;
  url?: string | null;
  source_kind: string;
  observation_date: string | null;
  published_date: string | null;
  source_version: string;
  license: string;
  language: string;
  original_excerpt: string;
  translated_excerpt: string | null;
  ai_provenance?: AISourceProvenance | null;
};

type StoredMapping = {
  version: string;
  rows: Array<{
    source_label: string;
    proposed_label: string | null;
    confidence: string;
    reason: string;
  }>;
};

type StoredVerification = {
  candidate_id: string;
  accepted: boolean;
  direct_measurement: boolean;
  checks: Array<{
    name: string;
    passed: boolean;
    expected: string;
    actual: string;
    reason: string;
  }>;
  reasons: string[];
};

type StoredRejectedSource = {
  candidate: StoredResearchSource;
  verification: StoredVerification;
};

type StoredEstimateTrace = {
  method: string;
  extractions: Array<{
    title: string;
    extracted_distribution: Record<string, number>;
    weight_basis: string;
  }>;
  calculation: string[];
  assumptions: string[];
  confidence_intervals: Record<string, { lower: number; upper: number }>;
  better_data_needed: string;
};

type StoredResearchTrace = {
  result_kind?: string;
  languages?: string[];
  mapping?: StoredMapping | null;
  mapping_confirmed?: boolean;
  verification?: StoredVerification[];
  sources?: {
    accepted?: StoredResearchSource[];
    rejected?: StoredRejectedSource[];
  };
  search_log?: Array<{
    engine: string;
    language: string;
    query_or_source: string;
    outcome: string;
    rejection_reasons?: string[];
  }>;
  estimate_trace?: StoredEstimateTrace | null;
  better_data?: string;
};

function safeWebUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function storedSource(
  source: StoredResearchSource,
  status: string,
  reasons: string[] = [],
): string {
  const href = safeWebUrl(source.url);
  const title = href
    ? `<a href="${e(href)}" target="_blank" rel="noreferrer">${e(source.title)} ↗</a>`
    : `<strong>${e(source.title)}</strong>`;
  return `<article>
    <div>${title}<span class="field-status ${status === 'accepted' ? 'present' : 'missing'}">${e(status)}</span></div>
    <small>${e(source.source_kind)} · ${e(source.language)} · observed ${e(source.observation_date ?? 'undated')} · published ${e(source.published_date ?? 'undated')} · ${e(source.source_version)} · ${e(source.license)}</small>
    ${source.ai_provenance ? `<small>AI extraction · ${e(source.ai_provenance.source_label)} · ${e(source.ai_provenance.model)} · ${e(source.ai_provenance.prompt_version)} · ${e(source.ai_provenance.generated_at)}</small>` : ''}
    ${reasons.length ? `<p>${reasons.map(e).join('<br>')}</p>` : ''}
    <p><b>Original</b> ${e(source.original_excerpt)}</p>
    ${source.translated_excerpt ? `<p><b>Translation</b> ${e(source.translated_excerpt)}</p>` : ''}
  </article>`;
}

function storedMapping(trace: StoredResearchTrace): string {
  if (!trace.mapping?.rows.length) return '';
  const state =
    trace.mapping_confirmed === undefined
      ? 'recorded'
      : trace.mapping_confirmed
        ? 'confirmed'
        : 'unconfirmed';
  return `<details><summary>Mapping · ${state} · ${e(trace.mapping.version)}</summary><dl>${trace.mapping.rows
    .map(
      (row) =>
        `<div><dt>${e(row.source_label)} → ${e(row.proposed_label ?? 'Unknown')}</dt><dd>${e(row.confidence)} · ${e(row.reason)}</dd></div>`,
    )
    .join('')}</dl></details>`;
}

function storedVerification(trace: StoredResearchTrace): string {
  const verifications = trace.verification ?? [];
  if (!verifications.length) return '';
  const accepted = verifications.filter((verification) => verification.accepted).length;
  return `<details><summary>Verification · ${accepted}/${verifications.length} accepted</summary>${verifications
    .map(
      (verification) => `<article>
        <strong>${e(verification.candidate_id)} · ${verification.accepted ? 'accepted' : 'rejected'}${verification.direct_measurement ? ' · direct' : ''}</strong>
        ${verification.reasons.length ? `<p>${verification.reasons.map(e).join('<br>')}</p>` : ''}
        <dl>${verification.checks
          .map(
            (check) =>
              `<div><dt>${check.passed ? 'Passed' : 'Failed'} · ${e(check.name)}</dt><dd>${e(check.reason)}<br>Expected ${e(check.expected)} · found ${e(check.actual)}</dd></div>`,
          )
          .join('')}</dl>
      </article>`,
    )
    .join('')}</details>`;
}

function cityResearchTrace(value: unknown): string {
  if (!value || typeof value !== 'object') return '';
  const trace = value as StoredResearchTrace;
  const sources = trace.sources?.accepted ?? [];
  const rejected = trace.sources?.rejected ?? [];
  const searches = trace.search_log ?? [];
  const estimate = trace.estimate_trace;
  const interval = estimate
    ? Object.entries(estimate.confidence_intervals)
        .map(
          ([label, bounds]) =>
            `${e(label)}: ${bounds.lower.toFixed(1)}–${bounds.upper.toFixed(1)}%`,
        )
        .join('<br>')
    : '';
  return `<details class="atlas-research-trace">
    <summary>Research trace · ${e(trace.result_kind ?? 'estimated draft')}</summary>
    ${trace.languages?.length ? `<p><strong>Languages</strong> ${trace.languages.map(e).join(', ')}</p>` : ''}
    ${storedMapping(trace)}
    ${storedVerification(trace)}
    ${sources.map((source) => storedSource(source, 'accepted')).join('')}
    ${rejected.map((source) => storedSource(source.candidate, 'rejected', source.verification.reasons)).join('')}
    ${
      estimate
        ? `<dl>
          <div><dt>Method</dt><dd>${e(estimate.method)}</dd></div>
          <div><dt>Extraction</dt><dd>${estimate.extractions.map((item) => `${e(item.title)}: ${e(JSON.stringify(item.extracted_distribution))} · ${e(item.weight_basis)}`).join('<br>')}</dd></div>
          <div><dt>Calculation</dt><dd>${estimate.calculation.map(e).join('<br>')}</dd></div>
          <div><dt>Assumptions</dt><dd>${estimate.assumptions.map(e).join('<br>')}</dd></div>
          <div><dt>Wide uncertainty</dt><dd>${interval}</dd></div>
          <div><dt>Better data needed</dt><dd>${e(estimate.better_data_needed)}</dd></div>
        </dl>`
        : trace.better_data
          ? `<p><strong>Better data needed</strong> ${e(trace.better_data)}</p>`
          : ''
    }
    ${searches.length ? `<details><summary>${searches.length.toLocaleString()} recorded searches</summary><ul>${searches.map((entry) => `<li>${e(entry.engine)} · ${e(entry.language)} · ${e(entry.outcome)}<br>${e(entry.query_or_source)}${entry.rejection_reasons?.length ? `<br>${entry.rejection_reasons.map(e).join('<br>')}` : ''}</li>`).join('')}</ul></details>` : ''}
  </details>`;
}

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
        ><button class="button primary" data-atlas-action="import" aria-label="Import data">Import data ↗</button>
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
    <nav class="atlas-tabs" role="tablist" aria-label="Data workspace">
      <button type="button" role="tab" aria-selected="true" data-atlas-action="tab" data-atlas-tab="coverage">Coverage</button>
      <button type="button" role="tab" aria-selected="false" data-atlas-action="tab" data-atlas-tab="features">Features</button>
      <button type="button" role="tab" aria-selected="false" data-atlas-action="tab" data-atlas-tab="evidence">Evidence</button>
      <button type="button" role="tab" aria-selected="false" data-atlas-action="tab" data-atlas-tab="cities">Cities</button>
      <button type="button" role="tab" aria-selected="false" data-atlas-action="tab" data-atlas-tab="imports">Imports</button>
    </nav>
    <section class="atlas-panel" data-atlas-panel="coverage" role="tabpanel">
      <div id="atlas-summary" class="atlas-summary"><p class="muted">Loading the atlas…</p></div>
      <div id="atlas-auto-import"></div>
      <div id="atlas-hierarchy-browser"></div>
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
                <th>Estimated cities</th>
                <th>Estimated population</th>
                <th>Missing cities</th>
              </tr>
            </thead>
            <tbody id="atlas-coverage"></tbody>
          </table>
        </div>
      </details>
    </section>
    <section class="atlas-section atlas-evidence-section atlas-panel" data-atlas-panel="features" role="tabpanel" id="atlas-feature-catalog" hidden><p class="muted">Loading feature registry…</p></section>
    <details class="atlas-section atlas-collapsible atlas-panel" data-atlas-panel="evidence" role="tabpanel" id="atlas-choice-panel" open hidden>
      <summary><div><span class="eyebrow">BEHAVIOUR EVIDENCE</span><strong>Choice evidence</strong></div><span>Measured, fitted, label-only, and missing behavioural links</span></summary>
      <section id="atlas-choice-evidence"><p class="muted">Loading choice evidence…</p></section>
    </details>
    <details class="atlas-section atlas-collapsible atlas-panel" data-atlas-panel="cities" role="tabpanel" id="atlas-city-audit" open hidden>
      <summary><div><span class="eyebrow">CITY AUDIT</span><strong>Direct city table</strong></div><span>Advanced filters and row-level provenance</span></summary>
      <section id="atlas-city-browser">
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
            <option value="estimated">Estimated</option>
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
    </details>
    <details class="atlas-section atlas-collapsible atlas-panel" data-atlas-panel="imports" role="tabpanel" id="atlas-history-panel" open hidden>
      <summary>
        <div><span class="eyebrow">PROVENANCE</span><strong>Import versions</strong></div>
        <span>Latest live and draft source versions; older versions remain available below each source.</span>
      </summary>
      <div id="atlas-history"></div>
    </details>
    <footer id="atlas-attribution" class="atlas-attribution atlas-panel" data-atlas-panel="imports" role="tabpanel" hidden></footer>
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
      <h2 id="atlas-import-title">Import atlas data</h2>
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
  const estimatedCells = s.fields.reduce((total, field) => total + field.estimated, 0);
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
      <span class="metric-label">Missing city-field cells</span><strong>${n(missingCells)}</strong
      ><span>${n(imputedCells)} imputed · ${n(estimatedCells)} estimated; excluded from measured and effective coverage</span>
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
      <td>${n(f.estimated)}</td>
      <td>${pct(f.estimated_population_percent)}</td>
      <td>${n(f.missing)}</td>
    </tr>
  `,
    )
    .join('');
}

export function cityRows(cities: AtlasCity[]): string {
  if (!cities.length)
    return '<tr><td colspan="14" class="atlas-empty">No cities match these filters. Adjust your search or load the full backbone.</td></tr>';
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
        ><small>${e(city.tier_reason)}</small>
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
          ${c.fields.map((f) => `<tr><th>${labels[f.field]}<br><span class="field-status ${f.status}">${f.status}</span></th><td><pre>${e(f.value === null ? 'Missing' : typeof f.value === 'number' ? String(f.value) : JSON.stringify(f.value, null, 2))}</pre>${f.unit ? `<small>${e(f.unit)}</small>` : ''}</td><td>${f.provenance ? `${e(f.provenance.source)}<small>Data ${f.provenance.source_date}<br>Published ${f.provenance.published_date}<br>Version ${e(f.provenance.version)}<br>Scope ${e(f.provenance.scope)}<br>Uploader ${e(f.provenance.uploader)}</small>` : `<a href="${e(f.source_url)}" target="_blank" rel="noreferrer">${e(f.suggested_source)} ↗</a>`}${cityResearchTrace(f.research_trace)}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>
    <h3>Still missing</h3>
    <p class="atlas-detail-note">${detail.missing_fields.length ? detail.missing_fields.map((field) => labels[field]).join(', ') : 'No unresolved fields.'}</p>
    <h3>Still needs a city observation</h3>
    <p class="atlas-detail-note">${detail.direct_observation_gaps.length ? detail.direct_observation_gaps.map((field) => `${labels[field]}: ${c.fields.find((f) => f.field === field)!.suggested_source}`).join('<br>') : 'Every field has city-specific observed data.'}</p>
    ${detail.legacy_fields.length ? `<h3>Legacy-only observations</h3><div class="atlas-detail-note">${detail.legacy_fields.map((field) => `<strong>Single-axis ideology</strong> · legacy only · never predictive or split into the three active axes<br><span class="mono">${e(JSON.stringify(field.value))}</span><br>${e(field.provenance.source)} · ${e(field.provenance.version)} · ${field.provenance.source_date}`).join('<br><br>')}</div>` : ''}
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
  const registry = catalog.registry_sources.length
    ? `<div class="atlas-source-inventory">
        <h3>Registry dump status</h3>
        <div class="atlas-source-grid">${catalog.registry_sources
          .map(
            (source) => `<article class="atlas-source">
              <div><h3><a href="${e(source.source_url)}" target="_blank" rel="noreferrer">${e(source.source)} ↗</a></h3>
              <span class="field-status ${source.access_status === 'imported' ? 'present' : source.access_status === 'unavailable' ? 'missing' : 'inherited'}">${e(source.access_status.replace('_', ' '))}</span></div>
              <p>${e(source.level)} · ${e(source.version)}${source.source_date ? ` · ${e(source.source_date)}` : ''}</p>
              <p>${e(source.license)}</p>
              <small>Coverage · ${e(JSON.stringify(source.coverage))}</small>
              ${source.restriction_reason ? `<p>${e(source.restriction_reason)}</p>` : ''}
              ${source.required_action ? `<strong>Needed: ${e(source.required_action)}</strong>` : ''}
              ${source.fallback ? `<small>Current fallback · ${e(source.fallback)}</small>` : ''}
            </article>`,
          )
          .join('')}</div>
      </div>`
    : '';
  const loaders = catalog.sources
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
  return `${registry}<div class="atlas-source-inventory"><h3>Import loaders</h3><div class="atlas-source-grid">${loaders}</div></div>`;
}
