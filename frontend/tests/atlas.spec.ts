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
  await expect(page.getByRole('tab', { name: 'Coverage', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('tabpanel')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'What needs importing' })).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'What needs importing' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Place hierarchy' })).toContainText('Regions');
  await page.getByRole('button', { name: 'Open countries in Europe' }).click();
  await expect(page.getByRole('navigation', { name: 'Place hierarchy' })).toContainText('Europe');
  await expect(page.getByRole('button', { name: 'Open cities in Germany' })).toBeVisible();
  await page.getByRole('button', { name: '← Back' }).click();
  await page.getByRole('tab', { name: 'Cities', exact: true }).click();
  await expect(page.locator('#atlas-summary')).toBeHidden();
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
  await page.getByRole('tab', { name: 'Imports', exact: true }).click();
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
  await expect(page.getByRole('heading', { name: 'Agent type inheritance' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('Data tab creates, edits, opens, and queries persistent agent features', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data coverage' })).toBeVisible();
  await page.getByRole('tab', { name: 'Features', exact: true }).click();
  const catalog = page.locator('#atlas-feature-catalog');
  await expect(catalog).toContainText('Economic ideology');
  await expect(catalog).toContainText('State ideology');
  await expect(catalog).toContainText('Cultural ideology');
  await expect(catalog).not.toContainText('Blood Type');
  await expect(catalog).not.toContainText('Eye Colour');
  await expect(catalog).not.toContainText('Age band');
  await expect(catalog).toContainText('Age');
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
  await catalog.getByRole('button', { name: 'Open Age feature details' }).click();
  await catalog.getByRole('button', { name: 'Import data for Age' }).click();
  const featureImport = page.getByRole('dialog', { name: 'Import atlas data' });
  await expect(featureImport).toContainText('Target feature');
  await expect(featureImport.getByLabel('Target feature')).toHaveValue('age');
  await featureImport.getByRole('button', { name: 'Cancel' }).click();
  const inheritanceAccordion = catalog.getByRole('button', {
    name: 'Agent inheritance: Place distribution and joined filters',
  });
  await expect(inheritanceAccordion).toHaveAttribute('aria-expanded', 'false');
  await inheritanceAccordion.click();
  await expect(inheritanceAccordion).toHaveAttribute('aria-expanded', 'true');
  await expect(catalog.locator('#feature-inheritance-accordion-panel')).toBeVisible();
  await catalog.getByLabel('Find a place or source').fill('IT');
  await expect(catalog.getByRole('row', { name: /Age 1/ })).toContainText('800 agents');
  await expect(catalog.locator('[data-inheritance-result]')).toContainText('agents');
  const filterRows = catalog.locator('[data-joined-row]');
  await filterRows.nth(0).locator('[data-filter-feature]').selectOption('age');
  await filterRows.nth(1).locator('[data-filter-feature]').selectOption('sex');
  await expect(catalog.locator('[data-joined-result]')).toContainText(
    'independence estimate — not measured',
  );
  await expect(catalog.locator('[data-joined-result]')).toContainText('Joint data needed');
  await page.reload();
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await page.getByRole('tab', { name: 'Features', exact: true }).click();
  await page.getByRole('searchbox', { name: 'Search features' }).fill('endurance');
  await expect(catalog).toContainText('Sustained effort measured by a validated assessment.');
  await page.getByRole('tab', { name: 'Evidence', exact: true }).click();
  await page.getByRole('button', { name: 'Import behavior evidence' }).click();
  const evidenceImport = page.getByRole('dialog', { name: 'Import atlas data' });
  await expect(evidenceImport.getByLabel('Data kind')).toHaveValue('behaviour');
  await evidenceImport.getByRole('button', { name: 'Cancel' }).click();
  expect(errors).toEqual([]);
});

test('Data tab reviews and explicitly promotes a field-level research import', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  const importer = page.locator('#atlas-auto-import');
  const primaryCohort = importer.getByRole('button', { name: /Regions, countries, and cities/ });
  const lowerCohort = importer.getByRole('button', { name: /Lower-priority cities/ });
  await expect(primaryCohort).toHaveAttribute('aria-pressed', 'true');
  await expect(lowerCohort).toHaveAttribute('aria-pressed', 'false');
  await lowerCohort.click();
  await expect(lowerCohort).toHaveAttribute('aria-pressed', 'true');
  await expect(primaryCohort).toHaveAttribute('aria-pressed', 'false');
  await primaryCohort.click();
  await expect(primaryCohort).toHaveAttribute('aria-pressed', 'true');
  await importer.getByLabel('Place level').selectOption('city');
  await importer.getByLabel('Feature').selectOption('income');
  await importer.getByLabel('Priority city threshold').fill('0');
  await importer.getByLabel('Priority city threshold').press('Tab');
  await importer.getByLabel('Search').fill('Alpha');
  const alphaRow = importer.locator(
    '.auto-import-queue-row:has(.auto-import-row-place strong:text-is("Alpha"))',
  );
  await expect(alphaRow).toHaveCount(1);
  await alphaRow.getByRole('button', { name: 'Import Income', exact: true }).click();
  const dialog = page.locator('.auto-import-dialog');
  await expect(dialog).toContainText('Income for Alpha');
  await expect(dialog).toContainText('Required distribution');
  const candidate = {
    title: 'Alpha income table',
    url: 'https://example.test/alpha-income',
    source_kind: 'representative_survey',
    feature: 'income',
    place: 'Alpha',
    place_level: 'city',
    denominator: 'persons',
    population: 1000,
    observation_date: '2020-01-01',
    published_date: '2020-02-01',
    time_unit: 'annual',
    unit: 'percent',
    distribution: { 'under 50k': 60, '50k or more': 40 },
    evidence_kind: 'measured',
    credible: true,
    credibility_reason: 'Published representative table with a stated universe',
    language: 'en',
    original_excerpt: 'Annual income: under 50k 60%; 50k or more 40%.',
    translated_excerpt: null,
    sample_size: 1000,
    source_version: '2020-table-1',
    license: 'CC BY 4.0',
  };
  await dialog.getByLabel('Pasted source text').fill(JSON.stringify(candidate));
  await dialog.getByRole('button', { name: 'Research automatically' }).click();
  await expect(dialog.getByRole('heading', { name: 'Confirm mapping' })).toBeVisible();
  await expect(dialog).toContainText('Under 50k');
  const before = await (await request.get('http://127.0.0.1:8011/atlas/cities/1')).json();
  expect(
    before.city.fields.find((field: { field: string }) => field.field === 'income').status,
  ).toBe('missing');
  await dialog
    .getByLabel(
      'I reviewed every mapping, including values, units, denominator, geography, and date.',
    )
    .check();
  await dialog.getByRole('button', { name: 'Confirm mapping and verify' }).click();
  await expect(dialog.getByRole('heading', { name: 'Measured evidence' })).toBeVisible();
  await expect(dialog).toContainText('Distribution totals 100');
  await expect(dialog.getByRole('button', { name: 'Retry unresolved research' })).toHaveCount(0);
  await expect(dialog).toContainText('Alpha income table');
  await expect(dialog.getByRole('link', { name: 'Open source ↗' })).toHaveCount(0);
  await dialog
    .getByLabel('I confirm this source permits redistribution in the shared atlas.')
    .check();
  await dialog.getByRole('button', { name: 'Promote', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Promote', exact: true })).toHaveCount(0);
  const after = await (await request.get('http://127.0.0.1:8011/atlas/cities/1')).json();
  const income = after.city.fields.find((field: { field: string }) => field.field === 'income');
  expect(income.status).toBe('present');
  expect(income.research_trace.result_kind).toBe('measured');
  await dialog.getByRole('button', { name: 'Cancel auto-import' }).click();
  await expect(alphaRow).toHaveCount(0);
  await page.getByRole('tab', { name: 'Cities', exact: true }).click();
  await page.locator('#atlas-cities').getByRole('button', { name: 'Alpha', exact: true }).click();
  const cityDialog = page.locator('#atlas-city-dialog');
  const trace = cityDialog.locator('.atlas-research-trace');
  await expect(trace.locator(':scope > summary')).toContainText('Research trace · measured');
  await trace.locator(':scope > summary').click();
  await expect(trace).toContainText('Mapping · confirmed');
  await expect(trace).toContainText('Verification · 1/1 accepted');
  await expect(trace).toContainText('Alpha income table');
  await expect(trace.getByRole('link', { name: /Alpha income table/ })).toHaveCount(0);
  await cityDialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('tab', { name: 'Features', exact: true }).click();
  await page
    .locator('#atlas-feature-catalog')
    .getByRole('button', { name: 'Open Annual income feature details' })
    .click();
  const feature = page.locator('#atlas-feature-catalog');
  await expect(feature).toContainText('Imported research evidence');
  await expect(feature).toContainText('Alpha');
  await expect(feature).toContainText('Annual income: under 50k 60%; 50k or more 40%.');
  expect(errors).toEqual([]);
});

test('Data tab reviews measured and estimated bulk results before promotion', async ({
  page,
  request,
}) => {
  const created = await request.post('http://127.0.0.1:8011/runs', {
    data: { countries: ['ITA'], end_day: 2, seed: 713 },
  });
  const run = (await created.json()).run_id as string;
  const requirement = {
    values: [],
    denominator: 'people with stated income universe',
    time_unit: 'annual',
    unit: 'percent',
    range: 'Annual individual income distribution',
    total: '100%',
  };
  const target = (placeId: string, placeLabel: string) => ({
    place_id: placeId,
    place_label: placeLabel,
    level: 'city',
    country_code: 'IT',
    geonameid: Number(placeId),
    population: placeId === '1' ? 1_000 : 2_000,
    field_id: 'income',
    field_label: 'Income',
    current_status: 'missing',
    as_of: '2026-10-26',
    required_distribution: requirement,
  });
  const queueItems = [
    {
      ...target('1', 'Alpha'),
      item_id: 'city|1|income',
      missing_impact: 1_000,
      priority: 'primary',
      place_item_count: 1,
    },
    {
      ...target('2', 'Alpha Town'),
      item_id: 'city|2|income',
      missing_impact: 2_000,
      priority: 'primary',
      place_item_count: 1,
    },
  ];
  const mappings = [
    {
      column: 'under 50k',
      target: 'under 50k',
      ambiguous: false,
      samples: ['60'],
      options: [{ id: 'under 50k', label: 'Under 50k' }],
    },
    {
      column: '50k or more',
      target: '50k or more',
      ambiguous: false,
      samples: ['40'],
      options: [{ id: '50k or more', label: '50k or more' }],
    },
  ];
  const batchItems = queueItems.map((item, index) => ({
    item_id: item.item_id,
    attempt_id: `attempt-${index + 1}`,
    target: Object.fromEntries(
      Object.entries(item).filter(
        ([key]) => !['item_id', 'missing_impact', 'priority', 'place_item_count'].includes(key),
      ),
    ),
    status: 'ready',
    evidence_kind: index === 0 ? 'measured' : 'estimated',
    mappings,
    mapping_confirmed: false,
    can_promote: true,
    error: null,
  }));
  const batch = (status: 'running' | 'review' | 'complete') => ({
    batch_id: 'batch-e2e',
    status,
    summary: {
      total: 2,
      completed: status === 'running' ? 0 : 2,
      queued: 0,
      running: status === 'running' ? 2 : 0,
      ready: status === 'review' ? 2 : 0,
      measured: status === 'running' ? 0 : 1,
      estimated: status === 'running' ? 0 : 1,
      failed: 0,
      retryable_failed: 0,
      promoted: status === 'complete' ? 2 : 0,
    },
    items: batchItems.map((item) => ({
      ...item,
      status: status === 'running' ? 'running' : status === 'complete' ? 'promoted' : 'ready',
      can_promote: status === 'review',
    })),
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:01Z',
  });
  let createBody: Record<string, unknown> | undefined;
  let promoteBody: Record<string, unknown> | undefined;
  let latestBatch: ReturnType<typeof batch> | null = null;
  await page.route('**/api/atlas/auto-import/queue?**', async (route) => {
    await route.fulfill({
      json: {
        items: queueItems,
        filtered_count: 2,
        filtered_population: 3_000,
        page: 1,
        page_size: 50,
        primary_count: 2,
        primary_population: 3_000,
        lower_priority_count: 0,
        lower_priority_population: 0,
      },
    });
  });
  await page.route('**/api/atlas/auto-import/batches**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/latest')) {
      await route.fulfill({ json: url.searchParams.get('scope') === run ? latestBatch : null });
      return;
    }
    if (url.pathname.endsWith('/promote')) {
      promoteBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: batch('complete') });
      return;
    }
    if (url.pathname.endsWith('/batches') && route.request().method() === 'POST') {
      createBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: batch('running') });
      return;
    }
    latestBatch = batch('review');
    await route.fulfill({ json: latestBatch });
  });
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await page.getByLabel('Data scope', { exact: true }).selectOption(run);
  const importer = page.locator('#atlas-auto-import');
  await importer.getByLabel('Select all filtered').check();
  await importer.getByLabel('Select Income for Alpha', { exact: true }).uncheck();
  await expect(importer.locator('[data-auto-import-selection-summary]')).toHaveText(
    '1 selected · 2,000 population',
  );
  await importer.getByLabel('Select Income for Alpha', { exact: true }).check();
  await importer.getByRole('button', { name: 'Start selected auto-import' }).click();
  const review = importer.getByRole('region', { name: 'Review before promotion' });
  await expect(review).toContainText('2 / 2');
  await expect(review).toContainText('measured');
  await expect(review).toContainText('estimated');
  await expect(review.getByText('2 mapped')).toHaveCount(2);
  await page.reload();
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await page.getByLabel('Data scope', { exact: true }).selectOption(run);
  await expect(review).toContainText('2 / 2');
  await expect(review).toContainText('estimated');
  await review
    .getByLabel('I reviewed the proposed mappings. Unknown values remain blocked from promotion.')
    .check();
  await review
    .getByLabel(
      `I confirm these distributions can be added to run ${run.slice(0, 8)} and remain scoped to that run.`,
    )
    .check();
  await review.getByRole('button', { name: 'Promote all eligible' }).click();
  await expect(review).toContainText('2 / 2');
  expect(createBody).toMatchObject({
    scope: run,
    concurrency: 4,
    selection: {
      mode: 'all_filtered',
      query: { city_population_threshold: 1_000_000, priority: 'primary' },
    },
  });
  expect(promoteBody).toMatchObject({
    mode: 'all_eligible',
    mapping_confirmed: true,
    redistribution_confirmed: true,
  });
});
