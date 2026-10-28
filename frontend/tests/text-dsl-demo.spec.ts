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
  await expect(editor).toHaveValue(/output places:/);
  await expect(editor).toHaveValue(/column fights = action_count\(fights, window=day\)/);
  await expect(page.getByRole('tab', { name: 'DSL Code' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Graph' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Decision Trees' })).toHaveCount(0);
  await expect(page.locator('.text-dsl-gutter')).toContainText('100');

  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.getByRole('heading', { name: 'DSL-defined small-group statistics' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Town overview' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Places' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Agent types' })).toBeVisible();
  await expect(page.locator('.text-dsl-result-cards')).toBeVisible();
  await expect(page.locator('.text-dsl-result-table').first()).toBeVisible();

  const original = await editor.inputValue();
  const edited = original
    .replace(
      'branch go_cinema p = 0.12 if hour >= 17 placeholder',
      'branch go_cinema p = 0.72 if hour >= 17 placeholder',
    )
    .replace(
      'results_subtitle = "DSL-defined small-group statistics"',
      'results_subtitle = "Edited DSL statistics"',
    )
    .replace('title = "Places"', 'title = "Location statistics"')
    .replace(
      'output places:\n  title = "Location statistics"\n  group_by = place\n  display = table',
      'output places:\n  title = "Location statistics"\n  group_by = place\n  display = cards',
    );
  expect(edited).not.toBe(original);
  await editor.fill(edited);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(page.getByText('Saved DSL is valid and ready to run.')).toBeVisible();
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Edited DSL statistics' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Location statistics' })).toBeVisible();
  await expect(page.locator('[data-report-id="places"].text-dsl-result-cards')).toBeVisible();
  await expect(page.getByText('vs baseline').first()).toBeVisible();
  await expect(
    page.locator('[data-report-id="places"]').getByRole('heading', { name: 'Cinema' }),
  ).toBeVisible();
});

test('shows Rust parser diagnostics with source line numbers', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  const original = await editor.inputValue();
  await editor.fill(
    original.replace(
      'duration = Triangular(min=0.20, median=0.45, max=0.90)',
      'duration = Triangular(min=0.90, median=0.45, max=0.20)',
    ),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();

  await expect(page.getByText('UNORDERED_DURATION')).toBeVisible();
  await expect(page.getByText(/Line \d+/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run saved DSL' })).toBeDisabled();
});

test('edits a household weight and changes weighted archetype output', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/archetype HouseholdLiberalUrban:/);
  await expect(editor).toHaveValue(/population TownHouseholds:/);
  await page.getByLabel('Population').selectOption('TownHouseholds');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.getByRole('heading', { name: 'TownHouseholds weighted archetype aggregates' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Archetypes' })).toBeVisible();
  await expect(page.getByText('300', { exact: true }).first()).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(
    source.replace('HouseholdLiberalUrban: weight = 40', 'HouseholdLiberalUrban: weight = 80'),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('TownHouseholds');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.locator('[data-report-id="weighted_summary"] dd').filter({ hasText: /^420/ }),
  ).toBeVisible();
});

test('learns, reuses, and invalidates an aggregate cache from DSL text', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/aggregate_function HouseholdLiberalUrban:/);
  await expect(editor).toHaveValue(/invalidate_on:/);
  await page.getByLabel('Aggregate function').selectOption('HouseholdLiberalUrban');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Relearn detailed' }).click();
  await expect(page.getByRole('status')).toContainText('Detailed relearn', { timeout: 15_000 });
  await expect(page.getByRole('status')).not.toContainText('· 0 agent ticks');

  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  await expect(page.getByText('CACHED FAST-FORWARD')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Fast-forward time series' })).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(source.replace('valid_for = 30 days', 'valid_for = 31 days'));
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Aggregate function').selectOption('HouseholdLiberalUrban');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Detailed relearn');
  await expect(page.getByText('dsl_source_hash_changed')).toBeVisible();
});

test('runs shared-place neighbourhoods and their cached aggregate', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/neighbourhood UrbanLiberal:/);
  await page.getByLabel('Population').selectOption('neighbourhood:UrbanLiberal');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.getByRole('heading', { name: 'UrbanLiberal neighbourhood aggregates' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Cross-archetype interactions' })).toBeVisible();
  await expect(page.getByText('place_membership').first()).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(
    source.replace('HouseholdLiberalUrban: weight = 60', 'HouseholdLiberalUrban: weight = 80'),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('neighbourhood:UrbanLiberal');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('UrbanLiberal');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Relearn detailed' }).click();
  await expect(page.getByRole('status')).toContainText('Detailed relearn', { timeout: 15_000 });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  await expect(page.getByText('CACHED FAST-FORWARD')).toBeVisible();
});
