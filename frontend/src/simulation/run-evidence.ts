import './run-evidence.css';

export type CoefficientEvidenceState = 'measured' | 'fitted' | 'default_estimated' | 'blocked';

export interface CoefficientPlace {
  level: 'global' | 'region' | 'country' | 'city';
  place_id: string;
  region_id?: string | null;
  country_id?: string | null;
  city_id?: string | null;
}

export interface CoefficientReceipt {
  action_id: string;
  edge_id: string;
  place: CoefficientPlace;
  source_place: CoefficientPlace | null;
  resolution_status: 'direct' | 'inherited' | 'imputed';
  evidence_state: CoefficientEvidenceState;
  value: number;
  interval: { low: number; high: number };
  coefficient_set_id: string;
  default_coefficient_set_id?: string;
  default_value?: number;
  fitted_delta?: number | null;
  promotion_id?: string | null;
  source_label: string;
  source_version: string;
  source_id: string | null;
  default_reason: string | null;
  held_out: {
    held_out_rows: number;
    fitted_score: number;
    default_score: number;
  } | null;
  affected_agents: number;
}

export interface ActionPlaceEvidenceSummary {
  action_id: string;
  place: CoefficientPlace;
  fitted_count: number;
  measured_count?: number;
  default_estimated_count: number;
  blocked_count: number;
  coefficients: CoefficientReceipt[];
}

export interface RunEvidenceSummary {
  fitted_count: number;
  measured_count?: number;
  default_estimated_count: number;
  blocked_count: number;
  by_action_place: ActionPlaceEvidenceSummary[];
}

export interface RunEvidenceWarning {
  code: 'default_estimated_coefficients';
  action_id: string;
  place: CoefficientPlace;
  coefficient_ids: string[];
  message: string;
}

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const titleCase = (value: string): string =>
  value
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const percentage = (value: number): string =>
  value.toLocaleString('en', { style: 'percent', maximumFractionDigits: 2 });

function receiptMarkup(receipt: CoefficientReceipt): string {
  const inherited = receipt.source_place
    ? `<span>Source place ${escapeHtml(receipt.source_place.place_id)} · ${escapeHtml(titleCase(receipt.resolution_status))}</span>`
    : `<span>${escapeHtml(titleCase(receipt.resolution_status))}</span>`;
  const fittedDiff =
    receipt.evidence_state === 'fitted' && typeof receipt.default_value === 'number'
      ? `<p class="run-evidence-diff"><strong>${escapeHtml(percentage(receipt.default_value))} → ${escapeHtml(percentage(receipt.value))}</strong>${typeof receipt.fitted_delta === 'number' ? `<span>${receipt.fitted_delta >= 0 ? '+' : ''}${escapeHtml(percentage(receipt.fitted_delta))}</span>` : ''}</p>`
      : '';
  const promotion = receipt.promotion_id
    ? `<p>Promotion ${escapeHtml(receipt.promotion_id)}</p>`
    : '';
  const reason = receipt.default_reason
    ? `<p>${escapeHtml(receipt.default_reason)}</p>`
    : receipt.held_out
      ? `<p>Held-out validation · ${receipt.held_out.held_out_rows.toLocaleString('en')} held-out rows · fitted ${escapeHtml(String(receipt.held_out.fitted_score))} vs default ${escapeHtml(String(receipt.held_out.default_score))}</p>`
      : '';
  return `<article class="run-evidence-coefficient is-${escapeHtml(receipt.evidence_state)}"><header><div><strong>${escapeHtml(titleCase(receipt.edge_id))}</strong><small>${escapeHtml(receipt.coefficient_set_id)}</small></div><span>${escapeHtml(titleCase(receipt.evidence_state))}</span></header>${fittedDiff}<dl><div><dt>Value</dt><dd>${escapeHtml(percentage(receipt.value))}</dd></div><div><dt>Uncertainty</dt><dd>${escapeHtml(percentage(receipt.interval.low))}–${escapeHtml(percentage(receipt.interval.high))}</dd></div><div><dt>Agents</dt><dd>${receipt.affected_agents.toLocaleString('en')}</dd></div></dl><div class="run-evidence-source"><strong>${escapeHtml(receipt.source_label)}</strong><span>${escapeHtml(receipt.source_version)}</span>${inherited}</div>${promotion}${reason}</article>`;
}

export function runEvidenceMarkup(
  summary: RunEvidenceSummary | undefined,
  warnings: RunEvidenceWarning[] | undefined,
): string {
  if (!summary) return '';
  const groups = summary.by_action_place
    .map(
      (group) =>
        `<details class="run-evidence-group" open><summary><span><strong>${escapeHtml(titleCase(group.action_id))}</strong><small>${escapeHtml(titleCase(group.place.level))} · ${escapeHtml(group.place.place_id)}</small></span><span>${group.default_estimated_count.toLocaleString('en')} default · ${(group.measured_count ?? 0).toLocaleString('en')} measured · ${group.fitted_count.toLocaleString('en')} fitted</span></summary><div>${group.coefficients.map(receiptMarkup).join('')}</div></details>`,
    )
    .join('');
  const warningMarkup = (warnings ?? [])
    .map(
      (warning) =>
        `<li><strong>${escapeHtml(titleCase(warning.action_id))} · ${escapeHtml(warning.place.place_id)}</strong><span>${escapeHtml(warning.message)}</span></li>`,
    )
    .join('');
  return `<section class="run-evidence" role="region" aria-label="Run coefficient evidence"><header><div><span class="small-label">EXECUTION EVIDENCE</span><h3>Coefficient evidence</h3></div><div class="run-evidence-counts"><strong>${summary.default_estimated_count.toLocaleString('en')} default / estimated</strong><span>${(summary.measured_count ?? 0).toLocaleString('en')} measured</span><span>${summary.fitted_count.toLocaleString('en')} fitted</span>${summary.blocked_count ? `<span class="is-blocked">${summary.blocked_count.toLocaleString('en')} blocked</span>` : ''}</div></header>${warningMarkup ? `<ul class="run-evidence-warnings">${warningMarkup}</ul>` : ''}<div class="run-evidence-groups">${groups || '<p>No action coefficients were used by this run.</p>'}</div></section>`;
}
