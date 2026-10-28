import './prompt2-ui.css';
import { escapeHtml, formatPercent } from './prompt2-ui-utils';

export type PipelineSourceType = 'measured' | 'estimated';

export interface CachedPipelineSearchStep {
  id: string;
  place: string;
  field: string;
  sourceTitle: string;
  sourceUrl?: string | null;
  sourceTier: string;
  language: string;
  engine: string;
  searchedAt: string;
  result: string;
}

export interface CachedPipelineCandidate {
  id: string;
  place: string;
  field: string;
  sourceTitle: string;
  sourceType: PipelineSourceType;
  summary: string;
  accepted: boolean;
  rejectionReason?: string | null;
}

export interface CachedPipelineDistributionValue {
  value: string;
  probability?: number;
  display?: string;
}

export interface CachedPipelineChosenResult {
  id: string;
  place: string;
  field: string;
  unit: string;
  denominator: string;
  sourceTitle: string;
  sourceType: PipelineSourceType;
  sourceDate: string;
  values: CachedPipelineDistributionValue[];
  reasoning: string;
  assumptions: string[];
  uncertainty: string;
  provenance: string;
}

export interface CachedDefaultSnapshot {
  hash: string;
  distributionCount: number;
  stateCount: number;
  initialAgentCount: number;
}

export interface CachedPipelineVersionDiff {
  researchedDataChanges: string[];
  chosenDataChanges: string[];
  reason: string;
}

export interface CachedPipelineVersion {
  id: string;
  label: string;
  createdAt: string;
  isDefault: boolean;
  searchLog: CachedPipelineSearchStep[];
  candidates: CachedPipelineCandidate[];
  chosenResults: CachedPipelineChosenResult[];
  defaultSnapshot: CachedDefaultSnapshot;
  diffFromPrevious?: CachedPipelineVersionDiff | null;
}

export interface CachedPipelineDefaultInspectorOptions {
  versions: CachedPipelineVersion[];
  selectedVersionId?: string;
  onRestore: (versionId: string) => Promise<void> | void;
  onSetDefault?: (versionId: string) => Promise<void> | void;
}

type PendingAction = 'restore' | 'set-default' | null;

export class CachedPipelineDefaultInspector {
  private versions: CachedPipelineVersion[];
  private selectedVersionId: string;
  private pendingAction: PendingAction = null;
  private busy = false;
  private error = '';

  constructor(
    private readonly host: HTMLElement,
    private readonly options: CachedPipelineDefaultInspectorOptions,
  ) {
    this.versions = [...options.versions];
    this.selectedVersionId =
      options.selectedVersionId ??
      this.versions.find((version) => version.isDefault)?.id ??
      this.versions[0]?.id ??
      '';
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('click', this.onClick);
    this.render();
  }

  update(versions: CachedPipelineVersion[], selectedVersionId = this.selectedVersionId): void {
    this.versions = [...versions];
    this.selectedVersionId = this.versions.some((version) => version.id === selectedVersionId)
      ? selectedVersionId
      : (this.versions.find((version) => version.isDefault)?.id ?? this.versions[0]?.id ?? '');
    this.pendingAction = null;
    this.error = '';
    this.render();
  }

  destroy(): void {
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private readonly onChange = (event: Event): void => {
    const select = event.target instanceof HTMLSelectElement ? event.target : null;
    if (select?.name !== 'cached-pipeline-version') return;
    this.selectedVersionId = select.value;
    this.pendingAction = null;
    this.error = '';
    this.render();
  };

  private readonly onClick = (event: Event): void => {
    const button =
      event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>('button[data-pipeline-action]')
        : null;
    const action = button?.dataset.pipelineAction;
    if (!action || this.busy) return;
    if (action === 'restore' || action === 'set-default') {
      this.pendingAction = action;
      this.error = '';
      this.render();
      return;
    }
    if (action === 'cancel') {
      this.pendingAction = null;
      this.render();
      return;
    }
    if (action === 'confirm') void this.confirmPendingAction();
  };

  private async confirmPendingAction(): Promise<void> {
    const action = this.pendingAction;
    if (!action || !this.selectedVersionId) return;
    this.busy = true;
    this.error = '';
    this.render();
    try {
      if (action === 'restore') await this.options.onRestore(this.selectedVersionId);
      if (action === 'set-default') await this.options.onSetDefault?.(this.selectedVersionId);
      this.pendingAction = null;
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = false;
      this.render();
    }
  }

  private selectedVersion(): CachedPipelineVersion | undefined {
    return this.versions.find((version) => version.id === this.selectedVersionId);
  }

  private render(): void {
    const version = this.selectedVersion();
    this.host.className = 'prompt2-card cached-pipeline-inspector';
    if (!version) {
      this.host.innerHTML = `
        <header class="prompt2-card-heading"><div><span class="prompt2-eyebrow">CACHED PIPELINE DEFAULT</span><h3>Saved research runs</h3></div></header>
        <p class="cached-pipeline-empty">No cached pipeline result is available yet.</p>
      `;
      return;
    }
    this.host.innerHTML = `
      <header class="prompt2-card-heading">
        <div><span class="prompt2-eyebrow">CACHED PIPELINE DEFAULT</span><h3>Saved research runs</h3></div>
        <label class="cached-pipeline-version"><span>Version</span><select name="cached-pipeline-version">${this.versions.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === version.id ? 'selected' : ''}>${escapeHtml(item.label)}${item.isDefault ? ' · current default' : ''}</option>`).join('')}</select></label>
      </header>
      <p class="prompt2-help">Inspect the complete cached research trail, compare versions, and restore distributions, states, and initial agents without rerunning research.</p>
      <div class="cached-pipeline-summary">
        <span>${escapeHtml(version.createdAt)}</span>
        <span>${version.searchLog.length} search steps</span>
        <span>${version.candidates.length} candidates</span>
        <span>${version.chosenResults.length} chosen results</span>
        <span>Snapshot ${escapeHtml(version.defaultSnapshot.hash.slice(0, 12))}…</span>
      </div>
      <div class="cached-pipeline-actions">
        <button type="button" data-pipeline-action="restore">Restore default from cached pipeline result</button>
        ${this.options.onSetDefault && !version.isDefault ? '<button type="button" data-pipeline-action="set-default">Save this version as default</button>' : ''}
      </div>
      ${this.confirmationMarkup(version)}
      ${this.error ? `<p class="cached-pipeline-error" role="alert">${escapeHtml(this.error)}</p>` : ''}
      <div class="cached-pipeline-sections">
        ${this.diffMarkup(version.diffFromPrevious)}
        ${this.chosenMarkup(version.chosenResults)}
        ${this.searchLogMarkup(version.searchLog)}
        ${this.candidatesMarkup(version.candidates)}
        ${this.snapshotMarkup(version.defaultSnapshot)}
      </div>
    `;
  }

  private confirmationMarkup(version: CachedPipelineVersion): string {
    if (!this.pendingAction) return '';
    const actionLabel =
      this.pendingAction === 'restore'
        ? 'restore distributions, states, and initial agents from'
        : 'make the current default snapshot';
    return `
      <section class="cached-pipeline-confirm" role="alertdialog" aria-label="Confirm cached pipeline action">
        <div><strong>Confirm saved pipeline change</strong><p>This will ${actionLabel} ${escapeHtml(version.label)}. Research will not run again.</p></div>
        <button type="button" data-pipeline-action="cancel" ${this.busy ? 'disabled' : ''}>Cancel</button>
        <button type="button" class="prompt2-primary" data-pipeline-action="confirm" ${this.busy ? 'disabled' : ''}>${this.busy ? 'Applying…' : 'Confirm'}</button>
      </section>
    `;
  }

  private diffMarkup(diff: CachedPipelineVersionDiff | null | undefined): string {
    const content = diff
      ? `
        <div class="cached-pipeline-diff-columns">
          <div><h4>Research changes</h4>${this.stringList(diff.researchedDataChanges)}</div>
          <div><h4>Chosen data changes</h4>${this.stringList(diff.chosenDataChanges)}</div>
        </div>
        <p><strong>Why:</strong> ${escapeHtml(diff.reason)}</p>
      `
      : '<p>This is the first cached version, so there is no earlier result to compare.</p>';
    return `<details open><summary>Diff from previous version</summary><div class="cached-pipeline-detail-body">${content}</div></details>`;
  }

  private chosenMarkup(results: CachedPipelineChosenResult[]): string {
    return `
      <details><summary>Final chosen data</summary><div class="cached-pipeline-detail-body cached-pipeline-chosen">
        ${
          results
            .map(
              (result) => `
          <article>
            <header><div><h4>${escapeHtml(result.place)} · ${escapeHtml(result.field)}</h4><span class="source-${result.sourceType}">${escapeHtml(result.sourceType)}</span></div><small>${escapeHtml(result.sourceTitle)} · ${escapeHtml(result.sourceDate)}</small></header>
            <div class="cached-pipeline-distribution">${result.values.map((item) => `<span><strong>${escapeHtml(item.value)}</strong>${escapeHtml(item.display ?? (item.probability === undefined ? 'Not recorded' : formatPercent(item.probability)))}</span>`).join('')}</div>
            <dl><div><dt>Unit / denominator</dt><dd>${escapeHtml(result.unit)} · ${escapeHtml(result.denominator)}</dd></div><div><dt>Reasoning</dt><dd>${escapeHtml(result.reasoning)}</dd></div><div><dt>Assumptions</dt><dd>${escapeHtml(result.assumptions.join('; '))}</dd></div><div><dt>Uncertainty</dt><dd>${escapeHtml(result.uncertainty)}</dd></div><div><dt>Provenance</dt><dd>${escapeHtml(result.provenance)}</dd></div></dl>
          </article>
        `,
            )
            .join('') || '<p>No chosen data was recorded.</p>'
        }
      </div></details>
    `;
  }

  private searchLogMarkup(rows: CachedPipelineSearchStep[]): string {
    return `
      <details><summary>Full search log (${rows.length})</summary><div class="cached-pipeline-detail-body cached-pipeline-table-wrap">
        <table><thead><tr><th>Place / field</th><th>Source</th><th>Language / engine</th><th>Date</th><th>Result</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(row.place)}<small>${escapeHtml(row.field)}</small></td><td>${row.sourceUrl ? `<a href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(row.sourceTitle)}</a>` : escapeHtml(row.sourceTitle)}<small>${escapeHtml(row.sourceTier)}</small></td><td>${escapeHtml(row.language)}<small>${escapeHtml(row.engine)}</small></td><td>${escapeHtml(row.searchedAt)}</td><td>${escapeHtml(row.result)}</td></tr>`).join('')}</tbody></table>
      </div></details>
    `;
  }

  private candidatesMarkup(candidates: CachedPipelineCandidate[]): string {
    return `
      <details><summary>Candidate data (${candidates.length})</summary><div class="cached-pipeline-detail-body cached-pipeline-candidates">
        ${candidates.map((candidate) => `<article><div><h4>${escapeHtml(candidate.place)} · ${escapeHtml(candidate.field)}</h4><span class="source-${candidate.sourceType}">${escapeHtml(candidate.sourceType)}</span><span class="candidate-${candidate.accepted ? 'accepted' : 'rejected'}">${candidate.accepted ? 'chosen' : 'not chosen'}</span></div><strong>${escapeHtml(candidate.sourceTitle)}</strong><p>${escapeHtml(candidate.summary)}</p>${candidate.rejectionReason ? `<p>Reason: ${escapeHtml(candidate.rejectionReason)}</p>` : ''}</article>`).join('') || '<p>No candidates were recorded.</p>'}
      </div></details>
    `;
  }

  private snapshotMarkup(snapshot: CachedDefaultSnapshot): string {
    return `
      <details><summary>Saved default snapshot</summary><div class="cached-pipeline-detail-body">
        <dl class="cached-default-snapshot"><div><dt>Snapshot hash</dt><dd><code>${escapeHtml(snapshot.hash)}</code></dd></div><div><dt>Distributions</dt><dd>${snapshot.distributionCount}</dd></div><div><dt>States</dt><dd>${snapshot.stateCount}</dd></div><div><dt>Initial agents</dt><dd>${snapshot.initialAgentCount.toLocaleString()}</dd></div></dl>
      </div></details>
    `;
  }

  private stringList(values: string[]): string {
    return values.length
      ? `<ul>${values.map((value) => `<li>${escapeHtml(value)}</li>`).join('')}</ul>`
      : '<p>No changes.</p>';
  }
}
