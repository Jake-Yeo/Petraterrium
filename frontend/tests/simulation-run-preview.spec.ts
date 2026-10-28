import { expect, test } from '@playwright/test';

test('launch preview shows DSL identity and coefficient evidence before a run exists', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationLaunchEvidencePreview } = await import(
      '/src/simulation/run-launch-preview.ts'
    );
    const host = document.createElement('section');
    host.id = 'run-launch-preview-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 1000,
      seed: 1,
      days: 30,
      tick_interval_hours: 24,
      start_date: '2026-10-27',
      place_scope: { level: 'country' as const, identifier: 'CA' },
      agent_type_mix: { person: 1 },
    };
    const preview = {
      config,
      agent_count: 1000,
      total_ticks: 30,
      data_version: 'population-v1:abc123',
      program_version: 'program-v1',
      default_dsl_version: 'base-1.0.0',
      default_dsl_hash: `sha256:${'a'.repeat(64)}`,
      evidence_summary: {
        fitted_count: 1,
        default_estimated_count: 1,
        blocked_count: 0,
        by_action_place: [
          {
            action_id: 'exercise',
            place: {
              level: 'country' as const,
              place_id: 'CA',
              region_id: 'Northern America',
              country_id: 'CA',
              city_id: null,
            },
            fitted_count: 1,
            default_estimated_count: 1,
            blocked_count: 0,
            coefficients: [
              {
                action_id: 'exercise',
                edge_id: 'go-to-gym',
                place: {
                  level: 'country' as const,
                  place_id: 'CA',
                  region_id: 'Northern America',
                  country_id: 'CA',
                  city_id: null,
                },
                source_place: null,
                resolution_status: 'direct' as const,
                evidence_state: 'default_estimated' as const,
                value: 0.22,
                interval: { low: 0.08, high: 0.45 },
                coefficient_set_id: 'exercise-default-ca',
                default_coefficient_set_id: 'exercise-default-ca',
                default_value: 0.22,
                fitted_delta: null,
                promotion_id: null,
                source_label: 'Shipped default DSL',
                source_version: 'base-1.0.0',
                source_id: null,
                default_reason: 'Executable starting estimate pending linked outcome data.',
                held_out: null,
                affected_agents: 1000,
              },
              {
                action_id: 'exercise',
                edge_id: 'stay-home',
                place: {
                  level: 'country' as const,
                  place_id: 'CA',
                  region_id: 'Northern America',
                  country_id: 'CA',
                  city_id: null,
                },
                source_place: null,
                resolution_status: 'direct' as const,
                evidence_state: 'fitted' as const,
                value: 0.61,
                interval: { low: 0.55, high: 0.67 },
                coefficient_set_id: 'exercise-fitted-ca',
                default_coefficient_set_id: 'exercise-default-ca',
                default_value: 0.48,
                fitted_delta: 0.13,
                promotion_id: 'promotion-exercise-ca',
                source_label: 'Canadian time-use evidence',
                source_version: '2025',
                source_id: 'time-use-ca',
                default_reason: null,
                held_out: { held_out_rows: 800, fitted_score: 0.39, default_score: 0.52 },
                affected_agents: 1000,
              },
            ],
          },
        ],
      },
      evidence_warnings: [
        {
          code: 'default_estimated_coefficients' as const,
          action_id: 'exercise',
          place: {
            level: 'country' as const,
            place_id: 'CA',
            region_id: 'Northern America',
            country_id: 'CA',
            city_id: null,
          },
          coefficient_ids: ['go-to-gym'],
          message: 'Exercise at CA uses 1 default/estimated coefficient.',
        },
      ],
    };
    const client = {
      preview: async (received: typeof config) => {
        (window as unknown as { previewConfig: typeof config }).previewConfig = received;
        return preview;
      },
    };
    const view = new SimulationLaunchEvidencePreview(host, client);
    await view.load(config);
  });

  const view = page.getByRole('region', { name: 'Simulation launch evidence' });
  await expect(view).toContainText('Review before launch');
  await expect(view).toContainText('1,000 agents · 30 ticks');
  await expect(view).toContainText('Default DSL base-1.0.0');
  await expect(view).toContainText('1 default / estimated');
  await expect(view).toContainText('1 fitted');
  await expect(view).toContainText('48% → 61%');
  await expect(view).toContainText('Exercise at CA uses 1 default/estimated coefficient.');
  expect(await page.evaluate(() => (window as unknown as { previewConfig: unknown }).previewConfig)).toEqual(
    {
      population_size: 1000,
      seed: 1,
      days: 30,
      tick_interval_hours: 24,
      start_date: '2026-10-27',
      place_scope: { level: 'country', identifier: 'CA' },
      agent_type_mix: { person: 1 },
    },
  );
});
