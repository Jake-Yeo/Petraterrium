import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
});

test('renders TSX DAG paths, role search, collapse, and exact code navigation', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.getByRole('tab', { name: 'Graph' }).click();

  for (const slice of ['Physical', 'Media', 'Corporate', 'Financial', 'Full system']) {
    await expect(page.getByLabel('Vertical slice').locator(`option[value="${slice}"]`)).toHaveCount(
      1,
    );
  }
  await expect(page.locator('.dsl-auxiliary-groups')).toContainText('Labs');
  await expect(page.locator('.dsl-auxiliary-groups')).toContainText('Allocation');
  await expect(page.locator('.dsl-graph-legend')).toContainText('Parent/child composition');
  await expect(page.locator('.dsl-graph-legend')).toContainText('Coupling across slices');

  await page.getByLabel('Search nodes or roles').fill('president');
  await expect(page.locator('.dsl-match-count')).toContainText(/2 nodes match/);
  await expect(page.locator('[data-graph-node="USA"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="Canada"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Search nodes or roles').fill('trader');
  await expect(page.locator('[data-graph-node="MarketAlpha"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="FirmAlpha"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="FinancialPerson"]').first()).toHaveClass(
    /highlighted/,
  );

  await page.getByLabel('Search nodes or roles').fill('Toronto');
  await expect(page.locator('[data-graph-node="Toronto"]')).toHaveCount(6);
  await expect(page.locator('[data-graph-path="World>Canada>Ontario>Toronto"]')).toBeVisible();
  await expect(page.locator('[data-graph-path="World>USA>California>Toronto"]')).toBeVisible();

  const canadaToronto = page.locator('[data-graph-path="World>Canada>Ontario>Toronto"]');
  const usaToronto = page.locator('[data-graph-path="World>USA>California>Toronto"]');
  await canadaToronto.getByRole('button', { name: 'Collapse subtree' }).click();
  await page.getByLabel('Search nodes or roles').fill('');
  await expect(page.locator('[data-graph-path^="World>Canada>Ontario>Toronto>"]')).toHaveCount(0);
  await expect(
    page.locator('[data-graph-path^="World>USA>California>Toronto>"]').first(),
  ).toBeVisible();
  await page.getByLabel('Search nodes or roles').fill('Toronto');
  await canadaToronto.getByRole('button', { name: /Expand/ }).click();
  await expect(
    page.locator('[data-graph-path^="World>Canada>Ontario>Toronto>"]').first(),
  ).toBeVisible();
  await expect(usaToronto).toBeVisible();

  await page.getByLabel('Search nodes or roles').fill('xyz-no-match');
  await expect(page.getByText("No nodes match 'xyz-no-match'")).toBeVisible();
  await page.getByLabel('Vertical slice').selectOption('Corporate');
  await page.getByLabel('Search nodes or roles').fill('FamilyStore');
  await page.locator('[data-graph-node="FamilyStore"]').click();
  await expect(page.locator('[data-graph-detail]')).toContainText('cashier');
  await expect(page.locator('[data-graph-detail]')).toContainText('manager');
  await expect(page.locator('[data-graph-detail]')).toContainText('owner');
  await page.getByLabel('Vertical slice').selectOption('Physical');
  await page.getByLabel('Search nodes or roles').fill('president');
  await page.locator('[data-graph-node="USA"]').click();
  const detail = page.locator('[data-graph-detail]');
  await expect(detail.getByRole('heading', { name: 'USA' })).toBeVisible();
  await expect(detail).toContainText('president');
  await expect(detail).toContainText('enact_policy');
  await expect(detail).toContainText('Probability');
  await detail.getByRole('button', { name: 'View in code' }).click();

  const editor = page.getByLabel('Simulation DSL code');
  await expect(page.getByRole('tab', { name: 'Code', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(editor).toBeFocused();
  const selectedLine = await editor.evaluate((element: HTMLTextAreaElement) =>
    element.value.slice(element.selectionStart, element.selectionEnd),
  );
  expect(selectedLine).toBe('composition USA:');

  await page.getByLabel('Search DSL outline').fill('StoreA');
  await page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'StoreA' }).click();
  const outlineLine = await editor.evaluate((element: HTMLTextAreaElement) =>
    element.value.slice(element.selectionStart, element.selectionEnd),
  );
  expect(outlineLine).toBe('composition StoreA:');
});

test('runs the full system by default and keeps debug and cached runs advanced', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await expect(page.getByLabel('What to run')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Run full system' })).toBeVisible();
  await expect(page.getByLabel('Days')).toHaveValue('30');
  await expect(page.getByLabel('Sample budget')).toHaveValue(/\d+/);
  await expect(page.locator('.text-dsl-debug-runs')).not.toHaveAttribute('open', '');
  await expect(page.locator('[data-fast-forward]')).not.toHaveAttribute('open', '');

  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run full system' }).click();
  const summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('Petraterrium full system');
  await expect(summary).toContainText('seed 1');
  await expect(summary).toContainText('sample budget');
  await expect(summary).toContainText('engine 0.12.0');
  await expect(page.getByRole('heading', { name: 'Population slices' })).toBeVisible();
  for (const slice of ['Physical', 'Media', 'Corporate', 'Financial']) {
    await expect(page.locator('.text-dsl-slice-results')).toContainText(slice);
  }
  await expect(page.getByRole('heading', { name: 'Coupling summary' })).toBeVisible();
  await expect(page.locator('.text-dsl-coupling-results')).toContainText('world_to_media');
  await expect(page.locator('.text-dsl-coupling-results')).toContainText('alpha_profit_to_market');

  const firstPhysical = await page
    .locator('.text-dsl-slice-results article')
    .filter({ hasText: 'Physical' })
    .textContent();
  await page.getByLabel('Sample budget').fill('1000');
  await page.getByRole('button', { name: 'Run full system' }).click();
  await expect(summary).toContainText('sample budget 1,000');
  const secondPhysical = await page
    .locator('.text-dsl-slice-results article')
    .filter({ hasText: 'Physical' })
    .textContent();
  expect(secondPhysical).not.toBe(firstPhysical);

  const advanced = page.locator('.text-dsl-advanced');
  await advanced.locator('summary').first().click();
  await page.locator('.text-dsl-debug-runs > summary').click();
  await expect(page.getByText(/Debug only — single slice/)).toBeVisible();
  await expect(page.getByLabel('Debug target')).toBeVisible();

  const fastForward = page.locator('[data-fast-forward]');
  await fastForward.locator('summary').click();
  await page.getByLabel('Learned aggregate function').selectOption('CorporateFinancialSystem');
  await page.getByLabel('Days').fill('30');
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await page.getByRole('button', { name: 'Evaluate cached' }).click();
  await expect(page.getByRole('status')).toContainText('Cache hit · 0 agent ticks', {
    timeout: 30_000,
  });
  await expect(page.getByText('cache_hit=true')).toBeVisible();
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
  await expect(page.getByRole('button', { name: 'Run full system' })).toBeDisabled();
  await page.locator('[data-fast-forward] summary').click();
  await expect(page.getByText('Save valid DSL before fast-forwarding.')).toBeVisible();
});
