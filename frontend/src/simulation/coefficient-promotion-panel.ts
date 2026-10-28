import './coefficient-promotion-panel.css';
import type { CoefficientPlace } from './run-evidence';

export type CoefficientTraitValue = string | number | boolean;

export interface AtlasFittedPromotionCandidate {
  action_id: string;
  place: CoefficientPlace;
  target_edge_id: string;
  complement_edge_id: string;
  imported_source_id: string;
  model_id: number;
  model_input_traits: Record<string, CoefficientTraitValue>;
}

export interface CoefficientPromotionChange {
  edge_id: string;
  default_value: number;
  fitted_value: number;
}

export interface FittedModelProvenance {
  imported_source_id: string;
  source: string;
  source_version: string;
  source_date: string;
  published_date: string;
  model_id: number;
  model_input_traits: Record<string, CoefficientTraitValue>;
  evidence_kind: string;
}

export interface HeldOutValidationReceipt {
  metric: 'log_loss';
  held_out_rows: number;
  fitted_score: number;
  default_score: number;
}

export interface CoefficientPromotionDiff {
  promotion_id: string;
  action_id: string;
  place: CoefficientPlace;
  default_coefficient_set_id: string;
  fitted_coefficient_set_id: string;
  changes: CoefficientPromotionChange[];
  provenance: FittedModelProvenance;
  held_out: HeldOutValidationReceipt;
  promoted_at: string;
}

export interface FittedPromotionResponse {
  registry_version: string;
  diff: CoefficientPromotionDiff;
}

export interface CoefficientPromotionClient {
  preview(candidate: AtlasFittedPromotionCandidate): Promise<FittedPromotionResponse>;
  promote(candidate: AtlasFittedPromotionCandidate): Promise<FittedPromotionResponse>;
}

export interface CoefficientPromotionInitialValues {
  importedSourceId?: string;
  modelId?: number;
  actionId?: string;
  regionId?: string;
  countryId?: string;
  targetEdgeId?: string;
  complementEdgeId?: string;
  modelInputTraits?: Record<string, CoefficientTraitValue>;
}

export interface CoefficientPromotionPanelOptions {
  initial?: CoefficientPromotionInitialValues;
  onPromoted?: (response: FittedPromotionResponse) => void;
}

const identifierPattern = /^[a-z][a-z0-9_-]*$/;
let panelSequence = 0;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

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

const score = (value: number): string => value.toLocaleString('en', { maximumFractionDigits: 6 });

function requirePromotionResponse(value: unknown): FittedPromotionResponse {
  if (!isRecord(value) || typeof value.registry_version !== 'string' || !isRecord(value.diff)) {
    throw new Error('The server returned an invalid coefficient promotion contract.');
  }
  const diff = value.diff;
  if (
    typeof diff.promotion_id !== 'string' ||
    typeof diff.action_id !== 'string' ||
    typeof diff.default_coefficient_set_id !== 'string' ||
    typeof diff.fitted_coefficient_set_id !== 'string' ||
    typeof diff.promoted_at !== 'string' ||
    !isRecord(diff.place) ||
    diff.place.level !== 'country' ||
    typeof diff.place.place_id !== 'string' ||
    typeof diff.place.region_id !== 'string' ||
    typeof diff.place.country_id !== 'string' ||
    !Array.isArray(diff.changes) ||
    !isRecord(diff.provenance) ||
    !isRecord(diff.held_out)
  ) {
    throw new Error('The server returned an invalid coefficient promotion diff.');
  }
  if (
    !diff.changes.every(
      (change) =>
        isRecord(change) &&
        typeof change.edge_id === 'string' &&
        isFiniteNumber(change.default_value) &&
        isFiniteNumber(change.fitted_value),
    )
  ) {
    throw new Error('The server returned invalid coefficient changes.');
  }
  const provenance = diff.provenance;
  if (
    typeof provenance.imported_source_id !== 'string' ||
    typeof provenance.source !== 'string' ||
    typeof provenance.source_version !== 'string' ||
    typeof provenance.source_date !== 'string' ||
    typeof provenance.published_date !== 'string' ||
    !isFiniteNumber(provenance.model_id) ||
    !isRecord(provenance.model_input_traits) ||
    typeof provenance.evidence_kind !== 'string'
  ) {
    throw new Error('The server returned invalid fitted model provenance.');
  }
  const heldOut = diff.held_out;
  if (
    heldOut.metric !== 'log_loss' ||
    !isFiniteNumber(heldOut.held_out_rows) ||
    !isFiniteNumber(heldOut.fitted_score) ||
    !isFiniteNumber(heldOut.default_score)
  ) {
    throw new Error('The server returned an invalid held-out validation receipt.');
  }
  return value as unknown as FittedPromotionResponse;
}

async function requestJson(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error('Cannot reach the backend. Start the API, then retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(body) ? body.detail : null;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : `Coefficient promotion request failed (${response.status})`,
    );
  }
  return body;
}

export function createCoefficientPromotionHttpClient(
  basePath = '/api/simulation/coefficient-evidence/promotions',
): CoefficientPromotionClient {
  return {
    preview: async (candidate) =>
      requirePromotionResponse(
        await requestJson(`${basePath}/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(candidate),
        }),
      ),
    promote: async (candidate) =>
      requirePromotionResponse(
        await requestJson(basePath, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ candidate, user_confirmed: true }),
        }),
      ),
  };
}

function parseTraits(raw: string): Record<string, CoefficientTraitValue> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('Model input traits must be valid JSON.');
  }
  if (!isRecord(parsed)) {
    throw new Error('Model input traits must be a JSON object.');
  }
  const traits: Record<string, CoefficientTraitValue> = {};
  for (const [key, value] of Object.entries(parsed)) {
    if (!key.trim()) throw new Error('Model input trait names cannot be empty.');
    if (
      typeof value !== 'string' &&
      typeof value !== 'boolean' &&
      !(typeof value === 'number' && Number.isFinite(value))
    ) {
      throw new Error(`Model input trait ${key} must be a string, number, or boolean.`);
    }
    traits[key] = value;
  }
  return traits;
}

function formValue(form: HTMLFormElement, name: string): string {
  return String(new FormData(form).get(name) ?? '').trim();
}

function candidateFromForm(form: HTMLFormElement): AtlasFittedPromotionCandidate {
  const actionId = formValue(form, 'action_id');
  if (!identifierPattern.test(actionId)) {
    throw new Error(
      'Action ID must start with a letter and use lowercase letters, numbers, _ or -.',
    );
  }
  const targetEdgeId = formValue(form, 'target_edge_id');
  const complementEdgeId = formValue(form, 'complement_edge_id');
  if (targetEdgeId === complementEdgeId) {
    throw new Error('Target and complement edges must be different.');
  }
  const modelId = Number(formValue(form, 'model_id'));
  if (!Number.isInteger(modelId) || modelId <= 0) {
    throw new Error('Atlas model ID must be a positive integer.');
  }
  const regionId = formValue(form, 'region_id');
  const countryId = formValue(form, 'country_id');
  return {
    action_id: actionId,
    place: {
      level: 'country',
      place_id: countryId,
      region_id: regionId,
      country_id: countryId,
      city_id: null,
    },
    target_edge_id: targetEdgeId,
    complement_edge_id: complementEdgeId,
    imported_source_id: formValue(form, 'imported_source_id'),
    model_id: modelId,
    model_input_traits: parseTraits(formValue(form, 'model_input_traits')),
  };
}

function changesMarkup(changes: CoefficientPromotionChange[]): string {
  return changes
    .map((change) => {
      const delta = (change.fitted_value - change.default_value) * 100;
      const signedDelta = `${delta >= 0 ? '+' : ''}${delta.toLocaleString('en', {
        maximumFractionDigits: 2,
      })} pp`;
      return `<tr><th scope="row">${escapeHtml(titleCase(change.edge_id))}<small>${escapeHtml(change.edge_id)}</small></th><td>${escapeHtml(percentage(change.default_value))}</td><td><strong>${escapeHtml(percentage(change.fitted_value))}</strong></td><td class="${delta >= 0 ? 'is-positive' : 'is-negative'}">${escapeHtml(signedDelta)}</td></tr>`;
    })
    .join('');
}

function provenanceMarkup(provenance: FittedModelProvenance): string {
  const traits = JSON.stringify(provenance.model_input_traits, null, 2);
  return `<section class="coefficient-promotion-receipt"><header><span class="coefficient-promotion-eyebrow">PROVENANCE</span><h4>Verified fitted model</h4></header><dl><div class="is-wide"><dt>Source</dt><dd>${escapeHtml(provenance.source)}</dd></div><div><dt>Version</dt><dd>${escapeHtml(provenance.source_version)}</dd></div><div><dt>Model</dt><dd>${provenance.model_id.toLocaleString('en')}</dd></div><div><dt>Source date</dt><dd>${escapeHtml(provenance.source_date)}</dd></div><div><dt>Published</dt><dd>${escapeHtml(provenance.published_date)}</dd></div><div class="is-wide"><dt>Imported source ID</dt><dd><code>${escapeHtml(provenance.imported_source_id)}</code></dd></div><div class="is-wide"><dt>Evidence kind</dt><dd>${escapeHtml(titleCase(provenance.evidence_kind))}</dd></div><div class="is-wide"><dt>Model inputs</dt><dd><pre>${escapeHtml(traits)}</pre></dd></div></dl></section>`;
}

function heldOutMarkup(heldOut: HeldOutValidationReceipt): string {
  const improvement = heldOut.default_score - heldOut.fitted_score;
  return `<section class="coefficient-promotion-receipt"><header><span class="coefficient-promotion-eyebrow">HELD-OUT VALIDATION</span><h4>${heldOut.held_out_rows.toLocaleString('en')} rows</h4></header><dl><div><dt>Metric</dt><dd>${escapeHtml(titleCase(heldOut.metric))}</dd></div><div><dt>Fitted score</dt><dd><strong>${escapeHtml(score(heldOut.fitted_score))}</strong></dd></div><div><dt>Default score</dt><dd>${escapeHtml(score(heldOut.default_score))}</dd></div><div><dt>Loss reduction</dt><dd>${escapeHtml(score(improvement))}</dd></div></dl></section>`;
}

export class CoefficientPromotionPanel {
  private readonly panelId: string;
  private readonly client: CoefficientPromotionClient;
  private previewCandidate: AtlasFittedPromotionCandidate | null = null;
  private previewResponse: FittedPromotionResponse | null = null;
  private busy = false;
  private disposed = false;

  constructor(
    private readonly host: HTMLElement,
    client: CoefficientPromotionClient = createCoefficientPromotionHttpClient(),
    private readonly options: CoefficientPromotionPanelOptions = {},
  ) {
    panelSequence += 1;
    this.panelId = `coefficient-promotion-${panelSequence}`;
    this.client = client;
    this.host.addEventListener('submit', this.onSubmit);
    this.host.addEventListener('input', this.onInput);
    this.host.addEventListener('click', this.onClick);
    this.render();
  }

  dispose(): void {
    this.disposed = true;
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.removeEventListener('input', this.onInput);
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private render(): void {
    const initial = this.options.initial ?? {};
    const traits = JSON.stringify(initial.modelInputTraits ?? {}, null, 2);
    this.host.innerHTML = `<section class="coefficient-promotion-panel" role="region" aria-label="Fitted coefficient promotion"><header class="coefficient-promotion-heading"><div><span class="coefficient-promotion-eyebrow">COEFFICIENT EVIDENCE</span><h3>Promote a verified fit</h3></div><p>Select an active Atlas model built from linked trait, context, and outcome data. The server resolves all probabilities and validation receipts.</p></header><form class="coefficient-promotion-form" data-promotion-form><fieldset data-promotion-fields><legend>Atlas model and action</legend><label for="${this.panelId}-source">Imported source ID<input id="${this.panelId}-source" name="imported_source_id" data-promotion-candidate required value="${escapeHtml(initial.importedSourceId ?? '')}" autocomplete="off"></label><label for="${this.panelId}-model">Atlas model ID<input id="${this.panelId}-model" name="model_id" data-promotion-candidate required min="1" step="1" type="number" value="${escapeHtml(initial.modelId ?? '')}"></label><label for="${this.panelId}-action">Action ID<input id="${this.panelId}-action" name="action_id" data-promotion-candidate required pattern="[a-z][a-z0-9_-]*" value="${escapeHtml(initial.actionId ?? '')}" autocomplete="off"></label></fieldset><fieldset data-promotion-fields><legend>Country overlay</legend><label for="${this.panelId}-region">Region ID<input id="${this.panelId}-region" name="region_id" data-promotion-candidate required value="${escapeHtml(initial.regionId ?? '')}" autocomplete="off"></label><label for="${this.panelId}-country">Country ID<input id="${this.panelId}-country" name="country_id" data-promotion-candidate required value="${escapeHtml(initial.countryId ?? '')}" autocomplete="off"></label><div class="coefficient-promotion-place-note"><strong>Country scope</strong><span>Promotion overlays this country only. Other places retain their current resolution.</span></div></fieldset><fieldset data-promotion-fields><legend>Binary outcomes</legend><label for="${this.panelId}-target">Target edge ID<input id="${this.panelId}-target" name="target_edge_id" data-promotion-candidate required value="${escapeHtml(initial.targetEdgeId ?? '')}" autocomplete="off"></label><label for="${this.panelId}-complement">Complement edge ID<input id="${this.panelId}-complement" name="complement_edge_id" data-promotion-candidate required value="${escapeHtml(initial.complementEdgeId ?? '')}" autocomplete="off"></label><label class="is-wide" for="${this.panelId}-traits">Model input traits<textarea id="${this.panelId}-traits" name="model_input_traits" data-promotion-candidate rows="5" required spellcheck="false">${escapeHtml(traits)}</textarea><small>JSON object with scalar values only. Inputs select a prediction from the verified fitted model.</small></label></fieldset><div class="coefficient-promotion-integrity"><strong>Server-controlled evidence</strong><span>Default and fitted values, source details, and held-out scores cannot be typed here. Preview resolves them from the installed defaults and selected promoted Atlas model.</span></div><div class="coefficient-promotion-actions"><button class="coefficient-promotion-button is-primary" type="submit" data-promotion-preview>Preview fitted overlay</button></div></form><div class="coefficient-promotion-review" data-promotion-review aria-live="polite"><p class="coefficient-promotion-empty">Enter a promoted shared behaviour source and preview its fitted model.</p></div></section>`;
  }

  private readonly onSubmit = (event: SubmitEvent): void => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-promotion-form]')) return;
    event.preventDefault();
    void this.preview(form);
  };

  private readonly onInput = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !target.matches('[data-promotion-candidate]')) return;
    if (this.previewResponse) this.invalidatePreview();
  };

  private readonly onClick = (event: MouseEvent): void => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('[data-promotion-confirm]')) void this.promote();
  };

  private async preview(form: HTMLFormElement): Promise<void> {
    if (this.busy) return;
    let candidate: AtlasFittedPromotionCandidate;
    try {
      candidate = candidateFromForm(form);
    } catch (error) {
      this.renderError(error);
      return;
    }
    this.setBusy(true);
    this.renderLoading('Resolving installed defaults and verified fitted evidence…');
    try {
      const response = await this.client.preview(candidate);
      if (this.disposed) return;
      this.previewCandidate = candidate;
      this.previewResponse = response;
      this.renderPreview(response, false);
    } catch (error) {
      if (!this.disposed) this.renderError(error);
    } finally {
      if (!this.disposed) this.setBusy(false);
    }
  }

  private async promote(): Promise<void> {
    if (this.busy || !this.previewCandidate || !this.previewResponse) return;
    const confirmation = this.host.querySelector<HTMLInputElement>('[data-promotion-confirmation]');
    if (!confirmation?.checked) return;
    this.setBusy(true);
    this.renderFeedback('Promoting the reviewed overlay…', 'status');
    try {
      const response = await this.client.promote(this.previewCandidate);
      if (this.disposed) return;
      this.previewResponse = response;
      this.renderPreview(response, true);
      this.options.onPromoted?.(response);
    } catch (error) {
      if (!this.disposed) {
        this.renderFeedback(error instanceof Error ? error.message : String(error), 'alert');
      }
    } finally {
      if (!this.disposed) this.setBusy(false);
    }
  }

  private invalidatePreview(): void {
    this.previewCandidate = null;
    this.previewResponse = null;
    const review = this.reviewHost();
    review.innerHTML =
      '<p class="coefficient-promotion-stale" role="status">Inputs changed. Preview the overlay again before promotion.</p>';
  }

  private renderPreview(response: FittedPromotionResponse, promoted: boolean): void {
    const { diff } = response;
    const heading = promoted ? 'Fitted overlay promoted' : 'Default → fitted overlay';
    const outcome = promoted
      ? `<div class="coefficient-promotion-success" role="status"><strong>Fitted overlay promoted</strong><span>Promotion <code>${escapeHtml(diff.promotion_id)}</code></span><span>Registry <code>${escapeHtml(response.registry_version)}</code></span></div>`
      : `<div class="coefficient-promotion-confirm"><label><input type="checkbox" data-promotion-confirmation>I reviewed this exact default to fitted overlay and want to promote it.</label><button class="coefficient-promotion-button is-primary" type="button" data-promotion-confirm disabled>Promote fitted overlay</button></div>`;
    this.reviewHost().innerHTML = `<section class="coefficient-promotion-preview" role="region" aria-label="Promotion preview"><header><div><span class="coefficient-promotion-eyebrow">${promoted ? 'PROMOTION RECEIPT' : 'EXACT DIFF'}</span><h3>${heading}</h3></div><div class="coefficient-promotion-scope"><strong>${escapeHtml(titleCase(diff.action_id))}</strong><span>${escapeHtml(diff.place.region_id ?? '')} · ${escapeHtml(diff.place.country_id ?? diff.place.place_id)}</span></div></header><div class="coefficient-promotion-set-ids"><span>Default <code>${escapeHtml(diff.default_coefficient_set_id)}</code></span><span>Fitted <code>${escapeHtml(diff.fitted_coefficient_set_id)}</code></span></div><div class="coefficient-promotion-table-wrap"><table><thead><tr><th scope="col">Transition</th><th scope="col">Default</th><th scope="col">Fitted</th><th scope="col">Change</th></tr></thead><tbody>${changesMarkup(diff.changes)}</tbody></table></div><div class="coefficient-promotion-receipts">${provenanceMarkup(diff.provenance)}${heldOutMarkup(diff.held_out)}</div>${outcome}<p class="coefficient-promotion-feedback" data-promotion-feedback hidden></p></section>`;
    if (!promoted) {
      const confirmation = this.host.querySelector<HTMLInputElement>(
        '[data-promotion-confirmation]',
      );
      confirmation?.addEventListener('input', () => {
        const button = this.host.querySelector<HTMLButtonElement>('[data-promotion-confirm]');
        if (button) button.disabled = !confirmation.checked || this.busy;
      });
    }
  }

  private renderLoading(message: string): void {
    this.reviewHost().innerHTML = `<p class="coefficient-promotion-loading" role="status">${escapeHtml(message)}</p>`;
  }

  private renderError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.reviewHost().innerHTML = `<p class="coefficient-promotion-error" role="alert">${escapeHtml(message)}</p>`;
  }

  private renderFeedback(message: string, role: 'status' | 'alert'): void {
    const feedback = this.host.querySelector<HTMLElement>('[data-promotion-feedback]');
    if (!feedback) return;
    feedback.hidden = false;
    feedback.classList.toggle('is-error', role === 'alert');
    feedback.setAttribute('role', role);
    feedback.textContent = message;
  }

  private setBusy(busy: boolean): void {
    this.busy = busy;
    const panel = this.host.querySelector<HTMLElement>('.coefficient-promotion-panel');
    panel?.setAttribute('aria-busy', String(busy));
    const fields = this.host.querySelectorAll<HTMLFieldSetElement>('[data-promotion-fields]');
    fields.forEach((field) => {
      field.disabled = busy;
    });
    const preview = this.host.querySelector<HTMLButtonElement>('[data-promotion-preview]');
    if (preview) preview.disabled = busy;
    const promote = this.host.querySelector<HTMLButtonElement>('[data-promotion-confirm]');
    const confirmation = this.host.querySelector<HTMLInputElement>('[data-promotion-confirmation]');
    if (promote) promote.disabled = busy || !confirmation?.checked;
  }

  private reviewHost(): HTMLElement {
    const review = this.host.querySelector<HTMLElement>('[data-promotion-review]');
    if (!review) throw new Error('Coefficient promotion review host is missing.');
    return review;
  }
}
