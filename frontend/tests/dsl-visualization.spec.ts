import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
});

test('renders one pool above four fixed sector lanes with current search and navigation', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.getByRole('tab', { name: 'Graph' }).click();

  await expect(page.getByLabel('Petraterrium system root')).toBeVisible();
  await expect(page.getByLabel('Global agent pool')).toBeVisible();
  await expect
    .poll(() => page.locator('[data-dsl-graph-view]').getAttribute('data-render-ms'))
    .not.toBeNull();
  const renderMs = Number(
    await page.locator('[data-dsl-graph-view]').getAttribute('data-render-ms'),
  );
  console.log(`pool graph render ${renderMs.toFixed(1)}ms`);
  expect(renderMs).toBeLessThan(500);
  for (const sector of ['Physical', 'Media', 'Conglomerate', 'Financial']) {
    await expect(
      page.getByLabel('Vertical slice').locator(`option[value="${sector}"]`),
    ).toHaveCount(1);
  }
  await expect(page.getByLabel('Vertical slice').locator('option[value="Corporate"]')).toHaveCount(
    0,
  );
  await expect(
    page.getByLabel('Vertical slice').locator('option[value="Full system"]'),
  ).toHaveCount(0);
  await expect(page.locator('[data-graph-node="Person"]')).toHaveCount(0);
  const layout = await page.locator('[data-graph-slice]').evaluateAll((elements) => {
    const rows = elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        slice: (element as HTMLElement).dataset.graphSlice ?? '',
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
      };
    });
    const overlaps: string[] = [];
    for (let left = 0; left < rows.length; left += 1) {
      for (let right = left + 1; right < rows.length; right += 1) {
        const a = rows[left];
        const b = rows[right];
        if (
          Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1
        ) {
          overlaps.push(`${a.slice}:${left}-${b.slice}:${right}`);
        }
      }
    }
    const leftBySlice = Object.fromEntries(
      ['Physical', 'Media', 'Conglomerate', 'Financial'].map((slice) => [
        slice,
        Math.min(...rows.filter((row) => row.slice === slice).map((row) => row.left)),
      ]),
    );
    return { overlaps, leftBySlice };
  });
  expect(layout.overlaps).toEqual([]);
  expect(layout.leftBySlice.Physical).toBeLessThan(layout.leftBySlice.Media);
  expect(layout.leftBySlice.Media).toBeLessThan(layout.leftBySlice.Conglomerate);
  expect(layout.leftBySlice.Conglomerate).toBeLessThan(layout.leftBySlice.Financial);

  await page.getByLabel('Search nodes or roles').fill('president');
  await expect(page.locator('[data-graph-node="USA"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="Canada"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Search nodes or roles').fill('trader');
  await expect(page.locator('[data-graph-node="BerkshireHathawayStock"]')).toHaveClass(
    /highlighted/,
  );
  await expect(page.locator('[data-graph-node="FinancialEconomy"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Search nodes or roles').fill('Toronto');
  await expect(page.locator('[data-graph-node="Toronto"]')).toHaveCount(1);
  const toronto = page.locator('[data-graph-path="World>Canada>Ontario>Toronto"]');
  await expect(toronto).toBeVisible();
  await toronto
    .getByRole('button', { name: 'Collapse subtree' })
    .evaluate((element: HTMLButtonElement) => element.click());
  await expect(page.locator('[data-graph-path^="World>Canada>Ontario>Toronto>"]')).toHaveCount(0);
  await toronto
    .getByRole('button', { name: /Expand/ })
    .evaluate((element: HTMLButtonElement) => element.click());
  await expect(
    page.locator('[data-graph-path^="World>Canada>Ontario>Toronto>"]').first(),
  ).toBeVisible();

  await page.getByLabel('Search nodes or roles').fill('xyz-no-match');
  await expect(page.getByText("No nodes match 'xyz-no-match'")).toBeVisible();
  await page.getByLabel('Search nodes or roles').fill('');
  await page.getByLabel('Vertical slice').selectOption('Conglomerate');
  await page
    .locator('[data-graph-node="BerkshireRetailStore"]')
    .evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('[data-graph-detail]')).toContainText('cashier');
  await expect(page.locator('[data-graph-detail]')).toContainText('manager');
  await expect(page.locator('[data-graph-detail]')).toContainText('owner');

  await page.getByLabel('Vertical slice').selectOption('Physical');
  await page.locator('[data-graph-node="USA"]').evaluate((element: HTMLElement) => element.click());
  const detail = page.locator('[data-graph-detail]');
  await detail.getByRole('button', { name: 'View in code' }).click();
  const editor = page.getByLabel('Simulation DSL code');
  const selectedLine = await editor.evaluate((element: HTMLTextAreaElement) =>
    element.value.slice(element.selectionStart, element.selectionEnd),
  );
  expect(selectedLine).toBe('composition USA:');
});

test('uses pool-first run inputs and reports one pool with overlapping roles', async ({ page }) => {
  test.setTimeout(90_000);
  await expect(page.getByLabel('Total represented pool')).toHaveValue('6999999999');
  await expect(page.getByLabel('Days')).toHaveValue('30');
  await expect(page.getByLabel('Seed', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Sample budget')).toHaveCount(0);
  await expect(page.getByLabel('Planned draws')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Run full system' })).toBeVisible();
  await expect(page.locator('.text-dsl-advanced')).not.toHaveAttribute('open', '');

  await page.getByLabel('Total represented pool').fill('8000000000');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run full system' }).click();
  const summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('Total pool 8,000,000,000', { timeout: 60_000 });
  await expect(summary).toContainText('seed 1');
  await expect(summary).toContainText('detail medium');
  await expect(page.getByRole('heading', { name: 'One global pool' })).toBeVisible();
  await expect(page.getByText('Unassigned required roles = 0')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Residence partition' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Sector role membership' })).toBeVisible();
  await expect(page.getByText(/Overlay sums exceed the total/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Leader assignments' })).toBeVisible();
  await page.getByRole('tab', { name: 'Graph' }).click();
  await page.getByLabel('Global agent pool').getByRole('button').click();
  await expect(page.locator('.dsl-pool-agents article').first()).toBeVisible();
  await page
    .locator('[data-graph-node="FinancialEconomy"]')
    .evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('.dsl-pool-agents')).toContainText('trader');
});

test('keeps validation, save, reset, and current outline navigation synchronized', async ({
  page,
}) => {
  test.setTimeout(60_000);
  const editor = page.getByLabel('Simulation DSL code');
  const shipped = await editor.inputValue();
  await page.getByLabel('Search DSL outline').fill('BerkshireHathaway');
  await expect(
    page
      .locator('.dsl-outline [data-outline-line]')
      .filter({ hasText: 'BerkshireHathaway' })
      .first(),
  ).toBeVisible();

  await editor.fill(`${shipped}\n`);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(page.getByText('Saved DSL is valid and ready to run.')).toBeVisible();

  await page.getByRole('button', { name: 'Reset shipped DSL' }).click();
  await page.getByRole('button', { name: 'Click again to reset' }).click();
  await expect(editor).toHaveValue(shipped);
});
