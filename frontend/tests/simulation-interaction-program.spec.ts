import { expect, test } from '@playwright/test';

const provenance = (id: string) => ({
  source: 'Canadian General Social Survey social contact panel',
  version: '2025-v1',
  source_date: '2025-09-17',
  evidence_id: id,
  licence: 'Statistics Canada Open Licence',
  status: 'measured_joint',
  uncertainty: 0.06,
  user_approved: false,
});

const factor = (id: string, value: number) => ({
  id,
  label: id.replaceAll('-', ' '),
  value,
  provenance: provenance(id),
});

const program = {
  version: 'contact-panel-2025-v1',
  status: 'confirmed',
  relationship_evidence: [
    {
      kind: 'family',
      weight: 0.86,
      trust: 0.79,
      similarity: 0.63,
      provenance: provenance('family-profile'),
    },
  ],
  rules: [
    {
      id: 'family-conversation',
      source_action: 'return home',
      interaction_type: 'talk',
      channel: 'in_person',
      max_targets_per_initiator: 1,
      allowed_relationships: ['family'],
      allowed_place_kinds: ['home'],
      base_factor: factor('hourly-contact', 0.4),
      relationship_factors: { family: factor('family-rate', 0.9) },
      colocation_factors: { same_specific_place: factor('same-place', 1) },
      place_factors: { home: factor('home-rate', 0.8) },
      time_factors: [
        {
          weekdays: [0, 1, 2, 3, 4, 5, 6],
          start_hour: 17,
          end_hour: 23,
          factor: factor('evening-rate', 0.7),
        },
      ],
      context_factors: [],
      unrelated_relationship: null,
      agent_effects: [],
      relationship_effects: [],
      interaction_tree_id: null,
      interaction_tree_context: {},
    },
  ],
};

test('interaction program shows evidence, validates, and requires explicit confirmation', async ({
  page,
}) => {
  let confirmedPayload: unknown;
  await page.route('**/api/simulation/interaction-program**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith('/validate')) {
      const submitted = request.postDataJSON() as typeof program;
      const unknown = JSON.stringify(submitted).includes('"status":"unknown"');
      await route.fulfill({
        json: unknown
          ? {
              valid: false,
              issues: [
                {
                  path: 'rules.0.base_factor',
                  message: 'Channel baseline evidence is unknown',
                },
              ],
            }
          : { valid: true, issues: [] },
      });
      return;
    }
    if (pathname.endsWith('/confirm')) {
      confirmedPayload = request.postDataJSON();
      await route.fulfill({ json: { configured: true, program } });
      return;
    }
    await route.fulfill({ json: { configured: true, program } });
  });
  await page.goto('/');
  await page
    .getByRole('tablist', { name: 'Simulation sections' })
    .getByRole('tab', { name: 'Decision Trees', exact: true })
    .click();
  await page
    .getByRole('tablist', { name: 'Decision tree sections' })
    .getByRole('tab', { name: 'Interaction program', exact: true })
    .click();

  await expect(page.getByRole('heading', { name: 'Interaction program' })).toBeVisible();
  await expect(page.getByText('P(talk | return home)')).toBeVisible();
  await expect(page.getByText('Canadian General Social Survey social contact panel').first()).toBeVisible();
  await expect(page.getByText('2025-09-17').first()).toBeVisible();
  await expect(page.getByText('Uncertainty ±0.06').first()).toBeVisible();

  const editor = page.getByLabel('Program JSON');
  await editor.fill((await editor.inputValue()).replace('"status": "measured_joint"', '"status": "unknown"'));
  await page.getByRole('button', { name: 'Validate', exact: true }).click();
  await expect(page.getByText('Blocked reasons')).toBeVisible();
  await expect(page.getByText('Channel baseline evidence is unknown')).toBeVisible();

  await editor.fill(JSON.stringify({ ...program, status: 'draft' }, null, 2));
  await page.getByRole('button', { name: 'Validate', exact: true }).click();
  await expect(page.getByText('Ready to confirm')).toBeVisible();
  const confirmButton = page.getByRole('button', { name: 'Confirm and save' });
  await expect(confirmButton).toBeDisabled();
  await page.getByText('I reviewed every probability, evidence source, and effect.').click();
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();

  await expect(page.getByText('Confirmed and saved')).toBeVisible();
  expect(confirmedPayload).toMatchObject({
    user_confirmed: true,
    program: { status: 'confirmed', version: 'contact-panel-2025-v1' },
  });
});
