import { expect, test } from '@playwright/test';

test('natural-language decision tree stays reviewable until explicit confirmation', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/');
  await page
    .getByRole('tablist', { name: 'Simulation sections' })
    .getByRole('tab', { name: 'Decision Trees', exact: true })
    .click();
  await page
    .getByRole('tablist', { name: 'Decision tree sections' })
    .getByRole('tab', { name: 'Build a tree', exact: true })
    .click();
  const builder = page.locator('[data-decision-tree-builder]');
  await expect(builder.getByRole('heading', { name: 'Describe a decision' })).toBeVisible();
  await builder
    .getByLabel('What should happen?')
    .fill(
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
  await builder.getByLabel('Name').fill('Weekend choice');
  await builder.getByLabel('Name').press('Tab');
  const confirm = builder.getByRole('button', { name: 'Confirm and save decision tree' });
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect(builder).toContainText('Decision tree saved');
  await page
    .getByRole('tablist', { name: 'Decision tree sections' })
    .getByRole('tab', { name: 'Browse trees', exact: true })
    .click();
  await expect(page.locator('[data-decision-tree-browser]')).toContainText('Weekend choice');
  expect(errors).toEqual([]);
});
