import './evidence_styles.css';
import type {
  ChoiceEvidenceCatalog,
  FeatureDefinition,
  HierarchyOverview,
  HierarchyRow,
  UniversalFeatureOverview,
} from '../contracts.generated';
import { escapeHtml as e } from '../views';
import { labels } from './views';

const n = (value: number): string => value.toLocaleString('en');
const pct = (value: number): string => `${value.toFixed(1)}%`;
const words = (value: string): string => value.replaceAll('_', ' ');

function featureSchema(feature: FeatureDefinition): string {
  if (feature.value_range)
    return `${feature.value_range.minimum}–${feature.value_range.maximum} ${e(feature.value_range.unit)}`;
  return `${feature.canonical_values?.length ?? 0} canonical values`;
}

export function universalFeatureView(view: UniversalFeatureOverview): string {
  const distributions = new Map<string, number>();
  (view.registry.distributions ?? []).forEach((distribution) =>
    distributions.set(
      distribution.feature_id,
      (distributions.get(distribution.feature_id) ?? 0) + 1,
    ),
  );
  const proofs = new Map<string, number>();
  (view.registry.joint_data ?? []).forEach((proof) =>
    proofs.set(proof.feature_id, (proofs.get(proof.feature_id) ?? 0) + 1),
  );
  return `
    <div class="atlas-evidence-heading">
      <div><p class="eyebrow">UNIVERSAL FEATURE REGISTRY</p><h2>Portable schemas, place-specific distributions</h2></div>
      <span class="mono">${e(view.registry.version)} · ${n(view.registry.definitions.length)} FEATURES</span>
    </div>
    <div class="universal-feature-grid">
      ${view.registry.definitions
        .map(
          (feature) => `
            <article class="universal-feature ${feature.provenance.status === 'label_only' ? 'label-only' : ''}">
              <div><strong>${e(feature.id)}</strong><span>${e(feature.kind)}</span></div>
              <p>${featureSchema(feature)}</p>
              <div class="feature-proof-row">
                <span class="field-status ${distributions.has(feature.id) ? 'present' : 'missing'}">${distributions.get(feature.id) ?? 0} place distributions</span>
                <span class="field-status ${proofs.has(feature.id) ? 'present' : 'missing'}">${proofs.get(feature.id) ?? 0} joint-data proofs</span>
              </div>
              ${feature.ancestry_linked ? '<small>Ancestry-linked · measured or compositional only</small>' : ''}
              ${feature.predictive ? '' : '<small>Label-only · excluded from predictors without joint data</small>'}
            </article>`,
        )
        .join('')}
    </div>
    <div class="feature-resolution-list">
      ${view.resolutions
        .map(
          (resolution) => `
          <article>
            <div><strong>${e(resolution.feature_id)}</strong><span class="field-status ${e(resolution.status)}">${e(resolution.status)}</span>${resolution.region_override ? '<span class="region-override">REGION OVERRIDE</span>' : ''}</div>
            <p>${e(resolution.city)} → ${e(resolution.country)} → ${e(resolution.region)} · resolved at ${e(resolution.resolved_level)}</p>
            <small>${resolution.source ? `${e(resolution.source)} · ${e(resolution.version ?? '')} · ${e(resolution.source_date ?? 'undated')} · ${e(resolution.population ?? 'population unspecified')} · ${resolution.coverage_percent == null ? 'coverage unspecified' : `${pct(resolution.coverage_percent)} coverage`}` : 'No distribution source'}${resolution.missing_requirement ? ` · needs ${e(resolution.missing_requirement)}` : ''}</small>
          </article>`,
        )
        .join('')}
    </div>`;
}

function hierarchyStatuses(row: HierarchyRow): string {
  return Object.entries(labels)
    .map(([field, label]) => {
      const status = row.statuses[field] ?? 'missing';
      const coverage = row.coverage_by_field[field] ?? 0;
      return `<span title="${e(label)} · ${pct(coverage)}"><i class="field-status ${status}">${status}</i><small>${e(label)} ${pct(coverage)}</small></span>`;
    })
    .join('');
}

export function hierarchyView(view: HierarchyOverview): string {
  const global = view.rows.find((row) => row.level === 'global');
  const regions = view.rows.filter((row) => row.level === 'region');
  const countries = view.rows.filter((row) => row.level === 'country');
  const row = (item: HierarchyRow, countryAction = false): string => `
    <div class="hierarchy-row hierarchy-${item.level}">
      <div><strong>${e(item.label)}</strong><small>${n(item.city_count)} cities · ${n(item.population)} listed population</small></div>
      <div class="hierarchy-statuses">${hierarchyStatuses(item)}</div>
      ${countryAction ? `<button class="text-button" data-atlas-action="hierarchy-country" data-country="${e(item.country_code ?? '')}">Open city rows →</button>` : '<span></span>'}
    </div>`;
  return `
    <div class="atlas-evidence-heading">
      <div><p class="eyebrow">GLOBAL → REGION → COUNTRY → CITY</p><h2>Distribution fallback hierarchy</h2></div>
      <span class="mono">${e(view.mapping_version)} · ${e(view.scope)}</span>
    </div>
    <p class="hierarchy-order">Most specific wins: ${view.resolution_order.map(e).join(' → ')}. City children open in the server-paged city table.</p>
    ${global ? row(global) : ''}
    <div class="hierarchy-regions">
      ${regions
        .map((region) => {
          const children = countries.filter((country) => country.parent_id === region.row_id);
          return `<details><summary>${row(region)}</summary><div class="hierarchy-countries">${children.map((country) => row(country, true)).join('') || '<p class="atlas-empty">No cities mapped to this region.</p>'}</div></details>`;
        })
        .join('')}
    </div>
    <p class="hierarchy-source">Aggregation weights: ${e(global?.weight_source ?? 'not available')}. Coverage is always shown with the aggregate.</p>`;
}

export function choiceEvidenceView(catalog: ChoiceEvidenceCatalog): string {
  return `
    <div class="atlas-evidence-heading">
      <div><p class="eyebrow">CHOICE EVIDENCE</p><h2>What agents do, separate from who they are</h2></div>
      <div class="atlas-evidence-actions"><span class="mono">${n(catalog.rows.length)} CONDITIONAL ROWS</span><button class="button primary" type="button" data-atlas-action="import-evidence">Import behavior evidence</button></div>
    </div>
    <div class="table-scroll">
      <table class="choice-evidence-table">
        <thead><tr><th>Action / conditioning</th><th>Evidence</th><th>Probability / CI</th><th>n / date</th><th>Population / denominator</th><th>Provenance</th></tr></thead>
        <tbody>${catalog.rows
          .map(
            (item) => `
              <tr class="choice-${item.tier_flag}">
                <th>${e(item.action_id)}<small>${e(item.conditioning_id)} · ${e(item.definition)} · per ${e(item.time_unit)}</small></th>
                <td><span class="choice-tier">T${item.tier}</span><span class="field-status ${item.tier_flag === 'measured' ? 'present' : item.tier_flag === 'imputed' ? 'imputed' : 'missing'}">${e(words(item.tier_flag))}</span><small>${e(words(item.source_type))}</small></td>
                <td>${item.value == null ? 'No coefficient' : item.value.toFixed(3)}<small>${item.ci_low.toFixed(3)}–${item.ci_high.toFixed(3)}</small></td>
                <td>${item.sample_size == null ? 'No sample' : n(item.sample_size)}<small>${e(item.source_date ?? 'Undated')}</small></td>
                <td>${e(item.population)}<small>${e(item.denominator)}</small></td>
                <td>${e(item.provenance.source)}<small>${e(item.provenance.version)} · uncertainty ${item.provenance.uncertainty.toFixed(2)}${item.missing_requirement ? `<br>${e(item.missing_requirement)}` : ''}</small></td>
              </tr>`,
          )
          .join('')}</tbody>
      </table>
    </div>`;
}
