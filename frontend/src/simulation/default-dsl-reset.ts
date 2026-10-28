import './default-dsl-reset.css';

export interface DefaultDslReceipt {
  schema_version: '1';
  version: string;
  hash: string;
  source: 'shipped';
  managed_sections: string[];
}

export interface DefaultDslInventory {
  agent_type_ids: string[];
  state_ids: string[];
  action_ids: string[];
  routine_ids: string[];
  decision_tree_ids: string[];
  interaction_tree_ids: string[];
  initial_agent_ids: string[];
}

export interface DefaultDslStatus {
  loaded: boolean;
  intact: boolean;
  receipt: DefaultDslReceipt;
  installed_receipt: DefaultDslReceipt | null;
  inventory: DefaultDslInventory;
  drifted_sections: string[];
}

export interface DefaultDslSectionPreview {
  name: string;
  disposition: 'unchanged' | 'restore' | 'replace';
  current_count: number;
  default_count: number;
  current_ids: string[];
  default_ids: string[];
  restored_ids: string[];
  replaced_ids: string[];
}

export interface DefaultDslResetPreview {
  changed: boolean;
  receipt: DefaultDslReceipt;
  sections: DefaultDslSectionPreview[];
}

export interface DefaultDslClient {
  status(): Promise<DefaultDslStatus>;
  preview(): Promise<DefaultDslResetPreview>;
  reset(expectedHash: string): Promise<DefaultDslStatus>;
}

export interface DefaultDslResetOptions {
  client?: DefaultDslClient;
  onRestored(): Promise<void> | void;
}

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

const titleCase = (value: string): string =>
  value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
        ? body.detail
        : `Default DSL request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export function createDefaultDslHttpClient(): DefaultDslClient {
  const basePath = '/api/simulation/default-dsl';
  return {
    status: () => requestJson<DefaultDslStatus>(basePath),
    preview: () => requestJson<DefaultDslResetPreview>(`${basePath}/reset/preview`, { method: 'POST' }),
    reset: (expectedHash) =>
      requestJson<DefaultDslStatus>(`${basePath}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_confirmed: true, expected_hash: expectedHash }),
      }),
  };
}

function sectionQuantity(section: DefaultDslSectionPreview): string {
  const subject = section.name === 'initial_population' ? 'initial agents' : titleCase(section.name).toLowerCase();
  return `${section.default_count.toLocaleString('en')} ${subject}`;
}

function sectionDetails(section: DefaultDslSectionPreview): string {
  if (section.disposition === 'unchanged') return 'Matches the shipped default';
  const restored = section.restored_ids.length
    ? `<span>Restore ${section.restored_ids.map(titleCase).map(escapeHtml).join(', ')}</span>`
    : '';
  const replaced = section.replaced_ids.length
    ? `<span>Replace ${section.replaced_ids.map(titleCase).map(escapeHtml).join(', ')}</span>`
    : '';
  return `${restored}${replaced}` || 'Restore the shipped section';
}

export class DefaultDslResetControl {
  private readonly client: DefaultDslClient;
  private status: DefaultDslStatus | null = null;
  private preview: DefaultDslResetPreview | null = null;
  private error = '';
  private busy = false;
  private disposed = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: DefaultDslResetOptions,
  ) {
    this.client = options.client ?? createDefaultDslHttpClient();
    this.host.classList.add('default-dsl-reset');
    this.host.addEventListener('click', this.onClick);
    this.render();
    void this.loadStatus();
  }

  dispose(): void {
    this.disposed = true;
    this.host.removeEventListener('click', this.onClick);
  }

  private async loadStatus(): Promise<void> {
    try {
      this.status = await this.client.status();
      if (!this.disposed) this.render();
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
      if (!this.disposed) this.render();
    }
  }

  private async openPreview(): Promise<void> {
    this.busy = true;
    this.error = '';
    this.render();
    try {
      this.preview = await this.client.preview();
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = false;
      if (!this.disposed) this.render();
    }
  }

  private async restore(): Promise<void> {
    if (!this.preview) return;
    this.busy = true;
    this.error = '';
    this.render();
    try {
      this.status = await this.client.reset(this.preview.receipt.hash);
      this.preview = null;
      await this.options.onRestored();
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = false;
      if (!this.disposed) this.render();
    }
  }

  private onClick = (event: MouseEvent): void => {
    const action = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-default-dsl-action]')
      ?.dataset.defaultDslAction;
    if (action === 'preview') void this.openPreview();
    if (action === 'cancel') {
      this.preview = null;
      this.error = '';
      this.render();
    }
    if (action === 'restore') void this.restore();
  };

  private render(): void {
    const receipt = this.status?.receipt;
    const version = receipt
      ? `<small>Default ${escapeHtml(receipt.version)} · ${escapeHtml(receipt.hash.slice(0, 18))}…</small>`
      : '<small>Loading shipped default…</small>';
    const notice = this.error
      ? `<output class="default-dsl-error" role="alert">${escapeHtml(this.error)}</output>`
      : this.status && !this.status.intact
        ? `<output>${this.status.drifted_sections.length.toLocaleString('en')} default ${this.status.drifted_sections.length === 1 ? 'section differs' : 'sections differ'}</output>`
        : '';
    this.host.innerHTML = `<div class="default-dsl-reset-trigger"><div>${version}${notice}</div><button class="button secondary" type="button" data-default-dsl-action="preview" ${this.busy ? 'disabled' : ''}>${this.busy && !this.preview ? 'Preparing preview…' : 'Reset to default DSL'}</button></div>${this.preview ? this.previewMarkup(this.preview) : ''}`;
  }

  private previewMarkup(preview: DefaultDslResetPreview): string {
    const sections = preview.sections
      .filter((section) => section.disposition !== 'unchanged')
      .map(
        (section) => `<article><div><strong>${escapeHtml(titleCase(section.name))}</strong><small>${escapeHtml(sectionQuantity(section))}</small></div><p>${sectionDetails(section)}</p></article>`,
      )
      .join('');
    return `<div class="default-dsl-dialog-backdrop"><section class="default-dsl-dialog" role="dialog" aria-modal="true" aria-labelledby="default-dsl-dialog-title"><header><span class="small-label">SHIPPED FOUNDATION</span><h2 id="default-dsl-dialog-title">Reset to default DSL</h2><p>Restore version <strong>${escapeHtml(preview.receipt.version)}</strong> with hash <code>${escapeHtml(preview.receipt.hash)}</code>. Managed user edits listed below will be replaced.</p></header><div class="default-dsl-preview">${sections || '<p>The registry already matches the shipped default.</p>'}</div>${this.error ? `<output class="default-dsl-error" role="alert">${escapeHtml(this.error)}</output>` : ''}<footer><button class="button secondary" type="button" data-default-dsl-action="cancel" ${this.busy ? 'disabled' : ''}>Cancel</button><button class="button primary" type="button" data-default-dsl-action="restore" ${this.busy || !preview.changed ? 'disabled' : ''}>${this.busy ? 'Restoring…' : 'Restore default DSL'}</button></footer></section></div>`;
  }
}
