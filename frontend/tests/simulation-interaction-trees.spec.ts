import { expect, test } from '@playwright/test';

test('interaction tree exposes evidence and atomic changes for both agents', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { mountInteractionTreeInspector } = await import('/src/simulation/interaction-trees.ts');
    const evidence = {
      source: 'Observed relationship panel',
      version: '2026-01',
      status: 'measured_joint' as const,
      uncertainty: 0.08,
      source_date: '2026-01-15',
      evidence_id: 'relationship-panel-acceptance',
    };
    const conditions = [
      { input: 'relationship.state.strength', operator: 'gte' as const, value: 0.5 },
      { input: 'co_located', operator: 'eq' as const, value: true },
    ];
    const definition = {
      id: 'ask_out',
      name: 'Ask someone out',
      version: '1',
      entry_node: 'asked',
      allowed_channels: ['in_person', 'phone_message'],
      co_location_policy: 'remote_allowed' as const,
      nodes: [
        { id: 'asked', label: 'Actor asks target', terminal: false },
        { id: 'dating', label: 'Target accepts', terminal: true },
        { id: 'declined', label: 'Target declines', terminal: true },
      ],
      transitions: [
        {
          id: 'accept',
          from_node: 'asked',
          to_node: 'dating',
          outcome: 'accepted',
          probability: 0.72,
          probability_factors: [
            {
              id: 'pair-trust',
              label: 'Pair trust',
              cases: [
                {
                  id: 'trusted',
                  conditions: [
                    { input: 'relationship.state.trust', operator: 'gte' as const, value: 0.5 },
                  ],
                  multiplier: 1.4,
                },
              ],
              evidence,
            },
          ],
          evidence,
          conditions,
          effects: [
            { kind: 'relationship_kind' as const, relationship_type: 'dating' },
            {
              kind: 'agent_routine' as const,
              participant: 'actor' as const,
              operation: 'add' as const,
              routine_id: 'partner_time',
            },
            {
              kind: 'agent_routine' as const,
              participant: 'target' as const,
              operation: 'add' as const,
              routine_id: 'partner_time',
            },
          ],
        },
        {
          id: 'decline',
          from_node: 'asked',
          to_node: 'declined',
          outcome: 'declined',
          probability: 0.28,
          evidence,
          conditions,
          effects: [],
        },
      ],
    };
    const participant = (agentId: string) => ({
      agent_id: agentId,
      place_id: 'cafe-1',
      states: { confidence: 0.5 },
      routines: ['weekly_social'],
    });
    const relationship = {
      source_agent_id: 'agent-a',
      target_agent_id: 'agent-b',
      eligible: true,
      relationship_type: 'acquaintance',
      states: { strength: 0.7 },
    };
    const result = {
      tree_id: 'ask_out',
      tree_version: '1',
      seed: 29,
      tick: 48,
      outcome_node: 'dating',
      outcome: 'accepted',
      path: [
        {
          node_id: 'asked',
          transition_id: 'accept',
          outcome: 'accepted',
          probability: 0.72,
          draw: 0.4,
          evidence,
        },
      ],
      receipt: {
        actor_id: 'agent-a',
        target_id: 'agent-b',
        relationship_direction: 'agent-a→agent-b',
        place_id: 'cafe-1',
        channel: 'in_person',
        weekday: 5,
        hour: 19,
      },
      actor_before: participant('agent-a'),
      actor_after: { ...participant('agent-a'), routines: ['partner_time', 'weekly_social'] },
      target_before: participant('agent-b'),
      target_after: { ...participant('agent-b'), routines: ['partner_time', 'weekly_social'] },
      relationship_before: relationship,
      relationship_after: { ...relationship, relationship_type: 'dating' },
      changes: [
        {
          recipient: 'relationship' as const,
          field: 'kind',
          before: 'acquaintance',
          after: 'dating',
        },
        {
          recipient: 'actor' as const,
          field: 'routine.partner_time',
          before: false,
          after: true,
        },
        {
          recipient: 'target' as const,
          field: 'routine.partner_time',
          before: false,
          after: true,
        },
      ],
    };
    document.body.innerHTML = '<main id="interaction-tree-test"></main>';
    mountInteractionTreeInspector(document.querySelector('#interaction-tree-test')!, {
      definition,
      result,
    });
  });

  const inspector = page.locator('[data-interaction-tree-inspector]');
  await expect(inspector.getByRole('heading', { name: 'Ask someone out' })).toBeVisible();
  await expect(inspector).toContainText('Directed eligibility');
  await expect(inspector).toContainText('Measured Joint');
  await expect(inspector).toContainText('Observed relationship panel');
  await expect(inspector).toContainText('relationship.state.strength ≥ 0.5');
  await expect(inspector).toContainText('Runtime probability factors');
  await expect(inspector).toContainText('Pair trust');
  await expect(inspector).toContainText('relationship.state.trust ≥ 0.5');
  await expect(inspector).toContainText('normalized across eligible branches');
  await expect(inspector.locator('[data-interaction-result-party="actor"]')).toContainText(
    'Partner Time',
  );
  await expect(inspector.locator('[data-interaction-result-party="target"]')).toContainText(
    'Partner Time',
  );
  await expect(inspector.locator('[data-interaction-result-party="relationship"]')).toContainText(
    'Acquaintance → Dating',
  );
  await expect(inspector).toContainText(
    'Both participant and relationship updates commit together',
  );

  const decline = inspector.getByRole('button', { name: /declined/i });
  await decline.focus();
  await page.keyboard.press('Enter');
  await expect(decline).toHaveAttribute('aria-pressed', 'true');
  await expect(inspector.locator('[data-interaction-transition-detail]')).toContainText('28.0%');
  await expect(inspector.locator('[data-interaction-transition-detail]')).toContainText(
    'No state changes',
  );
});

test('reference nodes open nested trees with breadcrumbs and flag broken targets', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { mountInteractionTreeInspector } = await import('/src/simulation/interaction-trees.ts');
    const evidence = {
      source: 'Imported conversation outcome panel',
      version: 'talk-2026',
      status: 'measured_joint' as const,
      uncertainty: 0.06,
      source_date: '2026-03-01',
      evidence_id: 'talk-response',
    };
    const response = {
      id: 'talk_response',
      name: 'Talk response',
      version: '1',
      entry_node: 'missing_follow_up',
      allowed_channels: ['in_person'],
      co_location_policy: 'required' as const,
      nodes: [
        {
          id: 'missing_follow_up',
          label: 'Open missing follow-up',
          terminal: true,
          target_tree_id: 'missing_follow_up',
        },
      ],
      transitions: [],
    };
    const talk = {
      id: 'talk',
      name: 'Talk',
      version: '1',
      entry_node: 'start',
      allowed_channels: ['in_person'],
      co_location_policy: 'required' as const,
      nodes: [
        { id: 'start', label: 'Start talking', terminal: false },
        {
          id: 'open_response',
          label: 'Open response',
          terminal: true,
          target_tree_id: 'talk_response',
        },
      ],
      transitions: [
        {
          id: 'speak',
          from_node: 'start',
          to_node: 'open_response',
          outcome: 'spoke',
          probability: 1,
          evidence,
          conditions: [],
          effects: [],
        },
      ],
    };
    const fetchFromApp = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input).endsWith('/api/simulation/interaction-trees/talk_response')) {
        return new Response(JSON.stringify(response), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return fetchFromApp(input, init);
    };
    document.body.innerHTML = '<main id="interaction-tree-test"></main>';
    mountInteractionTreeInspector(document.querySelector('#interaction-tree-test')!, {
      definition: talk,
    });
  });

  const inspector = page.locator('[data-interaction-tree-inspector]');
  const reference = inspector.locator('[data-interaction-tree-reference="talk_response"]');
  await expect(reference).toContainText('Opens:');
  await expect(reference).toContainText('Talk response');
  await reference.click();

  await expect(inspector.getByRole('heading', { name: 'Talk response' })).toBeVisible();
  await expect(inspector.locator('[data-broken-interaction-tree-reference]')).toContainText(
    'Broken reference',
  );
  await expect(inspector.locator('[data-broken-interaction-tree-reference]')).toContainText(
    'Opens: missing_follow_up',
  );
  await expect(inspector.getByRole('navigation')).toContainText('Talk');
  await inspector.getByRole('button', { name: 'Back' }).click();
  await expect(inspector.getByRole('heading', { name: 'Talk' })).toBeVisible();

  await inspector.locator('[data-interaction-tree-reference="talk_response"]').click();
  await inspector.getByRole('button', { name: 'Talk', exact: true }).click();
  await expect(inspector.getByRole('heading', { name: 'Talk' })).toBeVisible();
});
