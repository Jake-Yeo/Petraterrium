import { expect, test } from '@playwright/test';

test('validate a DSL, run it, drill from place to agents, and open an exact story', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'DSL', exact: true }).click();
  await expect(page.getByText('✓ Valid DSL')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Manage agent features' })).toBeVisible();
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
  await page
    .getByRole('dialog', { name: /Synthetic agent/ })
    .getByRole('button', { name: 'Open decision path' })
    .click();
  await expect(page.getByRole('heading', { name: 'Decision graph' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Recorded run' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('.decision-node')).toHaveCount(5);
  await expect(page.locator('.decision-path')).toBeVisible();
  expect(errors).toEqual([]);
});

test('static graph and evidence layers open without a completed run', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('tab', { name: 'Graph', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Decision graph' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Static DSL' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('.decision-node')).toHaveCount(5);
  await expect(page.locator('#decision-canvas')).toContainText('scroll');
  await page.getByRole('tab', { name: 'DSL', exact: true }).click();
  await expect(page.locator('#dsl-features')).toContainText('openness');
  await expect(page.locator('#dsl-features')).toContainText('mbti');
  await expect(page.locator('#dsl-features')).not.toContainText('blood_type');
  await expect(page.locator('#dsl-features')).toContainText('LABEL-ONLY');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await expect(page.locator('#atlas-feature-catalog')).toContainText('Features and evidence');
  await expect(page.locator('#atlas-feature-catalog')).toContainText('Age');
  await expect(page.locator('#atlas-feature-catalog')).not.toContainText('Age band');
  await expect(page.locator('#atlas-auto-import')).toContainText('What needs importing');
  await expect(page.locator('#atlas-hierarchy-browser')).toContainText('Europe');
  await expect(page.locator('#atlas-choice-evidence')).toContainText('hint only');
  await expect(page.locator('#atlas-choice-evidence')).toContainText('No coefficient');
  expect(errors).toEqual([]);
});
