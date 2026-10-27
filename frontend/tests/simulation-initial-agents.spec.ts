import { expect, test } from '@playwright/test';

test('initial agents supports search, filters, linked household detail, routines, and trees', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const modulePath = '/src/simulation/initial-agents.ts';
    const { InitialAgentsView } = await import(modulePath);
    const host = document.createElement('section');
    host.id = 'initial-agents-test-host';
    document.body.replaceChildren(host);
    const summary = {
      agent_id: 'agent-avery',
      display_name: 'Avery',
      agent_types: ['BusinessAgent', 'FamilyMember'],
      age: 40,
      sex: 'female',
      country: 'Canada',
      city: 'Vancouver',
      current_location: 'home:household-1',
      household_id: 'household-1',
      household_size: 4,
      family_status: 'parent',
    };
    const detail = {
      ...summary,
      location: {
        country: 'Canada',
        region: 'North America',
        city: 'Vancouver',
        neighbourhood: 'Kitsilano',
        specific_place: 'home:household-1',
      },
      household: {
        household_id: 'household-1',
        members: [
          {
            agent_id: 'agent-avery',
            display_name: 'Avery',
            age: 40,
            relationship: 'self',
            agent_types: ['BusinessAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-sam',
            display_name: 'Sam',
            age: 41,
            relationship: 'spouse',
            agent_types: ['WorkerAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-mira',
            display_name: 'Mira',
            age: 4,
            relationship: 'daughter',
            agent_types: ['StudentAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-noah',
            display_name: 'Noah',
            age: 6,
            relationship: 'son',
            agent_types: ['StudentAgent', 'FamilyMember'],
          },
        ],
      },
      family_relationships: [
        {
          target_agent_id: 'agent-sam',
          display_name: 'Sam',
          relationship: 'spouse',
          age: 41,
          weight: 0.95,
        },
      ],
      traits: { big_five_extraversion: 0.72 },
      initial_states: { health: 'healthy', location: 'home:household-1' },
      occupation: 'Founder',
      income: 125000,
      education: "Bachelor's degree",
      health: 'healthy',
      routines: [
        {
          routine_id: 'business-weekday',
          name: 'Business weekday',
          agent_type: 'BusinessAgent',
          inherited_from: null,
        },
        {
          routine_id: 'family-evening',
          name: 'Family evening',
          agent_type: 'FamilyMember',
          inherited_from: 'FamilyMember',
        },
      ],
      decision_trees: [
        {
          tree_id: 'business-social',
          name: 'Business social decisions',
          agent_type: 'BusinessAgent',
          inherited_from: null,
        },
      ],
      interaction_context: {
        program_status: 'confirmed',
        program_version: 'contact-panel-2025-v1',
        history_available: false,
        history_message:
          'No interaction frequency or history exists before a run. Run the simulation, then open Run Results for recorded interactions.',
        counterparts: [
          {
            target_agent_id: 'agent-sam',
            display_name: 'Sam',
            relationship: 'spouse',
            relationship_kind: 'family',
            weight: 0.95,
            trust: 0.82,
            similarity: 0.67,
            evidence: {
              status: 'measured_joint',
              source: 'Canadian General Social Survey contact panel',
              version: '2025-v1',
              source_date: '2025-09-17',
              evidence_id: 'family-profile',
              licence: 'Statistics Canada Open Licence',
              uncertainty: 0.06,
            },
            specific_place: 'home:household-1',
            target_specific_place: 'home:household-1',
            same_specific_place: true,
            in_person_eligibility: 'eligible',
            eligibility_reason:
              'Both agents are currently at the same exact place and a confirmed in-person rule applies.',
            applicable_rule_ids: ['family-conversation'],
          },
        ],
        rules: [
          {
            rule_id: 'family-conversation',
            source_action: 'return-home',
            interaction_type: 'talk',
            channel: 'in_person',
            interaction_tree_id: null,
            formula: 'P(talk | return-home) = base × relationship × co-location × place × time',
            factors: [
              {
                kind: 'base',
                condition: 'all eligible pairs',
                factor_id: 'hourly-contact',
                label: 'hourly contact',
                value: 0.4,
                provenance: {
                  status: 'measured_joint',
                  source: 'Canadian General Social Survey contact panel',
                  version: '2025-v1',
                  source_date: '2025-09-17',
                  evidence_id: 'hourly-contact',
                  licence: 'Statistics Canada Open Licence',
                  uncertainty: 0.06,
                },
              },
            ],
          },
        ],
      },
      representative_weight: 1,
    };
    const client = {
      list: async (query: Record<string, unknown>) => ({
        items:
          String(query.search ?? '').toLowerCase() === 'nobody' ||
          (query.agent_type && query.agent_type !== 'BusinessAgent')
            ? []
            : [summary],
        total:
          String(query.search ?? '').toLowerCase() === 'nobody' ||
          (query.agent_type && query.agent_type !== 'BusinessAgent')
            ? 0
            : 1,
        page: 1,
        page_size: 50,
        pages: 1,
        facets: {
          agent_types: ['BusinessAgent', 'FamilyMember', 'WorkerAgent'],
          countries: ['Canada'],
          cities: ['Vancouver'],
          family_statuses: ['parent'],
        },
      }),
      detail: async () => detail,
    };
    new InitialAgentsView(host, client);
  });

  const view = page.locator('#initial-agents-test-host');
  await expect(view.getByRole('heading', { name: 'Initial agents' })).toBeVisible();
  await expect(view.getByRole('button', { name: /Open Avery/ })).toContainText('BusinessAgent');
  await view.getByLabel('Agent type').selectOption('WorkerAgent');
  await expect(view).toContainText('No initial agents match');
  await view.getByRole('button', { name: 'Reset filters' }).click();
  await view.getByRole('button', { name: /Open Avery/ }).focus();
  await page.keyboard.press('Enter');

  await expect(view.getByRole('heading', { name: 'Avery' })).toBeVisible();
  await expect(view).toContainText('Founder');
  await expect(view).toContainText("Bachelor's degree");
  await expect(view.getByRole('region', { name: 'Household household-1' })).toContainText('Mira');
  await expect(view.getByRole('region', { name: 'Household household-1' })).toContainText('Noah');
  await expect(view.getByRole('button', { name: 'Open Business weekday routine' })).toBeVisible();
  await expect(
    view.getByRole('button', { name: 'Open Business social decisions decision tree' }),
  ).toBeVisible();
  const interactionContext = view.getByRole('region', { name: 'Pre-run interaction context' });
  await expect(interactionContext).toContainText('Sam');
  await expect(interactionContext).toContainText('Same exact place');
  await expect(interactionContext).toContainText('In-person eligible');
  await expect(interactionContext).toContainText('Weight 0.95');
  await expect(interactionContext).toContainText('Trust 0.82');
  await expect(interactionContext).toContainText('Similarity 0.67');
  await expect(interactionContext).toContainText('measured joint');
  await expect(interactionContext).toContainText('Canadian General Social Survey contact panel');
  await expect(interactionContext).toContainText(
    'P(talk | return-home) = base × relationship × co-location × place × time',
  );
  await expect(interactionContext).toContainText(
    'No interaction frequency or history exists before a run',
  );
  await view.getByRole('button', { name: 'Back to initial agents' }).click();
  await expect(view.getByLabel('Agent type')).toHaveValue('');
});

test('initial agent detail states when no confirmed interaction program exists', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const modulePath = '/src/simulation/initial-agents.ts';
    const { InitialAgentsView } = await import(modulePath);
    const host = document.createElement('section');
    host.id = 'initial-agents-absent-program';
    document.body.replaceChildren(host);
    const summary = {
      agent_id: 'agent-one',
      display_name: 'Agent One',
      agent_types: ['person'],
      age: 30,
      sex: 'unknown',
      country: 'Canada',
      city: 'Vancouver',
      current_location: 'home:one',
      household_id: null,
      household_size: 0,
      family_status: 'unknown',
    };
    const detail = {
      ...summary,
      location: {
        country: 'Canada',
        region: 'Northern America',
        city: 'Vancouver',
        neighbourhood: null,
        specific_place: 'home:one',
      },
      household: null,
      family_relationships: [],
      traits: {},
      initial_states: { location: 'home:one' },
      occupation: null,
      income: null,
      education: null,
      health: null,
      routines: [],
      decision_trees: [],
      interaction_context: {
        program_status: 'absent',
        program_version: null,
        history_available: false,
        history_message:
          'No interaction frequency or history exists before a run. Run the simulation, then open Run Results for recorded interactions.',
        counterparts: [],
        rules: [],
      },
      representative_weight: 1,
    };
    new InitialAgentsView(host, {
      list: async () => ({
        items: [summary],
        total: 1,
        page: 1,
        page_size: 50,
        pages: 1,
        facets: {
          agent_types: ['person'],
          countries: ['Canada'],
          cities: ['Vancouver'],
          family_statuses: ['unknown'],
        },
      }),
      detail: async () => detail,
    });
  });

  const view = page.locator('#initial-agents-absent-program');
  await view.getByRole('button', { name: /Open Agent One/ }).click();
  const interactions = view.getByRole('region', { name: 'Pre-run interaction context' });
  await expect(interactions).toContainText('No program');
  await expect(interactions).toContainText('No confirmed interaction program exists');
  await expect(interactions).toContainText(
    'No interaction frequency or history exists before a run',
  );
});
