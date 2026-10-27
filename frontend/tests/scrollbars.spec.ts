import { expect, test } from '@playwright/test';

const installScrollableSurfaces = async (
  page: Parameters<typeof test>[0]['page'],
): Promise<void> => {
  await page.evaluate(() => {
    const fixture = document.createElement('div');
    fixture.innerHTML = `
      <main data-scrollbar-surface><span></span></main>
      <aside data-scrollbar-surface><span></span></aside>
      <dialog open data-scrollbar-surface><span></span></dialog>
      <details open data-scrollbar-surface><summary>Details</summary><span></span></details>
      <div class="atlas-dialog">
        <select data-scrollbar-surface size="2"><option>One</option><option>Two</option><option>Three</option></select>
      </div>
    `;
    fixture.querySelectorAll<HTMLElement>('[data-scrollbar-surface]').forEach((surface) => {
      surface.style.width = '80px';
      surface.style.height = '40px';
      surface.style.overflow = 'scroll';
      const content = surface.querySelector<HTMLElement>('span');
      if (content) {
        content.style.display = 'block';
        content.style.width = '160px';
        content.style.height = '80px';
      }
    });
    document.body.append(fixture);
  });
};

const scrollbarStyles = async (page: Parameters<typeof test>[0]['page']) =>
  page.locator('[data-scrollbar-surface]').evaluateAll((surfaces) =>
    surfaces.map((surface) => {
      const style = getComputedStyle(surface);
      const thumb = getComputedStyle(surface, '::-webkit-scrollbar-thumb');
      const track = getComputedStyle(surface, '::-webkit-scrollbar-track');
      const corner = getComputedStyle(surface, '::-webkit-scrollbar-corner');
      return {
        colorScheme: style.colorScheme,
        scrollbarColor: style.scrollbarColor,
        scrollbarWidth: style.scrollbarWidth,
        thumb: thumb.backgroundColor,
        track: track.backgroundColor,
        corner: corner.backgroundColor,
      };
    }),
  );

test('all scrollable surfaces share themed dark and light scrollbar treatments', async ({
  page,
}) => {
  await page.goto('/');
  await installScrollableSurfaces(page);

  const dark = await scrollbarStyles(page);
  for (const style of dark) {
    expect(style.colorScheme).toContain('dark');
    expect(style.scrollbarColor).not.toBe('auto');
    expect(style.scrollbarWidth).toBe('thin');
    expect(style.thumb).not.toBe('rgba(0, 0, 0, 0)');
    expect(style.track).not.toBe('rgba(0, 0, 0, 0)');
    expect(style.corner).not.toBe('rgba(0, 0, 0, 0)');
  }

  await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light';
  });
  const light = await scrollbarStyles(page);
  for (const [index, style] of light.entries()) {
    expect(style.colorScheme).toContain('light');
    expect(style.scrollbarColor).not.toBe('auto');
    expect(style.scrollbarWidth).toBe('thin');
    expect(style.thumb).not.toBe(dark[index].thumb);
    expect(style.track).not.toBe(dark[index].track);
    expect(style.corner).toBe(style.track);
  }

  const hoverRule = await page.evaluate(() =>
    [...document.styleSheets].some((sheet) =>
      [...sheet.cssRules].some((rule) => rule.cssText.includes('::-webkit-scrollbar-thumb:hover')),
    ),
  );
  expect(hoverRule).toBeTruthy();
});
