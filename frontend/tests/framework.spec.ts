import { expect, test } from '@playwright/test';

test('validate a DSL, run it, drill from place to agents, and open an exact story', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'DSL', exact: true }).click();
  await expect(page.getByText('✓ Valid DSL')).toBeVisible();
  await page.getByRole('button', { name: 'Add eye colour' }).click();
  await expect(page.getByText('LABEL-ONLY', { exact: true })).toBeVisible();
  await expect(page.getByText(/cannot predict an action/i)).toBeVisible();
  await page.getByRole('button', { name: 'Run validated DSL' }).click();
  await expect(page.getByText('✓ Run complete')).toBeVisible();
  await expect(page.locator('#run-list')).toContainText('Smoke Spread');
  await expect(page.locator('#record-count')).toHaveText('8 DAYS RECORDED');
  await page.locator('[data-place="Northport"]').click();
  await expect(page.locator('#agent-lod-status')).toContainText('representative synthetic agents');
  await page.getByRole('tab', { name: 'Stories', exact: true }).click();
  await page.locator('[data-story-id]').first().click();
  await expect(page.locator('#story-reader')).toContainText('Cause receipt');
  await page.locator('[data-story-agent]').first().click();
  await expect(page.getByRole('dialog', { name: /Synthetic agent/ })).toBeVisible();
  await expect(page.locator('#agent-content')).toContainText('Current states');
  await page.getByRole('button', { name: 'Return to globe' }).click();
  expect(errors).toEqual([]);
});
