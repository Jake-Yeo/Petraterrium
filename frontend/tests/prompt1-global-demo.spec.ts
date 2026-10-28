import { expect, test } from '@playwright/test';

const countryAgentCounts = {
  India: 307,
  China: 304,
  'United States': 73,
  Indonesia: 60,
  Pakistan: 53,
  Nigeria: 49,
  Brazil: 45,
  Bangladesh: 36,
  Russia: 31,
  Mexico: 28,
  Canada: 8,
  Australia: 6,
};

const regionAgentCounts = {
  India: 307,
  China: 304,
  'Asia excluding China and India': 149,
  'Northern America': 81,
  'Latin America and the Caribbean': 73,
  Africa: 49,
  Europe: 31,
  Oceania: 6,
};

const countryCodes: Record<string, string> = {
  Australia: 'AU',
  Bangladesh: 'BD',
  Brazil: 'BR',
  Canada: 'CA',
  China: 'CN',
  India: 'IN',
  Indonesia: 'ID',
  Mexico: 'MX',
  Nigeria: 'NG',
  Pakistan: 'PK',
  Russia: 'RU',
  'United States': 'US',
};

const representedCountries = Object.keys(countryAgentCounts);

const ownCountryEvidence = (source: string, version: string) =>
  representedCountries.map((country) => ({
    country,
    country_code: countryCodes[country],
    status: 'own_country_inherited',
    source,
    source_place: countryCodes[country],
    source_level: 'country',
    source_version: version,
  }));

const countryMeasuredField = (source: string, version: string) => ({
  measured: [],
  own_country_inherited: representedCountries,
  regional_imputed: [],
  estimated: [],
  place_evidence: ownCountryEvidence(source, version),
});

const financeEvidence = representedCountries.map((country) => ({
  country,
  country_code: countryCodes[country],
  status: 'own_country_inherited',
  source:
    country === 'Canada'
      ? 'Statistics Canada financial survey'
      : 'World Bank World Development Indicators',
  source_place: countryCodes[country],
  source_level: 'country',
  source_version: country === 'Canada' ? '2023' : '2026-10-08',
}));

const financeField = {
  measured: [],
  own_country_inherited: representedCountries,
  regional_imputed: [],
  estimated: [],
  place_evidence: financeEvidence,
};

const distribution = (
  fieldId: string,
  label: string,
  summary: string,
  source: string,
  sourcePlace: string,
  count: number,
) => ({
  field_id: fieldId,
  label,
  summary,
  evidence_status: 'own_country_inherited',
  source,
  source_place: sourcePlace,
  bins: [
    { label: '0–17', percentage: 24.6, estimated_agents: Math.round(count * 0.246) },
    { label: '18–64', percentage: 65.1, estimated_agents: Math.round(count * 0.651) },
    { label: '65+', percentage: 10.3, estimated_agents: Math.round(count * 0.103) },
  ],
});

const countryComparisons = Object.entries(countryAgentCounts).map(([country, count]) => ({
  comparison_id: `country-${countryCodes[country].toLowerCase()}`,
  level: 'country',
  place: country,
  agent_count: count,
  distributions: [
    distribution(
      'age',
      'Age',
      country === 'China' ? 'China-specific age bands' : `${country}-specific age bands`,
      'UN World Population Prospects',
      countryCodes[country],
      count,
    ),
  ],
}));

const regionComparisons = Object.entries(regionAgentCounts).map(([region, count]) => ({
  comparison_id: `region-${region.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}`,
  level: 'region',
  place: region,
  agent_count: count,
  distributions: [
    distribution(
      'age',
      'Age',
      `${region} population-weighted age bands`,
      'UN World Population Prospects country aggregation',
      region,
      count,
    ),
  ],
}));

const globalSummary = {
  total_agents: 1_000,
  country_agent_counts: countryAgentCounts,
  region_agent_counts: regionAgentCounts,
  fields: {
    age: countryMeasuredField('UN World Population Prospects', '2024'),
    sex: countryMeasuredField('UN World Population Prospects', '2024'),
    education: {
      measured: [],
      own_country_inherited: representedCountries.filter((country) => country !== 'Brazil'),
      regional_imputed: ['Brazil'],
      estimated: [],
      place_evidence: representedCountries.map((country) =>
        country === 'Brazil'
          ? {
              country,
              country_code: 'BR',
              status: 'regional_imputed',
              source: 'Latin America education archetype',
              source_place: 'Latin America and the Caribbean',
              source_level: 'region',
              source_version: '2026-10-08',
            }
          : {
              country,
              country_code: countryCodes[country],
              status: 'own_country_inherited',
              source: 'World Bank World Development Indicators',
              source_place: countryCodes[country],
              source_level: 'country',
              source_version: '2026-10-08',
            },
      ),
    },
    specialization: countryMeasuredField(
      'Petraterrium specialization research pipeline',
      '2026-10-27',
    ),
    occupation: countryMeasuredField('Priority occupation registry', '2026-10-08'),
    personality: countryMeasuredField('Priority personality registry', '2026-10-08'),
    values: countryMeasuredField('Priority values registry', '2026-10-08'),
    money: financeField,
    income: financeField,
    expenses: financeField,
    wages: financeField,
    prices: financeField,
    costs: financeField,
    currency: financeField,
  },
  comparisons: [
    {
      comparison_id: 'global',
      level: 'global',
      place: 'Global population',
      agent_count: 1_000,
      distributions: [
        distribution(
          'age',
          'Age',
          'Population-weighted age bands',
          'UN World Population Prospects country aggregation',
          'Represented countries',
          1_000,
        ),
      ],
    },
    ...countryComparisons,
    ...regionComparisons,
  ],
  deviations: [
    {
      deviation_id: 'education-br',
      field: 'education',
      status: 'regional_imputed',
      places: ['Brazil'],
      reason: 'A regional education estimate was used for this build.',
      full_requirement: 'a Brazilian measured ISCED distribution with source version and date',
    },
    {
      deviation_id: 'finance-person-level',
      field: 'income',
      status: 'estimated',
      places: representedCountries.filter((country) => country !== 'Canada'),
      reason:
        'Country aggregates seed person-level synthetic finance states with wide uncertainty.',
      full_requirement: 'licensed weighted household microdata for each represented country',
    },
  ],
  interactions: {
    status: 'recorded',
    run_id: 'global-seed-1',
    participating_countries: ['China', 'India', 'Indonesia', 'United States'],
    participating_regions: ['China', 'India', 'Asia excluding China and India', 'Northern America'],
    cross_country_interactions: 42,
    cross_region_interactions: 17,
  },
} as const;

test('global demo summary exposes geographic mix, evidence, comparisons, interactions, and deviations', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async (summary) => {
    const { InitialAgentsView } = await import('/src/simulation/initial-agents.ts');
    const host = document.createElement('div');
    host.id = 'prompt1-global-demo-host';
    document.body.replaceChildren(host);
    new InitialAgentsView(host, {
      list: async (query) => ({
        items: [
          {
            agent_id: 'global-agent-cn',
            agent_types: ['person'],
            age: 31,
            sex: 'female',
            country: 'China',
            city: 'Shanghai',
            current_location: 'home:global-agent-cn',
            household_id: null,
            household_size: 1,
            family_status: 'unknown',
          },
        ],
        total: query.country === 'China' ? 304 : 1_000,
        page: 1,
        page_size: 50,
        pages: query.country === 'China' ? 7 : 20,
        facets: {
          agent_types: ['person'],
          countries: Object.keys(summary.country_agent_counts),
          cities: ['Shanghai'],
          family_statuses: ['unknown'],
        },
        evidence_summary: summary,
      }),
      detail: async () => {
        throw new Error('Detail is outside this focused summary test.');
      },
    });
  }, globalSummary);

  const view = page.locator('#prompt1-global-demo-host');
  await expect(view.getByRole('heading', { name: 'Initial agents' })).toBeVisible();
  const summary = page.getByRole('region', {
    name: 'Population, evidence, and gaps',
  });
  await expect(summary).toContainText('1,000 agents across 12 countries and 8 regions');
  await expect(summary).toContainText('India307');
  await expect(summary).toContainText('Northern America81');
  await expect(summary).toContainText('Country isolation verified');

  const coverage = summary.locator('[data-global-demo-panel="evidence"]');
  await expect(coverage).toContainText('Own-country inherited');
  await expect(coverage).toContainText('Regional-imputed');
  await expect(coverage.getByRole('row', { name: /Education/ })).toContainText('Brazil');
  const incomeRow = coverage.getByRole('row', { name: /Income/ });
  await incomeRow.getByText('Source audit · 12 places').click();
  const chinaIncomeSource = incomeRow
    .locator('.global-demo-source-audit li')
    .filter({ hasText: 'China' });
  await expect(chinaIncomeSource).toContainText('World Bank World Development Indicators');
  await expect(chinaIncomeSource).not.toContainText('Statistics Canada');

  await summary.getByRole('button', { name: 'Distributions' }).click();
  await expect(summary).toContainText('Global population');
  await expect(summary).toContainText('Population-weighted age bands');
  await summary.getByLabel('Compare distributions').selectOption('country-cn');
  await expect(summary).toContainText('China-specific age bands');
  await expect(summary).toContainText('198 agents');

  const firstSummary = await summary.elementHandle();
  await view.locator('select[name="country"]').selectOption('China');
  await expect(view.locator('.global-demo-summary')).toHaveCount(1);
  expect(await firstSummary?.evaluate((element) => element.isConnected)).toBe(false);
  await expect(view.locator('.initial-agents-heading > strong')).toHaveText('304 agents');
  await summary.getByRole('button', { name: 'Distributions' }).click();
  await expect(summary.getByLabel('Compare distributions')).toHaveValue('global');

  await summary.getByRole('button', { name: 'Deviations' }).click();
  await expect(summary).toContainText('42 cross-country · 17 cross-region interactions');
  await expect(summary).toContainText('2 registered');
  await expect(summary).toContainText('a Brazilian measured ISCED distribution');
  await expect(summary).toContainText('licensed weighted household microdata');
});

test('global demo audit rejects a single-place demo and exposes Canadian fallback leakage', async ({
  page,
}) => {
  await page.goto('/');
  const result = await page.evaluate(async (summary) => {
    const { auditGlobalDemoSummary, GlobalDemoSummaryView } =
      await import('/src/simulation/global-demo-summary.ts');
    const invalid = structuredClone(summary);
    const chinaIndex = invalid.fields.income.place_evidence.findIndex(
      (evidence) => evidence.country === 'China',
    );
    invalid.fields.income.place_evidence[chinaIndex] = {
      ...invalid.fields.income.place_evidence[chinaIndex],
      source: 'Statistics Canada financial survey',
      source_place: 'CA',
    };
    const host = document.createElement('div');
    document.body.replaceChildren(host);
    new GlobalDemoSummaryView(host, invalid);
    const singlePlace = structuredClone(summary);
    singlePlace.country_agent_counts = { Canada: 1_000 };
    singlePlace.region_agent_counts = { 'Northern America': 1_000 };
    return {
      invalidIssues: auditGlobalDemoSummary(invalid),
      singlePlaceIssues: auditGlobalDemoSummary(singlePlace),
    };
  }, globalSummary);

  expect(result.invalidIssues).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ code: 'canadian_source_leakage' }),
      expect.objectContaining({ code: 'cross_country_source' }),
    ]),
  );
  expect(result.singlePlaceIssues).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ code: 'single_country_demo' }),
      expect.objectContaining({ code: 'single_region_demo' }),
    ]),
  );
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Global demo integrity failed');
  await expect(alert).toContainText('income for China points to Canadian evidence');
});

test('completed simulation run keeps global population evidence and its controls available', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async (sourceSummary) => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const summary = structuredClone(sourceSummary);
    summary.fields.specialization = {
      measured: ['Canada'],
      own_country_inherited: Object.keys(summary.country_agent_counts).filter(
        (country) => country !== 'Canada' && country !== 'China',
      ),
      regional_imputed: [],
      estimated: ['China'],
      place_evidence: summary.fields.specialization.place_evidence?.map((evidence) => {
        if (evidence.country === 'Canada') {
          return {
            ...evidence,
            status: 'measured',
            source: 'Statistics Canada education table',
            source_place: 'CA',
          };
        }
        if (evidence.country === 'China') {
          return {
            ...evidence,
            status: 'estimated',
            source: 'China specialization research pipeline estimate',
            source_place: 'CN',
          };
        }
        return evidence;
      }),
    };
    const host = document.createElement('section');
    host.id = 'simulation-run-population-evidence-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 1_000,
      seed: 1,
      days: 30,
      tick_interval_hours: 24,
      start_date: '2026-10-27',
      place_scope: { level: 'global', identifier: null },
      agent_type_mix: { person: 1 },
    };
    const run = {
      run_id: 'global-evidence-run',
      config,
      status: 'completed',
      progress: 1,
      completed_ticks: 30,
      total_ticks: 30,
      result: {
        source: 'rust',
        protocol_version: '1',
        engine_version: '0.1.0',
        data_version: 'atlas-global-v1',
        program_version: 'default-dsl-v1',
        input_hash: 'global-input-hash',
        output_hash: 'global-output-hash',
        snapshots: [
          {
            day: 30,
            date: '2026-11-25',
            tick: 30,
            elapsed_hours: 720,
            state_counts: { 'daily / home': 1_000 },
            place_counts: summary.country_agent_counts,
            transition_counts: [],
            event_count: 0,
            interaction_count: 0,
          },
        ],
      },
      error: null,
      global_demo_summary: summary,
    };
    const client = {
      launch: async () => run,
      list: async () => [],
      get: async () => run,
      cancel: async () => run,
      delete: async () => undefined,
      agents: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
      agent: async () => {
        throw new Error('not used');
      },
      events: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    };
    new SimulationRunPanel(host, client, {
      pollIntervalMs: 60_000,
      launchPreviewClient: null,
    });
  }, globalSummary);

  const panel = page.locator('#simulation-run-population-evidence-test');
  await panel.getByRole('button', { name: 'Launch Rust simulation' }).click();
  await expect(panel.locator('.simulation-result-heading')).toContainText('Completed');

  const populationEvidence = panel.getByRole('region', {
    name: 'Population, evidence, and gaps',
  });
  await expect(populationEvidence).toContainText('1,000 agents across 12 countries and 8 regions');
  await expect(populationEvidence).toContainText('India307');
  await expect(populationEvidence).toContainText('Northern America81');
  const specialization = populationEvidence.getByRole('row', { name: /Specialization/ });
  await expect(specialization.locator('td').nth(0)).toContainText('Canada');
  await expect(specialization.locator('td').nth(3)).toContainText('China');
  await specialization.getByText('Source audit · 12 places').click();
  await expect(specialization).toContainText('Statistics Canada education table');
  await expect(specialization).toContainText('China specialization research pipeline estimate');

  await populationEvidence.getByRole('button', { name: 'Distributions' }).click();
  await expect(populationEvidence.getByLabel('Compare distributions')).toBeVisible();
  await populationEvidence.getByRole('button', { name: 'Deviations' }).click();
  await expect(populationEvidence).toContainText('Deviations and data gaps');
});
