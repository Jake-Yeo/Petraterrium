import './global-demo-summary.css';

export type GlobalDemoEvidenceStatus =
  | 'measured'
  | 'own_country_inherited'
  | 'regional_imputed'
  | 'estimated';

export interface GlobalDemoFieldPlaceEvidence {
  country: string;
  country_code: string;
  status: GlobalDemoEvidenceStatus;
  source: string | null;
  source_place: string | null;
  source_level: 'country' | 'region' | 'global';
  source_version: string | null;
}

export interface GlobalDemoFieldCoverage {
  measured: string[];
  own_country_inherited: string[];
  regional_imputed: string[];
  estimated: string[];
  place_evidence?: GlobalDemoFieldPlaceEvidence[];
}

export interface GlobalDemoDistributionBin {
  label: string;
  percentage: number;
  estimated_agents: number;
}

export interface GlobalDemoDistribution {
  field_id: string;
  label: string;
  summary: string;
  evidence_status: GlobalDemoEvidenceStatus;
  source: string | null;
  source_place: string | null;
  bins: GlobalDemoDistributionBin[];
}

export interface GlobalDemoPlaceComparison {
  comparison_id: string;
  level: 'global' | 'country' | 'region';
  place: string;
  agent_count: number;
  distributions: GlobalDemoDistribution[];
}

export interface GlobalDemoDeviation {
  deviation_id: string;
  field: string;
  status: 'estimated' | 'regional_imputed' | 'omitted';
  places: string[];
  reason: string;
  full_requirement: string;
}

export interface GlobalDemoInteractionSummary {
  status: 'configured' | 'recorded' | 'unavailable';
  run_id: string | null;
  participating_countries: string[];
  participating_regions: string[];
  cross_country_interactions: number;
  cross_region_interactions: number;
}

export interface GlobalDemoSummaryData {
  total_agents: number;
  country_agent_counts: Record<string, number>;
  region_agent_counts: Record<string, number>;
  fields: Record<string, GlobalDemoFieldCoverage>;
  comparisons: GlobalDemoPlaceComparison[];
  deviations: GlobalDemoDeviation[];
  interactions: GlobalDemoInteractionSummary;
}

export interface GlobalDemoAuditIssue {
  code:
    | 'single_country_demo'
    | 'single_region_demo'
    | 'overlapping_evidence_status'
    | 'unrepresented_country'
    | 'missing_major_field'
    | 'missing_evidence_status'
    | 'missing_source_provenance'
    | 'evidence_status_mismatch'
    | 'cross_country_source'
    | 'canadian_source_leakage'
    | 'missing_distribution_comparison'
    | 'missing_deviation_register';
  message: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

const isCountRecord = (value: unknown): value is Record<string, number> =>
  isRecord(value) && Object.values(value).every((count) => typeof count === 'number');

const isEvidenceStatus = (value: unknown): value is GlobalDemoEvidenceStatus =>
  ['measured', 'own_country_inherited', 'regional_imputed', 'estimated'].includes(
    String(value),
  );

const isPlaceEvidence = (value: unknown): value is GlobalDemoFieldPlaceEvidence =>
  isRecord(value) &&
  typeof value.country === 'string' &&
  typeof value.country_code === 'string' &&
  isEvidenceStatus(value.status) &&
  (value.source === null || typeof value.source === 'string') &&
  (value.source_place === null || typeof value.source_place === 'string') &&
  ['country', 'region', 'global'].includes(String(value.source_level)) &&
  (value.source_version === null || typeof value.source_version === 'string');

const isFieldCoverage = (value: unknown): value is GlobalDemoFieldCoverage =>
  isRecord(value) &&
  isStringArray(value.measured) &&
  isStringArray(value.own_country_inherited) &&
  isStringArray(value.regional_imputed) &&
  isStringArray(value.estimated) &&
  (value.place_evidence === undefined ||
    (Array.isArray(value.place_evidence) && value.place_evidence.every(isPlaceEvidence)));

const isDistributionBin = (value: unknown): value is GlobalDemoDistributionBin =>
  isRecord(value) &&
  typeof value.label === 'string' &&
  typeof value.percentage === 'number' &&
  typeof value.estimated_agents === 'number';

const isDistribution = (value: unknown): value is GlobalDemoDistribution =>
  isRecord(value) &&
  typeof value.field_id === 'string' &&
  typeof value.label === 'string' &&
  typeof value.summary === 'string' &&
  isEvidenceStatus(value.evidence_status) &&
  (value.source === null || typeof value.source === 'string') &&
  (value.source_place === null || typeof value.source_place === 'string') &&
  Array.isArray(value.bins) &&
  value.bins.every(isDistributionBin);

const isComparison = (value: unknown): value is GlobalDemoPlaceComparison =>
  isRecord(value) &&
  typeof value.comparison_id === 'string' &&
  ['global', 'country', 'region'].includes(String(value.level)) &&
  typeof value.place === 'string' &&
  typeof value.agent_count === 'number' &&
  Array.isArray(value.distributions) &&
  value.distributions.every(isDistribution);

const isDeviation = (value: unknown): value is GlobalDemoDeviation =>
  isRecord(value) &&
  typeof value.deviation_id === 'string' &&
  typeof value.field === 'string' &&
  ['estimated', 'regional_imputed', 'omitted'].includes(String(value.status)) &&
  isStringArray(value.places) &&
  typeof value.reason === 'string' &&
  typeof value.full_requirement === 'string';

const isInteractions = (value: unknown): value is GlobalDemoInteractionSummary =>
  isRecord(value) &&
  ['configured', 'recorded', 'unavailable'].includes(String(value.status)) &&
  (value.run_id === null || typeof value.run_id === 'string') &&
  isStringArray(value.participating_countries) &&
  isStringArray(value.participating_regions) &&
  typeof value.cross_country_interactions === 'number' &&
  typeof value.cross_region_interactions === 'number';

export const isGlobalDemoSummaryData = (value: unknown): value is GlobalDemoSummaryData =>
  isRecord(value) &&
  typeof value.total_agents === 'number' &&
  isCountRecord(value.country_agent_counts) &&
  isCountRecord(value.region_agent_counts) &&
  isRecord(value.fields) &&
  Object.values(value.fields).every(isFieldCoverage) &&
  Array.isArray(value.comparisons) &&
  value.comparisons.every(isComparison) &&
  Array.isArray(value.deviations) &&
  value.deviations.every(isDeviation) &&
  isInteractions(value.interactions);

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const displayLabel = (value: string): string =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());

const populatedEntries = (values: Record<string, number>): Array<[string, number]> =>
  Object.entries(values)
    .filter(([, count]) => count > 0)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));

const normalizedPlace = (value: string | null): string =>
  String(value ?? '')
    .trim()
    .toLocaleLowerCase();

const isCanada = (value: string | null): boolean =>
  ['ca', 'can', 'canada'].includes(normalizedPlace(value));

const isCanadianSource = (value: string | null): boolean =>
  /statistics canada|statcan|canadian/i.test(String(value ?? ''));

const requiredMajorFields = [
  'age',
  'sex',
  'education',
  'specialization',
  'occupation',
  'personality',
  'values',
  'money',
  'income',
  'expenses',
  'wages',
  'prices',
  'costs',
  'currency',
];

export function auditGlobalDemoSummary(summary: GlobalDemoSummaryData): GlobalDemoAuditIssue[] {
  const issues: GlobalDemoAuditIssue[] = [];
  const countries = populatedEntries(summary.country_agent_counts).map(([country]) => country);
  const regions = populatedEntries(summary.region_agent_counts).map(([region]) => region);
  if (countries.length < 2) {
    issues.push({
      code: 'single_country_demo',
      message: 'The demo must represent multiple countries.',
    });
  }
  if (regions.length < 2) {
    issues.push({
      code: 'single_region_demo',
      message: 'The demo must represent multiple regions.',
    });
  }
  const missingMajorFields = requiredMajorFields.filter((field) => !(field in summary.fields));
  if (missingMajorFields.length) {
    issues.push({
      code: 'missing_major_field',
      message: `Major-field coverage is missing: ${missingMajorFields.join(', ')}.`,
    });
  }
  for (const [field, coverage] of Object.entries(summary.fields)) {
    const categories = [
      ['measured', coverage.measured],
      ['own-country inherited', coverage.own_country_inherited],
      ['regional-imputed', coverage.regional_imputed],
      ['estimated', coverage.estimated],
    ] as const;
    const memberships = new Map<string, string[]>();
    for (const [category, places] of categories) {
      for (const country of places) {
        memberships.set(country, [...(memberships.get(country) ?? []), category]);
        if (!countries.includes(country)) {
          issues.push({
            code: 'unrepresented_country',
            message: `${field} lists ${country}, which is absent from the demo population.`,
          });
        }
      }
    }
    for (const [country, statuses] of memberships) {
      if (statuses.length > 1) {
        issues.push({
          code: 'overlapping_evidence_status',
          message: `${field} assigns ${country} to ${statuses.join(', ')}.`,
        });
      }
    }
    const placeEvidence = coverage.place_evidence ?? [];
    const evidenceByCountry = new Map(
      placeEvidence.map((evidence) => [evidence.country, evidence]),
    );
    for (const country of countries) {
      const statuses = memberships.get(country) ?? [];
      if (!statuses.length) {
        issues.push({
          code: 'missing_evidence_status',
          message: `${field} does not classify ${country} as measured, own-country inherited, regional-imputed, or estimated.`,
        });
      }
      const evidence = evidenceByCountry.get(country);
      if (!evidence) {
        issues.push({
          code: 'missing_source_provenance',
          message: `${field} has no source-place provenance for ${country}.`,
        });
        continue;
      }
      const expectedStatus: GlobalDemoEvidenceStatus | null = statuses.includes(
        'measured',
      )
        ? 'measured'
        : statuses.includes('own-country inherited')
          ? 'own_country_inherited'
          : statuses.includes('regional-imputed')
            ? 'regional_imputed'
            : statuses.includes('estimated')
              ? 'estimated'
              : null;
      if (expectedStatus && evidence.status !== expectedStatus) {
        issues.push({
          code: 'evidence_status_mismatch',
          message: `${field} classifies ${country} as ${expectedStatus.replaceAll('_', ' ')}, but its provenance is ${evidence.status.replaceAll('_', ' ')}.`,
        });
      }
    }
    for (const evidence of placeEvidence) {
      const nonCanadianCountry = !isCanada(evidence.country_code) && !isCanada(evidence.country);
      if (
        nonCanadianCountry &&
        (isCanada(evidence.source_place) || isCanadianSource(evidence.source))
      ) {
        issues.push({
          code: 'canadian_source_leakage',
          message: `${field} for ${evidence.country} points to Canadian evidence (${evidence.source ?? evidence.source_place}).`,
        });
      }
      if (
        ['measured', 'own_country_inherited'].includes(evidence.status) &&
        evidence.source_level === 'country' &&
        evidence.source_place !== null &&
        ![evidence.country, evidence.country_code]
          .map(normalizedPlace)
          .includes(normalizedPlace(evidence.source_place))
      ) {
        issues.push({
          code: 'cross_country_source',
          message: `${field} for ${evidence.country} is labelled own-country but points to ${evidence.source_place}.`,
        });
      }
    }
    for (const [status, places] of [
      ['regional-imputed', coverage.regional_imputed],
      ['estimated', coverage.estimated],
    ] as const) {
      for (const country of places) {
        const logged = summary.deviations.some(
          (deviation) => deviation.field === field && deviation.places.includes(country),
        );
        if (!logged) {
          issues.push({
            code: 'missing_deviation_register',
            message: `${field} is ${status} for ${country}, but that gap is absent from the deviation register.`,
          });
        }
      }
    }
  }
  const hasComparison = (level: GlobalDemoPlaceComparison['level'], place?: string) =>
    summary.comparisons.some(
      (comparison) =>
        comparison.level === level &&
        (!place || comparison.place === place) &&
        comparison.distributions.length > 0,
    );
  const missingCountryComparisons = countries.filter(
    (country) => !hasComparison('country', country),
  );
  const missingRegionComparisons = regions.filter((region) => !hasComparison('region', region));
  if (
    !hasComparison('global') ||
    missingCountryComparisons.length ||
    missingRegionComparisons.length
  ) {
    const gaps = [
      !hasComparison('global') ? 'global' : '',
      missingCountryComparisons.length ? `countries: ${missingCountryComparisons.join(', ')}` : '',
      missingRegionComparisons.length ? `regions: ${missingRegionComparisons.join(', ')}` : '',
    ].filter(Boolean);
    issues.push({
      code: 'missing_distribution_comparison',
      message: `Distribution comparisons are missing for ${gaps.join('; ')}.`,
    });
  }
  if (!summary.deviations.length) {
    issues.push({
      code: 'missing_deviation_register',
      message:
        'The demo summary must explicitly register estimates, imputations, and omissions.',
    });
  }
  return issues;
}

const placeCountMarkup = (label: string, values: Record<string, number>): string => {
  const entries = populatedEntries(values);
  return `<section class="global-demo-place-group"><header><h4>${escapeHtml(label)}</h4><span>${entries.length} represented</span></header><div>${entries
    .map(
      ([place, count]) =>
        `<span class="global-demo-place-pill"><strong>${escapeHtml(place)}</strong><b>${count.toLocaleString('en')}</b></span>`,
    )
    .join('')}</div></section>`;
};

const placesMarkup = (values: string[]): string =>
  values.length
    ? values.map((value) => `<span>${escapeHtml(value)}</span>`).join('')
    : '<em>None</em>';

const sourceAuditMarkup = (coverage: GlobalDemoFieldCoverage): string => {
  const evidence = coverage.place_evidence ?? [];
  if (!evidence.length) {
    return '<span class="global-demo-source-missing">Source-place provenance missing</span>';
  }
  const rows = [...evidence]
    .sort((left, right) => left.country.localeCompare(right.country))
    .map(
      (item) => `<li>
        <strong>${escapeHtml(item.country)}</strong>
        <span>${escapeHtml(displayLabel(item.status))}</span>
        <span>${escapeHtml(item.source ?? 'No source')}</span>
        <span>${escapeHtml(item.source_place ?? 'No source place')}${item.source_version ? ` · ${escapeHtml(item.source_version)}` : ''}</span>
      </li>`,
    )
    .join('');
  return `<details class="global-demo-source-audit"><summary>Source audit · ${evidence.length} places</summary><ul>${rows}</ul></details>`;
};

const evidenceMarkup = (summary: GlobalDemoSummaryData): string => {
  const rows = Object.entries(summary.fields)
    .map(
      ([field, coverage]) => `<tr>
        <th scope="row"><strong>${escapeHtml(displayLabel(field))}</strong>${sourceAuditMarkup(coverage)}</th>
        <td><div class="global-demo-place-list">${placesMarkup(coverage.measured)}</div></td>
        <td><div class="global-demo-place-list">${placesMarkup(coverage.own_country_inherited)}</div></td>
        <td><div class="global-demo-place-list">${placesMarkup(coverage.regional_imputed)}</div></td>
        <td><div class="global-demo-place-list">${placesMarkup(coverage.estimated)}</div></td>
      </tr>`,
    )
    .join('');
  return `<div class="global-demo-evidence" data-global-demo-panel="evidence">
    <div class="global-demo-place-grid">
      ${placeCountMarkup('Countries', summary.country_agent_counts)}
      ${placeCountMarkup('Regions', summary.region_agent_counts)}
    </div>
    <div class="global-demo-table-scroll">
      <table>
        <thead><tr><th scope="col">Major field</th><th scope="col">Measured</th><th scope="col">Own-country inherited</th><th scope="col">Regional-imputed</th><th scope="col">Estimated</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
};

const distributionMarkup = (distribution: GlobalDemoDistribution): string => {
  const bins = distribution.bins
    .map(
      (bin) => `<li>
        <div><span>${escapeHtml(bin.label)}</span><strong>${bin.percentage.toLocaleString('en', { maximumFractionDigits: 1 })}%</strong></div>
        <span class="global-demo-distribution-track"><i style="--distribution-percentage:${Math.min(100, Math.max(0, bin.percentage))}%"></i></span>
        <small>${bin.estimated_agents.toLocaleString('en')} agents</small>
      </li>`,
    )
    .join('');
  return `<article class="global-demo-distribution-card">
    <header><div><h4>${escapeHtml(distribution.label)}</h4><p>${escapeHtml(distribution.summary)}</p></div><span data-evidence-status="${distribution.evidence_status}">${escapeHtml(displayLabel(distribution.evidence_status))}</span></header>
    <ul>${bins}</ul>
    <footer><span>${escapeHtml(distribution.source ?? 'Source metadata not supplied')}</span><b>${escapeHtml(distribution.source_place ?? 'Source place not supplied')}</b></footer>
  </article>`;
};

const comparisonsMarkup = (summary: GlobalDemoSummaryData): string => {
  const comparisons = summary.comparisons;
  const options = comparisons
    .map(
      (comparison) =>
        `<option value="${escapeHtml(comparison.comparison_id)}">${escapeHtml(displayLabel(comparison.level))} · ${escapeHtml(comparison.place)} · ${comparison.agent_count.toLocaleString('en')} agents</option>`,
    )
    .join('');
  const panels = comparisons
    .map(
      (
        comparison,
        index,
      ) => `<section class="global-demo-comparison" data-global-demo-comparison="${escapeHtml(comparison.comparison_id)}"${index ? ' hidden' : ''}>
        <header><div><span>${escapeHtml(displayLabel(comparison.level))}</span><h4>${escapeHtml(comparison.place)}</h4></div><strong>${comparison.agent_count.toLocaleString('en')} agents</strong></header>
        <div class="global-demo-distribution-grid">${comparison.distributions.map(distributionMarkup).join('')}</div>
      </section>`,
    )
    .join('');
  return `<div class="global-demo-comparisons" data-global-demo-panel="comparisons" hidden>
    ${comparisons.length ? `<label>Compare distributions<select data-global-demo-comparison-select>${options}</select></label>${panels}` : '<div class="global-demo-empty">No global and place distribution comparison was supplied.</div>'}
  </div>`;
};

const deviationMarkup = (summary: GlobalDemoSummaryData): string => {
  const interactions = summary.interactions;
  const deviations = summary.deviations
    .map(
      (deviation) => `<li>
        <header><span data-deviation-status="${deviation.status}">${escapeHtml(displayLabel(deviation.status))}</span><strong>${escapeHtml(displayLabel(deviation.field))}</strong></header>
        <p><b>${escapeHtml(deviation.places.join(', ') || 'Global')}</b> · ${escapeHtml(deviation.reason)}</p>
        <small>Full version requires: ${escapeHtml(deviation.full_requirement)}</small>
      </li>`,
    )
    .join('');
  const interactionLabel =
    interactions.status === 'recorded'
      ? `${interactions.cross_country_interactions.toLocaleString('en')} cross-country · ${interactions.cross_region_interactions.toLocaleString('en')} cross-region interactions`
      : interactions.status === 'configured'
        ? 'Cross-country interaction rules configured; launch a run for recorded counts'
        : 'Cross-country interaction evidence unavailable';
  return `<div class="global-demo-deviations" data-global-demo-panel="deviations" hidden>
    <section class="global-demo-interactions" aria-label="Global interaction coverage">
      <header><div><span>Interaction coverage</span><h4>${escapeHtml(displayLabel(interactions.status))}</h4></div>${interactions.run_id ? `<code>${escapeHtml(interactions.run_id)}</code>` : ''}</header>
      <p>${escapeHtml(interactionLabel)}</p>
      <div><span><b>${interactions.participating_countries.length}</b> participating countries</span><span><b>${interactions.participating_regions.length}</b> participating regions</span></div>
    </section>
    <section class="global-demo-deviation-register"><header><h4>Deviations and data gaps</h4><span>${summary.deviations.length} registered</span></header><ul>${deviations || '<li class="global-demo-empty">No deviations were registered.</li>'}</ul></section>
  </div>`;
};

const auditMarkup = (issues: GlobalDemoAuditIssue[]): string => {
  if (!issues.length) {
    return `<div class="global-demo-audit global-demo-audit-pass" role="status"><strong>Country isolation verified</strong><span>Measured, inherited, regional-imputed, and estimated evidence remain distinct. No cross-country fallback was detected.</span></div>`;
  }
  return `<div class="global-demo-audit global-demo-audit-fail" role="alert"><strong>Global demo integrity failed</strong><ul>${issues.map((issue) => `<li>${escapeHtml(issue.message)}</li>`).join('')}</ul></div>`;
};

export function globalDemoSummaryMarkup(summary: GlobalDemoSummaryData): string {
  const issues = auditGlobalDemoSummary(summary);
  return `<section class="global-demo-summary" aria-labelledby="global-demo-summary-title">
    <header class="global-demo-heading"><div><span>GLOBAL DEMO</span><h3 id="global-demo-summary-title">Population, evidence, and gaps</h3><p>${summary.total_agents.toLocaleString('en')} agents across ${populatedEntries(summary.country_agent_counts).length} countries and ${populatedEntries(summary.region_agent_counts).length} regions.</p></div>${auditMarkup(issues)}</header>
    <nav class="global-demo-tabs" aria-label="Global demo summary sections">
      <button type="button" aria-selected="true" data-global-demo-tab="evidence">Coverage</button>
      <button type="button" aria-selected="false" data-global-demo-tab="comparisons">Distributions</button>
      <button type="button" aria-selected="false" data-global-demo-tab="deviations">Deviations</button>
    </nav>
    ${evidenceMarkup(summary)}
    ${comparisonsMarkup(summary)}
    ${deviationMarkup(summary)}
  </section>`;
}

export class GlobalDemoSummaryView {
  private readonly onClick = (event: Event): void => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-global-demo-tab]',
    );
    if (!button) return;
    const selected = button.dataset.globalDemoTab;
    this.host
      .querySelectorAll<HTMLButtonElement>('[data-global-demo-tab]')
      .forEach((item) => item.setAttribute('aria-selected', String(item === button)));
    this.host
      .querySelectorAll<HTMLElement>('[data-global-demo-panel]')
      .forEach((panel) => (panel.hidden = panel.dataset.globalDemoPanel !== selected));
  };

  private readonly onChange = (event: Event): void => {
    const select = (event.target as HTMLElement).closest<HTMLSelectElement>(
      '[data-global-demo-comparison-select]',
    );
    if (!select) return;
    this.host
      .querySelectorAll<HTMLElement>('[data-global-demo-comparison]')
      .forEach((panel) => (panel.hidden = panel.dataset.globalDemoComparison !== select.value));
  };

  constructor(
    private readonly host: HTMLElement,
    summary: GlobalDemoSummaryData,
  ) {
    this.host.innerHTML = globalDemoSummaryMarkup(summary);
    this.host.addEventListener('click', this.onClick);
    this.host.addEventListener('change', this.onChange);
  }

  destroy(): void {
    this.host.removeEventListener('click', this.onClick);
    this.host.removeEventListener('change', this.onChange);
  }
}
