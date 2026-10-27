import { expect, test } from '@playwright/test';

const measuredEvaluation = {
  decision_id: 'go_out_friday',
  edge_id: 'leave_home',
  formula_id: 'go_out_formula',
  formula_name: 'Friday social outing probability',
  expression:
    'P(Go out on Friday night) = Extraversion fit × Venue availability × Friday timing',
  agent_id: 'jp-1',
  status: 'measured',
  status_label: 'measured',
  probability: 0.27,
  ci_low: 0.18,
  ci_high: 0.38,
  fittable: true,
  source: {
    kind: 'research_paper',
    imported_source_id: 'japan-fixture-study',
    title: 'FAKE Japan Friday activity study',
    source: 'FAKE fixture journal',
    publication_date: '2024-01-01',
    population_studied: 'Adults in Japan',
    link_or_reference: 'fixture://japan-fixture-study',
    supports_decision_ids: ['go_out_friday'],
    supports_factor_ids: ['extraversion_factor', 'venue_factor', 'weekday_factor'],
  },
  factors: [
    {
      factor_id: 'extraversion_factor',
      factor_name: 'Extraversion fit',
      input_kind: 'trait',
      input_key: 'big_five_extraversion',
      evaluated_value: 'high',
      status: 'measured',
      estimate: 0.5,
      ci_low: 0.4,
      ci_high: 0.6,
      fittable: true,
      evidence_id: 'jp-extraversion',
      evidence_basis: 'measured_joint',
      evidence_place: {
        level: 'country',
        place_id: 'JP',
        region_id: 'eastern-asia',
        country_id: 'JP',
        city_id: null,
      },
      resolved_level: 'country',
      source: {
        kind: 'research_paper',
        imported_source_id: 'japan-fixture-study',
        title: 'FAKE Japan Friday activity study',
        source: 'FAKE fixture journal',
        publication_date: '2024-01-01',
        population_studied: 'Adults in Japan',
        link_or_reference: 'fixture://japan-fixture-study',
        supports_decision_ids: ['go_out_friday'],
        supports_factor_ids: ['extraversion_factor', 'venue_factor', 'weekday_factor'],
      },
      message: 'Resolved from country evidence for JP',
    },
  ],
};

const unknownEvaluation = {
  ...measuredEvaluation,
  agent_id: 'br-1',
  status: 'unknown',
  status_label: 'unknown — qualifying evidence missing',
  probability: null,
  ci_low: 0,
  ci_high: 1,
  fittable: false,
  source: {
    kind: 'none',
    label: 'no source attached — estimated / unknown',
    reason: 'No imported study supports this decision yet',
  },
  factors: [
    {
      ...measuredEvaluation.factors[0],
      status: 'unknown',
      estimate: null,
      ci_low: 0,
      ci_high: 1,
      fittable: false,
      evidence_id: null,
      evidence_basis: null,
      evidence_place: null,
      resolved_level: null,
      source: {
        kind: 'none',
        label: 'no source attached — estimated / unknown',
        reason: 'No qualifying evidence for Brazil',
      },
      message: 'No qualifying evidence for Brazil',
    },
  ],
};

test('decision evidence shows the formula, per-agent values, and source receipt', async ({
  page,
}) => {
  await page.goto('/');
  await page.addStyleTag({ url: '/src/simulation/decision-evidence.css' });
  await page.evaluate(async (evaluation) => {
    const module = await import('/src/simulation/decision-evidence.ts');
    const host = document.createElement('div');
    host.id = 'decision-evidence-test-host';
    document.body.replaceChildren(host);
    module.renderDecisionEvidence(host, evaluation);
  }, measuredEvaluation);

  const panel = page.locator('#decision-evidence-test-host');
  await expect(
    panel.getByRole('heading', { name: 'Friday social outing probability' }),
  ).toBeVisible();
  await expect(panel.locator('[data-decision-expression]')).toContainText(
    'Extraversion fit × Venue availability × Friday timing',
  );
  await expect(panel.locator('[data-decision-probability]')).toHaveText('27.0%');
  await expect(panel.locator('[data-factor-value]')).toContainText('high');
  await expect(panel.locator('[data-factor-place]')).toContainText('country · JP');
  await expect(panel.locator('[data-factor-source]')).toContainText(
    'FAKE Japan Friday activity study',
  );
  await expect(panel.locator('[data-decision-source]')).toContainText('Adults in Japan');
  await expect(panel.locator('[data-decision-fit]')).toHaveText('Predictor eligible');

  const darkBackground = await panel
    .locator('.decision-evidence')
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light';
  });
  const lightBackground = await panel
    .locator('.decision-evidence')
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(lightBackground).not.toBe(darkBackground);
});

test('unknown decisions show wide uncertainty and the exact no-source label', async ({ page }) => {
  await page.goto('/');
  await page.addStyleTag({ url: '/src/simulation/decision-evidence.css' });
  await page.evaluate(async (evaluation) => {
    const module = await import('/src/simulation/decision-evidence.ts');
    const host = document.createElement('div');
    host.id = 'decision-evidence-test-host';
    document.body.replaceChildren(host);
    module.renderDecisionEvidence(host, evaluation);
  }, unknownEvaluation);

  const panel = page.locator('#decision-evidence-test-host');
  await expect(panel.locator('[data-decision-probability]')).toHaveText('Unknown');
  await expect(panel.locator('[data-decision-interval]')).toContainText('0.0%–100.0%');
  await expect(panel.locator('[data-decision-source]')).toContainText(
    'no source attached — estimated / unknown',
  );
  await expect(panel.locator('[data-factor-source]')).toContainText(
    'no source attached — estimated / unknown',
  );
  await expect(panel.locator('[data-decision-fit]')).toHaveText('Label-only / non-fittable');
});
