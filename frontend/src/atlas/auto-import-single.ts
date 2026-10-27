import { escapeHtml as e } from '../views';
import type {
  AutoImportAttempt,
  AutoImportClient,
  AutoImportSourceInput,
  AutoImportTarget,
  MappingColumn,
  ResearchSearchEntry,
  ResearchSource,
  VerificationCheck,
} from './auto-import-model';

type SingleDialogOptions = {
  client: AutoImportClient;
  context: () => { scope: string; asOf: string };
  onPromoted?: (attempt: AutoImportAttempt) => void | Promise<void>;
  onChanged?: (attempt: AutoImportAttempt) => void | Promise<void>;
  onError?: (message: string) => void;
};

const integer = new Intl.NumberFormat('en');

function safeWebUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function promotionConfirmation(scope: string): string {
  if (scope === 'shared') {
    return 'I confirm this source permits redistribution in the shared atlas.';
  }
  return `I confirm this distribution can be added to run ${scope.slice(0, 8)} and remains scoped to that run.`;
}

function sentence(value: string): string {
  return value
    .split(/[._-]/)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ''}${part.slice(1)}`)
    .join(' ');
}

function requirementView(target: AutoImportTarget): string {
  const requirement = target.required_distribution;
  const values = requirement.values.length
    ? requirement.values
        .map((value) => `<li><code>${e(value.id)}</code>${e(value.label)}</li>`)
        .join('')
    : '<li>Continuous distribution</li>';
  return `<section class="auto-import-requirement" aria-labelledby="auto-import-requirement-title">
    <h3 id="auto-import-requirement-title">Required distribution</h3>
    <dl>
      <div><dt>Values</dt><dd><ul>${values}</ul></dd></div>
      <div><dt>Denominator</dt><dd>${e(requirement.denominator)}</dd></div>
      <div><dt>Time unit</dt><dd>${e(requirement.time_unit)}</dd></div>
      <div><dt>Unit</dt><dd>${e(requirement.unit)}</dd></div>
      ${requirement.range ? `<div><dt>Range</dt><dd>${e(requirement.range)}</dd></div>` : ''}
      ${requirement.total ? `<div><dt>Total</dt><dd>${e(requirement.total)}</dd></div>` : ''}
    </dl>
  </section>`;
}

function sourceForm(): string {
  return `<form class="auto-import-source-form" data-auto-import-source-form>
    <div class="auto-import-step-heading"><span>1</span><div><h3>Add sources</h3><p>Sources are checked before broader research begins.</p></div></div>
    <label>Source URLs<textarea name="urls" rows="3" placeholder="One URL per line"></textarea></label>
    <label class="auto-import-file">Source files<input name="files" type="file" multiple accept=".csv,.json,.parquet,.txt,.tsv,.html" /><span data-auto-import-file-label>No files selected</span></label>
    <label>Pasted source text<textarea name="pasted_text" rows="6" placeholder="Paste a table, extract, or source text"></textarea></label>
    <div class="auto-import-form-actions">
      <button class="button primary" type="submit">Research automatically</button>
      <span>Local-language official sources are searched first; English sources follow.</span>
    </div>
  </form>`;
}

function mappingOptions(mapping: MappingColumn): string {
  const options = [...mapping.options];
  if (mapping.target && !options.some((option) => option.id === mapping.target)) {
    options.unshift({ id: mapping.target, label: sentence(mapping.target) });
  }
  return `<option value="">Unknown</option>${options
    .map(
      (option) =>
        `<option value="${e(option.id)}"${option.id === mapping.target ? ' selected' : ''}>${e(option.label)}</option>`,
    )
    .join('')}`;
}

function mappingView(attempt: AutoImportAttempt): string {
  const rows = attempt.mappings
    .map(
      (mapping, index) => `<tr class="${mapping.ambiguous ? 'ambiguous' : ''}">
        <th>${e(mapping.column)}${mapping.ambiguous ? '<span>Ambiguous</span>' : ''}</th>
        <td>${mapping.samples.length ? mapping.samples.map(e).join(' · ') : 'No sample'}</td>
        <td><label><span class="visually-hidden">Map ${e(mapping.column)}</span><select data-auto-import-mapping="${index}">${mappingOptions(mapping)}</select></label></td>
      </tr>`,
    )
    .join('');
  return `<form data-auto-import-mapping-form>
    <div class="auto-import-step-heading"><span>2</span><div><h3>Confirm mapping</h3><p>Unknown columns stay unused until you map them.</p></div></div>
    <div class="auto-import-table-scroll"><table class="auto-import-mapping-table">
      <thead><tr><th>Source column</th><th>Samples</th><th>Canonical target</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="3">No mappable columns were found.</td></tr>'}</tbody>
    </table></div>
    <label class="auto-import-check"><input type="checkbox" name="mapping_reviewed" />I reviewed every mapping, including values, units, denominator, geography, and date.</label>
    <div class="auto-import-form-actions"><button class="button primary" type="submit">Confirm mapping and verify</button></div>
  </form>`;
}

function verificationView(checks: VerificationCheck[]): string {
  if (!checks.length) return '';
  return `<section class="auto-import-review-section"><h3>Verification</h3><ul class="auto-import-checks">${checks
    .map(
      (check) =>
        `<li class="${check.status}"><i>${check.status === 'passed' ? '✓' : check.status === 'failed' ? '×' : '?'}</i><div><strong>${e(check.label)}</strong><span>${e(check.detail)}</span></div></li>`,
    )
    .join('')}</ul></section>`;
}

function sourceView(source: ResearchSource): string {
  const status = source.accepted ? 'accepted' : 'rejected';
  const href = safeWebUrl(source.url);
  const link = href
    ? `<a href="${e(href)}" target="_blank" rel="noreferrer">Open source ↗</a>`
    : '';
  const metadata = [
    source.publisher,
    source.source_date ? `observed ${source.source_date}` : null,
    source.published_date ? `published ${source.published_date}` : null,
    source.version,
    source.licence,
  ]
    .filter(Boolean)
    .map((value) => e(String(value)))
    .join(' · ');
  const excerpt = source.original_excerpt
    ? `<div><dt>Original · ${e(source.language)}</dt><dd lang="${e(source.language)}">${e(source.original_excerpt)}</dd></div>`
    : '';
  const translation = source.translated_excerpt
    ? `<div><dt>English translation</dt><dd>${e(source.translated_excerpt)}</dd></div>`
    : '';
  return `<article class="auto-import-source ${status}">
    <div><span class="auto-import-source-status">${status}</span><h4>${e(source.title)}</h4>${link}</div>
    <p>${metadata || 'Source metadata unavailable'}</p>
    ${source.rejection_reason ? `<p class="auto-import-rejection">${e(source.rejection_reason)}</p>` : ''}
    ${excerpt || translation ? `<details><summary>Source text and translation</summary><dl>${excerpt}${translation}</dl></details>` : ''}
  </article>`;
}

function searchLogView(entries: ResearchSearchEntry[]): string {
  if (!entries.length) return '';
  return `<details class="auto-import-search-log"><summary>Research search log · ${entries.length}</summary><div class="auto-import-table-scroll"><table>
    <thead><tr><th>Engine</th><th>Language</th><th>Query</th><th>Results</th><th>Outcome</th><th>Reasons</th></tr></thead>
    <tbody>${entries
      .map(
        (entry) =>
          `<tr><td>${e(entry.engine)}</td><td>${e(entry.language)}</td><td>${e(entry.query)}</td><td>${integer.format(entry.result_count)}</td><td>${e(entry.outcome)}</td><td>${entry.rejection_reasons.length ? entry.rejection_reasons.map(e).join('<br>') : '—'}</td></tr>`,
      )
      .join('')}</tbody>
  </table></div></details>`;
}

function valuesView(attempt: AutoImportAttempt): string {
  const entries = Object.entries(attempt.candidate_values);
  if (!entries.length) return '';
  return `<section class="auto-import-review-section"><h3>Distribution</h3><dl class="auto-import-values">${entries
    .map(
      ([key, value]) =>
        `<div><dt>${e(sentence(key))}</dt><dd>${value === null ? 'Unknown' : e(String(value))}</dd></div>`,
    )
    .join('')}</dl></section>`;
}

function estimateView(attempt: AutoImportAttempt): string {
  const trace = attempt.estimate_trace;
  if (!trace) return '';
  return `<section class="auto-import-review-section auto-import-estimate"><h3>Estimate trace</h3>
    <dl><div><dt>Method</dt><dd>${e(trace.method)}</dd></div><div><dt>Calculation</dt><dd>${e(trace.calculation)}</dd></div><div><dt>Confidence interval</dt><dd>${e(trace.confidence_interval)}</dd></div></dl>
    ${trace.inputs.length ? `<h4>Inputs</h4><ul>${trace.inputs.map((input) => `<li><strong>${e(input.label)}</strong><span>${e(input.value)}</span></li>`).join('')}</ul>` : ''}
    ${trace.assumptions.length ? `<h4>Assumptions</h4><ul>${trace.assumptions.map((value) => `<li>${e(value)}</li>`).join('')}</ul>` : ''}
    ${trace.limitations.length ? `<h4>Better data needed</h4><ul>${trace.limitations.map((value) => `<li>${e(value)}</li>`).join('')}</ul>` : ''}
  </section>`;
}

function reviewView(attempt: AutoImportAttempt, scope: string): string {
  const evidence = attempt.evidence_kind
    ? `<span class="auto-import-evidence ${attempt.evidence_kind}">${attempt.evidence_kind}</span>`
    : '<span class="auto-import-evidence unresolved">unresolved</span>';
  const error = attempt.error
    ? `<div class="auto-import-error" role="alert">${e(attempt.error)}</div>`
    : '';
  const promote = attempt.can_promote
    ? `<form class="auto-import-promote" data-auto-import-promote-form>
        <label class="auto-import-check"><input type="checkbox" name="redistribution_confirmed" />${e(promotionConfirmation(scope))}</label>
        <button class="button primary" type="submit">Promote</button>
      </form>`
    : '';
  const researchAgain =
    attempt.stage === 'failed'
      ? '<button class="button secondary" type="button" data-auto-import-action="continue-research">Retry unresolved research</button>'
      : '';
  return `<div class="auto-import-review">
    <div class="auto-import-review-heading"><div><span>Review result</span><h3>${attempt.evidence_kind ? `${sentence(attempt.evidence_kind)} evidence` : 'No credible distribution found'}</h3></div>${evidence}</div>
    ${error}${verificationView(attempt.verification)}${valuesView(attempt)}
    <section class="auto-import-review-section"><h3>Sources</h3><div class="auto-import-sources">${attempt.sources.map(sourceView).join('') || '<p>No credible source was accepted.</p>'}</div></section>
    ${estimateView(attempt)}${searchLogView(attempt.search_log)}
    <div class="auto-import-review-actions">${researchAgain}${promote}</div>
  </div>`;
}

function stageView(attempt: AutoImportAttempt | undefined, scope: string): string {
  if (!attempt) return sourceForm();
  if (attempt.stage === 'collecting' || attempt.stage === 'verifying') {
    return `<div class="auto-import-working" role="status"><span></span><strong>${attempt.stage === 'collecting' ? 'Checking sources and researching' : 'Verifying mapped data'}</strong><p>This attempt remains recorded if no credible source is found.</p></div>`;
  }
  if (attempt.stage === 'mapping') return mappingView(attempt);
  return reviewView(attempt, scope);
}

export class AutoImportSingleDialog {
  private target?: AutoImportTarget;
  private current?: AutoImportAttempt;
  private busy = false;

  constructor(
    private readonly dialog: HTMLDialogElement,
    private readonly options: SingleDialogOptions,
  ) {
    dialog.classList.add('auto-import-dialog');
    dialog.addEventListener('click', this.onClick);
    dialog.addEventListener('submit', this.onSubmit);
    dialog.addEventListener('change', this.onChange);
  }

  openTarget(target: AutoImportTarget): void {
    this.target = target;
    this.current = undefined;
    this.render();
    this.dialog.showModal();
  }

  async openAttempt(attemptId: string): Promise<void> {
    this.setBusy(true);
    try {
      this.current = await this.options.client.attempt(attemptId);
      this.target = this.current.target;
      this.render();
      if (!this.dialog.open) this.dialog.showModal();
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }

  close(): void {
    this.dialog.close();
  }

  destroy(): void {
    this.dialog.removeEventListener('click', this.onClick);
    this.dialog.removeEventListener('submit', this.onSubmit);
    this.dialog.removeEventListener('change', this.onChange);
  }

  private render(): void {
    if (!this.target) return;
    const target = this.target;
    this.dialog.setAttribute('aria-labelledby', 'auto-import-dialog-title');
    this.dialog.innerHTML = `<div class="auto-import-dialog-top">
      <div><p>${e(target.level)} · ${integer.format(target.population)} people</p><h2 id="auto-import-dialog-title">${e(target.field_label)} for ${e(target.place_label)}</h2></div>
      <button class="icon-button" type="button" data-auto-import-action="close" aria-label="Cancel auto-import">×</button>
    </div>
    <div class="auto-import-target-facts"><span>Place <strong>${e(target.place_label)}</strong></span><span>Level <strong>${e(target.level)}</strong></span><span>Feature <strong>${e(target.field_label)}</strong></span><span>Current status <strong>${e(target.current_status)}</strong></span></div>
    ${requirementView(target)}
    <div class="auto-import-stage" data-auto-import-stage>${stageView(this.current, this.options.context().scope)}</div>
    <div class="auto-import-busy" data-auto-import-busy ${this.busy ? '' : 'hidden'} aria-live="polite">Working…</div>`;
    if (this.busy) this.setBusy(true);
  }

  private setBusy(busy: boolean): void {
    this.busy = busy;
    this.dialog.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
      if (button.dataset.autoImportAction !== 'close') button.disabled = busy;
    });
    const status = this.dialog.querySelector<HTMLElement>('[data-auto-import-busy]');
    if (status) status.hidden = !busy;
  }

  private report(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.options.onError?.(message);
    const stage = this.dialog.querySelector<HTMLElement>('[data-auto-import-stage]');
    if (stage)
      stage.insertAdjacentHTML(
        'afterbegin',
        `<div class="auto-import-error" role="alert">${e(message)}</div>`,
      );
  }

  private update(attempt: AutoImportAttempt): void {
    this.current = attempt;
    this.target = attempt.target;
    void this.options.onChanged?.(attempt);
    this.render();
  }

  private readonly onChange = (event: Event): void => {
    const input = event.target as HTMLInputElement;
    if (input.name !== 'files') return;
    const label = this.dialog.querySelector<HTMLElement>('[data-auto-import-file-label]');
    if (label)
      label.textContent = input.files?.length
        ? `${input.files.length} file${input.files.length === 1 ? '' : 's'} selected`
        : 'No files selected';
  };

  private readonly onClick = (event: Event): void => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
      '[data-auto-import-action]',
    );
    if (!button) return;
    const action = button.dataset.autoImportAction;
    if (action === 'close') {
      this.close();
      return;
    }
    if (this.busy) return;
    if (action === 'continue-research' && this.current) void this.continueResearch();
  };

  private readonly onSubmit = (event: SubmitEvent): void => {
    event.preventDefault();
    if (this.busy) return;
    const form = event.target as HTMLFormElement;
    if (form.matches('[data-auto-import-source-form]')) void this.start(form);
    if (form.matches('[data-auto-import-mapping-form]')) void this.confirmMapping(form);
    if (form.matches('[data-auto-import-promote-form]')) void this.promote(form);
  };

  private async start(form: HTMLFormElement): Promise<void> {
    if (!this.target) return;
    const data = new FormData(form);
    const fileInput = form.elements.namedItem('files') as HTMLInputElement;
    const input: AutoImportSourceInput = {
      urls: String(data.get('urls') ?? '')
        .split(/\r?\n/)
        .map((url) => url.trim())
        .filter(Boolean),
      pasted_text: String(data.get('pasted_text') ?? '').trim(),
      files: Array.from(fileInput.files ?? []),
    };
    this.setBusy(true);
    try {
      this.update(
        await this.options.client.start(this.target, input, this.options.context().scope),
      );
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }

  private async confirmMapping(form: HTMLFormElement): Promise<void> {
    if (!this.current) return;
    const reviewed = (form.elements.namedItem('mapping_reviewed') as HTMLInputElement).checked;
    if (!reviewed) {
      this.report(new Error('Review and confirm the mapping before verification.'));
      return;
    }
    const mappings = this.current.mappings.map((mapping, index) => ({
      column: mapping.column,
      target:
        this.dialog.querySelector<HTMLSelectElement>(`[data-auto-import-mapping="${index}"]`)
          ?.value || null,
    }));
    this.setBusy(true);
    try {
      this.update(
        await this.options.client.confirmMapping(this.current.attempt_id, { mappings, reviewed }),
      );
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }

  private async continueResearch(): Promise<void> {
    if (!this.current) return;
    this.setBusy(true);
    try {
      this.update(await this.options.client.continueResearch(this.current.attempt_id));
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }

  private async promote(form: HTMLFormElement): Promise<void> {
    if (!this.current) return;
    const confirmed = (form.elements.namedItem('redistribution_confirmed') as HTMLInputElement)
      .checked;
    if (!confirmed) {
      const scope = this.options.context().scope;
      this.report(
        new Error(
          scope === 'shared'
            ? 'Confirm redistribution rights before promotion.'
            : 'Confirm the run-scoped import before promotion.',
        ),
      );
      return;
    }
    this.setBusy(true);
    try {
      const attempt = await this.options.client.promote(this.current.attempt_id, {
        redistribution_confirmed: confirmed,
      });
      this.update(attempt);
      await this.options.onPromoted?.(attempt);
    } catch (error) {
      this.report(error);
    } finally {
      this.setBusy(false);
    }
  }
}
