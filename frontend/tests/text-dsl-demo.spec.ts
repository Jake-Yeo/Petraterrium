import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const cachedCompositionDsl = readFileSync(
  resolve(process.cwd(), '../engine-rust/dsl/cached_composition_test.dsl'),
  'utf8',
);
const countryWorldDsl = readFileSync(
  resolve(process.cwd(), '../engine-rust/dsl/country_world_test.dsl'),
  'utf8',
);
const mediaDsl = readFileSync(resolve(process.cwd(), '../engine-rust/dsl/media_test.dsl'), 'utf8');
const corporateDsl = readFileSync(
  resolve(process.cwd(), '../engine-rust/dsl/corporate_test.dsl'),
  'utf8',
);

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
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
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks', {
    timeout: 30_000,
  });
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
  await page.getByLabel('Population').selectOption('composition:UrbanLiberal');
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
  await page.getByLabel('Population').selectOption('composition:UrbanLiberal');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('UrbanLiberal');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Relearn detailed' }).click();
  await expect(page.getByRole('status')).toContainText('Detailed relearn', { timeout: 15_000 });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks', {
    timeout: 30_000,
  });
  await expect(page.getByText('CACHED FAST-FORWARD')).toBeVisible();
});

test('runs and edits generic municipality and division compositions', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/composition Toronto:/);
  await expect(editor).toHaveValue(/level = municipality/);
  await expect(editor).toHaveValue(/composition Ontario:/);
  await expect(editor).toHaveValue(/level = division/);

  await page.getByLabel('Population').selectOption('composition:Toronto');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Toronto municipality aggregates' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Composition boundary flows' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Cross-composition interactions' })).toBeVisible();
  await expect(page.getByText('commute_urban_suburban', { exact: true })).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(source.replace('UrbanLiberal: weight = 120', 'UrbanLiberal: weight = 140'));
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('composition:Toronto');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Population').selectOption('composition:Ontario');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Ontario division aggregates' })).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('Toronto');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Relearn detailed' }).click();
  await expect(page.getByRole('status')).toContainText('Branch relearn', { timeout: 30_000 });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
});

test('shows recursive cache metadata, branch invalidation, feedback, and evolving fast-forward', async ({
  page,
}) => {
  const editor = page.getByLabel('Simulation DSL code');
  await editor.fill(cachedCompositionDsl);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();

  await page.getByLabel('Population').selectOption('composition:Province');
  await page.getByLabel('Days').fill('2');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Province synthetic_division aggregates' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Cross-composition interactions' })).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('Province');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/);
  await expect(page.getByRole('heading', { name: 'Composition cache hierarchy' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Composition feedback convergence' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: 'NorthOne', exact: true })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: 'MetroNorth', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');

  await page.getByLabel('Branch inputs').fill('NorthOne.unemployment=0.8');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Branch relearn');
  await expect(page.getByText('input:unemployment', { exact: true })).toBeVisible();

  await page.getByLabel('Branch inputs').fill('');
  await page.getByLabel('Input schedule').fill('30.unemployment=0.8');
  await page.getByLabel('Days').fill('90');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  const rows = page.locator('[data-report-id="aggregate_time_series"] tbody tr');
  const day30 = rows.filter({ has: page.getByRole('rowheader', { name: '30', exact: true }) });
  const day90 = rows.filter({ has: page.getByRole('rowheader', { name: '90', exact: true }) });
  await expect(day30).toBeVisible();
  await expect(day90).toBeVisible();
  expect(await day90.textContent()).not.toBe(await day30.textContent());

  await page.getByLabel('tax').fill('0.35');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Hierarchy updated|Branch relearn/);
  await expect(page.getByRole('heading', { name: 'Cached composition boundary flows' })).toBeVisible();
});

test('runs the shipped division detailed and from its recursive zero-tick cache', async ({ page }) => {
  test.setTimeout(90_000);
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/composition Ontario:/);
  await expect(editor).toHaveValue(/cached:/);
  await expect(editor).toHaveValue(/intermunicipal_visit Toronto -> Vancouver/);

  await page.getByLabel('Population').selectOption('composition:Ontario');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Ontario division aggregates' })).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('Ontario');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  const status = page.getByRole('status');
  await expect(status).toContainText(/Branch relearn|Cache hit/, { timeout: 60_000 });
  if ((await status.textContent())?.includes('Branch relearn')) {
    await page.getByRole('button', { name: 'Evaluate cached' }).click();
  }
  await expect(status).toContainText('Cache hit · 0 agent ticks', { timeout: 30_000 });
  const hierarchy = page.locator('[data-report-id="cache_hierarchy"]');
  await expect(hierarchy.getByRole('heading', { name: 'Composition cache hierarchy' })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'Ontario', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'Toronto', exact: true })).toBeVisible();
  await expect(
    hierarchy.getByRole('rowheader', { name: 'UrbanLiberal', exact: true }).first(),
  ).toBeVisible();

  await page.getByLabel('Input schedule').fill('30.unemployment_national=0.075');
  await page.getByLabel('Days').fill('90');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks', {
    timeout: 30_000,
  });
  const rows = page.locator('[data-report-id="aggregate_time_series"] tbody tr');
  const day30 = rows.filter({ has: page.getByRole('rowheader', { name: '30', exact: true }) });
  const day90 = rows.filter({ has: page.getByRole('rowheader', { name: '90', exact: true }) });
  await expect(day30).toBeVisible();
  await expect(day90).toBeVisible();
  expect(await day90.textContent()).not.toBe(await day30.textContent());
  await expect(page.getByRole('heading', { name: 'Cached cross-composition interactions' })).toBeVisible();
});

test('runs synthetic countries and a world through the generic detailed and cached UI', async ({
  page,
}) => {
  const editor = page.getByLabel('Simulation DSL code');
  await editor.fill(countryWorldDsl);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(editor).toHaveValue(/archetype GenericFederation:/);
  await expect(editor).toHaveValue(/composition TestWorld:/);

  await page.getByLabel('Population').selectOption('composition:NationA');
  await page.getByLabel('Days').fill('2');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'NationA country aggregates' })).toBeVisible();
  await expect(page.getByText('country_exchange', { exact: true })).toBeVisible();

  await page.getByLabel('Population').selectOption('composition:TestWorld');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'TestWorld world aggregates' })).toBeVisible();
  await expect(page.getByText('trade_a_b', { exact: true })).toBeVisible();
  await expect(page.getByText('infection_a_b', { exact: true })).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(source.replace('NationA: weight = 60', 'NationA: weight = 80'));
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('composition:TestWorld');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('TestWorld');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/);
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  const hierarchy = page.locator('[data-report-id="cache_hierarchy"]');
  await expect(hierarchy.getByRole('rowheader', { name: 'TestWorld', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'NationA', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'NationB', exact: true })).toBeVisible();

  await page.getByLabel('Branch inputs').fill('ProvinceB.division_policy=0.8');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Hierarchy updated');
  await expect(
    hierarchy.getByRole('rowheader', { name: 'NationA', exact: true }).locator('..'),
  ).toContainText('cached');
  await expect(
    hierarchy.getByRole('rowheader', { name: 'NationB', exact: true }).locator('..'),
  ).toContainText('updated');

  await page.getByLabel('Branch inputs').fill('');
  await page.getByLabel('Input schedule').fill('30.tax=0.8');
  await page.getByLabel('Days').fill('90');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  const rows = page.locator('[data-report-id="aggregate_time_series"] tbody tr');
  const day30 = rows.filter({ has: page.getByRole('rowheader', { name: '30', exact: true }) });
  const day90 = rows.filter({ has: page.getByRole('rowheader', { name: '90', exact: true }) });
  await expect(day30).toBeVisible();
  await expect(day90).toBeVisible();
  expect(await day90.textContent()).not.toBe(await day30.textContent());
});

test('runs media and physical coupling from editable DSL code', async ({ page }) => {
  test.setTimeout(90_000);
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/entity Post:/);
  await expect(editor).toHaveValue(/spotlight agent InfluencerX:/);
  await expect(editor).toHaveValue(/composition Reddit:/);
  await expect(editor).toHaveValue(/couplings:/);

  await editor.fill(mediaDsl);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();

  await page.getByLabel('Population').selectOption('composition:Reddit');
  await page.getByLabel('Days').fill('2');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'Reddit platform aggregates' })).toBeVisible();
  await expect(page.getByText('viral_spread', { exact: true })).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(
    source.replace('place.engagement * 0.001', 'place.engagement * 0.004'),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('composition:Reddit');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Population').selectOption('composition:CoupledTownMedia');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.getByRole('heading', { name: 'CoupledTownMedia coupled_modules aggregates' }),
  ).toBeVisible();
  await expect(page.getByRole('rowheader', { name: /physical_to_media/ }).first()).toBeVisible();
  await expect(
    page.getByRole('rowheader', { name: /media_outage_to_physical/ }).first(),
  ).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('Reddit');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/, {
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  const hierarchy = page.locator('[data-report-id="cache_hierarchy"]');
  await expect(hierarchy.getByRole('rowheader', { name: 'Reddit', exact: true })).toBeVisible();
  await expect(
    hierarchy.getByRole('rowheader', { name: 'PersonalFinance', exact: true }),
  ).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('CoupledTownMedia');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/, {
    timeout: 30_000,
  });
  await expect(page.getByRole('heading', { name: 'Cached composition boundary flows' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: /physical_to_media/ }).first()).toBeVisible();
  await expect(
    page.getByRole('rowheader', { name: /media_outage_to_physical/ }).first(),
  ).toBeVisible();
});

test('runs detailed, cached, and physically coupled corporate DSL code', async ({ page }) => {
  test.setTimeout(90_000);
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toHaveValue(/composition CorporateForest:/);
  await expect(editor).toHaveValue(/composition TexasStoreDistribution:/);
  await editor.fill(corporateDsl);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();

  await page.getByLabel('Population').selectOption('composition:CorporateForest');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'CorporateForest forest aggregates' })).toBeVisible();
  await expect(page.getByText('total profit', { exact: true }).first()).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(
    source
      .replace('revenue = 100', 'revenue = 120')
      .replace('wages = 20', 'wages = 24')
      .replace('franchise_fee = 5', 'franchise_fee = 6'),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByLabel('Population').selectOption('composition:CorporateForest');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('CorporateForest');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/, {
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  const hierarchy = page.locator('[data-report-id="cache_hierarchy"]');
  await expect(hierarchy.getByRole('rowheader', { name: 'CorporateForest', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'BrandOne', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'FamilyStore', exact: true })).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('CoupledPhysicalCorporate');
  await page.getByLabel('Days').fill('180');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('heading', { name: 'Cached composition boundary flows' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: /demand_to_price/ }).first()).toBeVisible();
  await expect(page.getByRole('rowheader', { name: /profit_to_demand/ }).first()).toBeVisible();
});

test('runs corporate-financial peers and mutable role-owned decisions from DSL code', async ({
  page,
}) => {
  test.setTimeout(90_000);
  const editor = page.getByLabel('Simulation DSL code');
  const population = page.locator('[data-dsl-population]');
  await expect(editor).toHaveValue(/composition CorporateFinancialSystem:/);
  await expect(editor).toHaveValue(/role redditor:/);
  await expect(editor).toHaveValue(/role ceo:/);
  await expect(editor).toHaveValue(/role_distribution trader:/);

  await population.selectOption({ label: 'coupled corporate financial · CorporateFinancialSystem' });
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(
    page.getByRole('heading', {
      name: 'CorporateFinancialSystem coupled_corporate_financial aggregates',
    }),
  ).toBeVisible();
  await expect(page.getByText('alpha price', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('alpha dividend', { exact: true }).first()).toBeVisible();
  const compositionHierarchy = page.locator('[data-report-id="composition_hierarchy"]');
  await expect(compositionHierarchy.getByRole('rowheader', { name: 'FirmAlpha', exact: true })).toBeVisible();
  await expect(compositionHierarchy.getByRole('rowheader', { name: 'MarketAlpha', exact: true })).toBeVisible();
  await expect(compositionHierarchy.getByRole('rowheader', { name: 'SectorAlpha', exact: true })).toBeVisible();

  const source = await editor.inputValue();
  await editor.fill(
    source
      .replace(
        'composition FirmAlpha:\n  level = conglomerate\n  children:\n    LedgerCohort: weight = 1\n    CEOAlpha: weight = 1\n  parameters:\n    profit = 100',
        'composition FirmAlpha:\n  level = conglomerate\n  children:\n    LedgerCohort: weight = 1\n    CEOAlpha: weight = 1\n  parameters:\n    profit = 140',
      )
      .replaceAll('interest_rate = 0.05', 'interest_rate = 0.08')
      .replace(
        'risk ~ Uniform(min=0.5, max=0.5)',
        'risk ~ Uniform(min=0.8, max=0.8)',
      )
      .replace('roles = redditor, tiktoker', 'roles = redditor'),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await population.selectOption({ label: 'coupled corporate financial · CorporateFinancialSystem' });
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByText('vs baseline').first()).toBeVisible();

  await population.selectOption({ label: 'transaction lab · SecondaryBuyLab' });
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'SecondaryBuyLab transaction_lab aggregates' })).toBeVisible();
  await expect(page.getByText('firm cash', { exact: true }).first()).toBeVisible();

  await population.selectOption({ label: 'role action demo · RoleActionDemo' });
  await page.getByLabel('Days').fill('5');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('rowheader', { name: 'NeitherRoleDemo', exact: true })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: 'BothRoleDemo', exact: true })).toBeVisible();

  await population.selectOption({ label: 'country leadership · CanadaLeadership' });
  await page.getByLabel('Days').fill('2');
  await page.getByRole('button', { name: 'Run saved DSL' }).click();
  await expect(page.getByRole('heading', { name: 'CanadaLeadership country_leadership aggregates' })).toBeVisible();

  await page.getByLabel('Aggregate function').selectOption('CorporateFinancialSystem');
  await page.getByLabel('Days').fill('90');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(/Branch relearn|Hierarchy updated|Cache hit/, {
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  const hierarchy = page.locator('[data-report-id="cache_hierarchy"]');
  await expect(hierarchy.getByRole('rowheader', { name: 'FirmAlpha', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'MarketAlpha', exact: true })).toBeVisible();
  await expect(hierarchy.getByRole('rowheader', { name: 'FamilyBusiness', exact: true })).toBeVisible();
});
