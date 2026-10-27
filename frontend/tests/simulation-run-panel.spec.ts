import { expect, test } from '@playwright/test';

test('run panel shows the executable decision evidence blocker without creating a run', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-run-blocked-test';
    document.body.replaceChildren(host);
    const message =
      'Run blocked: 2 selected agents have no applicable confirmed executable decision tree: agent-1 (worker), agent-2 (worker). Confirm ready decision trees with measured-joint or fitted-model evidence for every selected agent type in Simulation > Decision Trees, then run again.';
    const client = {
      launch: async () => {
        throw new Error(message);
      },
      list: async () => [],
      get: async () => {
        throw new Error('not used');
      },
      cancel: async () => {
        throw new Error('not used');
      },
      delete: async () => undefined,
      agents: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
      agent: async () => {
        throw new Error('not used');
      },
      events: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    };
    new SimulationRunPanel(host, client);
  });

  const panel = page.locator('#simulation-run-blocked-test');
  await panel.getByRole('button', { name: 'Launch Rust simulation' }).click();

  await expect(panel.getByRole('alert')).toContainText('Run blocked: 2 selected agents');
  await expect(panel.getByRole('alert')).toContainText('agent-1 (worker), agent-2 (worker)');
  await expect(panel.getByRole('alert')).toContainText(
    'Confirm ready decision trees with measured-joint or fitted-model evidence',
  );
  await expect(panel).toContainText('No saved runs yet.');
});

test('run panel launches Rust, reports progress, and browses recorded agent timelines', async ({
  page,
}) => {
  await page.route(/\/api\/simulation\/runs\/rust-run-1\/locations$/, async (route) => {
    await route.fulfill({
      json: {
        run_id: 'rust-run-1',
        tick: 48,
        root_location_ids: ['canada'],
        places: [
          {
            id: 'canada',
            name: 'Canada',
            level: 'country',
            parent_id: null,
            child_ids: [],
            current_agent_count: 4,
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: null,
            state: {},
            evidence: null,
            decision_trees: [],
          },
        ],
        agents: [],
      },
    });
  });
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-run-panel-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 4,
      seed: 42,
      days: 2,
      tick_interval_hours: 1,
      start_date: '2026-10-27',
      place_scope: { level: 'city', identifier: 'Vancouver' },
      agent_type_mix: { BusinessAgent: 0.5, WorkerAgent: 0.5 },
    };
    const running = {
      run_id: 'rust-run-1',
      config,
      status: 'running',
      progress: 0.5,
      completed_ticks: 24,
      total_ticks: 48,
      result: null,
      error: null,
    };
    const completed = {
      ...running,
      status: 'completed',
      progress: 1,
      completed_ticks: 48,
      result: {
        source: 'rust',
        protocol_version: '1',
        engine_version: '0.1.0',
        data_version: 'atlas-v3',
        program_version: 'decisions-v8',
        input_hash: 'abc123input',
        output_hash: 'def456output',
        snapshots: [
          {
            day: 1,
            date: '2026-10-27',
            tick: 24,
            elapsed_hours: 24,
            state_counts: { 'day / outside': 3, 'day / home': 1 },
            place_counts: { Vancouver: 4 },
            transition_counts: [],
            interaction_outcome_counts: {},
            event_count: 2,
            interaction_count: 0,
          },
          {
            day: 2,
            date: '2026-10-28',
            tick: 48,
            elapsed_hours: 48,
            state_counts: { 'day / outside': 2, 'day / home': 2 },
            place_counts: { Vancouver: 4 },
            transition_counts: [{ module: 'day', transition: 'return-home', count: 2 }],
            interaction_outcome_counts: { became_friends: 1 },
            event_count: 1,
            interaction_count: 1,
          },
        ],
      },
    };
    let polls = 0;
    const client = {
      launch: async () => ({ ...running, status: 'queued', progress: 0 }),
      list: async () => [],
      get: async () => (++polls > 1 ? completed : running),
      cancel: async () => ({ ...running, status: 'cancelling' }),
      delete: async () => undefined,
      agents: async () => ({
        items: [
          {
            agent_id: 'agent-1',
            display_name: 'Avery',
            final_module: 'day',
            final_state: 'home',
            final_location: 'Vancouver',
          },
          {
            agent_id: 'agent-2',
            display_name: 'Noah',
            final_module: 'day',
            final_state: 'home',
            final_location: 'Vancouver',
          },
        ],
        total: 2,
        page: 1,
        page_size: 100,
        pages: 1,
      }),
      agent: async (_runId: string, agentId: string) => ({
        agent_id: agentId,
        display_name: agentId === 'agent-1' ? 'Avery' : 'Noah',
        final_module: 'day',
        final_state: 'home',
        final_location: 'Vancouver',
        initial_module: 'day',
        initial_state: 'choose',
        initial_location: 'Vancouver',
        traits: { age: 40 },
        memory: {},
        initial_profile: {
          agent_types: ['BusinessAgent', 'FamilyMan'],
          geography: { country: 'Canada', city: 'Vancouver', specific_place: 'Home' },
          household: {
            id: 'household-1',
            role: 'parent',
            family_status: 'partnered parent',
          },
          traits: {
            age: 40,
            sex: 'female',
            occupation: 'manager',
            income: 120000,
            education: 'ISCED 7',
            health: 'good',
          },
          states: { location: 'Home' },
          relationships: [
            {
              target_id: agentId === 'agent-1' ? 'agent-2' : 'agent-1',
              kind: 'family',
            },
          ],
          routines: ['business_work', 'family_dinner'],
          decision_trees: ['business_meeting', 'family_dinner_choice'],
          provenance: { sampling_basis: 'measured_joint' },
        },
        timeline: [
          {
            day: 1,
            date: '2026-10-27',
            tick: 24,
            elapsed_hours: 24,
            module: 'day',
            state: 'outside',
            location: 'Downtown bar',
            actions: ['meet-friend'],
            routine_actions: ['commute'],
            interactions: [],
            decision_path: [],
            location_transitions: [
              {
                tick: 8,
                kind: 'travel_started',
                source: 'weekday-commute',
                schedule: 'weekday-commute',
                from_location: 'Vancouver',
                to_location: 'Transit',
                destination_location: 'Downtown bar',
                provenance: {
                  recorded_by: 'rust_numeric_core',
                  record: 'location_transitions',
                  source_kind: 'schedule',
                },
              },
              {
                tick: 9,
                kind: 'travel_arrived',
                source: 'weekday-commute',
                schedule: 'weekday-commute',
                from_location: 'Transit',
                to_location: 'Downtown bar',
                destination_location: 'Downtown bar',
                provenance: {
                  recorded_by: 'rust_numeric_core',
                  record: 'location_transitions',
                  source_kind: 'schedule',
                },
              },
            ],
          },
          {
            day: 2,
            date: '2026-10-28',
            tick: 48,
            elapsed_hours: 48,
            module: 'day',
            state: 'home',
            location: 'Vancouver',
            actions: [],
            routine_actions: [],
            interactions: [agentId === 'agent-1' ? 'talked with agent-2' : 'talked with agent-1'],
            interaction_details: [
              {
                tick: 48,
                role: agentId === 'agent-1' ? 'initiator' : 'target',
                interaction_type: 'talk',
                channel: 'in_person',
                other_agent_id: agentId === 'agent-1' ? 'agent-2' : 'agent-1',
                other_agent_name: agentId === 'agent-1' ? 'Noah' : 'Avery',
                place: 'Downtown bar',
                state_deltas: [
                  {
                    agent_id: agentId,
                    state: 'mood',
                    before: agentId === 'agent-1' ? 0.2 : 0.4,
                    delta: agentId === 'agent-1' ? 0.3 : 0.1,
                    after: 0.5,
                  },
                ],
                relationship_deltas: [
                  {
                    source_agent_id: 'agent-1',
                    target_agent_id: 'agent-2',
                    field: 'trust',
                    before: 0.7,
                    delta: 0.05,
                    after: 0.75,
                  },
                ],
                interaction_tree: {
                  tree_id: 'daily-talk-tree',
                  tree_version: 'v2',
                  outcome_node: 'friends',
                  outcome: 'became_friends',
                  path: [
                    {
                      tree_id: 'daily-talk-tree',
                      node_id: 'opening',
                      transition_id: 'opening-to-topic',
                      outcome: 'continue_talking',
                      probability: 0.8,
                      draw: 0.2,
                      evidence: {
                        source: 'Daily interaction study',
                        version: '2026-v1',
                        status: 'measured_joint',
                        uncertainty: 0.01,
                        source_date: '2026-01-01',
                        evidence_id: 'daily-talk-opening',
                      },
                    },
                    {
                      tree_id: 'friendship-subtree',
                      node_id: 'topic',
                      transition_id: 'topic-to-friends',
                      outcome: 'became_friends',
                      probability: 0.6,
                      draw: 0.3,
                      evidence: {
                        source: 'Daily interaction study',
                        version: '2026-v1',
                        status: 'measured_joint',
                        uncertainty: 0.02,
                        source_date: '2026-01-01',
                        evidence_id: 'daily-talk-friendship',
                      },
                    },
                  ],
                },
              },
            ],
            decision_path: [],
            location_transitions: [
              {
                tick: 30,
                kind: 'schedule_move',
                source: 'return-home',
                schedule: 'return-home',
                from_location: 'Downtown bar',
                to_location: 'Vancouver',
                destination_location: 'Vancouver',
                provenance: {
                  recorded_by: 'rust_numeric_core',
                  record: 'location_transitions',
                  source_kind: 'schedule',
                },
              },
            ],
          },
        ],
      }),
      events: async (_runId: string, kind = '') => {
        const items = [
          {
            day: 1,
            date: '2026-10-27',
            tick: 8,
            kind: 'location',
            label: 'Vancouver → Transit',
            agent_ids: ['agent-1'],
            location: 'Transit',
            details: {
              kind: 'travel_started',
              source: 'weekday-commute',
              schedule: 'weekday-commute',
              from_location: 'Vancouver',
              to_location: 'Transit',
              destination_location: 'Downtown bar',
              provenance: {
                recorded_by: 'rust_numeric_core',
                record: 'location_transitions',
                source_kind: 'schedule',
              },
            },
          },
          {
            day: 2,
            date: '2026-10-28',
            tick: 48,
            kind: 'interaction',
            label: 'talked with',
            agent_ids: ['agent-1', 'agent-2'],
            location: 'Downtown bar',
            details: {},
          },
          {
            day: 1,
            date: '2026-10-27',
            tick: 7,
            kind: 'availability',
            label: 'Bar choice unavailable — agent is at home',
            agent_ids: ['agent-1'],
            location: 'Home',
            details: {
              schedule: 'bar-visit',
              decision_module: 'bar-choice',
              current_place_index: 0,
              destination_place_index: 2,
            },
          },
        ];
        const filtered = kind ? items.filter((item) => item.kind === kind) : items;
        return {
          items: filtered,
          total: filtered.length,
          page: 1,
          page_size: 100,
          pages: filtered.length ? 1 : 0,
        };
      },
    };
    new SimulationRunPanel(host, client, { pollIntervalMs: 10 });
  });

  const panel = page.locator('#simulation-run-panel-test');
  await expect(panel.getByRole('heading', { name: 'Run simulation' })).toBeVisible();
  await panel.getByLabel('Population').fill('4');
  await panel.getByLabel('Seed').fill('42');
  await panel.getByLabel('Days').fill('2');
  await panel.getByLabel('Start date').fill('2026-10-27');
  await panel.getByLabel('Tick interval (hours)').fill('1');
  await panel.getByLabel('Place scope').selectOption('city');
  await panel.getByLabel('Place', { exact: true }).fill('Vancouver');
  await panel.getByLabel('Agent type mix').fill('BusinessAgent: 0.5\nWorkerAgent: 0.5');
  await panel.getByRole('button', { name: 'Launch Rust simulation' }).click();
  await expect(panel.getByText('Completed')).toBeVisible();
  await expect(panel).toContainText('Rust 0.1.0');
  await expect(panel).toContainText('day / home');
  await expect(panel).toContainText('2 agents');
  await expect(panel).toContainText('day / return-home');
  await expect(panel).toContainText('Interaction / Became Friends');

  await panel.getByRole('button', { name: 'Agents' }).click();
  await expect(panel.getByRole('button', { name: /Open Avery/ })).toBeVisible();
  await panel.getByRole('button', { name: /Open Avery/ }).click();
  await expect(panel.getByRole('heading', { name: 'Avery' })).toBeVisible();
  await expect(panel).toContainText('choose');
  await expect(panel).toContainText('Downtown bar');
  await expect(panel).toContainText('meet-friend');
  await expect(panel).toContainText('talked with agent-2');
  await panel.getByText('1 interaction detail').click();
  await expect(panel).toContainText('Talk · In Person with Noah');
  await expect(panel).toContainText('Opening → Continue Talking');
  await expect(panel).toContainText('Friendship Subtree · Topic → Became Friends');
  await expect(panel).toContainText('Mood 0.2 +0.3 → 0.5');
  await expect(panel).toContainText('Trust agent-1 → agent-2 0.7 +0.05 → 0.75');
  await expect(panel.getByRole('heading', { name: 'Full initial state' })).toBeVisible();
  await panel.getByText('Agent types').click();
  await expect(panel).toContainText('BusinessAgent');
  await panel.getByText('Household and family').click();
  await expect(panel).toContainText('household-1');
  await panel.getByText('2 location changes').click();
  await expect(panel).toContainText('Vancouver → Transit');
  await expect(panel).toContainText('Travel Started · weekday-commute');
  await expect(panel).toContainText('Rust Numeric Core · destination Downtown bar · tick 8');
  await panel.getByRole('button', { name: 'Back to results' }).click();
  await panel.getByRole('button', { name: /Open Noah/ }).click();
  await panel.getByText('1 interaction detail').click();
  await expect(panel).toContainText('Talk · In Person with Avery');
  await expect(panel).toContainText('Friendship Subtree · Topic → Became Friends');
  await expect(panel).toContainText('Mood 0.4 +0.1 → 0.5');
  await expect(panel).toContainText('Trust agent-1 → agent-2 0.7 +0.05 → 0.75');
  await panel.getByRole('button', { name: 'Back to results' }).click();
  await panel.getByRole('button', { name: 'Events' }).click();
  await expect(panel).toContainText('talked with');
  await expect(panel).toContainText('agent-1 → agent-2');
  await expect(panel).toContainText('Vancouver → Transit');
  await panel.getByLabel('Event type').selectOption('availability');
  await expect(panel).toContainText('Bar choice unavailable — agent is at home');
  await expect(panel).toContainText("Bar Choice · Bar Visit · blocked at the agent's actual place");
  await panel.getByLabel('Event type').selectOption('location');
  await expect(panel).toContainText('Travel Started · weekday-commute · Rust Numeric Core');
  await expect(panel).not.toContainText('talked with');
  await panel.getByRole('button', { name: 'Locations' }).click();
  await expect(panel.getByRole('heading', { name: 'Locations' })).toBeVisible();
  await expect(panel.getByRole('button', { name: /Canada country/ })).toBeVisible();
});

test('run panel cancels an active Rust run', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-run-cancel-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 10,
      seed: 7,
      days: 24,
      tick_interval_hours: 1,
      start_date: '2026-10-27',
      place_scope: { level: 'global', identifier: null },
      agent_type_mix: {},
    };
    const active = {
      run_id: 'rust-run-cancel',
      config,
      status: 'running',
      progress: 0.25,
      completed_ticks: 144,
      total_ticks: 576,
      result: null,
      error: null,
    };
    const client = {
      launch: async () => active,
      list: async () => [],
      get: async () => active,
      cancel: async () => ({ ...active, status: 'cancelled' }),
      delete: async () => undefined,
      agents: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
      agent: async () => {
        throw new Error('not used');
      },
      events: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    };
    new SimulationRunPanel(host, client, { pollIntervalMs: 60_000 });
  });

  const panel = page.locator('#simulation-run-cancel-test');
  await panel.getByRole('button', { name: 'Launch Rust simulation' }).click();
  await expect(panel.getByRole('button', { name: 'Cancel run' })).toBeVisible();
  await panel.getByRole('button', { name: 'Cancel run' }).click();
  await expect(panel.getByRole('strong').filter({ hasText: 'Cancelled' })).toBeVisible();
});

test('run panel reopens and permanently deletes a saved run after inline confirmation', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-saved-runs-test';
    document.body.replaceChildren(host);
    const config = {
      population_size: 250,
      seed: 19,
      days: 14,
      tick_interval_hours: 6,
      start_date: '2026-10-27',
      place_scope: { level: 'country', identifier: 'Canada' },
      agent_type_mix: { ResidentAgent: 1 },
    };
    const saved = {
      run_id: 'saved-rust-run',
      config,
      status: 'completed',
      progress: 1,
      completed_ticks: 56,
      total_ticks: 56,
      result: {
        source: 'rust',
        protocol_version: '1',
        engine_version: '0.1.0',
        data_version: 'atlas-v3',
        program_version: 'decisions-v8',
        input_hash: 'input-hash',
        output_hash: 'output-hash',
        snapshots: [
          {
            day: 14,
            date: '2026-11-09',
            tick: 56,
            elapsed_hours: 336,
            state_counts: { 'day / home': 250 },
            place_counts: { Canada: 250 },
            transition_counts: [],
            interaction_outcome_counts: {},
            event_count: 0,
            interaction_count: 0,
          },
        ],
      },
      error: null,
    };
    let runs = [saved];
    const client = {
      launch: async () => saved,
      list: async () => runs,
      get: async () => saved,
      cancel: async () => saved,
      delete: async (runId: string, confirmation: string) => {
        if (runId !== confirmation) throw new Error('confirmation mismatch');
        runs = [];
      },
      agents: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
      agent: async () => {
        throw new Error('not used');
      },
      events: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    };
    new SimulationRunPanel(host, client);
  });

  const panel = page.locator('#simulation-saved-runs-test');
  await expect(panel.getByRole('heading', { name: 'Saved runs' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Open run saved-rust-run' })).toBeVisible();
  await panel.getByRole('button', { name: 'Open run saved-rust-run' }).click();
  await expect(panel).toContainText('Rust 0.1.0');
  await expect(panel).toContainText('250 agents');

  await panel.getByRole('button', { name: 'Delete run saved-rust-run' }).click();
  await expect(panel).toContainText('Delete this recorded run?');
  await expect(panel).toContainText('This removes its snapshots, timelines, and events.');
  await panel.getByRole('button', { name: 'Delete permanently' }).click();
  await expect(panel).toContainText('No saved runs yet.');
  await expect(panel).toContainText('Launch a simulation or open a saved run.');
});

test('saved run list reports a recoverable load failure', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { SimulationRunPanel } = await import('/src/simulation/run-panel.ts');
    const host = document.createElement('section');
    host.id = 'simulation-saved-error-test';
    document.body.replaceChildren(host);
    let attempts = 0;
    const client = {
      launch: async () => {
        throw new Error('not used');
      },
      list: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error('Saved run recorder is unavailable');
        return [];
      },
      get: async () => {
        throw new Error('not used');
      },
      cancel: async () => {
        throw new Error('not used');
      },
      delete: async () => undefined,
      agents: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
      agent: async () => {
        throw new Error('not used');
      },
      events: async () => ({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    };
    new SimulationRunPanel(host, client);
  });

  const panel = page.locator('#simulation-saved-error-test');
  await expect(panel).toContainText('Saved run recorder is unavailable');
  await panel.getByRole('button', { name: 'Retry' }).click();
  await expect(panel).toContainText('No saved runs yet.');
});
