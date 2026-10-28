import { expect, test } from '@playwright/test';

test('run launch shows default and fitted coefficient evidence by action and place', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-run-evidence-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 1000,
      seed: 1,
      days: 30,
      tick_interval_hours: 24,
      start_date: '2026-10-27',
      place_scope: { level: 'country', identifier: 'CA' },
      agent_type_mix: { person: 1 },
    };
    const run = {
      run_id: 'evidence-run',
      config,
      status: 'queued',
      progress: 0,
      completed_ticks: 0,
      total_ticks: 30,
      result: null,
      error: null,
      evidence_summary: {
        fitted_count: 1,
        default_estimated_count: 2,
        blocked_count: 0,
        by_action_place: [
          {
            action_id: 'daily-choice',
            place: {
              level: 'country',
              place_id: 'CA',
              region_id: 'Northern America',
              country_id: 'CA',
              city_id: null,
            },
            fitted_count: 1,
            default_estimated_count: 2,
            blocked_count: 0,
            coefficients: [
              {
                action_id: 'daily-choice',
                edge_id: 'go-to-gym',
                place: {
                  level: 'country',
                  place_id: 'CA',
                  region_id: 'Northern America',
                  country_id: 'CA',
                  city_id: null,
                },
                source_place: null,
                resolution_status: 'direct',
                evidence_state: 'default_estimated',
                value: 0.22,
                interval: { low: 0.08, high: 0.45 },
                coefficient_set_id: 'daily-ca',
                default_coefficient_set_id: 'daily-ca',
                default_value: 0.22,
                fitted_delta: null,
                promotion_id: null,
                source_label: 'Shipped default DSL',
                source_version: 'base-1.0.0',
                source_id: null,
                default_reason: 'Executable starting prior pending linked outcome data.',
                held_out: null,
                affected_agents: 1000,
              },
              {
                action_id: 'daily-choice',
                edge_id: 'go-out',
                place: {
                  level: 'country',
                  place_id: 'CA',
                  region_id: 'Northern America',
                  country_id: 'CA',
                  city_id: null,
                },
                source_place: null,
                resolution_status: 'direct',
                evidence_state: 'fitted',
                value: 0.64,
                interval: { low: 0.59, high: 0.69 },
                coefficient_set_id: 'fitted-ca-go-out',
                default_coefficient_set_id: 'daily-ca',
                default_value: 0.51,
                fitted_delta: 0.13,
                promotion_id: 'promotion-ca-go-out',
                source_label: 'Canadian time-use survey',
                source_version: '2025',
                source_id: 'statscan-time-use-2025',
                default_reason: null,
                held_out: { held_out_rows: 400, fitted_score: 0.42, default_score: 0.58 },
                affected_agents: 1000,
              },
            ],
          },
        ],
      },
      evidence_warnings: [
        {
          code: 'default_estimated_coefficients',
          action_id: 'daily-choice',
          place: {
            level: 'country',
            place_id: 'CA',
            region_id: 'Northern America',
            country_id: 'CA',
            city_id: null,
          },
          coefficient_ids: ['go-to-gym', 'skip-lunch'],
          message:
            'daily-choice at CA uses 2 default/estimated coefficients; inspect provenance and uncertainty.',
        },
      ],
    };
    const client = {
      launch: async () => run,
      list: async () => [],
      get: async () => run,
      cancel: async () => ({ ...run, status: 'cancelling' }),
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
  });

  const panel = page.locator('#simulation-run-evidence-test');
  await panel.getByLabel('Seed').fill('1');
  await panel.getByRole('button', { name: 'Launch Rust simulation' }).click();

  const receipt = panel.getByRole('region', { name: 'Run coefficient evidence' });
  await expect(receipt).toContainText('2 default / estimated');
  await expect(receipt).toContainText('1 fitted');
  await expect(receipt).toContainText('Daily Choice');
  await expect(receipt).toContainText('CA');
  await expect(receipt).toContainText('Go To Gym');
  await expect(receipt).toContainText('Shipped default DSL');
  await expect(receipt).toContainText('Executable starting prior');
  await expect(receipt).toContainText('51% → 64%');
  await expect(receipt).toContainText('Promotion promotion-ca-go-out');
  await expect(receipt).toContainText('400 held-out rows');
  await expect(receipt).toContainText('Canadian time-use survey');
});
