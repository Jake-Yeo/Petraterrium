import { expect, test } from '@playwright/test';

declare global {
  interface Window {
    simulationRunGlobeHarness: {
      globe: {
        diagnostics(): {
          render_count: number;
          aggregate_upload_count: number;
          agent_point_upload_count: number;
          area_color_upload_count: number;
          country_surface_count: number;
          displayed_agent_points: number;
          detail_level: string;
        };
      };
      requests: Array<{
        day: number;
        detail_level: string;
        visible_city_ids: string[];
        bounds: { north: number; east: number; south: number; west: number };
      }>;
      selectedAgents: string[];
    };
  }
}

test.beforeEach(async ({ page }) => {
  await page.goto('/tests/fixtures/simulation-run-globe.html');
  await expect(page.getByRole('heading', { name: 'Simulation globe' })).toBeVisible();
});

test('colors recorded geographic areas, picks places, and plays recorded ticks', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const globe = page.locator('[data-simulation-run-globe]');
  const canvas = globe.getByRole('application', { name: /3D simulation globe/ });

  await expect(canvas).toBeVisible();
  await expect(globe.getByLabel('Globe statistic')).toHaveValue('unemployment_rate');
  await expect(globe.getByLabel('Globe statistic').locator('option')).toHaveCount(4);
  await expect(globe).toContainText('Unemployment rate');
  await expect(globe).toContainText('1 region clusters');
  await expect(globe).toContainText('2 country aggregates');
  await expect(globe).toContainText('2 city aggregates');
  expect(
    await page.evaluate(() => window.simulationRunGlobeHarness.globe.diagnostics()),
  ).toMatchObject({ country_surface_count: 2, area_color_upload_count: 1 });

  const canvasBounds = await canvas.boundingBox();
  if (!canvasBounds) throw new Error('Globe canvas bounds are unavailable');
  const canvasCenter = { x: canvasBounds.width / 2, y: canvasBounds.height / 2 };
  await canvas.click({ position: canvasCenter });
  await expect(globe.getByRole('heading', { name: 'Northern America' })).toBeVisible();
  await expect(globe.getByLabel('Selected place aggregate statistics')).toContainText(
    'Unemployment',
  );
  await expect(globe.getByLabel('Selected place aggregate statistics')).toContainText('Finances');
  await expect(globe.getByLabel('Selected place aggregate statistics')).toContainText('Estimated');

  await globe.getByLabel('Map detail level').selectOption('country');
  await expect(globe).toContainText('Country detail');
  await canvas.click({ position: canvasCenter });
  await expect(globe.getByRole('heading', { name: 'United States' })).toBeVisible();
  await expect(globe.getByLabel('Selected place aggregate statistics')).toContainText(
    'National labour force survey',
  );

  await globe.getByLabel('Globe statistic').selectOption('action_rate');
  await expect(globe.getByLabel('Action rate statistic')).toBeVisible();
  await globe.getByLabel('Action rate statistic').selectOption('work');
  await expect(globe).toContainText('Work rate per 1,000');
  await globe.getByLabel('Globe statistic').selectOption('mean_income');
  await expect(globe).toContainText('Mean income');
  await globe.getByRole('slider', { name: 'Simulation tick' }).fill('1');
  await expect(globe).toContainText('Day 2 · 2026-11-02');
  await expect(globe.getByLabel('Selected place aggregate statistics')).toContainText('Day 2');

  await globe.getByRole('button', { name: 'Play simulation ticks' }).click();
  await expect(globe.getByRole('button', { name: 'Pause simulation ticks' })).toBeVisible();
  await expect(globe.locator('.simulation-run-globe-day-output')).not.toHaveText(
    'Day 2 · 2026-11-02',
    { timeout: 1_500 },
  );
  await globe.getByRole('button', { name: 'Pause simulation ticks' }).click();
  await expect(globe.getByRole('button', { name: 'Play simulation ticks' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('loads only viewport agents into one GPU point cloud without an animation loop', async ({
  page,
}) => {
  const globe = page.locator('[data-simulation-run-globe]');
  const canvas = globe.getByRole('application', { name: /3D simulation globe/ });

  await globe.getByLabel('Map detail level').selectOption('city');
  await expect(globe).toContainText('2 viewport agents');
  const request = await page.evaluate(
    () => window.simulationRunGlobeHarness.requests.at(-1) ?? null,
  );
  expect(request).not.toBeNull();
  expect(request?.detail_level).toBe('city');
  expect(request?.visible_city_ids).toEqual(['new-york']);
  expect(request?.bounds.north).toBeGreaterThan(0);
  await expect(globe.locator('[data-agent-id]')).toHaveCount(0);
  expect(
    await page.evaluate(() => window.simulationRunGlobeHarness.globe.diagnostics()),
  ).toMatchObject({
    displayed_agent_points: 2,
    detail_level: 'city',
  });

  await globe.getByLabel('Map detail level').selectOption('neighborhood');
  await expect(globe).toContainText('Neighborhood detail');
  await expect
    .poll(async () =>
      page.evaluate(() => window.simulationRunGlobeHarness.requests.at(-1)?.detail_level ?? null),
    )
    .toBe('neighborhood');
  await expect(globe).toContainText('2 viewport agents');

  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('Globe canvas bounds are unavailable');
  await canvas.click({ position: { x: bounds.width / 2, y: bounds.height / 2 } });
  await expect(globe.locator('.simulation-run-globe-live')).toContainText(
    'agent-visible-1 selected',
  );
  expect(await page.evaluate(() => window.simulationRunGlobeHarness.selectedAgents)).toEqual([
    'agent-visible-1',
  ]);

  await page.waitForTimeout(250);
  const renderCount = await page.evaluate(
    () => window.simulationRunGlobeHarness.globe.diagnostics().render_count,
  );
  await page.waitForTimeout(400);
  expect(
    await page.evaluate(() => window.simulationRunGlobeHarness.globe.diagnostics().render_count),
  ).toBe(renderCount);

  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light';
  });
  const background = await globe
    .getByLabel('Globe statistic')
    .evaluate((select) => getComputedStyle(select).backgroundColor);
  expect(background).not.toBe('rgba(0, 0, 0, 0)');
});
