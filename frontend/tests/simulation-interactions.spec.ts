import { expect, test } from '@playwright/test';

test('interaction browser filters an agent and audits directed effects and evidence', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { InteractionsView } = await import('/src/simulation/interactions.ts');
    const host = document.createElement('section');
    host.id = 'interaction-test-host';
    document.body.replaceChildren(host);
    const events = [
      {
        event_id: 'event-1',
        tick: 12,
        hour: 19,
        weekday: 4,
        rule_id: 'family-talk',
        interaction_type: 'talk',
        channel: 'in_person',
        initiator_id: 'agent-mara',
        initiator_name: 'Mara',
        target_id: 'agent-noah',
        target_name: 'Noah',
        place_id: 'home-1',
        relationship_type: 'family',
        probability: 0.54,
        effect_count: 2,
      },
      {
        event_id: 'event-2',
        tick: 14,
        hour: 21,
        weekday: 4,
        rule_id: 'friend-message',
        interaction_type: 'share_media',
        channel: 'phone_message',
        initiator_id: 'agent-avery',
        initiator_name: 'Avery',
        target_id: 'agent-mara',
        target_name: 'Mara',
        place_id: 'home-1',
        relationship_type: 'friend',
        probability: 0.18,
        effect_count: 1,
      },
    ];
    const client = {
      list: async (_runId: string, query: Record<string, string | number>) => {
        const selected = events.filter((event) => {
          if (!query.agent_id) return true;
          if (query.direction === 'initiator') return event.initiator_id === query.agent_id;
          if (query.direction === 'target') return event.target_id === query.agent_id;
          return event.initiator_id === query.agent_id || event.target_id === query.agent_id;
        });
        return {
          items: selected,
          total: selected.length,
          page: 1,
          page_size: 50,
          pages: 1,
          facets: {
            agents: { 'agent-mara': 'Mara', 'agent-noah': 'Noah', 'agent-avery': 'Avery' },
            interaction_types: ['share_media', 'talk'],
            channels: ['in_person', 'phone_message'],
            relationships: ['family', 'friend'],
            places: ['home-1'],
          },
          breakdown: {
            by_relationship: Object.fromEntries(
              [...new Set(selected.map((event) => event.relationship_type))].map((kind) => [
                kind,
                selected.filter((event) => event.relationship_type === kind).length,
              ]),
            ),
            by_channel: Object.fromEntries(
              [...new Set(selected.map((event) => event.channel))].map((channel) => [
                channel,
                selected.filter((event) => event.channel === channel).length,
              ]),
            ),
            by_place: { 'home-1': selected.length },
            by_counterparty: query.agent_id ? { Noah: 1, Avery: 1 } : {},
          },
        };
      },
      detail: async () => ({
        ...events[0],
        relationship_weight: 0.9,
        trust: 0.8,
        similarity: 0.7,
        factors: [
          {
            kind: 'base',
            factor: {
              id: 'base-contact',
              label: 'hourly contact',
              value: 0.9,
              provenance: {
                source: 'Imported time-use panel',
                version: '2025-v2',
                status: 'measured_joint',
                uncertainty: 0.04,
              },
            },
          },
          {
            kind: 'relationship',
            factor: {
              id: 'family-rate',
              label: 'family relationship',
              value: 0.6,
              provenance: {
                source: 'Household contact study',
                version: '2024-v1',
                status: 'fitted_model',
                uncertainty: 0.08,
              },
            },
          },
        ],
        state_deltas: [
          { agent_id: 'agent-noah', state: 'mood', before: 0.1, delta: 0.2, after: 0.3 },
        ],
        relationship_deltas: [
          {
            source_agent_id: 'agent-mara',
            target_agent_id: 'agent-noah',
            field: 'trust',
            before: 0.8,
            delta: 0.05,
            after: 0.85,
          },
        ],
        interaction_tree: {
          tree_id: 'talk-tree',
          tree_version: 'v2',
          outcome_node: 'agree',
          outcome: 'increase_trust',
          path: [
            {
              node_id: 'choose-topic',
              transition_id: 'topic-to-agree',
              outcome: 'increase_trust',
              probability: 0.6,
              draw: 0.2,
              evidence: {
                source: 'Imported conversation study',
                version: '2025-v1',
                status: 'measured_joint',
                uncertainty: 0.08,
              },
              factors: [
                {
                  factor_id: 'pair-trust',
                  label: 'Pair trust',
                  case_id: 'trusted',
                  multiplier: 1.4,
                  inputs: {
                    'relationship.state.trust': 0.8,
                    'relationship.state.weight': 0.9,
                  },
                  evidence: {
                    source: 'Observed relationship outcome panel',
                    version: '2026-v1',
                    status: 'measured_joint',
                    uncertainty: 0.05,
                  },
                },
                {
                  factor_id: 'live-place',
                  label: 'Live place state',
                  case_id: 'crowded',
                  multiplier: 0.7,
                  inputs: {
                    'place.state.occupancy': 80,
                    'place.state.crowd_density': 0.8,
                    'place.state.contamination': 0.2,
                  },
                  evidence: {
                    source: 'Observed venue outcome panel',
                    version: '2026-v2',
                    status: 'fitted_model',
                    uncertainty: 0.09,
                  },
                },
              ],
              outgoing_probabilities: [
                {
                  transition_id: 'topic-to-agree',
                  outcome: 'increase_trust',
                  base_probability: 0.6,
                  unnormalized_weight: 0.588,
                  probability: 0.7,
                  factors: [],
                  evidence: {
                    source: 'Imported conversation study',
                    version: '2025-v1',
                    status: 'measured_joint',
                    uncertainty: 0.08,
                  },
                },
                {
                  transition_id: 'topic-to-leave',
                  outcome: 'leave',
                  base_probability: 0.4,
                  unnormalized_weight: 0.252,
                  probability: 0.3,
                  factors: [],
                  evidence: {
                    source: 'Imported conversation study',
                    version: '2025-v1',
                    status: 'measured_joint',
                    uncertainty: 0.08,
                  },
                },
              ],
            },
          ],
        },
      }),
    };
    new InteractionsView(host, client, 'run-1');
  });

  const view = page.locator('#interaction-test-host');
  await expect(view.getByRole('heading', { name: 'Interactions' })).toBeVisible();
  await expect(view.getByRole('region', { name: 'Interaction breakdowns' })).toContainText(
    'Family',
  );
  await view.getByLabel('Agent').selectOption('agent-mara');
  await expect(view.getByLabel('Direction')).toBeEnabled();
  await expect(view.getByRole('button', { name: /Open Mara to Noah/ })).toBeVisible();
  await view.getByLabel('Direction').selectOption('target');
  await expect(view.getByRole('button', { name: /Open Avery to Mara/ })).toBeVisible();
  await view.getByLabel('Direction').selectOption('either');
  await view.getByRole('button', { name: /Open Mara to Noah/ }).click();
  await expect(view.getByRole('heading', { name: /Mara.*Noah/ })).toBeVisible();
  await expect(view).toContainText('P(hourly contact)');
  await expect(view).toContainText('Imported time-use panel');
  await expect(view).toContainText('agent-noah · Mood');
  await expect(view).toContainText('0.1 → 0.3');
  await expect(view).toContainText('agent-mara → agent-noah · Trust');
  await expect(view.getByRole('heading', { name: 'Talk Tree' })).toBeVisible();
  await expect(view).toContainText('Choose Topic → Increase Trust');
  await expect(view).toContainText('Imported conversation study');
  await expect(view).toContainText('Evaluated branches');
  await expect(view).toContainText('Pair trust ×1.4');
  await expect(view).toContainText('Relationship State Trust = 0.8');
  await expect(view).toContainText('Place State Crowd Density = 0.8');
  await expect(view).toContainText('Observed relationship outcome panel');
  await view.getByRole('button', { name: 'Back to interactions' }).click();
  await expect(view.getByLabel('Agent')).toHaveValue('agent-mara');
});
