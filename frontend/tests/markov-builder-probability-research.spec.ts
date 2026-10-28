import { expect, test } from '@playwright/test';

interface ResearchRequest {
  transition_id: string;
  outcome_id: string;
  outcome_description: string;
  outcomes: Array<{ id: string; description: string }>;
  conditioning_id: string;
  place: {
    level: string;
    place_id: string;
    place_label: string;
    population: number;
    country_code: string;
    local_names: Record<string, string>;
    dominant_languages: string[];
  };
  time_unit: string;
  condition_values: Record<string, string>;
  population_basis: string;
}

const estimate = (request: ResearchRequest, probability: number) => ({
  id: `estimate-${request.transition_id}`,
  kind: 'pipeline_estimate',
  review_state: 'draft',
  pipeline_attempt_id: `attempt-${request.transition_id}`,
  outcome_id: request.outcome_id,
  conditioning_id: request.conditioning_id,
  place: request.place.place_id,
  time_unit: request.time_unit,
  predictor_values: {},
  condition_values: request.condition_values,
  probability,
  ci_low: probability === 0.6 ? 0.2 : 0.05,
  ci_high: probability === 0.6 ? 0.9 : 0.75,
  population: request.population_basis,
  sample_size: 412,
  reasoning: `The retrieved Chinese survey supports an estimated ${request.outcome_description} rate.`,
  assumptions: [
    'The survey population represents adults making this Friday decision.',
    'The wide interval reflects uncertainty when mapping the survey response to this edge.',
  ],
  method: 'source_synthesis',
  sources: [
    {
      id: `china-friday-${request.transition_id}`,
      title: '中国居民周五晚间活动调查',
      url: 'https://example.cn/friday-activity',
      source_kind: 'representative_survey',
      observation_date: '2025-06-01',
      published_date: '2025-07-12',
      retrieved_date: '2026-10-27',
      language: 'zh',
      excerpt: '调查记录了成年人周五晚间的活动选择。',
      source_version: '2025-v1',
      license: 'Publisher terms apply',
      supports_joint_outcome: false,
    },
  ],
  selected_source_ids: [`china-friday-${request.transition_id}`],
  search_log: [
    {
      sequence: 1,
      origin: 'automatic',
      language: 'zh',
      engine: 'National Bureau of Statistics of China',
      query_or_source: `中国 ${request.outcome_description} 官方统计`,
      source_kind: 'official_statistics',
      outcome: 'no_result',
      source_ids: [],
    },
    {
      sequence: 2,
      origin: 'automatic',
      language: 'zh',
      engine: 'Baidu',
      query_or_source: `中国 ${request.outcome_description} 调查`,
      source_kind: 'representative_survey',
      outcome: 'candidate',
      source_ids: [`china-friday-${request.transition_id}`],
    },
  ],
  pipeline_provider: 'openai_cli',
  pipeline_model: 'gpt-6.1-sol',
  prompt_version: 'markov-transition-research-v1',
});

test('researches unresolved edges in local context and applies only reviewed draft rates', async ({
  page,
}) => {
  const requests: ResearchRequest[] = [];
  await page.route('**/api/markov-builder/probability-research', async (route) => {
    const request = route.request().postDataJSON() as ResearchRequest;
    requests.push(request);
    const probability = request.outcome_description.includes('Stay home') ? 0.6 : 0.3;
    await route.fulfill({ json: estimate(request, probability) });
  });

  await page.goto('/');
  await page
    .getByRole('tablist', { name: 'Simulation sections' })
    .getByRole('tab', { name: 'Decision Trees', exact: true })
    .click();
  await page
    .getByRole('tablist', { name: 'Decision tree sections' })
    .getByRole('tab', { name: 'Build a tree', exact: true })
    .click();
  const builder = page.locator('[data-decision-tree-builder]');
  await builder
    .getByLabel('What should happen?')
    .fill(
      'Decision -> Stay home [terminal] | if Friday; ' +
        'Decision -> Go out [terminal] | if Friday',
    );
  await builder.getByLabel('Use the configured model when available').uncheck();
  await builder.getByRole('button', { name: 'Propose chain' }).click();

  const research = builder.getByRole('region', { name: 'Probability research' });
  await expect(research.getByRole('heading', { name: 'Research missing probabilities' })).toBeVisible();
  const runResearch = research.getByRole('button', { name: 'Research missing probabilities' });
  await expect(runResearch).toBeDisabled();
  await research.getByLabel('Place level').selectOption('country');
  await research.getByLabel('Place id').fill('CHN');
  await research.getByLabel('Place label').fill('China');
  await research.getByLabel('Country code').fill('CN');
  await research.getByLabel('Population').fill('1409000000');
  await research.getByLabel('Research languages').fill('zh, en');
  await research.getByLabel('Local labels').fill('zh=中国');
  await research.getByLabel('Time unit').selectOption('friday');
  await expect(runResearch).toBeEnabled();
  await runResearch.click();

  const receipts = research.locator('[data-probability-research-receipt]');
  await expect(receipts).toHaveCount(2);
  await expect(receipts.first()).toContainText('Estimated draft');
  await expect(receipts.first()).toContainText('60%');
  await expect(receipts.first()).toContainText('Wide CI 20%–90%');
  await expect(receipts.first()).toContainText('The retrieved Chinese survey supports');
  await expect(receipts.first()).toContainText('The survey population represents adults');
  await expect(receipts.first()).toContainText('中国居民周五晚间活动调查');
  await expect(receipts.first().getByRole('heading', { name: 'Ordered search log' })).toBeVisible();
  await expect(receipts.first()).toContainText('National Bureau of Statistics of China');
  await expect(receipts.first()).toContainText('Baidu');

  const probabilityInputs = builder.getByLabel('Transition probability');
  await expect(probabilityInputs.nth(0)).toHaveValue('');
  await expect(probabilityInputs.nth(1)).toHaveValue('');
  expect(requests).toHaveLength(2);
  expect(requests[0]?.place).toMatchObject({
    level: 'country',
    place_id: 'CHN',
    place_label: 'China',
    population: 1_409_000_000,
    country_code: 'CN',
    local_names: { zh: '中国' },
    dominant_languages: ['zh', 'en'],
  });
  expect(requests[0]?.outcomes).toHaveLength(2);
  expect(requests[0]?.time_unit).toBe('friday');

  await receipts.first().getByRole('button', { name: 'Use 60% draft' }).click();
  await expect(probabilityInputs.nth(0)).toHaveValue('0.6');
  await expect(probabilityInputs.nth(1)).toHaveValue('');
  await receipts.nth(1).getByRole('button', { name: 'Use 30% draft' }).click();
  await expect(probabilityInputs.nth(1)).toHaveValue('0.3');
  await expect(builder).toContainText('Outgoing 90%');
  await expect(builder).toContainText('sum to 0.9, not 1');
  await expect(
    builder.getByRole('button', { name: 'Confirm and save decision tree' }),
  ).toBeDisabled();
});
