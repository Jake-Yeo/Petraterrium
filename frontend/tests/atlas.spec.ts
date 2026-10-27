import { expect, test } from '@playwright/test';

test('Data tab filters, validates, commits privately, promotes explicitly, and returns to the simulator', async ({
  page,
  request,
}) => {
  const created = await request.post('http://127.0.0.1:8011/runs', {
    data: { countries: ['ITA'], end_day: 4, seed: 230 },
  });
  const run = (await created.json()).run_id;
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await expect(page.locator('#atlas-summary')).toContainText('5');
  await expect(page.getByRole('heading', { name: 'What needs importing' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Place hierarchy' })).toContainText('Regions');
  await page.getByRole('button', { name: 'Open countries in Europe' }).click();
  await expect(page.getByRole('navigation', { name: 'Place hierarchy' })).toContainText('Europe');
  await expect(page.getByRole('button', { name: 'Open cities in Germany' })).toBeVisible();
  await page.getByRole('button', { name: '← Back' }).click();
  await page.locator('#atlas-city-audit summary').click();
  await expect(page.locator('#atlas-cities tr')).toHaveCount(5);
  await page.getByRole('searchbox', { name: 'Search cities' }).fill('Alpha');
  await expect(page.locator('#atlas-cities tr')).toHaveCount(2);
  await page.getByLabel('Country', { exact: true }).selectOption('FR');
  await expect(page.locator('#atlas-cities')).toContainText('No cities match');
  await page.getByLabel('Country', { exact: true }).selectOption('IT');
  await expect(page.locator('#atlas-cities tr')).toHaveCount(2);
  await page.locator('#atlas-cities').getByRole('button', { name: 'Alpha', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Still missing');
  await expect(page.getByRole('dialog')).toContainText('Age & sex');
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Import data', exact: true }).click();
  await page.locator('[name="run_id"]').selectOption(run);
  await page.getByLabel('Source label').fill('FAKE browser-test observations');
  await page.getByLabel('Data date', { exact: true }).fill('2020-01-01');
  await page.getByLabel('Publication date').fill('2020-01-02');
  await page.getByLabel('Source version').fill('test-v1');
  await page.getByLabel(/Propose mappings with an LLM/).uncheck();
  await page.getByLabel(/This source allows redistribution/).check();
  await page.locator('[name="file"]').setInputFiles({
    name: 'marginals.json',
    mimeType: 'application/json',
    buffer: Buffer.from(
      JSON.stringify([
        {
          geonameid: 1,
          country_code: 'IT',
          age_sex: { male: 49, female: 51 },
          household_size: 2.5,
        },
      ]),
    ),
  });
  await page.getByRole('button', { name: 'Preview & map' }).click();
  await expect(page.getByRole('dialog')).toContainText('Confirm every column');
  await page.getByRole('button', { name: 'Close import', exact: true }).click();
  await page.getByLabel('Data scope', { exact: true }).selectOption(run);
  await page.getByRole('button', { name: 'Resume review', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Confirm every column');
  await page.getByRole('button', { name: 'Validate confirmed mapping' }).click();
  await expect(page.locator('#atlas-validation')).toContainText('Write blocked');
  await page.getByLabel('I reviewed the mappings, including units and geography.').check();
  await page.getByRole('button', { name: 'Validate confirmed mapping' }).click();
  await expect(page.locator('#atlas-validation')).toContainText('Validation passed');
  await page.getByRole('button', { name: 'Commit to this run' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#atlas-cities')).toContainText('28.57%');
  const scoped = await (
    await request.get(`http://127.0.0.1:8011/atlas/overview?scope=${run}`)
  ).json();
  const shared = await (await request.get('http://127.0.0.1:8011/atlas/overview')).json();
  expect(scoped.summary.direct.partial).toBe(1);
  expect(shared.summary.direct.none).toBe(5);
  await page.getByRole('button', { name: 'Promote…' }).click();
  await page.getByRole('button', { name: 'Keep private' }).click();
  expect(
    (await (await request.get('http://127.0.0.1:8011/atlas/overview')).json()).summary.direct.none,
  ).toBe(5);
  await page.getByRole('button', { name: 'Promote…' }).click();
  await page
    .getByRole('checkbox', { name: /I confirm this source permits redistribution/ })
    .check();
  await page.getByRole('button', { name: 'Promote version', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByLabel('Data scope', { exact: true }).selectOption('shared');
  await expect(page.locator('#atlas-cities')).toContainText('28.57%');
  await page.screenshot({ path: 'test-results/data-atlas-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Source loaders', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('IPUMS International');
  await expect(page.getByRole('dialog')).toContainText('Gallup World Poll');
  await page.getByRole('button', { name: 'Close source loaders' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: 'test-results/data-atlas-mobile.png' });
  await page.getByRole('tab', { name: 'Simulation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Trace the state.' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('Data tab creates, edits, opens, and queries persistent agent features', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data coverage' })).toBeVisible();
  const catalog = page.locator('#atlas-feature-catalog');
  await expect(catalog).toContainText('Economic ideology');
  await expect(catalog).toContainText('State ideology');
  await expect(catalog).toContainText('Cultural ideology');
  await expect(catalog).not.toContainText('Blood Type');
  await expect(catalog).not.toContainText('Eye Colour');
  await expect(catalog).toContainText('MBTI');
  await expect(catalog.getByRole('button', { name: 'Open Ideology feature details' })).toHaveCount(
    0,
  );
  await catalog.getByRole('button', { name: 'Add feature', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Add agent feature' })).not.toContainText('go_out');
  const create = page.getByRole('dialog', { name: 'Add agent feature' });
  await create.getByLabel('Feature ID').fill('endurance_e2e');
  await create.getByLabel('Name').fill('Endurance');
  await create
    .getByLabel('Description')
    .fill('Sustained physical effort on a validated 0–100 assessment.');
  await create.getByLabel('Provenance placeholder').fill('Representative endurance survey');
  await create.getByLabel('Minimum').fill('0');
  await create.getByLabel('Maximum').fill('100');
  await create.getByLabel('Unit').fill('score');
  await create.getByLabel('Status').selectOption('awaiting_data');
  await create.getByRole('button', { name: 'Create feature', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Endurance' })).toBeVisible();
  await expect(catalog).toContainText('Awaiting data');
  await expect(catalog).toContainText('Label-only');
  await catalog.getByRole('button', { name: 'Edit', exact: true }).click();
  await catalog
    .locator('[data-feature-description-form] textarea')
    .fill('Sustained effort measured by a validated assessment.');
  await catalog.getByRole('button', { name: 'Save description' }).click();
  await expect(catalog).toContainText('Sustained effort measured by a validated assessment.');
  await catalog.getByRole('button', { name: '← Back to features' }).click();
  const economic = catalog.getByRole('button', {
    name: 'Open Economic ideology feature details',
  });
  await economic.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Economic ideology' })).toBeVisible();
  await catalog.getByRole('button', { name: '← Back to features' }).click();
  const state = catalog.getByRole('button', { name: 'Open State ideology feature details' });
  await state.focus();
  await page.keyboard.press('Space');
  await expect(catalog).toContainText('anti-authoritarian');
  await expect(catalog).toContainText('not identical');
  await catalog.getByRole('button', { name: '← Back to features' }).click();
  await catalog.getByRole('button', { name: 'Open Age band feature details' }).click();
  await expect(page.getByRole('heading', { name: 'Place distribution and joined filters' })).toBeVisible();
  await expect(catalog.locator('[data-inheritance-result]')).toContainText('agents');
  const filterRows = catalog.locator('[data-joined-row]');
  await filterRows.nth(0).locator('[data-filter-feature]').selectOption('age_band');
  await filterRows.nth(1).locator('[data-filter-feature]').selectOption('sex');
  await expect(catalog.locator('[data-joined-result]')).toContainText(
    'independence estimate — not measured',
  );
  await expect(catalog.locator('[data-joined-result]')).toContainText('Joint data needed');
  await page.getByRole('tab', { name: 'DSL', exact: true }).click();
  await expect(page.locator('#dsl-features')).toContainText('Endurance');
  await expect(page.locator('#dsl-features')).toContainText('LABEL-ONLY');
  await page.reload();
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await page.getByRole('searchbox', { name: 'Search features' }).fill('endurance');
  await expect(catalog).toContainText('Sustained effort measured by a validated assessment.');
  expect(errors).toEqual([]);
});
