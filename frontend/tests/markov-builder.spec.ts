import { expect, test } from '@playwright/test';

test('natural-language chain stays reviewable until explicit confirmation saves it to the DSL', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/');
  await page.getByRole('tab', { name: 'DSL', exact: true }).click();
  const builder = page.locator('#markov-chain-builder');
  await expect(builder.getByRole('heading', { name: 'Describe a decision' })).toBeVisible();
  await builder.getByLabel('What should happen?').fill(
    'Decision -> Stay home [terminal] | 60% if weekend; ' +
      'Decision -> Go out [terminal] | 40% if weekend',
  );
  await builder.getByLabel('Use the configured model when available').uncheck();
  await builder.getByRole('button', { name: 'Propose chain' }).click();

  await expect(builder.getByLabel('Markov chain graph preview')).toBeVisible();
  await expect(builder).toContainText('Outgoing 100%');
  await expect(builder).toContainText('2 terminal states');
  await builder.getByLabel('Chain id').fill('weekend_choice');
  await builder.getByLabel('Chain id').press('Tab');
  const confirm = builder.getByRole('button', { name: 'Confirm and save to DSL' });
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect(builder).toContainText('Saved to this DSL');
  await expect(page.getByLabel('DSL JSON')).toHaveValue(/markov_chain_drafts/);
  await expect(page.getByLabel('DSL JSON')).toHaveValue(/weekend_choice/);
  expect(errors).toEqual([]);
});
