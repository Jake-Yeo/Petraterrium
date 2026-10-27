import './ai-settings.css';

export type AISource = 'openai_cli' | 'openai_api';

export type AISettingsView = {
  source: AISource;
  cli_command: string;
  cli_model: string;
  api_model: string;
  api_key_configured: boolean;
  api_key_storage: string;
  updated_at: string;
};

export type AISourceProvenance = {
  source: AISource;
  source_label: 'OpenAI CLI' | 'OpenAI API';
  model: string;
  generated_at: string;
  prompt_version: string;
  input_tokens: number | null;
  output_tokens: number | null;
};

export type AIConnectionTest = {
  ok: boolean;
  message: string | null;
  error: string | null;
  provenance: AISourceProvenance | null;
};

export type AISettingsPanelOptions = {
  endpoint?: string;
  title?: string;
  compact?: boolean;
};

type AISettingsUpdate = {
  source: AISource;
  cli_command: string;
  cli_model: string;
  api_model: string;
  api_key?: string;
  clear_api_key: boolean;
};

let panelSequence = 0;

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function responseBody<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body as T;
}

export class AISettingsPanel {
  private readonly endpoint: string;
  private readonly panelId: string;
  private settings?: AISettingsView;
  private active = false;

  constructor(
    private readonly host: HTMLElement,
    private readonly options: AISettingsPanelOptions = {},
  ) {
    panelSequence += 1;
    this.panelId = `ai-settings-${panelSequence}`;
    this.endpoint = options.endpoint ?? '/api/settings/ai';
    this.host.addEventListener('change', this.onChange);
    this.host.addEventListener('submit', this.onSubmit);
    this.host.addEventListener('click', this.onClick);
  }

  async activate(): Promise<void> {
    this.active = true;
    this.host.innerHTML = this.loadingMarkup();
    try {
      const response = await fetch(this.endpoint);
      this.settings = await responseBody<AISettingsView>(response);
      if (this.active) this.render();
    } catch (error) {
      if (this.active) this.renderLoadError(error);
    }
  }

  deactivate(): void {
    this.active = false;
  }

  destroy(): void {
    this.deactivate();
    this.host.removeEventListener('change', this.onChange);
    this.host.removeEventListener('submit', this.onSubmit);
    this.host.removeEventListener('click', this.onClick);
    this.host.replaceChildren();
  }

  private loadingMarkup(): string {
    return `<section class="ai-settings ${this.options.compact ? 'compact' : ''}" role="region" aria-label="AI source settings"><p class="ai-settings-loading">Loading AI settings…</p></section>`;
  }

  private render(): void {
    if (!this.settings) return;
    const settings = this.settings;
    const apiKeyState = settings.api_key_configured
      ? `Saved in ${escapeHtml(settings.api_key_storage)}`
      : 'No API key saved';
    this.host.innerHTML = `
      <section class="ai-settings ${this.options.compact ? 'compact' : ''}" role="region" aria-label="AI source settings">
        <header class="ai-settings-header">
          <div>
            <p class="ai-settings-eyebrow">AI SOURCE</p>
            <h2>${escapeHtml(this.options.title ?? 'AI settings')}</h2>
          </div>
          <p>Every AI feature uses this source. Failures stop at the selected source.</p>
        </header>
        <form class="ai-settings-form">
          <fieldset class="ai-source-options">
            <legend>Source</legend>
            <label class="ai-source-option">
              <input id="${this.panelId}-cli" type="radio" name="ai-source" value="openai_cli" ${settings.source === 'openai_cli' ? 'checked' : ''}>
              <span><strong>OpenAI CLI</strong><small>Uses the configured <code>codex exec</code> command and its existing login.</small></span>
            </label>
            <label class="ai-source-option">
              <input id="${this.panelId}-api" type="radio" name="ai-source" value="openai_api" ${settings.source === 'openai_api' ? 'checked' : ''}>
              <span><strong>OpenAI API</strong><small>Uses the API key stored in the system credential store.</small></span>
            </label>
          </fieldset>
          <div class="ai-source-fields" data-ai-source-fields="openai_cli" ${settings.source === 'openai_cli' ? '' : 'hidden'}>
            <label for="${this.panelId}-cli-command">CLI command</label>
            <input id="${this.panelId}-cli-command" name="cli-command" value="${escapeHtml(settings.cli_command)}" autocomplete="off" spellcheck="false" required>
            <small>Set a binary path or command prefix. Petraterrium adds the noninteractive <code>exec</code> arguments.</small>
            <label for="${this.panelId}-cli-model">CLI model</label>
            <input id="${this.panelId}-cli-model" name="cli-model" value="${escapeHtml(settings.cli_model)}" autocomplete="off" spellcheck="false" required>
          </div>
          <div class="ai-source-fields" data-ai-source-fields="openai_api" ${settings.source === 'openai_api' ? '' : 'hidden'}>
            <label for="${this.panelId}-api-model">API model</label>
            <input id="${this.panelId}-api-model" name="api-model" value="${escapeHtml(settings.api_model)}" autocomplete="off" spellcheck="false" required>
            <label for="${this.panelId}-api-key">API key</label>
            <input id="${this.panelId}-api-key" name="api-key" type="password" value="" autocomplete="new-password" placeholder="${settings.api_key_configured ? 'Leave blank to keep saved key' : 'Enter API key'}">
            <div class="ai-key-state"><span>${apiKeyState}</span>${settings.api_key_configured ? `<label><input type="checkbox" name="clear-api-key"> Remove saved API key</label>` : ''}</div>
          </div>
          <div class="ai-settings-actions">
            <button type="submit" class="button secondary" data-ai-settings-action="save">Save settings</button>
            <button type="button" class="button primary" data-ai-settings-action="test">Test source</button>
          </div>
          <p class="ai-settings-feedback" data-ai-settings-status role="status" hidden></p>
          <p class="ai-settings-feedback error" data-ai-settings-error role="alert" hidden></p>
        </form>
      </section>`;
  }

  private renderLoadError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.host.innerHTML = `
      <section class="ai-settings" role="region" aria-label="AI source settings">
        <p class="ai-settings-feedback error" role="alert">${escapeHtml(message)}</p>
        <button type="button" class="button secondary" data-ai-settings-action="retry">Retry</button>
      </section>`;
  }

  private onChange = (event: Event): void => {
    const input = event.target as HTMLInputElement;
    if (input.name !== 'ai-source') return;
    this.toggleSource(input.value as AISource);
    this.clearFeedback();
  };

  private onSubmit = (event: SubmitEvent): void => {
    if (!(event.target as HTMLElement).classList.contains('ai-settings-form')) return;
    event.preventDefault();
    void this.save(true).catch(() => undefined);
  };

  private onClick = (event: MouseEvent): void => {
    const action = (event.target as HTMLElement)
      .closest<HTMLElement>('[data-ai-settings-action]')
      ?.dataset.aiSettingsAction;
    if (action === 'test') void this.testSource();
    if (action === 'retry') void this.activate();
  };

  private toggleSource(source: AISource): void {
    this.host.querySelectorAll<HTMLElement>('[data-ai-source-fields]').forEach((section) => {
      section.hidden = section.dataset.aiSourceFields !== source;
    });
  }

  private currentUpdate(): AISettingsUpdate {
    const source = this.host.querySelector<HTMLInputElement>(
      'input[name="ai-source"]:checked',
    )?.value as AISource | undefined;
    const read = (name: string): string =>
      this.host.querySelector<HTMLInputElement>(`input[name="${name}"]`)?.value.trim() ?? '';
    if (!source) throw new Error('Choose an AI source.');
    const update: AISettingsUpdate = {
      source,
      cli_command: read('cli-command'),
      cli_model: read('cli-model'),
      api_model: read('api-model'),
      clear_api_key:
        this.host.querySelector<HTMLInputElement>('input[name="clear-api-key"]')?.checked ??
        false,
    };
    const apiKey = read('api-key');
    if (apiKey) update.api_key = apiKey;
    return update;
  }

  private async save(showStatus: boolean): Promise<AISettingsView> {
    this.setBusy(true);
    this.clearFeedback();
    try {
      const response = await fetch(this.endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.currentUpdate()),
      });
      this.settings = await responseBody<AISettingsView>(response);
      const keyInput = this.host.querySelector<HTMLInputElement>('input[name="api-key"]');
      if (keyInput) keyInput.value = '';
      this.updateKeyState();
      if (showStatus) this.showStatus('AI settings saved.');
      window.dispatchEvent(
        new CustomEvent('petraterrium:ai-settings-saved', { detail: this.settings }),
      );
      return this.settings;
    } catch (error) {
      this.showError(error);
      throw error;
    } finally {
      this.setBusy(false);
    }
  }

  private async testSource(): Promise<void> {
    try {
      const settings = await this.save(false);
      this.setBusy(true);
      const response = await fetch(`${this.endpoint}/test`, { method: 'POST' });
      const result = await responseBody<AIConnectionTest>(response);
      if (!result.ok) {
        this.showError(new Error(result.error ?? 'The selected AI source failed its test.'));
        return;
      }
      const provenance = result.provenance;
      const detail = provenance
        ? `${provenance.source_label} · ${provenance.model}`
        : settings.source === 'openai_cli'
          ? `OpenAI CLI · ${settings.cli_model}`
          : `OpenAI API · ${settings.api_model}`;
      this.showStatus(`${result.message ?? 'Connection succeeded.'} · ${detail}`);
    } catch (error) {
      this.showError(error);
      return;
    } finally {
      this.setBusy(false);
    }
  }

  private updateKeyState(): void {
    if (!this.settings) return;
    const state = this.host.querySelector<HTMLElement>('.ai-key-state');
    if (!state) return;
    state.innerHTML = this.settings.api_key_configured
      ? `<span>Saved in ${escapeHtml(this.settings.api_key_storage)}</span><label><input type="checkbox" name="clear-api-key"> Remove saved API key</label>`
      : '<span>No API key saved</span>';
  }

  private setBusy(busy: boolean): void {
    this.host.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
      button.disabled = busy;
    });
  }

  private clearFeedback(): void {
    for (const selector of ['[data-ai-settings-status]', '[data-ai-settings-error]']) {
      const target = this.host.querySelector<HTMLElement>(selector);
      if (target) target.hidden = true;
    }
  }

  private showStatus(message: string): void {
    this.clearFeedback();
    const target = this.host.querySelector<HTMLElement>('[data-ai-settings-status]');
    if (!target) return;
    target.textContent = message;
    target.hidden = false;
  }

  private showError(error: unknown): void {
    this.clearFeedback();
    const target = this.host.querySelector<HTMLElement>('[data-ai-settings-error]');
    if (!target) return;
    target.textContent = error instanceof Error ? error.message : String(error);
    target.hidden = false;
  }
}

export async function mountAISettings(
  host: HTMLElement,
  options: AISettingsPanelOptions = {},
): Promise<AISettingsPanel> {
  const panel = new AISettingsPanel(host, options);
  await panel.activate();
  return panel;
}
