import { expect, test } from '@playwright/test';

test('Simulation replaces the standalone DSL and Graph tabs', async ({ page }) => {
  await page.goto('/');

  const workspaceTabs = page.getByRole('tablist', { name: 'Workspace view' });
  await expect(workspaceTabs.getByRole('tab', { name: 'Simulation', exact: true })).toBeVisible();
  await expect(workspaceTabs.getByRole('tab', { name: 'Stories', exact: true })).toBeVisible();
  await expect(workspaceTabs.getByRole('tab', { name: 'Data', exact: true })).toBeVisible();
  await expect(workspaceTabs.getByRole('tab', { name: 'DSL', exact: true })).toHaveCount(0);
  await expect(workspaceTabs.getByRole('tab', { name: 'Graph', exact: true })).toHaveCount(0);

  const simulationTabs = page.getByRole('tablist', { name: 'Simulation sections' });
  await expect(simulationTabs.getByRole('tab', { name: 'Graph', exact: true })).toBeVisible();
  await expect(
    simulationTabs.getByRole('tab', { name: 'Initial Agents', exact: true }),
  ).toBeVisible();
  await expect(
    simulationTabs.getByRole('tab', { name: 'Decision Trees', exact: true }),
  ).toBeVisible();
  await expect(
    simulationTabs.getByRole('tab', { name: 'Run Simulation', exact: true }),
  ).toBeVisible();
});

test('Graph decision mode renders the shared filtered tree navigator', async ({ page }) => {
  await page.route('**/api/simulation/agent-types', async (route) => {
    await route.fulfill({
      json: {
        configured: true,
        confirmed: null,
        resolved: {
          types: [
            {
              id: 'business_agent',
              name: 'BusinessAgent',
              description: 'Business role',
              parent_ids: [],
              traits: [],
              routines: [],
              decisions: [
                {
                  member: {
                    id: 'business_evening',
                    name: 'Business evening',
                    definition: 'Choose the next evidenced business activity.',
                    description: null,
                    source_feature_ids: [],
                  },
                  source_type_id: 'business_agent',
                  inherited: false,
                  explicit_override: false,
                  overridden_source_type_ids: [],
                },
              ],
            },
          ],
        },
      },
    });
  });
  await page.route('**/api/simulation/decision-trees', async (route) => {
    await route.fulfill({
      json: {
        registry: {
          version: '1',
          trees: [
            {
              id: 'business_evening',
              version: '1',
              name: 'Business evening',
              description: 'Evidence-gated evening decisions.',
              root_module_id: 'business_evening_module',
              agent_type_ids: ['business_agent'],
              place_ids: [],
              source: 'Imported time-use study',
              status: 'ready',
            },
          ],
          modules: [
            {
              id: 'business_evening_module',
              version: '1',
              name: 'Business evening module',
              description: 'Choose a measured evening activity.',
              entry_node: 'choose',
              nodes: [
                {
                  id: 'choose',
                  label: 'Choose activity',
                  kind: 'decision',
                  description: '',
                  target_module_id: null,
                },
                {
                  id: 'outside',
                  label: 'Go outside',
                  kind: 'terminal',
                  description: '',
                  target_module_id: null,
                },
              ],
              edges: [
                {
                  id: 'leave_home',
                  from_node: 'choose',
                  to_node: 'outside',
                  label: 'Leave home',
                  condition: '',
                  decision_id: 'business_evening',
                  evidence_edge_id: 'leave_home',
                },
              ],
              source: 'Imported time-use study',
              status: 'ready',
            },
          ],
        },
        validation: {
          valid: true,
          issues: [],
          broken_references: [],
          reference_cycles: [],
          unreachable_nodes: { business_evening_module: [] },
        },
      },
    });
  });
  await page.route('**/api/simulation/decision-evidence', async (route) => {
    await route.fulfill({
      json: {
        status: {
          configured: true,
          version: '1',
          template_count: 1,
          evidence_count: 0,
          valid: true,
          issue_count: 0,
        },
        registry: {
          version: '1',
          templates: [
            {
              id: 'business_evening',
              name: 'Business evening',
              domain: 'social',
              status: 'ready',
              entry_state: 'choose',
              terminal_states: ['outside'],
              nodes: [
                { id: 'choose', label: 'Choose activity', kind: 'decision' },
                { id: 'outside', label: 'Go outside', kind: 'terminal' },
              ],
              edges: [
                {
                  id: 'leave_home',
                  decision_id: 'business_evening',
                  domain: 'social',
                  from_state: 'choose',
                  to_state: 'outside',
                  label: 'Leave home',
                  formula: {
                    id: 'leave_home_probability',
                    name: 'Evidenced outing probability',
                    combination: 'product',
                    factors: [
                      {
                        id: 'age_effect',
                        name: 'Age effect',
                        input_kind: 'trait',
                        input_key: 'age',
                        feature_id: 'age',
                      },
                      {
                        id: 'weekday_effect',
                        name: 'Weekday effect',
                        input_kind: 'time',
                        input_key: 'weekday',
                        feature_id: null,
                      },
                    ],
                  },
                  source: {
                    kind: 'none',
                    label: 'no source attached — estimated / unknown',
                    reason: 'Workspace route fixture',
                  },
                },
              ],
            },
          ],
          evidence: [],
        },
        validation: { valid: true, issues: [] },
        catalog: [],
      },
    });
  });
  await page.goto('/');

  await page.getByRole('button', { name: 'Decision tree view' }).click();

  await expect(page.getByRole('heading', { name: 'Decision trees' })).toBeVisible();
  await expect(page.locator('[data-tree-id="business_evening"]')).toBeVisible();
  await expect(page.locator('[data-tree-edge="leave_home"]')).toContainText(
    'Evidenced outing probability',
  );
  await expect(page.locator('[data-tree-edge="leave_home"]')).toContainText(
    'Age effect × Weekday effect',
  );
  await expect(page.getByLabel('Agent type').locator('option:checked')).toHaveText(
    'Business Agent',
  );
});

test('Initial agent routine links open the typed routine detail and return to the agent', async ({
  page,
}) => {
  const listItem = {
    agent_id: 'business-1',
    display_name: 'Morgan Lee',
    agent_types: ['business_agent'],
    age: 40,
    sex: 'female',
    country: 'Canada',
    city: 'Vancouver',
    current_location: 'home:household-1',
    household_id: 'household-1',
    household_size: 1,
    family_status: 'household',
  };
  await page.route('**/api/simulation/initial-agents**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/business-1')) {
      await route.fulfill({
        json: {
          ...listItem,
          location: {
            country: 'Canada',
            region: 'British Columbia',
            city: 'Vancouver',
            neighbourhood: 'Downtown',
            specific_place: 'home:household-1',
          },
          household: null,
          family_relationships: [],
          traits: {},
          initial_states: { location: 'home:household-1' },
          occupation: 'Owner',
          income: 90000,
          education: 'ISCED 6',
          health: 'healthy',
          routines: [
            {
              routine_id: 'business_weekday',
              name: 'Business weekday',
              agent_type: 'business_agent',
              inherited_from: null,
            },
          ],
          decision_trees: [],
          representative_weight: 1,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        items: [listItem],
        total: 1,
        page: 1,
        page_size: 50,
        pages: 1,
        facets: {
          agent_types: ['business_agent'],
          countries: ['Canada'],
          cities: ['Vancouver'],
          family_statuses: ['household'],
        },
      },
    });
  });
  await page.route('**/api/simulation/routines/agent-types/business_agent', async (route) => {
    await route.fulfill({
      json: {
        agent_type_id: 'business_agent',
        agent_type_name: 'BusinessAgent',
        routines: [
          {
            routine: {
              id: 'business_weekday',
              name: 'Business weekday',
              agent_type_id: 'business_agent',
              description: 'Measured weekday schedule.',
              evidence: {
                status: 'measured',
                source_title: 'Canadian time-use survey',
                source_date: '2025-01-01',
                source_uri: 'https://example.test/time-use',
                note: null,
              },
              steps: [
                {
                  id: 'pub_meeting',
                  name: 'Pub business meeting',
                  activity: 'meet another business agent',
                  schedule: {
                    days: ['friday'],
                    start_time: '18:30',
                    end_time: '20:30',
                    ends_next_day: false,
                    place_ids: ['pub'],
                    role_ids: ['business_agent'],
                  },
                  decision_tree_module_id: null,
                },
              ],
            },
            source_type_id: 'business_agent',
            inherited: false,
            explicit_override: false,
            overridden_source_type_ids: [],
          },
        ],
      },
    });
  });
  await page.goto('/');

  await page
    .getByRole('tablist', { name: 'Simulation sections' })
    .getByRole('tab', { name: 'Initial Agents', exact: true })
    .click();
  await page.getByRole('button', { name: 'Open Morgan Lee initial state' }).click();
  await page.getByRole('button', { name: 'Open Business weekday routine' }).click();

  await expect(page.getByRole('heading', { name: 'BusinessAgent routines' })).toBeVisible();
  await expect(page.getByText('Pub business meeting')).toBeVisible();
  await page.getByRole('button', { name: '← Back' }).click();
  await expect(page.getByRole('heading', { name: 'Morgan Lee' })).toBeVisible();
});

test('Decision Trees exposes registered two-agent interaction trees', async ({ page }) => {
  const definition = {
    id: 'ask_out',
    name: 'Ask someone out',
    version: '1',
    entry_node: 'asked',
    allowed_channels: ['in_person'],
    co_location_policy: 'required',
    nodes: [
      { id: 'asked', label: 'Actor asks target', terminal: false },
      {
        id: 'accepted',
        label: 'Target accepts',
        terminal: true,
        target_tree_id: 'plan_date',
      },
    ],
    transitions: [
      {
        id: 'accept',
        from_node: 'asked',
        to_node: 'accepted',
        outcome: 'accepted',
        probability: 1,
        evidence: {
          source: 'Observed relationship panel',
          version: '2026-01',
          status: 'measured_joint',
          uncertainty: 0.08,
          source_date: '2026-01-15',
          evidence_id: 'relationship-panel-acceptance',
        },
        conditions: [{ input: 'co_located', operator: 'eq', value: true }],
        effects: [{ kind: 'relationship_kind', relationship_type: 'dating' }],
      },
    ],
  };
  const nestedDefinition = {
    id: 'plan_date',
    name: 'Plan date',
    version: '1',
    entry_node: 'choose_place',
    allowed_channels: ['phone_message'],
    co_location_policy: 'remote_allowed',
    nodes: [{ id: 'choose_place', label: 'Choose a place', terminal: true }],
    transitions: [],
  };
  await page.route('**/api/simulation/interaction-trees**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith('/ask_out')) {
      await route.fulfill({ json: definition });
      return;
    }
    if (pathname.endsWith('/plan_date')) {
      await route.fulfill({ json: nestedDefinition });
      return;
    }
    await route.fulfill({
      json: [
        {
          id: 'ask_out',
          name: 'Ask someone out',
          version: '1',
          node_count: 2,
          transition_count: 1,
          co_location_policy: 'required',
          allowed_channels: ['in_person'],
        },
        {
          id: 'plan_date',
          name: 'Plan date',
          version: '1',
          node_count: 1,
          transition_count: 0,
          co_location_policy: 'remote_allowed',
          allowed_channels: ['phone_message'],
        },
      ],
    });
  });
  await page.goto('/');

  await page
    .getByRole('tablist', { name: 'Simulation sections' })
    .getByRole('tab', { name: 'Decision Trees', exact: true })
    .click();
  await page
    .getByRole('tablist', { name: 'Decision tree sections' })
    .getByRole('tab', { name: 'Interaction trees', exact: true })
    .click();

  await expect(page.getByRole('heading', { name: 'Interaction trees' })).toBeVisible();
  await expect(page.locator('[data-interaction-tree-id="ask_out"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const inspector = page.locator('[data-interaction-tree-inspector]');
  await expect(inspector.getByRole('heading', { name: 'Ask someone out' })).toBeVisible();
  await expect(inspector).toContainText('Observed relationship panel');
  await expect(inspector).toContainText('Relationship · becomes Dating');
  await inspector.locator('[data-interaction-tree-reference="plan_date"]').click();
  await expect(inspector.getByRole('heading', { name: 'Plan date' })).toBeVisible();
  await expect(inspector.getByRole('navigation')).toContainText('Ask someone out');
});
