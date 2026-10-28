import { expect, test } from '@playwright/test';

test('feature research and inheritance details use one collapsed, scrollable accordion', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/');
  await page.getByRole('tab', { name: 'Data', exact: true }).click();
  await page.getByRole('tab', { name: 'Features', exact: true }).click();
  await page
    .locator('#atlas-feature-catalog')
    .getByRole('button', { name: 'Open Age feature details' })
    .click();

  const research = page.getByRole('button', { name: 'Imported research evidence' });
  const inheritance = page.getByRole('button', {
    name: 'Agent inheritance: Place distribution and joined filters',
  });
  const researchPanel = page.locator('#feature-research-accordion-panel');
  const inheritancePanel = page.locator('#feature-inheritance-accordion-panel');

  await expect(research).toHaveAttribute('aria-expanded', 'false');
  await expect(inheritance).toHaveAttribute('aria-expanded', 'false');
  await expect(researchPanel).toBeHidden();
  await expect(inheritancePanel).toBeHidden();

  await research.focus();
  await page.keyboard.press('Enter');
  await expect(research).toHaveAttribute('aria-expanded', 'true');
  await expect(researchPanel).toBeVisible();
  await expect(research).toContainText('Research pipeline ready');
  await expect(inheritance).toHaveAttribute('aria-expanded', 'false');

  await inheritance.focus();
  await page.keyboard.press('Space');
  await expect(inheritance).toHaveAttribute('aria-expanded', 'true');
  await expect(inheritancePanel).toBeVisible();
  await expect(research).toHaveAttribute('aria-expanded', 'false');
  await expect(researchPanel).toBeHidden();
  await expect(inheritancePanel).toHaveCSS('overflow-y', 'auto');
  const placeSelect = inheritancePanel.locator('[data-joined-place]');
  await expect(placeSelect).toHaveCSS('appearance', 'none');
  expect(await placeSelect.evaluate((select) => getComputedStyle(select).backgroundColor)).not.toBe(
    'rgba(0, 0, 0, 0)',
  );
  const filters = inheritancePanel.locator('[data-joined-row]');
  await filters.nth(0).locator('[data-filter-feature]').selectOption('age');
  await filters.nth(1).locator('[data-filter-feature]').selectOption('sex');
  await expect(inheritancePanel.locator('[data-joined-result]')).toContainText(
    'independence estimate — not measured',
  );

  const darkTheme = await inheritancePanel.evaluate((panel) => {
    const select = panel.querySelector('select')!;
    return {
      selectBackground: getComputedStyle(select).backgroundColor,
      scrollbarColor: getComputedStyle(panel).scrollbarColor,
    };
  });
  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light';
  });
  const lightTheme = await inheritancePanel.evaluate((panel) => {
    const select = panel.querySelector('select')!;
    return {
      colorScheme: getComputedStyle(select).colorScheme,
      selectBackground: getComputedStyle(select).backgroundColor,
      scrollbarColor: getComputedStyle(panel).scrollbarColor,
    };
  });
  expect(lightTheme.colorScheme).toContain('light');
  expect(lightTheme.selectBackground).not.toBe(darkTheme.selectBackground);
  expect(lightTheme.scrollbarColor).not.toBe(darkTheme.scrollbarColor);

  await page.keyboard.press('Space');
  await expect(inheritance).toHaveAttribute('aria-expanded', 'false');
  await expect(inheritancePanel).toBeHidden();
  expect(errors).toEqual([]);
});
