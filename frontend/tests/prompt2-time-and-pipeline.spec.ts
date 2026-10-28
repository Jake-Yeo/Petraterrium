import { expect, test } from '@playwright/test';

test('selected agent time view shows sampled durations, evidence, remaining time, and exact totals', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { AgentTimeAccountingView } =
      await import('/src/simulation/agent-time-accounting-view.ts');
    const host = document.createElement('section');
    host.id = 'time-accounting-host';
    document.body.replaceChildren(host);
    const duration = {
      min_hours: 7,
      median_hours: 8,
      max_hours: 9,
      shape: 'triangular' as const,
      shape_parameters: {},
      evidence: {
        status: 'measured' as const,
        source: 'ATUS sleep episodes',
        sourceVersion: '2025',
        sourceDate: '2025-01-01',
        uncertainty: 0.08,
      },
    };
    new AgentTimeAccountingView(host, {
      agent_id: 'agent-42',
      agent_label: 'Agent 42',
      days: [
        {
          day: 1,
          date: '2026-10-27',
          category_hours: { Sleep: 8, Work: 8, Commute: 1, Eat: 2, Social: 2, Idle: 3 },
          ticks: [
            {
              tick: 1,
              day: 1,
              start_hour: 0,
              tick_hours: 1,
              interruptions: [
                {
                  interrupted_action: 'Work',
                  interrupting_action: 'Emergency care',
                  remaining_hours: 2.5,
                  outcome: 'defer',
                },
              ],
              actions: [
                {
                  occurrence_id: 'sleep-1',
                  action_id: 'sleep',
                  action_name: 'Sleep',
                  category: 'Sleep',
                  mode: 'primary',
                  duration,
                  sampled_duration_hours: 8,
                  hours_in_tick: 1,
                  remaining_duration_hours: 7,
                  continuing_to_next_tick: true,
                  interrupted: false,
                },
                {
                  occurrence_id: 'music-1',
                  action_id: 'listen-music',
                  action_name: 'Listen to music',
                  category: 'Media',
                  mode: 'passive',
                  duration: {
                    ...duration,
                    min_hours: 0.1,
                    median_hours: 0.5,
                    max_hours: 1,
                  },
                  sampled_duration_hours: 0.6,
                  hours_in_tick: 0,
                  remaining_duration_hours: 0,
                  continuing_to_next_tick: false,
                  interrupted: false,
                },
              ],
            },
            {
              tick: 2,
              day: 1,
              start_hour: 1,
              tick_hours: 1,
              actions: [
                {
                  occurrence_id: 'snack-1',
                  action_id: 'snack',
                  action_name: 'Eat a snack',
                  category: 'Eat',
                  mode: 'primary',
                  duration: { ...duration, min_hours: 0.2, median_hours: 0.3, max_hours: 0.4 },
                  sampled_duration_hours: 0.4,
                  hours_in_tick: 0.4,
                  remaining_duration_hours: 0,
                  continuing_to_next_tick: false,
                  interrupted: false,
                },
                {
                  occurrence_id: 'gym-1',
                  action_id: 'gym',
                  action_name: 'Go to the gym',
                  category: 'Exercise',
                  mode: 'primary',
                  duration: { ...duration, min_hours: 0.8, median_hours: 1, max_hours: 1.2 },
                  sampled_duration_hours: 1,
                  hours_in_tick: 1,
                  remaining_duration_hours: 0,
                  continuing_to_next_tick: false,
                  interrupted: false,
                },
              ],
            },
          ],
        },
      ],
    });
  });

  const view = page.locator('#time-accounting-host');
  await expect(view).toContainText('Tick budget');
  await expect(view).toContainText('Sampled occurrence');
  await expect(view).toContainText('8 h');
  await expect(view).toContainText('Continues · 7 h remaining');
  await expect(view).toContainText('ATUS sleep episodes');
  await expect(view).toContainText('passive');
  await expect(view).toContainText('24 / 24 h');
  await expect(view).toContainText('Recorded categories sum to exactly 24 hours.');
  await expect(view.getByLabel('Recorded interruptions')).toContainText(
    'Work interrupted by Emergency care',
  );
  await expect(view.getByLabel('Recorded interruptions')).toContainText('2.5 h remaining');

  await view.locator('select[name="time-accounting-tick"]').selectOption('2');
  await expect(view.getByRole('alert')).toContainText('Tick rejected');
  await expect(view.getByRole('alert')).toContainText('Go to the gym');
  await expect(view).toContainText('1.4 h');
});

test('cached pipeline inspector exposes research, version diff, and confirmed restore', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { CachedPipelineDefaultInspector } =
      await import('/src/simulation/cached-pipeline-default-inspector.ts');
    const host = document.createElement('section');
    host.id = 'pipeline-inspector-host';
    document.body.replaceChildren(host);
    const base = {
      searchLog: [
        {
          id: 'search-1',
          place: 'China',
          field: 'sleep duration',
          sourceTitle: '中国时间利用调查',
          sourceUrl: 'https://example.test/china-time-use',
          sourceTier: 'official',
          language: 'Chinese',
          engine: 'Baidu',
          searchedAt: '2026-10-27',
          result: 'Candidate distribution found',
        },
      ],
      candidates: [
        {
          id: 'candidate-1',
          place: 'China',
          field: 'sleep duration',
          sourceTitle: '中国时间利用调查',
          sourceType: 'measured' as const,
          summary: 'Weighted time-use episodes by age.',
          accepted: true,
        },
      ],
      chosenResults: [
        {
          id: 'chosen-1',
          place: 'China',
          field: 'sleep duration',
          unit: 'hours per occurrence',
          denominator: 'adult residents',
          sourceTitle: '中国时间利用调查',
          sourceType: 'measured' as const,
          sourceDate: '2025-01-01',
          values: [
            { value: '7–8 hours', probability: 0.6 },
            { value: '8–9 hours', probability: 0.4 },
          ],
          reasoning: 'Weighted survey episodes were harmonized to the DSL range.',
          assumptions: ['Survey weekday weights apply to the baseline schedule.'],
          uncertainty: '95% interval retained from the survey extract.',
          provenance: 'Pipeline run pipeline-v2, mapping duration-v1.',
        },
      ],
    };
    new CachedPipelineDefaultInspector(host, {
      selectedVersionId: 'pipeline-v2',
      versions: [
        {
          id: 'pipeline-v1',
          label: 'Pipeline v1',
          createdAt: '2026-10-20',
          isDefault: false,
          ...base,
          defaultSnapshot: {
            hash: 'snapshot-hash-v1',
            distributionCount: 10,
            stateCount: 4,
            initialAgentCount: 1000,
          },
        },
        {
          id: 'pipeline-v2',
          label: 'Pipeline v2',
          createdAt: '2026-10-27',
          isDefault: true,
          ...base,
          defaultSnapshot: {
            hash: 'snapshot-hash-v2',
            distributionCount: 12,
            stateCount: 4,
            initialAgentCount: 1000,
          },
          diffFromPrevious: {
            researchedDataChanges: ['Added the 2025 Chinese time-use release.'],
            chosenDataChanges: ['Sleep median changed from 7.8 to 8.0 hours.'],
            reason: 'The newer official survey supersedes the earlier estimate.',
          },
        },
      ],
      onRestore: (versionId) => {
        document.body.dataset.restoredPipeline = versionId;
      },
    });
  });

  const inspector = page.locator('#pipeline-inspector-host');
  await expect(inspector).toContainText('Added the 2025 Chinese time-use release.');
  await expect(inspector).toContainText('Sleep median changed from 7.8 to 8.0 hours.');
  await expect(inspector).toContainText('measured');
  await expect(inspector).toContainText('Weighted survey episodes were harmonized');
  await inspector.getByText('Final chosen data').click();
  await expect(inspector.getByText('中国时间利用调查').first()).toBeVisible();

  await inspector.getByText('Full search log (1)').click();
  await expect(inspector).toContainText('Chinese');
  await expect(inspector).toContainText('Baidu');

  await inspector
    .getByRole('button', { name: 'Restore default from cached pipeline result' })
    .click();
  const dialog = inspector.getByRole('alertdialog');
  await expect(dialog).toContainText('Research will not run again.');
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.locator('body')).toHaveAttribute('data-restored-pipeline', 'pipeline-v2');
});
