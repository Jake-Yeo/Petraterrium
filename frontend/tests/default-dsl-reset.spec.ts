import { expect, test } from '@playwright/test';

test('Graph previews and confirms restoration of the checked-in default DSL', async ({ page }) => {
  let reset = false;
  let resetBody: unknown;
  await page.route('**/api/simulation/agent-types', async (route) => {
    const type = reset
      ? {
          id: 'person',
          name: 'Person',
          description: 'Shipped base person type',
          parent_ids: [],
          traits: [],
          routines: [],
          decisions: [],
        }
      : {
          id: 'edited-person',
          name: 'Edited person',
          description: 'User edit',
          parent_ids: [],
          traits: [],
          routines: [],
          decisions: [],
        };
    await route.fulfill({
      json: {
        configured: true,
        confirmed: null,
        resolved: { types: [type] },
      },
    });
  });
  await page.route('**/api/simulation/default-dsl', async (route) => {
    await route.fulfill({
      json: {
        loaded: true,
        intact: reset,
        receipt: {
          schema_version: '1',
          version: 'foundation-1',
          hash: 'default-hash-1',
          source: 'checked-in',
          managed_sections: ['agent_types', 'states', 'decision_trees', 'initial_population'],
        },
        installed_receipt: {
          schema_version: '1',
          version: 'foundation-1',
          hash: reset ? 'default-hash-1' : 'edited-hash',
          source: 'checked-in',
          managed_sections: ['agent_types', 'states', 'decision_trees', 'initial_population'],
        },
        inventory: {
          agent_type_ids: ['person'],
          state_ids: ['stress', 'health'],
          action_ids: ['work', 'eat-lunch', 'go-to-gym'],
          routine_ids: ['weekday'],
          decision_tree_ids: ['daily-choice'],
          interaction_tree_ids: [],
          initial_agent_ids: ['agent-000001', 'agent-000002'],
        },
        drifted_sections: reset ? [] : ['agent_types'],
      },
    });
  });
  await page.route('**/api/simulation/default-dsl/reset/preview', async (route) => {
    await route.fulfill({
      json: {
        changed: true,
        receipt: {
          schema_version: '1',
          version: 'foundation-1',
          hash: 'default-hash-1',
          source: 'checked-in',
          managed_sections: ['agent_types', 'states', 'decision_trees', 'initial_population'],
        },
        sections: [
          {
            name: 'agent_types',
            disposition: 'replace',
            current_count: 1,
            default_count: 1,
            current_ids: ['edited-person'],
            default_ids: ['person'],
            restored_ids: ['person'],
            replaced_ids: ['edited-person'],
          },
          {
            name: 'initial_population',
            disposition: 'restore',
            current_count: 0,
            default_count: 2,
            current_ids: [],
            default_ids: ['agent-000001', 'agent-000002'],
            restored_ids: ['agent-000001', 'agent-000002'],
            replaced_ids: [],
          },
        ],
      },
    });
  });
  await page.route('**/api/simulation/default-dsl/reset', async (route) => {
    resetBody = route.request().postDataJSON();
    reset = true;
    await route.fulfill({
      json: {
        loaded: true,
        intact: true,
        receipt: {
          schema_version: '1',
          version: 'foundation-1',
          hash: 'default-hash-1',
          source: 'checked-in',
          managed_sections: ['agent_types', 'states', 'decision_trees', 'initial_population'],
        },
        installed_receipt: {
          schema_version: '1',
          version: 'foundation-1',
          hash: 'default-hash-1',
          source: 'checked-in',
          managed_sections: ['agent_types', 'states', 'decision_trees', 'initial_population'],
        },
        inventory: {
          agent_type_ids: ['person'],
          state_ids: ['stress', 'health'],
          action_ids: ['work', 'eat-lunch', 'go-to-gym'],
          routine_ids: ['weekday'],
          decision_tree_ids: ['daily-choice'],
          interaction_tree_ids: [],
          initial_agent_ids: ['agent-000001', 'agent-000002'],
        },
        drifted_sections: [],
      },
    });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Edited person' })).toBeVisible();
  await page.getByRole('button', { name: 'Reset to default DSL' }).click();

  const dialog = page.getByRole('dialog', { name: 'Reset to default DSL' });
  await expect(dialog).toContainText('foundation-1');
  await expect(dialog).toContainText('default-hash-1');
  await expect(dialog).toContainText('Edited Person');
  await expect(dialog).toContainText('2 initial agents');
  await dialog.getByRole('button', { name: 'Restore default DSL' }).click();

  await expect(page.getByRole('heading', { name: 'Person' })).toBeVisible();
  expect(resetBody).toEqual({ user_confirmed: true, expected_hash: 'default-hash-1' });
});
