import './decision-evidence.css';

export type DecisionDomain =
  | 'work'
  | 'social'
  | 'family'
  | 'health'
  | 'consumption'
  | 'political'
  | 'other';

export type InputKind = 'trait' | 'place' | 'time' | 'context';
export type PlaceLevel = 'city' | 'country' | 'region' | 'global';
export type EvidenceBasis = 'measured_joint' | 'fitted_model' | 'marginal';
export type FactorStatus =
  | 'measured'
  | 'independence_estimate'
  | 'unknown'
  | 'label_only'
  | 'ambiguous';

export interface ResearchCitation {
  kind: 'article' | 'research_paper';
  imported_source_id: string;
  title: string;
  source: string;
  publication_date: string;
  population_studied: string;
  link_or_reference: string;
  supports_decision_ids: string[];
  supports_factor_ids: string[];
}

export interface NoSourceAttachment {
  kind: 'none';
  label: 'no source attached — estimated / unknown';
  reason: string;
}

export type SourceAttachment = ResearchCitation | NoSourceAttachment;

export interface EvidencePlace {
  level: PlaceLevel;
  place_id: string;
  region_id: string | null;
  country_id: string | null;
  city_id: string | null;
}

export interface EvaluatedFactorReceipt {
  factor_id: string;
  factor_name: string;
  input_kind: InputKind;
  input_key: string;
  evaluated_value: string | number | boolean | null;
  status: FactorStatus;
  estimate: number | null;
  ci_low: number;
  ci_high: number;
  fittable: boolean;
  evidence_id: string | null;
  evidence_basis: EvidenceBasis | null;
  evidence_place: EvidencePlace | null;
  resolved_level: PlaceLevel | null;
  source: SourceAttachment;
  message: string;
}

export interface EvaluatedDecisionProbability {
  decision_id: string;
  edge_id: string;
  formula_id: string;
  formula_name: string;
  expression: string;
  agent_id: string;
  status: 'measured' | 'independence_estimate' | 'unknown';
  status_label: string;
  probability: number | null;
  ci_low: number;
  ci_high: number;
  fittable: boolean;
  factors: EvaluatedFactorReceipt[];
  source: SourceAttachment;
}

export const DECISION_DOMAIN_LABELS: Record<DecisionDomain, string> = {
  work: 'Work',
  social: 'Social',
  family: 'Family',
  health: 'Health',
  consumption: 'Consumption',
  political: 'Political',
  other: 'Other',
};

function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatValue(value: string | number | boolean | null): string {
  if (value === null) return 'Missing';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

function sourceMarkup(source: SourceAttachment, attribute: string): string {
  if (source.kind === 'none') {
    return `
      <section class="decision-source is-missing" ${attribute}>
        <strong>${escapeHtml(source.label)}</strong>
        <span>${escapeHtml(source.reason)}</span>
      </section>
    `;
  }
  return `
    <section class="decision-source" ${attribute}>
      <div class="decision-source-heading">
        <strong>${escapeHtml(source.title)}</strong>
        <span>${source.kind === 'research_paper' ? 'Research paper' : 'Article'}</span>
      </div>
      <dl>
        <div><dt>Source</dt><dd>${escapeHtml(source.source)}</dd></div>
        <div><dt>Date</dt><dd>${escapeHtml(source.publication_date)}</dd></div>
        <div><dt>Population</dt><dd>${escapeHtml(source.population_studied)}</dd></div>
        <div><dt>Reference</dt><dd>${escapeHtml(source.link_or_reference)}</dd></div>
        <div><dt>Import receipt</dt><dd>${escapeHtml(source.imported_source_id)}</dd></div>
      </dl>
    </section>
  `;
}

function factorMarkup(factor: EvaluatedFactorReceipt): string {
  const place = factor.evidence_place
    ? `${factor.evidence_place.level} · ${factor.evidence_place.place_id}`
    : 'No qualifying place evidence';
  const estimate = factor.estimate === null ? 'Unknown' : formatPercent(factor.estimate);
  const basis = factor.evidence_basis?.replaceAll('_', ' ') ?? 'no evidence';
  return `
    <li class="decision-factor is-${factor.status}" data-decision-factor="${escapeHtml(factor.factor_id)}">
      <div class="decision-factor-heading">
        <div>
          <span class="decision-factor-kind">${escapeHtml(factor.input_kind)}</span>
          <strong>${escapeHtml(factor.factor_name)}</strong>
        </div>
        <span class="decision-factor-estimate">${estimate}</span>
      </div>
      <dl class="decision-factor-values">
        <div><dt>Agent value</dt><dd data-factor-value>${escapeHtml(formatValue(factor.evaluated_value))}</dd></div>
        <div><dt>Input</dt><dd>${escapeHtml(factor.input_key)}</dd></div>
        <div><dt>Evidence</dt><dd>${escapeHtml(basis)}</dd></div>
        <div><dt>Place</dt><dd data-factor-place>${escapeHtml(place)}</dd></div>
        <div><dt>Interval</dt><dd>${formatPercent(factor.ci_low)}–${formatPercent(factor.ci_high)}</dd></div>
        <div><dt>Use</dt><dd>${factor.fittable ? 'Predictor eligible' : 'Non-fittable'}</dd></div>
      </dl>
      <p class="decision-factor-message">${escapeHtml(factor.message)}</p>
      ${sourceMarkup(factor.source, 'data-factor-source')}
    </li>
  `;
}

export function renderDecisionEvidence(
  container: HTMLElement,
  evaluation: EvaluatedDecisionProbability,
): void {
  const probability =
    evaluation.probability === null ? 'Unknown' : formatPercent(evaluation.probability);
  container.innerHTML = `
    <article class="decision-evidence is-${evaluation.status}">
      <header class="decision-evidence-header">
        <div>
          <p class="decision-evidence-eyebrow">Agent ${escapeHtml(evaluation.agent_id)} · Edge ${escapeHtml(evaluation.edge_id)}</p>
          <h3>${escapeHtml(evaluation.formula_name)}</h3>
        </div>
        <span class="decision-evidence-status">${escapeHtml(evaluation.status_label)}</span>
      </header>
      <div class="decision-formula">
        <code data-decision-expression>${escapeHtml(evaluation.expression)}</code>
        <div class="decision-probability-summary">
          <div><span>Evaluated probability</span><strong data-decision-probability>${probability}</strong></div>
          <div><span>Uncertainty interval</span><strong data-decision-interval>${formatPercent(evaluation.ci_low)}–${formatPercent(evaluation.ci_high)}</strong></div>
          <div><span>Model use</span><strong data-decision-fit>${evaluation.fittable ? 'Predictor eligible' : 'Label-only / non-fittable'}</strong></div>
        </div>
      </div>
      <section class="decision-factor-list-section">
        <div class="decision-section-heading">
          <h4>Evaluated factors</h4>
          <span>${evaluation.factors.length}</span>
        </div>
        <ul class="decision-factor-list">${evaluation.factors.map(factorMarkup).join('')}</ul>
      </section>
      <section class="decision-citation-section">
        <h4>Decision source</h4>
        ${sourceMarkup(evaluation.source, 'data-decision-source')}
      </section>
    </article>
  `;
}
