import { expect, test } from '@playwright/test';

const previewResponse = {
  registry_version: 'coefficients-v1+promotion-ca-social-outing',
  diff: {
    promotion_id: 'promotion-ca-social-outing',
    action_id: 'social-outing',
    place: {
      level: 'country' as const,
      place_id: 'CA',
      region_id: 'Northern America',
      country_id: 'CA',
      city_id: null,
    },
    default_coefficient_set_id: 'social-outing-default-ca',
    fitted_coefficient_set_id: 'social-outing-fitted-ca',
    changes: [
      { edge_id: 'go-out', default_value: 0.45, fitted_value: 0.68 },
      { edge_id: 'stay-home', default_value: 0.55, fitted_value: 0.32 },
    ],
    provenance: {
      imported_source_id: 'statscan-time-use-2025',
      source: 'Statistics Canada General Social Survey',
      source_version: 'cycle-39',
      source_date: '2025-06-01',
      published_date: '2026-02-12',
      model_id: 42,
      model_input_traits: { age: 31, extraversion: 0.72, employed: true },
      evidence_kind: 'linked_trait_context_outcome',
    },
    held_out: {
      metric: 'log_loss' as const,
      held_out_rows: 840,
      fitted_score: 0.41,
      default_score: 0.57,
    },
    promoted_at: '2026-10-27T12:00:00Z',
  },
};

test('fitted coefficient promotion previews the exact overlay before explicit confirmation', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async (response) => {
    const { CoefficientPromotionPanel } =
      await import('/src/simulation/coefficient-promotion-panel.ts');
    const host = document.createElement('section');
    host.id = 'coefficient-promotion-test';
    document.body.replaceChildren(host);
    const calls: Array<{ operation: string; body: unknown }> = [];
    const client = {
      preview: async (candidate: unknown) => {
        calls.push({ operation: 'preview', body: candidate });
        return response;
      },
      promote: async (candidate: unknown) => {
        calls.push({ operation: 'promote', body: candidate });
        return response;
      },
    };
    (window as unknown as { promotionCalls: typeof calls }).promotionCalls = calls;
    new CoefficientPromotionPanel(host, client);
  }, previewResponse);

  const panel = page.getByRole('region', { name: 'Fitted coefficient promotion' });
  await panel.getByLabel('Imported source ID').fill('statscan-time-use-2025');
  await panel.getByLabel('Atlas model ID').fill('42');
  await panel.getByLabel('Action ID').fill('social-outing');
  await panel.getByLabel('Region ID').fill('Northern America');
  await panel.getByLabel('Country ID').fill('CA');
  await panel.getByLabel('Target edge ID').fill('go-out');
  await panel.getByLabel('Complement edge ID').fill('stay-home');
  await panel
    .getByLabel('Model input traits')
    .fill('{"age":31,"extraversion":0.72,"employed":true}');
  await panel.getByRole('button', { name: 'Preview fitted overlay' }).click();

  const review = panel.getByRole('region', { name: 'Promotion preview' });
  await expect(review).toContainText('Default → fitted overlay');
  await expect(review.getByRole('row', { name: /Go Out/ })).toContainText('45%');
  await expect(review.getByRole('row', { name: /Go Out/ })).toContainText('68%');
  await expect(review.getByRole('row', { name: /Go Out/ })).toContainText('+23 pp');
  await expect(review.getByRole('row', { name: /Stay Home/ })).toContainText('55%');
  await expect(review.getByRole('row', { name: /Stay Home/ })).toContainText('32%');
  await expect(review).toContainText('Statistics Canada General Social Survey');
  await expect(review).toContainText('cycle-39');
  await expect(review).toContainText('840');
  await expect(review).toContainText('0.41');
  await expect(review).toContainText('0.57');
  await expect(review).toContainText('statscan-time-use-2025');
  await expect(review).toContainText('social-outing-default-ca');
  await expect(review).toContainText('social-outing-fitted-ca');

  const promote = review.getByRole('button', { name: 'Promote fitted overlay' });
  await expect(promote).toBeDisabled();
  await review
    .getByLabel('I reviewed this exact default to fitted overlay and want to promote it.')
    .check();
  await expect(promote).toBeEnabled();
  await promote.click();

  await expect(review).toContainText('Fitted overlay promoted');
  await expect(review).toContainText('promotion-ca-social-outing');
  await expect(review).toContainText('coefficients-v1+promotion-ca-social-outing');
  expect(
    await page.evaluate(() => (window as unknown as { promotionCalls: unknown }).promotionCalls),
  ).toEqual([
    {
      operation: 'preview',
      body: {
        action_id: 'social-outing',
        place: {
          level: 'country',
          place_id: 'CA',
          region_id: 'Northern America',
          country_id: 'CA',
          city_id: null,
        },
        target_edge_id: 'go-out',
        complement_edge_id: 'stay-home',
        imported_source_id: 'statscan-time-use-2025',
        model_id: 42,
        model_input_traits: { age: 31, extraversion: 0.72, employed: true },
      },
    },
    {
      operation: 'promote',
      body: {
        action_id: 'social-outing',
        place: {
          level: 'country',
          place_id: 'CA',
          region_id: 'Northern America',
          country_id: 'CA',
          city_id: null,
        },
        target_edge_id: 'go-out',
        complement_edge_id: 'stay-home',
        imported_source_id: 'statscan-time-use-2025',
        model_id: 42,
        model_input_traits: { age: 31, extraversion: 0.72, employed: true },
      },
    },
  ]);
});

test('editing evidence inputs invalidates a preview and malformed traits never reach the server', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async (response) => {
    const { CoefficientPromotionPanel } =
      await import('/src/simulation/coefficient-promotion-panel.ts');
    const host = document.createElement('section');
    document.body.replaceChildren(host);
    let previews = 0;
    const client = {
      preview: async () => {
        previews += 1;
        return response;
      },
      promote: async () => response,
    };
    (window as unknown as { previewCount: () => number }).previewCount = () => previews;
    new CoefficientPromotionPanel(host, client, {
      initial: {
        importedSourceId: 'statscan-time-use-2025',
        modelId: 42,
        actionId: 'social-outing',
        regionId: 'Northern America',
        countryId: 'CA',
        targetEdgeId: 'go-out',
        complementEdgeId: 'stay-home',
        modelInputTraits: { age: 31 },
      },
    });
  }, previewResponse);

  const panel = page.getByRole('region', { name: 'Fitted coefficient promotion' });
  await panel.getByRole('button', { name: 'Preview fitted overlay' }).click();
  await expect(panel.getByRole('region', { name: 'Promotion preview' })).toBeVisible();

  await panel.getByLabel('Country ID').fill('US');
  await expect(panel).toContainText('Inputs changed. Preview the overlay again before promotion.');
  await expect(panel.getByRole('button', { name: 'Promote fitted overlay' })).toHaveCount(0);

  await panel.getByLabel('Model input traits').fill('{"age":{"minimum":18}}');
  await panel.getByRole('button', { name: 'Preview fitted overlay' }).click();
  await expect(panel.getByRole('alert')).toContainText(
    'Model input trait age must be a string, number, or boolean.',
  );
  expect(await page.evaluate(() => window.previewCount())).toBe(1);
});

test('coefficient promotion client uses the preview and confirmed promotion contracts', async ({
  page,
}) => {
  const requests: Array<{ path: string; body: unknown }> = [];
  await page.route('**/api/simulation/coefficient-evidence/promotions/preview', async (route) => {
    requests.push({
      path: new URL(route.request().url()).pathname,
      body: route.request().postDataJSON(),
    });
    await route.fulfill({ json: previewResponse });
  });
  await page.route('**/api/simulation/coefficient-evidence/promotions', async (route) => {
    requests.push({
      path: new URL(route.request().url()).pathname,
      body: route.request().postDataJSON(),
    });
    await route.fulfill({ json: previewResponse });
  });
  await page.goto('/');

  const candidate = {
    action_id: 'social-outing',
    place: {
      level: 'country' as const,
      place_id: 'CA',
      region_id: 'Northern America',
      country_id: 'CA',
      city_id: null,
    },
    target_edge_id: 'go-out',
    complement_edge_id: 'stay-home',
    imported_source_id: 'statscan-time-use-2025',
    model_id: 42,
    model_input_traits: { age: 31 },
  };
  await page.evaluate(async (input) => {
    const { createCoefficientPromotionHttpClient } =
      await import('/src/simulation/coefficient-promotion-panel.ts');
    const client = createCoefficientPromotionHttpClient();
    await client.preview(input);
    await client.promote(input);
  }, candidate);

  expect(requests).toEqual([
    {
      path: '/api/simulation/coefficient-evidence/promotions/preview',
      body: candidate,
    },
    {
      path: '/api/simulation/coefficient-evidence/promotions',
      body: { candidate, user_confirmed: true },
    },
  ]);
});
