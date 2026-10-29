import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/simulation/text-dsl/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Population simulation program' })).toBeVisible();
});

test('renders each main vertical slice as one root-to-leaf level line', async ({ page }) => {
  test.setTimeout(60_000);
  await page.getByRole('tab', { name: 'Graph' }).click();

  await expect(page.getByLabel('Petraterrium system root')).toBeVisible();
  await expect(page.getByLabel('Logical population summary')).toBeVisible();
  const slices = page.getByRole('tablist', { name: 'Vertical slices' });
  for (const slice of [
    'World',
    'Platforms',
    'Conglomerates',
    'Independent businesses',
    'Economies',
  ]) {
    await expect(slices.getByRole('tab', { name: slice })).toBeVisible();
  }
  await expect(slices.getByRole('tab', { name: 'World' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-hierarchy-lane]')).toHaveCount(0);
  for (const level of ['World', 'Countries', 'Divisions', 'Cities', 'Neighbourhoods']) {
    await expect(page.locator(`[data-graph-node="${level}"]`)).toBeVisible();
  }
  await expect(
    page.locator('[data-graph-path="World>Countries>Divisions>Cities>Neighbourhoods"]'),
  ).toBeVisible();
  await expect(page.locator('[data-graph-slice="Physical"]')).toHaveCount(5);
  for (const instance of ['Canada', 'USA', 'Mexico', 'Toronto']) {
    await expect(page.locator(`[data-graph-node="${instance}"]`)).toHaveCount(0);
  }

  await slices.getByRole('tab', { name: 'Platforms' }).click();
  for (const level of ['Platforms', 'Communities']) {
    await expect(page.locator(`[data-graph-node="${level}"]`)).toBeVisible();
  }
  await expect(page.locator('[data-graph-path="Platforms>Communities"]')).toBeVisible();
  await expect(page.locator('[data-graph-slice="Media"]')).toHaveCount(2);
  await expect(page.locator('[data-graph-node="Media"]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="Reddit"]')).toHaveCount(0);

  await slices.getByRole('tab', { name: 'Conglomerates' }).click();
  for (const level of ['Conglomerates', 'Brands', 'Franchises', 'Stores']) {
    await expect(page.locator(`[data-graph-node="${level}"]`)).toBeVisible();
  }
  await expect(
    page.locator('[data-graph-path="Conglomerates>Brands>Franchises>Stores"]'),
  ).toBeVisible();
  await expect(page.locator('[data-graph-slice="Conglomerate"]')).toHaveCount(4);
  await expect(page.locator('[data-graph-node="Conglomerate"]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="Independent businesses"]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="BerkshireHathaway"]')).toHaveCount(0);

  await slices.getByRole('tab', { name: 'Economies' }).click();
  for (const level of ['Economies', 'Sectors', 'Markets', 'Stocks']) {
    await expect(page.locator(`[data-graph-node="${level}"]`)).toBeVisible();
  }
  await expect(page.locator('[data-graph-path="Economies>Sectors>Markets>Stocks"]')).toBeVisible();
  await expect(page.locator('[data-graph-slice="Financial"]')).toHaveCount(4);
  await expect(page.locator('[data-graph-node="Financial"]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="FinancialEconomy"]')).toHaveCount(0);

  await slices.getByRole('tab', { name: 'Independent businesses' }).click();
  await expect(page.locator('[data-graph-path="Independent businesses"]')).toBeVisible();
  await expect(page.locator('[data-graph-slice="Independent Businesses"]')).toHaveCount(1);
  await expect(page.locator('[data-graph-node="IndependentBusinesses"]')).toHaveCount(0);

  await slices.getByRole('tab', { name: 'World' }).click();
  await expect(page.locator('[data-graph-node="Person"]')).toHaveCount(0);

  await page.getByLabel('Search nodes or roles').fill('president');
  await expect(page.locator('[data-graph-node="Countries"]')).toHaveClass(/highlighted/);
  await page.getByLabel('Search nodes or roles').fill('prime_minister');
  await expect(page.locator('[data-graph-node="Countries"]')).toHaveClass(/highlighted/);

  await page.getByLabel('Search nodes or roles').fill('Toronto');
  const cities = page.locator('[data-graph-node="Cities"]');
  await expect(cities).toHaveClass(/highlighted/);
  await cities
    .getByRole('button', { name: 'Hide lower levels' })
    .evaluate((element: HTMLButtonElement) => element.click());
  await expect(page.locator('[data-graph-node="Neighbourhoods"]')).toHaveCount(0);
  await cities
    .getByRole('button', { name: 'Show next level' })
    .evaluate((element: HTMLButtonElement) => element.click());
  await expect(page.locator('[data-graph-node="Neighbourhoods"]')).toBeVisible();

  await page.getByLabel('Search nodes or roles').fill('xyz-no-match');
  await expect(page.getByText("No nodes match 'xyz-no-match'")).toBeVisible();
  await page.getByLabel('Search nodes or roles').fill('');
  await page
    .locator('[data-graph-node="Countries"]')
    .evaluate((element: HTMLElement) => element.click());
  const detail = page.locator('[data-graph-detail]');
  await expect(detail).toContainText('Canada');
  await expect(detail).toContainText('USA');
  await expect(detail).toContainText('Mexico');
  await detail.getByRole('button', { name: 'View in code' }).click();
  const editor = page.getByLabel('Simulation DSL code');
  const selectedLine = await editor.evaluate((element: HTMLTextAreaElement) => {
    const start = element.value.lastIndexOf('\n', element.selectionStart - 1) + 1;
    const end = element.value.indexOf('\n', element.selectionStart);
    return element.value.slice(start, end < 0 ? undefined : end);
  });
  expect(selectedLine).toBe('composition Canada:');
});

test('derives slice tabs and vertical level lines from edited DSL metadata', async ({ page }) => {
  test.setTimeout(60_000);
  const editor = page.getByLabel('Simulation DSL code');
  const shipped = await editor.inputValue();
  const custom = `${shipped.replaceAll('slice = "Physical"', 'slice = "Territory"')}

composition CivicRegistry:
  slice = "Civic"
  graph_group = main
  level = registry
  clock = 1 days
  sync_up = 7 days
  children:
    HouseholdLiberalUrban: weight = 1.0
  output population = count()
`;
  await editor.fill(custom);
  await page.getByRole('button', { name: 'Validate code' }).click();
  await expect(page.getByText('Valid Rust DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Save DSL' }).click();
  await page.getByRole('tab', { name: 'Graph' }).click();

  const slices = page.getByRole('tablist', { name: 'Vertical slices' });
  for (const slice of [
    'World',
    'Platforms',
    'Conglomerates',
    'Independent businesses',
    'Economies',
    'Registries',
  ]) {
    await expect(slices.getByRole('tab', { name: slice })).toBeVisible();
  }
  await expect(page.locator('[data-active-slice="Territory"]')).toBeVisible();
  await expect(page.locator('[data-hierarchy-lane]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="World"]')).toBeVisible();
  await expect(page.locator('[data-graph-node="Countries"]')).toBeVisible();

  await slices.getByRole('tab', { name: 'Registries' }).click();
  await expect(page.locator('[data-active-slice="Civic"]')).toBeVisible();
  await expect(page.locator('[data-graph-node="Registries"]')).toBeVisible();
  await expect(page.locator('[data-graph-node="Civic"]')).toHaveCount(0);
  await expect(page.locator('[data-graph-node="CivicRegistry"]')).toHaveCount(0);
  await expect(page.locator('[data-hierarchy-lane]')).toHaveCount(0);
});

test('surfaces disconnected main vertical slice validation', async ({ page }) => {
  const editor = page.getByLabel('Simulation DSL code');
  const shipped = await editor.inputValue();
  const disconnected = shipped.replace(
    'entity BerkshireHathawayListing:',
    `composition CooperativeBusinesses:
  slice = "Conglomerate"
  graph_group = main
  level = independent_businesses
  clock = 7 days
  sync_up = 28 days
  children:
    HouseholdRuralMixed: weight = 1.0
  output population = count()

entity BerkshireHathawayListing:`,
  );
  expect(disconnected).not.toBe(shipped);
  await editor.fill(disconnected);
  await page.getByRole('button', { name: 'Validate code' }).click();
  const invalid = page.locator('.text-dsl-invalid');
  await expect(invalid).toContainText('INVALID_VERTICAL_SLICE');
  await expect(invalid).toContainText('one connected level chain');
  await expect(page.getByRole('button', { name: 'Save DSL' })).toBeDisabled();
});

test('contains wheel zoom and keeps the DSL editor controls and gutter anchored', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.getByRole('tab', { name: 'Graph' }).click();
  await expect(page.getByRole('tablist', { name: 'Simulation sections' })).toHaveCount(0);
  const graph = page.locator('.dsl-react-flow');
  await graph.scrollIntoViewIfNeeded();
  const pageScrollBefore = await page.evaluate(() => window.scrollY);
  const zoomBefore = Number(await graph.getAttribute('data-viewport-zoom'));
  await page.locator('.dsl-react-node').first().hover();
  await page.mouse.wheel(0, 500);
  await expect
    .poll(async () => Number(await graph.getAttribute('data-viewport-zoom')))
    .toBeLessThan(zoomBefore);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageScrollBefore);
  const zoomedOut = Number(await graph.getAttribute('data-viewport-zoom'));
  await page.mouse.wheel(0, -500);
  await expect
    .poll(async () => Number(await graph.getAttribute('data-viewport-zoom')))
    .toBeGreaterThan(zoomedOut);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageScrollBefore);

  await page.getByRole('tab', { name: 'Code', exact: true }).click();
  const toolbar = page.locator('.text-dsl-editor-toolbar');
  await expect(toolbar).toHaveCSS('position', 'sticky');
  const stickyPosition = await toolbar.evaluate(async (element) => {
    const scrolling = document.scrollingElement!;
    scrolling.scrollTop = (element as HTMLElement).offsetTop + 240;
    await new Promise(requestAnimationFrame);
    return {
      top: element.getBoundingClientRect().top,
      viewportTop: document.documentElement.getBoundingClientRect().top,
    };
  });
  expect(stickyPosition.top).toBeGreaterThanOrEqual(0);

  const editor = page.getByLabel('Simulation DSL code');
  const gutter = page.locator('.text-dsl-gutter');
  await editor.evaluate((element: HTMLTextAreaElement) => {
    element.scrollTop = 640;
    element.dispatchEvent(new Event('scroll'));
  });
  await expect.poll(() => gutter.evaluate((element) => element.scrollTop)).toBe(640);
  const alignment = await page.locator('.text-dsl-code-frame').evaluate((frame) => {
    const frameRect = frame.getBoundingClientRect();
    const gutterRect = frame.querySelector('.text-dsl-gutter')!.getBoundingClientRect();
    const codeRect = frame.querySelector('.text-dsl-code')!.getBoundingClientRect();
    return {
      gutterTop: gutterRect.top - frameRect.top,
      gutterBottom: frameRect.bottom - gutterRect.bottom,
      codeTop: codeRect.top - frameRect.top,
      codeBottom: frameRect.bottom - codeRect.bottom,
    };
  });
  expect(alignment).toEqual({ gutterTop: 1, gutterBottom: 1, codeTop: 1, codeBottom: 1 });
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

  const cities = page.locator('[data-graph-node="Cities"]');
  await cities.evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('[data-graph-detail]')).toContainText('City mixture distributions');
  await expect(page.locator('[data-graph-detail]')).toContainText('Toronto');

  const neighbourhoods = page.locator('[data-graph-node="Neighbourhoods"]');
  await neighbourhoods.evaluate((element: HTMLElement) => element.click());
  await expect(page.locator('[data-graph-detail]')).toContainText('Detailed exemplar households');
  await expect(page.locator('[data-graph-detail]')).toContainText('75 households');
  await page.getByLabel('Exposes role').selectOption('trader');
  await expect(neighbourhoods).toHaveClass(/highlighted/);

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
