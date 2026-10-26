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
  await page.getByRole('button', { name: 'Import data' }).click();
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
  await expect(page.locator('#atlas-cities')).toContainText('40.00%');
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
  await expect(page.locator('#atlas-cities')).toContainText('40.00%');
  await page.screenshot({ path: 'test-results/data-atlas-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Source loaders', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('IPUMS International');
  await expect(page.getByRole('dialog')).toContainText('Gallup World Poll');
  await page.getByRole('button', { name: 'Close source loaders' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: 'test-results/data-atlas-mobile.png', fullPage: true });
  await page.getByRole('tab', { name: 'Simulation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Trace the spread.' })).toBeVisible();
  expect(errors).toEqual([]);
});
