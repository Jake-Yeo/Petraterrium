import { expect, test } from '@playwright/test';

test('six global agent type controls gate launch and never expose a raw mix field', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { AgentTypeMixControl } = await import('/src/simulation/agent-type-mix-control.ts');
    const host = document.createElement('section');
    host.id = 'mix-host';
    const launch = document.createElement('button');
    launch.id = 'launch-control';
    launch.textContent = 'Launch';
    document.body.replaceChildren(host, launch);
    new AgentTypeMixControl(host, {
      onChange: (state) => {
        launch.disabled = !state.valid;
        launch.dataset.total = String(state.total);
      },
    });
  });

  const host = page.locator('#mix-host');
  await expect(host.getByRole('slider')).toHaveCount(6);
  await expect(host.getByRole('spinbutton')).toHaveCount(6);
  await expect(host.locator('textarea')).toHaveCount(0);
  await expect(host).toContainText('Mix is valid');
  await expect(page.locator('#launch-control')).toBeEnabled();

  await host.getByRole('spinbutton', { name: 'Person share' }).fill('0.25');
  await host.getByRole('spinbutton', { name: 'Person share' }).press('Tab');
  await expect(host).toContainText('Mix totals 105%');
  await expect(page.locator('#launch-control')).toBeDisabled();

  await host.getByRole('spinbutton', { name: 'Caregiver share' }).fill('0.05');
  await host.getByRole('spinbutton', { name: 'Caregiver share' }).press('Tab');
  await expect(host).toContainText('Mix is valid');
  await expect(page.locator('#launch-control')).toBeEnabled();
});

test('saved runs explain status and launch policy while keeping hashes behind details', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SavedRunStatusList } = await import('/src/simulation/saved-run-status-list.ts');
    const host = document.createElement('section');
    host.id = 'saved-runs-host';
    document.body.replaceChildren(host);
    new SavedRunStatusList(host, {
      launchPolicy: 'queue',
      runs: [
        {
          id: 'completed-run-1',
          name: 'Global baseline',
          status: 'completed',
          progress: 1,
          completedTicks: 720,
          totalTicks: 720,
          populationSize: 1000,
          days: 30,
          hashes: {
            protocol: 'protocol-hash-1',
            program: 'program-hash-1',
            dsl: 'dsl-hash-1',
            input: 'input-hash-1',
            output: 'output-hash-1',
          },
        },
        {
          id: 'running-run-2',
          status: 'running',
          progress: 0.25,
          completedTicks: 180,
          totalTicks: 720,
          populationSize: 1000,
          days: 30,
          hashes: {},
        },
      ],
      onOpen: (runId) => {
        document.body.dataset.openedRun = runId;
      },
    });
  });

  const host = page.locator('#saved-runs-host');
  await expect(host).toContainText(
    'Starting another run while one is running adds the new run to the queue.',
  );
  await expect(host).toContainText('Finished. Its recorded output can be opened and inspected.');
  await expect(host).toContainText(
    'Still executing. Progress is live and its recorded output is not final.',
  );
  await expect(host.getByText('protocol-hash-1')).not.toBeVisible();

  await host.getByText('Details and reproducibility hashes').first().click();
  await expect(host.getByText('protocol-hash-1')).toBeVisible();
  await expect(host).toContainText('The exact editable simulation definition used for this run.');
  await host.getByRole('button', { name: 'Open run completed-run-1' }).click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-run', 'completed-run-1');
});
