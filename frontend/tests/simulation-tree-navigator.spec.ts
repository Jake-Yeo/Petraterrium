import { expect, test } from '@playwright/test';

async function mountNavigator(page: Parameters<typeof test>[0]['page']) {
  await page.evaluate(async () => {
    const { mountDecisionTreeNavigator } = await import('/src/simulation/tree-navigator.ts');
    const social = {
      id: 'social_choice',
      version: '2025.1',
      name: 'Social choice',
      description: 'Choose how to spend the evening.',
      entry_node: 'choose',
      source: 'Time Use Survey 2025',
      proposal_audit: {
        origin: 'ai' as const,
        source_id: 'openai_cli',
        source_label: 'OpenAI CLI',
        model: 'gpt-test',
        generated_at: '2026-10-27T12:00:00Z',
        prompt_version: 'markov-chain-proposal-v7',
        input_tokens: 41,
        output_tokens: 23,
        estimated_cost_usd: 0.0042,
        message: 'Confirmed after review.',
      },
      status: 'ready' as const,
      nodes: [
        {
          id: 'choose',
          label: 'Choose an evening activity',
          kind: 'decision' as const,
          description: 'Evaluates measured activity choices.',
          target_module_id: null,
        },
        {
          id: 'open_bar',
          label: 'Visit a bar',
          kind: 'module_reference' as const,
          description: 'Calls the reusable bar visit module.',
          target_module_id: 'bar_visit',
        },
        {
          id: 'stay_home',
          label: 'Stay home',
          kind: 'terminal' as const,
          description: '',
          target_module_id: null,
        },
      ],
      edges: [
        {
          id: 'choose_bar',
          from_node: 'choose',
          to_node: 'open_bar',
          label: 'Go out',
          condition: '',
          decision_id: 'go_out_friday',
          evidence_edge_id: 'leave_home',
        },
        {
          id: 'choose_home',
          from_node: 'choose',
          to_node: 'stay_home',
          label: 'Stay in',
          condition: '',
        },
      ],
    };
    const bar = {
      id: 'bar_visit',
      version: '2024.3',
      name: 'Bar visit',
      description: 'Reusable social visit decisions.',
      entry_node: 'arrive',
      source: 'Canada General Social Survey 2024',
      proposal_audit: {
        origin: 'deterministic' as const,
        source_id: 'deterministic-parser',
        source_label: 'Deterministic parser',
        model: 'none',
        generated_at: null,
        prompt_version: 'markov-chain-proposal-v1',
        input_tokens: 0,
        output_tokens: 0,
        estimated_cost_usd: null,
        message: 'Only explicit transitions were extracted.',
      },
      status: 'ready' as const,
      nodes: [
        {
          id: 'arrive',
          label: 'Arrive at bar',
          kind: 'action' as const,
          description: '',
          target_module_id: null,
        },
        {
          id: 'meet_friend',
          label: 'Meet a friend',
          kind: 'action' as const,
          description: 'A recorded social interaction.',
          target_module_id: null,
        },
        {
          id: 'leave',
          label: 'Leave bar',
          kind: 'terminal' as const,
          description: '',
          target_module_id: null,
        },
      ],
      edges: [
        {
          id: 'arrive_meet',
          from_node: 'arrive',
          to_node: 'meet_friend',
          label: '',
          condition: 'friend present',
        },
        {
          id: 'meet_leave',
          from_node: 'meet_friend',
          to_node: 'leave',
          label: '',
          condition: 'visit complete',
        },
      ],
    };
    const broken = {
      id: 'broken_import',
      version: '0.1',
      name: 'Broken import',
      description: 'Import with an unresolved module call.',
      entry_node: 'missing_call',
      source: 'Imported draft',
      status: 'blocked' as const,
      nodes: [
        {
          id: 'missing_call',
          label: 'Open missing module',
          kind: 'module_reference' as const,
          description: '',
          target_module_id: 'missing_module',
        },
      ],
      edges: [],
    };
    const registry = {
      version: 'tree-registry-1',
      trees: [
        {
          id: 'evening_routine',
          version: '2025.1',
          name: 'Evening routine',
          description: 'Evening choices for workers and students.',
          root_module_id: 'social_choice',
          agent_type_ids: ['worker', 'student'],
          place_ids: ['canada'],
          source: 'Time Use Survey 2025',
          proposal_audit: {
            origin: 'ai' as const,
            source_id: 'openai_cli',
            source_label: 'OpenAI CLI',
            model: 'gpt-test',
            generated_at: '2026-10-27T12:00:00Z',
            prompt_version: 'markov-chain-proposal-v7',
            input_tokens: 41,
            output_tokens: 23,
            estimated_cost_usd: 0.0042,
            message: 'Confirmed after review.',
          },
          status: 'ready' as const,
        },
        {
          id: 'bar_arrival',
          version: '2024.3',
          name: 'Bar arrival',
          description: 'Direct use of the shared bar module.',
          root_module_id: 'bar_visit',
          agent_type_ids: ['worker'],
          place_ids: ['canada', 'japan'],
          source: 'Canada General Social Survey 2024',
          status: 'ready' as const,
        },
        {
          id: 'broken_tree',
          version: '0.1',
          name: 'Broken imports',
          description: 'Needs its referenced module.',
          root_module_id: 'broken_import',
          agent_type_ids: ['executive'],
          place_ids: ['mexico'],
          source: 'Imported draft',
          status: 'blocked' as const,
        },
      ],
      modules: [social, bar, broken],
    };
    document.body.innerHTML = '<main id="tree-navigator-test"></main>';
    mountDecisionTreeNavigator(document.querySelector('#tree-navigator-test')!, {
      registry,
      evidenceTemplates: [
        {
          id: 'go_out_friday',
          name: 'Friday social outing',
          domain: 'social',
          status: 'ready',
          entry_state: 'choose',
          terminal_states: ['outside', 'home'],
          nodes: [
            { id: 'choose', label: 'Choose', kind: 'decision' },
            { id: 'outside', label: 'Outside', kind: 'terminal' },
            { id: 'home', label: 'Home', kind: 'terminal' },
          ],
          edges: [
            {
              id: 'leave_home',
              decision_id: 'go_out_friday',
              domain: 'social',
              from_state: 'choose',
              to_state: 'outside',
              label: 'Leave home',
              formula: {
                id: 'leave_home_probability',
                name: 'Friday outing probability',
                combination: 'product',
                factors: [
                  {
                    id: 'extraversion_effect',
                    name: 'Extraversion effect',
                    input_kind: 'trait',
                    input_key: 'extraversion',
                    feature_id: 'extraversion',
                  },
                  {
                    id: 'friday_timing',
                    name: 'Friday timing',
                    input_kind: 'time',
                    input_key: 'weekday',
                    feature_id: null,
                  },
                ],
              },
              source: {
                kind: 'none',
                label: 'no source attached — estimated / unknown',
                reason: 'Navigator formula fixture',
              },
            },
          ],
        },
      ],
      initialTreeId: 'evening_routine',
      renderEdgeEvidence: (host, selection) => {
        host.innerHTML = `<strong data-test-edge-receipt>${selection.edge.decision_id} / ${selection.edge.evidence_edge_id} / ${selection.evidence?.formula.name ?? 'missing formula'}</strong>`;
      },
      validation: {
        valid: false,
        issues: [
          {
            code: 'broken_module_reference',
            path: 'modules.broken_import.nodes.missing_call.target_module_id',
            message: 'Referenced module missing_module does not exist',
          },
        ],
        broken_references: [
          {
            module_id: 'broken_import',
            node_id: 'missing_call',
            target_module_id: 'missing_module',
          },
        ],
        reference_cycles: [],
        unreachable_nodes: {},
      },
    });
  });
}

test('shows every edge probability formula without requiring selection', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  const linked = page.locator('[data-tree-edge="choose_bar"]');
  await expect(linked).toContainText('Friday outing probability');
  await expect(linked).toContainText('Extraversion effect × Friday timing');
  await expect(page.locator('[data-tree-edge="choose_home"]')).toContainText(
    'No confirmed probability formula',
  );
});

test('shows the full persisted proposal audit for the tree and module', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  const provenance = page.getByRole('region', { name: 'Decision tree proposal provenance' });
  await expect(provenance).toContainText('Tree proposal');
  await expect(provenance).toContainText('Module proposal');
  await expect(provenance).toContainText('AI proposal');
  await expect(provenance).toContainText('OpenAI CLI (openai_cli)');
  await expect(provenance).toContainText('gpt-test');
  await expect(provenance).toContainText('markov-chain-proposal-v7');
  await expect(provenance).toContainText('41 input · 23 output');
  await expect(provenance).toContainText('2026-10-27');
  await expect(provenance).toContainText('Confirmed after review.');
});

test('opens one reusable module at a time and restores its parent view', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  await expect(page.getByRole('heading', { name: 'Social choice' })).toBeVisible();
  await expect(page.locator('[data-tree-node]')).toHaveCount(3);
  await expect(page.getByText('Meet a friend')).toHaveCount(0);

  await page.getByRole('button', { name: 'Zoom in' }).click();
  await expect(page.getByLabel('Zoom level')).toHaveText('125%');
  await page.getByRole('button', { name: 'Open Bar visit' }).click();

  await expect(page.getByRole('heading', { name: 'Bar visit' })).toBeVisible();
  await expect(page.getByText('Meet a friend')).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Decision tree module breadcrumbs' }),
  ).toContainText('Social choice');
  await page.getByRole('button', { name: 'Back' }).click();

  await expect(page.getByRole('heading', { name: 'Social choice' })).toBeVisible();
  await expect(page.getByLabel('Zoom level')).toHaveText('125%');
  await expect(page.locator('[data-select-node="open_bar"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('opens linked probability evidence from a mouse or keyboard action', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  const transition = page.getByRole('button', {
    name: 'Inspect Go out probability evidence',
  });
  await transition.click();
  await expect(page.getByRole('region', { name: 'Selected decision transition' })).toContainText(
    'go_out_friday · leave_home',
  );
  await expect(page.locator('[data-test-edge-receipt]')).toHaveText(
    'go_out_friday / leave_home / Friday outing probability',
  );

  await page.getByRole('button', { name: 'Inspect Stay in probability evidence' }).focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('region', { name: 'Selected decision transition' })).toContainText(
    'No evidence link attached',
  );
  await expect(page.locator('.tree-evidence-unlinked')).toContainText(
    'cannot be presented as measured',
  );
});

test('previews a referenced module entry and exits on hover and keyboard focus', async ({
  page,
}) => {
  await page.goto('/');
  await mountNavigator(page);

  const referenceNode = page.locator('[data-tree-node="open_bar"]');
  const preview = page.getByRole('tooltip');
  await referenceNode.hover();
  await expect(preview).toBeVisible();
  await expect(preview).toContainText('Entry');
  await expect(preview).toContainText('Arrive at bar');
  await expect(preview).toContainText('Exits');
  await expect(preview).toContainText('Leave bar');

  await page.mouse.move(0, 0);
  await page.getByRole('button', { name: 'Open Bar visit' }).focus();
  await expect(preview).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open Bar visit' })).toHaveAttribute(
    'aria-describedby',
    'tree-reference-preview-social_choice-open_bar',
  );
});

test('edits a shared module once and persists it through explicit confirmation', async ({
  page,
}) => {
  let savedRequest: {
    registry: {
      modules: Array<{
        id: string;
        proposal_audit?: {
          source_id: string;
          prompt_version: string;
          input_tokens: number;
          output_tokens: number;
        };
        nodes: Array<{ id: string; label: string }>;
        edges: Array<{ id: string; label: string; condition: string }>;
      }>;
    };
    user_confirmed: boolean;
  } | null = null;
  await page.route('**/api/simulation/decision-trees/confirm', async (route) => {
    savedRequest = route.request().postDataJSON() as typeof savedRequest;
    await route.fulfill({
      json: {
        registry: savedRequest!.registry,
        validation: {
          valid: true,
          issues: [],
          broken_references: [],
          reference_cycles: [],
          unreachable_nodes: {},
        },
      },
    });
  });
  await page.goto('/');
  await mountNavigator(page);
  await page.getByRole('button', { name: 'Open Bar visit' }).click();

  await page.getByRole('button', { name: 'Edit module' }).click();
  const editor = page.getByRole('form', { name: 'Edit Bar visit module' });
  await expect(editor).toBeVisible();
  await editor.getByLabel('Label for node arrive').fill('Enter the venue');
  await editor.getByLabel('Label for edge arrive_meet').fill('Find company');
  await editor.getByLabel('Condition for edge arrive_meet').fill('friend is present');
  await editor.getByRole('button', { name: 'Confirm module changes' }).click();

  await expect(page.locator('.tree-editor-notice')).toContainText(
    'Bar visit saved everywhere it is referenced.',
  );
  await expect(page.locator('[data-select-node="arrive"]')).toContainText('Enter the venue');
  expect(savedRequest).not.toBeNull();
  expect(savedRequest!.user_confirmed).toBe(true);
  const savedModule = savedRequest!.registry.modules.find((module) => module.id === 'bar_visit');
  expect(savedModule?.nodes.find((node) => node.id === 'arrive')?.label).toBe('Enter the venue');
  expect(savedModule?.edges.find((edge) => edge.id === 'arrive_meet')).toMatchObject({
    label: 'Find company',
    condition: 'friend is present',
  });
  expect(savedModule?.proposal_audit).toMatchObject({
    source_id: 'deterministic-parser',
    prompt_version: 'markov-chain-proposal-v1',
    input_tokens: 0,
    output_tokens: 0,
  });

  await page.locator('[data-tree-id="bar_arrival"]').click();
  await expect(page.getByRole('heading', { name: 'Bar visit' })).toBeVisible();
  await expect(page.locator('[data-select-node="arrive"]')).toContainText('Enter the venue');
});

test('collapses branches and supports zoom and pointer panning', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  await page.getByRole('button', { name: 'Collapse Choose an evening activity' }).click();
  await expect(page.locator('[data-tree-node]')).toHaveCount(1);
  await page.getByRole('button', { name: 'Expand Choose an evening activity' }).click();
  await expect(page.locator('[data-tree-node]')).toHaveCount(3);

  const viewport = page.getByLabel('Social choice module graph');
  const bounds = await viewport.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.move(bounds!.x + bounds!.width - 25, bounds!.y + bounds!.height - 25);
  await page.mouse.down();
  await page.mouse.move(bounds!.x + bounds!.width - 90, bounds!.y + bounds!.height - 70);
  await page.mouse.up();
  await expect(page.locator('[data-tree-plane]')).not.toHaveCSS('transform', 'none');
  await page.getByRole('button', { name: 'Reset view' }).click();
  await expect(page.getByLabel('Zoom level')).toHaveText('100%');
});

test('searches nodes through module references and joins all catalog filters', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  await page.getByLabel('Agent type').selectOption('student');
  await page.getByLabel('Place').selectOption('canada');
  await page.getByLabel('Source').selectOption('Time Use Survey 2025');
  await page.getByLabel('Status').selectOption('ready');
  await expect(page.locator('[data-tree-id]')).toHaveCount(1);
  await expect(page.locator('[data-tree-id]')).toContainText('Evening routine');

  await page.getByLabel('Search trees and nodes').fill('friend');
  const result = page.getByRole('option').filter({ hasText: 'Evening routine' });
  await expect(result).toContainText('Meet a friend');
  await result.click();

  await expect(page.getByRole('heading', { name: 'Bar visit' })).toBeVisible();
  await expect(page.locator('[data-select-node="meet_friend"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('shows callers and blocks navigation through broken module references', async ({ page }) => {
  await page.goto('/');
  await mountNavigator(page);

  await page.getByRole('button', { name: 'Open Bar visit' }).click();
  const usedBy = page.locator('.tree-reference-list');
  await expect(usedBy).toContainText('Social choice');
  await expect(usedBy).toContainText('Bar arrival');

  await page.getByLabel('Status').selectOption('blocked');
  await page.getByRole('button', { name: /Broken imports/ }).click();
  await expect(page.getByRole('heading', { name: 'Broken import' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('missing_call → missing_module');
  await expect(page.locator('.tree-reference-broken')).toHaveText(
    'Broken reference · missing_module',
  );
  await expect(page.locator('[data-open-reference]')).toHaveCount(0);
});
