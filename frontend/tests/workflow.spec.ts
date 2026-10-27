import { test, expect } from '@playwright/test';

test('global new experiment opens the Rust Simulation run workflow', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();

  await page.getByRole('button', { name: 'New experiment' }).click();

  await expect(page.getByRole('tab', { name: 'Simulation', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('tab', { name: 'Run Simulation', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.locator('#rust-run-panel')).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Set the world in motion.' })).not.toBeVisible();
  await expect(page.getByText('Recorded compatibility runs', { exact: true })).not.toBeVisible();
  await expect(page.getByText('Pandemic', { exact: true })).not.toBeVisible();
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
        ensemble: (_update, sequence) => {
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
  expect(received.sequences).toEqual([4, 5, 6, 7, 8, 9]);
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
        ensemble: (_update, sequence) => {
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
  expect(result.sequences).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  expect(result.reconnects).toBeGreaterThanOrEqual(1);
  expect(resumeCursors).toEqual(['3', '3']);
});
