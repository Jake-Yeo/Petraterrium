import { test, expect } from '@playwright/test';

test('create, inspect, play, export, reopen, cancel deletion, delete, and recover from an API error', async ({
  page,
  request,
}) => {
  const runs = await request.get('http://127.0.0.1:8011/runs');
  for (const run of (await runs.json()).runs)
    await request.delete(`http://127.0.0.1:8011/runs/${run.run_id}`);
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('API connected')).toBeVisible();
  await expect(page.getByText('No experiments yet.')).toBeVisible();
  await page.getByRole('button', { name: 'Create your first run' }).click();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'New experiment' }).click();
  await page.getByLabel('End day', { exact: true }).fill('120');
  await page.getByRole('button', { name: 'Launch experiment' }).click();
  await expect(page.getByText('✓ Run complete')).toBeVisible();
  await expect(page.locator('#record-count')).toHaveText('121 DAYS RECORDED');
  await page.getByRole('button', { name: 'Pause timeline' }).click();
  await page.locator('#timeline').evaluate((input: HTMLInputElement) => {
    input.value = '55';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await expect(page.locator('#timeline-day')).toHaveText('DAY 055');
  await page.getByRole('button', { name: 'Play timeline' }).click();
  await expect(page.locator('#timeline-day')).not.toHaveText('DAY 055');
  await page.getByRole('button', { name: 'Pause timeline' }).click();
  await page.getByText('↳ Snapshot receipt', { exact: true }).click();
  await expect(page.locator('#snapshot-table tr')).toHaveCount(4);
  await expect(page.locator('#provenance')).toContainText('FAKE-atlas');
  await expect(page.locator('#metric-population')).toHaveText('3,900,000');
  await page.getByText('Export ↓', { exact: true }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Run as JSON' }).click();
  expect((await download).suggestedFilename()).toMatch(/^petraterrium-FAKE-.*\.json$/);
  await page.getByText('Export ↓', { exact: true }).click();
  await page.screenshot({ path: 'test-results/lab-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'New experiment' }).click();
  await page.getByLabel('Random seed', { exact: true }).fill('43');
  await page.getByLabel('End day', { exact: true }).fill('30');
  await page.getByRole('button', { name: 'Launch experiment' }).click();
  await expect(page.locator('.saved-run')).toHaveCount(2);
  await expect(page.getByText('✓ Run complete')).toBeVisible();
  await page.locator('.run-open').filter({ hasText: '#42' }).click();
  await expect(page.locator('#record-count')).toHaveText('121 DAYS RECORDED');
  await page.getByRole('button', { name: 'Delete run with seed 42' }).click();
  await page.getByRole('button', { name: 'Keep run' }).click();
  await expect(page.locator('.saved-run')).toHaveCount(2);
  await page.getByRole('button', { name: 'Delete run with seed 42' }).click();
  await page.getByRole('button', { name: 'Delete run', exact: true }).click();
  await expect(page.locator('.saved-run')).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Create your first run' })).toBeVisible();
  await page.route('**/api/runs', (route) => route.abort());
  await page.getByRole('button', { name: 'Refresh saved runs' }).click();
  await expect(page.locator('#error-banner')).toContainText('Cannot reach the backend');
  await page.unroute('**/api/runs');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('#error-banner')).not.toBeVisible();
  await page.locator('.run-open').click();
  await expect(page.locator('#record-count')).toHaveText('31 DAYS RECORDED');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'New experiment' })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: 'test-results/lab-mobile.png', fullPage: true });
  expect(pageErrors).toEqual([]);
});

test('a resumed stream starts after the last received sequence', async ({ page, request }) => {
  const created = await request.post('http://127.0.0.1:8011/runs', {
    data: { countries: ['ITA'], end_day: 6, seed: 99 },
  });
  const { run_id: id } = await created.json();
  await expect
    .poll(async () => (await (await request.get(`http://127.0.0.1:8011/runs/${id}`)).json()).status)
    .toBe('done');
  await page.goto('/');
  const received = await page.evaluate(async (runId) => {
    const { RunStream } = await import('/src/api.ts');
    return new Promise<{ sequences: number[]; day: number }>((resolve, reject) => {
      const sequences: number[] = [];
      const stream = new RunStream(runId, 3, {
        snapshot: (_snapshot, sequence) => {
          sequences.push(sequence);
        },
        complete: (_event, sequence) => {
          sequences.push(sequence);
          stream.dispose();
          resolve({ sequences, day: sequence });
        },
        failed: () => reject(new Error('Unexpected failed run')),
        connection: () => {},
        error: (message) => reject(new Error(message)),
      });
    });
  }, id);
  expect(received.sequences).toEqual([4, 5, 6, 7, 8]);
});

test('an interrupted SSE connection resumes without skipping or duplicating recorded days', async ({
  page,
  request,
}) => {
  const response = await request.post('http://127.0.0.1:8011/runs', {
    data: { countries: ['ITA'], end_day: 6, seed: 101 },
  });
  const { run_id: id } = await response.json();
  await expect
    .poll(async () => (await (await request.get(`http://127.0.0.1:8011/runs/${id}`)).json()).status)
    .toBe('done');
  const recorded = await (await request.get(`http://127.0.0.1:8011/runs/${id}/stream`)).text();
  const firstThree = recorded
    .split('\n\n')
    .filter((frame) => frame.startsWith('id:'))
    .slice(0, 3)
    .join('\n\n');
  let attempts = 0;
  const resumeCursors: string[] = [];
  await page.route(`**/api/runs/${id}/stream?after=*`, async (route) => {
    attempts++;
    if (attempts > 1) resumeCursors.push(new URL(route.request().url()).searchParams.get('after')!);
    if (attempts === 1)
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: `retry: 100\n\n${firstThree}\n\n`,
      });
    else if (attempts === 2) await route.abort('connectionrefused');
    else await route.continue();
  });
  await page.goto('/');
  const result = await page.evaluate(async (runId) => {
    const { RunStream } = await import('/src/api.ts');
    return new Promise<{ sequences: number[]; reconnects: number }>((resolve, reject) => {
      const sequences: number[] = [];
      let reconnects = 0;
      const stream = new RunStream(runId, 0, {
        snapshot: (_snapshot, sequence) => {
          sequences.push(sequence);
        },
        complete: (_event, sequence) => {
          sequences.push(sequence);
          stream.dispose();
          resolve({ sequences, reconnects });
        },
        failed: () => reject(new Error('Unexpected failed run')),
        connection: (status) => {
          if (status === 'reconnecting') reconnects++;
        },
        error: (message) => reject(new Error(message)),
      });
    });
  }, id);
  expect(result.sequences).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  expect(result.reconnects).toBeGreaterThanOrEqual(1);
  expect(resumeCursors).toEqual(['3', '3']);
});
