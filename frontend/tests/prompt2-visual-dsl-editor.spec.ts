import { expect, test } from '@playwright/test';

test('visual DSL editor stages duration, state, formula, node, edge, and requirement changes before confirmation', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { VisualDslEditor } = await import('/src/simulation/visual-dsl-editor.ts');
    const host = document.createElement('section');
    host.id = 'dsl-editor-host';
    document.body.replaceChildren(host);
    new VisualDslEditor(host, {
      document: {
        schema_version: '2',
        version: 'prompt2-default-1',
        tick_hours: 1,
        actions: [
          {
            id: 'apply-for-job',
            name: 'Apply for a job',
            description: 'Submit a job application.',
            category: 'work',
            mode: 'primary',
            priority: 50,
            aggregate_statistic_id: 'job_application',
            interruptibility: 'interruptible',
            interruption_outcome: 'defer',
            emergency_interruptions: [],
            duration: {
              min_hours: 0.1,
              median_hours: 0.2,
              max_hours: 0.5,
              shape: 'triangular',
              shape_parameters: {},
              evidence: {
                status: 'measured',
                source: 'ATUS time-use extract',
                sourceVersion: '2025',
                sourceDate: '2025-01-01',
                uncertainty: 0.1,
                reasoning: 'Weighted time-use episodes.',
              },
            },
            formula: 'base_probability + stress_weight * stress',
            coefficients: [
              {
                id: 'stress-weight',
                name: 'Stress weight',
                value: 0.1,
                evidence: {
                  status: 'estimated',
                  source: 'Default structural estimate',
                  sourceVersion: '1',
                  sourceDate: '2026-10-27',
                  uncertainty: 0.5,
                  reasoning: 'Used until fitted evidence is promoted.',
                },
              },
            ],
            place_requirements: ['home or employment service'],
            time_requirements: ['awake'],
          },
        ],
        states: [
          {
            id: 'stress',
            name: 'Stress',
            min: 0,
            max: 1,
            initial: 0.4,
            decay_per_hour: 0.01,
            recovery_per_hour: 0.02,
            thresholds: [{ id: 'high', label: 'High stress', value: 0.8 }],
          },
        ],
        trees: [
          {
            id: 'job-search',
            name: 'Job search',
            entry_node: 'start',
            nodes: [
              { id: 'start', label: 'Start', kind: 'entry' },
              {
                id: 'apply',
                label: 'Apply',
                kind: 'action',
                action_id: 'apply-for-job',
              },
              { id: 'done', label: 'Done', kind: 'terminal' },
            ],
            edges: [
              {
                id: 'start-apply',
                from_node: 'start',
                to_node: 'apply',
                probability: 1,
                formula: '1',
                condition: 'is_unemployed',
                place_requirements: ['home'],
                time_requirements: ['weekday'],
              },
              {
                id: 'apply-done',
                from_node: 'apply',
                to_node: 'done',
                probability: 1,
                formula: '1',
                condition: 'always',
                place_requirements: [],
                time_requirements: [],
              },
            ],
          },
        ],
      },
      onConfirm: (document, diff) => {
        (
          window as typeof window & { confirmedDsl?: unknown; confirmedDiff?: unknown }
        ).confirmedDsl = document;
        (
          window as typeof window & { confirmedDsl?: unknown; confirmedDiff?: unknown }
        ).confirmedDiff = diff;
      },
    });
  });

  const editor = page.locator('#dsl-editor-host');
  await editor.locator('[data-dsl-field="action.duration.shape"]').selectOption('lognormal');
  await expect(editor.getByLabel('Lognormal sigma')).toBeVisible();
  await editor.getByLabel('Lognormal sigma').fill('0.45');
  await editor.getByLabel('Lognormal sigma').dispatchEvent('change');
  await expect(editor.getByLabel('Lognormal sigma')).toHaveValue('0.45');
  await editor.locator('[data-dsl-field="action.duration.shape"]').selectOption('triangular');
  await expect(editor).toContainText('Hours per sampled occurrence');
  await expect(editor.getByLabel('Source').first()).toHaveValue('ATUS time-use extract');
  await expect(editor).toContainText('No fixed durations');
  await editor.getByLabel('Median hours').fill('0.4');
  await editor.getByLabel('Median hours').press('Tab');
  await editor.getByLabel('Value').first().fill('0.2');
  await editor.getByLabel('Value').first().press('Tab');

  await editor.getByRole('tab', { name: /States/ }).click();
  await editor.getByLabel('Initial value').fill('0.5');
  await editor.getByLabel('Initial value').press('Tab');

  await editor.getByRole('tab', { name: /Trees/ }).click();
  await expect(editor.getByLabel('Decision tree preview')).toContainText('Start');
  await editor.getByLabel('Condition').first().fill('is_unemployed and weekday');
  await editor.getByLabel('Condition').first().press('Tab');
  const firstPlaceRequirements = editor
    .locator('.dsl-requirements')
    .filter({
      hasText: 'Place requirements',
    })
    .first();
  await firstPlaceRequirements.getByRole('button', { name: 'Add' }).click();
  await firstPlaceRequirements.getByLabel('Place requirements 2').fill('employment service');
  await firstPlaceRequirements.getByLabel('Place requirements 2').press('Tab');

  await expect(editor).toContainText('Valid for confirmation');
  await expect(editor).toContainText(/staged changes/);
  await editor.getByRole('button', { name: 'Review and confirm changes' }).click();
  await expect(editor.getByRole('alertdialog')).toContainText(
    'Existing runs keep their recorded definition and results.',
  );
  await editor.getByRole('button', { name: 'Confirm DSL changes' }).click();

  const confirmed = await page.evaluate(
    () =>
      (
        window as typeof window & {
          confirmedDsl?: {
            actions: Array<{
              duration: { median_hours: number };
              coefficients: Array<{ value: number }>;
            }>;
            states: Array<{ initial: number }>;
            trees: Array<{ edges: Array<{ condition: string; place_requirements: string[] }> }>;
          };
        }
      ).confirmedDsl,
  );
  expect(confirmed?.actions[0]?.duration.median_hours).toBe(0.4);
  expect(confirmed?.actions[0]?.coefficients[0]?.value).toBe(0.2);
  expect(confirmed?.states[0]?.initial).toBe(0.5);
  expect(confirmed?.trees[0]?.edges[0]?.condition).toBe('is_unemployed and weekday');
  expect(confirmed?.trees[0]?.edges[0]?.place_requirements).toContain('employment service');
});

test('visual DSL editor blocks fixed durations and invalid outgoing totals', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { VisualDslEditor } = await import('/src/simulation/visual-dsl-editor.ts');
    const host = document.createElement('section');
    host.id = 'dsl-validation-host';
    document.body.replaceChildren(host);
    new VisualDslEditor(host, {
      document: {
        schema_version: '2',
        version: 'validation-1',
        tick_hours: 1,
        actions: [
          {
            id: 'read',
            name: 'Read',
            description: '',
            category: 'leisure',
            mode: 'primary',
            priority: 10,
            aggregate_statistic_id: 'read',
            interruptibility: 'interruptible',
            interruption_outcome: 'defer',
            emergency_interruptions: [],
            duration: {
              min_hours: 0.1,
              median_hours: 0.3,
              max_hours: 0.5,
              shape: 'triangular',
              shape_parameters: {},
              evidence: {
                status: 'estimated',
                source: 'Time-use estimate',
                sourceVersion: '1',
                uncertainty: 0.5,
              },
            },
            formula: '1',
            coefficients: [],
            place_requirements: [],
            time_requirements: [],
          },
        ],
        states: [],
        trees: [
          {
            id: 'read-tree',
            name: 'Read tree',
            entry_node: 'start',
            nodes: [
              { id: 'start', label: 'Start', kind: 'entry' },
              { id: 'done', label: 'Done', kind: 'terminal' },
            ],
            edges: [
              {
                id: 'start-done',
                from_node: 'start',
                to_node: 'done',
                probability: 1,
                formula: '1',
                condition: 'always',
                place_requirements: [],
                time_requirements: [],
              },
            ],
          },
        ],
      },
      onConfirm: () => undefined,
    });
  });

  const editor = page.locator('#dsl-validation-host');
  for (const label of ['Minimum hours', 'Median hours', 'Maximum hours']) {
    await editor.getByLabel(label).fill('0.4');
    await editor.getByLabel(label).press('Tab');
  }
  await expect(editor).toContainText('A single fixed duration is invalid');
  await expect(editor.getByRole('button', { name: 'Review and confirm changes' })).toBeDisabled();

  await editor.getByRole('tab', { name: /Trees/ }).click();
  await editor.getByLabel('Probability').fill('0.8');
  await editor.getByLabel('Probability').press('Tab');
  await expect(editor).toContainText('total 0.800 instead of 1');
});
