import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Small-town simulation program' })).toBeVisible();
});

test('shows exact DSL code, edits it, runs it, and compares place aggregates', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/agent Person:/);
  await expect(editor).toHaveValue(/decision where_to_go:/);
  await expect(editor).toHaveValue(/action start_fight:/);
  await expect(page.getByRole('tab', { name: 'DSL Code' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Graph' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Decision Trees' })).toHaveCount(0);
  await expect(page.locator('.text-dsl-gutter')).toContainText('100');

  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Small-group aggregates' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Places' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Agent types' })).toBeVisible();

  const original = await editor.inputValue();
  const edited = original.replace(
    'branch go_cinema p = 0.12 if hour >= 17 placeholder',
    'branch go_cinema p = 0.72 if hour >= 17 placeholder',
  );
  expect(edited).not.toBe(original);
  await editor.fill(edited);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(page.getByText('Saved DSL is valid and ready to run.')).toBeVisible();
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();
  await expect(page.getByRole('rowheader', { name: 'Cinema' })).toBeVisible();
});

test('shows Rust parser diagnostics with source line numbers', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  const original = await editor.inputValue();
  await editor.fill(original.replace('duration = Triangular(min=0.20, median=0.45, max=0.90)', 'duration = Triangular(min=0.90, median=0.45, max=0.20)'));
  await page.getByRole('button', { name: 'Validate code' }).click();

  await expect(page.getByText('UNORDERED_DURATION')).toBeVisible();
  await expect(page.getByText(/Line \d+/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run saved DSL' })).toBeDisabled();
});
