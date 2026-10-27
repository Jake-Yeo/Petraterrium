import { expect, test, type Page } from '@playwright/test';

type SettingsState = {
  source: 'openai_cli' | 'openai_api';
  cli_command: string;
  cli_model: string;
  api_model: string;
  api_key_configured: boolean;
  api_key_storage: string;
  updated_at: string;
};

async function mockSettings(page: Page, initial?: Partial<SettingsState>) {
  const state: SettingsState = {
    source: 'openai_cli',
    cli_command: 'codex',
    cli_model: 'gpt-5-mini',
    api_model: 'gpt-5-mini',
    api_key_configured: false,
    api_key_storage: 'macOS Keychain',
    updated_at: '2026-10-27T12:00:00Z',
    ...initial,
  };
  await page.route('**/api/settings/ai**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/settings/ai/test')) {
      const response =
        state.source === 'openai_cli'
          ? {
              ok: true,
              message: 'Connected through OpenAI CLI',
              error: null,
              provenance: {
                source: 'openai_cli',
                source_label: 'OpenAI CLI',
                model: state.cli_model,
                generated_at: '2026-10-27T12:00:01Z',
                prompt_version: 'ai-settings-test-v1',
                input_tokens: null,
                output_tokens: null,
              },
            }
          : {
              ok: false,
              message: null,
              error:
                'OpenAI API key is not configured. Save a key in AI Settings; no fallback was attempted.',
              provenance: null,
            };
      await route.fulfill({ json: response });
      return;
    }
    if (request.method() === 'PATCH') {
      const update = request.postDataJSON();
      state.source = update.source ?? state.source;
      state.cli_command = update.cli_command ?? state.cli_command;
      state.cli_model = update.cli_model ?? state.cli_model;
      state.api_model = update.api_model ?? state.api_model;
      if (update.api_key) state.api_key_configured = true;
      if (update.clear_api_key) state.api_key_configured = false;
      state.updated_at = '2026-10-27T12:00:02Z';
    }
    await route.fulfill({ json: state });
  });
  return state;
}

async function mountPanel(page: Page): Promise<void> {
  await page.evaluate(async () => {
    document.body.innerHTML = '<main id="ai-settings-test"></main>';
    const module = await import('/src/simulation/ai-settings.ts');
    const panel = new module.AISettingsPanel(
      document.querySelector<HTMLElement>('#ai-settings-test')!,
    );
    (window as typeof window & { aiSettingsPanel?: unknown }).aiSettingsPanel = panel;
    await panel.activate();
  });
}

test('AI source switches persist and tests never fall back to the other source', async ({ page }) => {
  const state = await mockSettings(page);
  await page.goto('/');
  await mountPanel(page);
  const panel = page.getByRole('region', { name: 'AI source settings' });

  await expect(panel.getByLabel('OpenAI CLI')).toBeChecked();
  await panel.getByLabel('CLI command').fill('/usr/local/bin/codex');
  await panel.getByLabel('CLI model').fill('gpt-cli-test');
  await panel.getByRole('button', { name: 'Test source' }).click();
  await expect(panel.getByRole('status')).toContainText('Connected through OpenAI CLI');
  await expect(panel.getByRole('status')).toContainText('gpt-cli-test');

  await panel.getByLabel('OpenAI API').check();
  await panel.getByRole('button', { name: 'Test source' }).click();
  await expect(panel.getByRole('alert')).toHaveText(
    'OpenAI API key is not configured. Save a key in AI Settings; no fallback was attempted.',
  );

  await panel.getByLabel('OpenAI CLI').check();
  await panel.getByRole('button', { name: 'Test source' }).click();
  await expect(panel.getByRole('status')).toContainText('Connected through OpenAI CLI');
  expect(state.source).toBe('openai_cli');
  expect(state.cli_command).toBe('/usr/local/bin/codex');

  await mountPanel(page);
  await expect(page.getByLabel('OpenAI CLI')).toBeChecked();
  await expect(page.getByLabel('CLI command')).toHaveValue('/usr/local/bin/codex');
});

test('API keys are write-only and the saved value is never rendered', async ({ page }) => {
  const state = await mockSettings(page);
  await page.goto('/');
  await mountPanel(page);
  const panel = page.getByRole('region', { name: 'AI source settings' });

  await panel.getByLabel('OpenAI API').check();
  await panel.getByLabel('API key', { exact: true }).fill('sk-browser-secret');
  await panel.getByRole('button', { name: 'Save settings' }).click();

  expect(state.api_key_configured).toBe(true);
  await expect(panel.getByLabel('API key', { exact: true })).toHaveValue('');
  await expect(panel).not.toContainText('sk-browser-secret');
  await expect(panel).toContainText('Saved in macOS Keychain');
  await expect(panel.getByLabel('Remove saved API key')).toBeVisible();
});
