import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
});

test('renders the physical hierarchy with current search collapse and code navigation', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.getByRole('tab', { name: 'Graph' }).click();

  await expect(page.getByLabel('Petraterrium system root')).toBeVisible();
  await expect(page.getByLabel('Logical population summary')).toBeVisible();
  await expect(page.getByLabel('Vertical slice').locator('option[value="Physical"]')).toHaveCount(
    1,
  );
  for (const removed of ['Full system', 'Media', 'Conglomerate', 'Financial']) {
    await expect(
      page.getByLabel('Vertical slice').locator(`option[value="${removed}"]`),
    ).toHaveCount(0);
  }
  await expect(page.locator('[data-graph-node="Person"]')).toHaveCount(0);

  await page.getByLabel('Search nodes or roles').fill('president');
  await expect(page.locator('[data-graph-node="USA"]')).toHaveClass(/highlighted/);
  await expect(page.locator('[data-graph-node="Mexico"]')).toHaveClass(/highlighted/);
  await page.getByLabel('Search nodes or roles').fill('prime_minister');
  await expect(page.locator('[data-graph-node="Canada"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Search nodes or roles').fill('Toronto');
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
  await page.locator('[data-graph-node="USA"]').evaluate((element: HTMLElement) => element.click());
  const detail = page.locator('[data-graph-detail]');
  await detail.getByRole('button', { name: 'View in code' }).click();
  const editor = page.getByLabel('Simulation DSL code');
  const selectedLine = await editor.evaluate((element: HTMLTextAreaElement) => {
    const start = element.value.lastIndexOf('\n', element.selectionStart - 1) + 1;
    const end = element.value.indexOf('\n', element.selectionStart);
    return element.value.slice(start, end < 0 ? undefined : end);
  });
  expect(selectedLine).toBe('composition USA:');
});

test('learns weighted exemplars then composes from cache with zero mass ticks', async ({
  page,
}) => {
  test.setTimeout(120_000);
  await expect(page.getByLabel('Total represented pool')).toHaveValue('6999999999');
  await expect(page.getByLabel('Days')).toHaveValue('30');
  await expect(page.getByLabel('Seed', { exact: true })).toHaveValue('1');
  for (const removed of ['Detail', 'Sample budget', 'Planned draws']) {
    await expect(page.getByLabel(removed, { exact: true })).toHaveCount(0);
  }
  await expect(page.locator('.text-dsl-advanced')).not.toHaveAttribute('open', '');

  await page.getByLabel('Total represented pool').fill('8000000000');
  await page.getByLabel('Days').fill('1');
  await page.getByRole('button', { name: 'Run full system' }).click();
  const summary = page.locator('.text-dsl-results > header');
  await expect(summary).toContainText('Total pool 8,000,000,000', { timeout: 90_000 });
  await expect(summary).toContainText('exemplars');
  await expect(
    page.getByRole('heading', { name: 'Weighted neighbourhood exemplars' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'City convergence' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Exemplar cache' })).toBeVisible();
  await expect(page.getByText('Unassigned required roles = 0')).toBeVisible();
  for (const city of [
    'Toronto',
    'Vancouver',
    'Lytton',
    'LosAngeles',
    'Houston',
    'MexicoCity',
    'Monterrey',
  ]) {
    await expect(
      page.getByRole('heading', { name: 'City convergence' }).locator('..'),
    ).toContainText(city);
  }

  await page.getByRole('button', { name: 'Run full system' }).click();
  await expect(page.getByRole('status')).toContainText('0 mass agent ticks', { timeout: 90_000 });
  await expect(page.getByRole('heading', { name: 'Exemplar cache' }).locator('..')).toContainText(
    'Relearned 0',
  );

  await page.getByRole('tab', { name: 'Graph' }).click();
  await expect
    .poll(() => page.locator('[data-dsl-graph-view]').getAttribute('data-render-ms'))
    .not.toBeNull();
  const renderMs = Number(
    await page.locator('[data-dsl-graph-view]').getAttribute('data-render-ms'),
  );
  console.log(`exemplar graph render ${renderMs.toFixed(1)}ms`);
  expect(renderMs).toBeLessThan(500);
  await page.getByLabel('Logical population summary').getByRole('button').click();
  await expect(page.locator('.dsl-pool-agents article').first()).toBeVisible();

  const torontoCity = page.locator('[data-graph-node="Toronto"]');
  await torontoCity.evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('[data-graph-detail]')).toContainText('City mixture distribution');
  await expect(page.locator('[data-graph-detail]')).toContainText('Exemplar weights');

  const exemplar = page.locator('[data-graph-node^="Toronto__"]').first();
  await expect(exemplar).toBeVisible();
  await expect(exemplar).toContainText('Cache');
  await exemplar.evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('[data-graph-detail]')).toContainText('Detailed exemplar households');
  await expect(page.locator('[data-graph-detail]')).toContainText('75 households');
  await expect(page.locator('[data-graph-detail]')).toContainText('resident_neighbourhood_');
  await page.getByLabel('Exposes role').selectOption('trader');
  await expect(page.locator('[data-graph-node^="Toronto__"]').first()).toHaveClass(/highlighted/);

  const overlaps = await page.locator('[data-graph-slice]').evaluateAll((elements) => {
    const boxes = elements.map((element) => element.getBoundingClientRect());
    const collisions: string[] = [];
    for (let left = 0; left < boxes.length; left += 1) {
      for (let right = left + 1; right < boxes.length; right += 1) {
        const a = boxes[left];
        const b = boxes[right];
        if (
          Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1
        ) {
          collisions.push(`${left}-${right}`);
        }
      }
    }
    return collisions;
  });
  expect(overlaps).toEqual([]);
});

test('keeps validation save reset and exemplar outline navigation synchronized', async ({
  page,
}) => {
  test.setTimeout(60_000);
  const editor = page.getByLabel('Simulation DSL code');
  const shipped = await editor.inputValue();
  await page.getByLabel('Search DSL outline').fill('Toronto');
  await expect(
    page.locator('.dsl-outline [data-outline-line]').filter({ hasText: 'Toronto' }).first(),
  ).toBeVisible();

  await editor.fill(`${shipped}\n`);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await expect(page.locator('.text-dsl-valid')).toContainText('weighted neighbourhood exemplar');
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await expect(page.getByText('Saved DSL is valid and ready to run.')).toBeVisible();

  await page.getByRole('button', { name: 'Reset shipped DSL' }).click();
  await page.getByRole('button', { name: 'Click again to reset' }).click();
  await expect(editor).toHaveValue(shipped);
});
