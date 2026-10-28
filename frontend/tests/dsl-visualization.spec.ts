import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
});

test('renders the validated program graph and keeps code navigation exact', async ({ page }) => {
  await page.getByRole('tab', { name: 'Graph' }).click();

  await expect(page.locator('.dsl-graph-lane')).toHaveCount(34);
  await expect(page.locator('[data-slice="World"] > header')).toContainText('World');
  await expect(page.locator('[data-slice="Reddit"] > header')).toContainText('Reddit');
  await expect(page.locator('[data-slice="CorporateForest"] > header')).toContainText(
    'Corporate Forest',
  );
  await expect(page.locator('[data-slice="FinancialEconomy"] > header')).toContainText(
    'Financial Economy',
  );
  await expect(page.locator('.dsl-graph-edges .parent_child')).toHaveCount(132);
  await expect(page.locator('.dsl-graph-edges .coupling')).toHaveCount(14);
  await expect(
    page.locator('.dsl-graph-edges text').filter({ hasText: 'daily sync' }).first(),
  ).toBeVisible();
  await expect(
    page.locator('.dsl-graph-edges text').filter({ hasText: '90-day sync' }).first(),
  ).toBeVisible();
  await expect(page.locator('.dsl-graph-legend')).toContainText('Parent/child composition');
  await expect(page.locator('.dsl-graph-legend')).toContainText('Coupling across slices');

  await page.getByLabel('Search nodes or roles').fill('trader');
  await expect(page.locator('[data-graph-node="FinancialPerson"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="MarketAlpha"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="FirmAlpha"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Vertical slice').selectOption('CorporateForest');
  await page.locator('[data-graph-node="StoreA"]').click({ force: true });
  const detail = page.locator('[data-graph-detail]');
  await expect(detail.getByRole('heading', { name: 'StoreA' })).toBeVisible();
  await expect(detail.getByRole('heading', { name: 'Roles exposed' })).toBeVisible();
  await expect(detail.getByRole('heading', { name: 'Actions' })).toBeVisible();
  await expect(detail).toContainText('cashier');
  await expect(detail).toContainText('manager');
  await detail.getByRole('button', { name: 'View in code' }).click();

  await expect(page.getByRole('tab', { name: 'Code', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  const editor = page.getByLabel('Simulation DSL code');
  await expect(editor).toBeFocused();
  const selectedLine = await editor.evaluate((element: HTMLTextAreaElement) =>
    element.value.slice(element.selectionStart, element.selectionEnd),
  );
  expect(selectedLine).toBe('composition StoreA:');

  await page.getByLabel('Search DSL outline').fill('StoreA');
  await page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'StoreA' }).click();
  await expect(editor).toBeFocused();
  const outlineLine = await editor.evaluate((element: HTMLTextAreaElement) =>
    element.value.slice(element.selectionStart, element.selectionEnd),
  );
  expect(outlineLine).toBe('composition StoreA:');

  await page.getByRole('tab', { name: 'Graph' }).click();
  await page.getByLabel('Search nodes or roles').fill('');
  await page.getByLabel('Vertical slice').selectOption('World');
  await expect(page.locator('[data-slice="World"] [data-graph-node]')).toHaveCount(21);
  await page
    .locator('[data-graph-node="World"]')
    .getByRole('button', { name: /Subtree roles/ })
    .click({ force: true });
  await expect(
    page.locator('[data-graph-node="World"]').getByRole('button', { name: 'worker' }),
  ).toBeVisible();
  await page
    .locator('[data-graph-node="World"]')
    .getByRole('button', { name: 'Collapse subtree' })
    .click({ force: true });
  await expect(page.locator('[data-slice="World"] [data-graph-node]')).toHaveCount(1);
  await page
    .locator('[data-graph-node="World"]')
    .getByRole('button', { name: 'Expand subtree' })
    .click({ force: true });
  await expect(page.locator('[data-slice="World"] [data-graph-node]')).toHaveCount(21);

  await expect(page.locator('[data-dsl-graph-view]')).toHaveAttribute('data-render-ms', /\d/);
  const renderMs = Number(
    await page.locator('[data-dsl-graph-view]').getAttribute('data-render-ms'),
  );
  expect(renderMs).toBeLessThan(2_000);
});

test('runs Town by default and keeps advanced cached evaluation optional', async ({ page }) => {
  test.setTimeout(60_000);
  await expect(page.getByLabel('What to run')).toHaveValue('');
  await expect(page.getByLabel('Days')).toHaveValue('30');
  await expect(page.locator('[data-fast-forward]')).not.toHaveAttribute('open', '');

  await page.getByRole('button', { name: 'Run simulation' }).click();
  let summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('Town');
  await expect(summary).toContainText('30 days · seed 1');
  await expect(summary).toContainText('130 simulated');
  await expect(summary).toContainText('130 represented');
  await expect(summary).toContainText('Deltas below compare this run');
  await expect(page.getByRole('heading', { name: 'Town overview' })).toBeVisible();

  await page.getByLabel('Days').fill('1');
  await page.getByLabel('What to run').selectOption('composition:World');
  await page.getByRole('button', { name: 'Run simulation' }).click();
  summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('World');
  await expect(summary).toContainText('180 simulated');
  await expect(summary).toContainText('6,999,999,999 represented');

  await page.getByLabel('What to run').selectOption('composition:Reddit');
  await page.getByRole('button', { name: 'Run simulation' }).click();
  summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('Reddit');
  await expect(summary).toContainText('100 simulated');
  await expect(summary).toContainText('8,000,000 represented');

  await page.getByLabel('What to run').selectOption('composition:CorporateFinancialSystem');
  await page.getByRole('button', { name: 'Run simulation' }).click();
  summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('CorporateFinancialSystem');
  await expect(summary).toContainText('simulated');
  await expect(summary).toContainText('engine 0.12.0');

  const fastForward = page.locator('[data-fast-forward]');
  await expect(fastForward).not.toHaveAttribute('open', '');
  await fastForward.locator('summary').click();
  await page.getByLabel('Learned aggregate function').selectOption('CorporateFinancialSystem');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText(
    /Branch relearn|Hierarchy updated|Cache hit/,
  );
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks');
  await expect(page.getByText('cache_hit=true')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Fast-forward time series' })).toBeVisible();

  await page.getByRole('button', { name: 'Relearn detailed' }).click();
  await expect(page.getByRole('status')).toContainText('Branch relearn', { timeout: 30_000 });
  await expect(page.getByRole('status')).not.toContainText('· 0 agent ticks');
});

test('keeps validate save reset diagnostics and outline synchronized', async ({ page }) => {
  test.setTimeout(60_000);
  const editor = page.getByLabel('Simulation DSL code');
  const shipped = await editor.inputValue();
  await page.getByLabel('Search DSL outline').fill('StoreA');
  await expect(
    page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'StoreA' }),
  ).toBeVisible();

  await editor.fill(`${shipped}\n`);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await expect(
    page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'StoreA' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(page.getByText('Saved DSL is valid and ready to run.')).toBeVisible();

  await page.getByRole('button', { name: 'Reset shipped DSL' }).click();
  await page.getByRole('button', { name: 'Click again to reset' }).click();
  await expect(editor).toHaveValue(shipped);
  await page.getByLabel('Search DSL outline').fill('StoreA');
  await expect(
    page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'StoreA' }),
  ).toBeVisible();

  await editor.fill(
    shipped.replace(
      'duration = Triangular(min=0.20, median=0.45, max=0.90)',
      'duration = Triangular(min=0.90, median=0.45, max=0.20)',
    ),
  );
  await page.getByRole('button', { name: 'Validate code' }).click();
  const diagnostic = page.locator('[data-dsl-error-line]').first();
  await expect(diagnostic).toContainText('UNORDERED_DURATION');
  await diagnostic.click();
  await expect(editor).toBeFocused();
  await expect(page.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
  await page.locator('[data-fast-forward] summary').click();
  await expect(page.getByText('Save valid DSL before fast-forwarding.')).toBeVisible();
});
