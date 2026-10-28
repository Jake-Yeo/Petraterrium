import { expect, test } from '@playwright/test';

const mountGraph = async (page: Parameters<typeof test>[0]['page']) => {
  await page.evaluate(async () => {
    const { mountAgentTypeGraph } = await import('/src/simulation/agent-type-graph.ts');
    const item = (
      id: string,
      name: string,
      definition: string,
      source: string,
      inherited: boolean,
    ) => ({
      member: {
        id,
        name,
        definition,
        description: null,
        source_feature_ids: [],
      },
      source_type_id: source,
      inherited,
      explicit_override: false,
      overridden_source_type_ids: [],
    });
    const family = {
      id: 'family_man',
      name: 'FamilyMan',
      description: 'Shared family behavior',
      parent_ids: [],
      traits: [item('family_role', 'Family role', 'Parent or partner', 'family_man', false)],
      routines: [item('family_dinner', 'Family dinner', 'Weekday evening', 'family_man', false)],
      decisions: [
        item('family_evening', 'Family evening', 'family_evening_tree', 'family_man', false),
      ],
    };
    const business = {
      id: 'business_agent',
      name: 'BusinessAgent',
      description: 'Runs or develops a business',
      parent_ids: ['family_man'],
      traits: [
        item('employment_role', 'Employment role', 'Business owner', 'business_agent', false),
        item('family_role', 'Family role', 'Parent or partner', 'family_man', true),
      ],
      routines: [
        item('family_dinner', 'Family dinner', 'Weekday evening', 'family_man', true),
        item('pub_meeting', 'Pub business meeting', 'Friday evening', 'business_agent', false),
      ],
      decisions: [
        item('business_meeting', 'Business meeting', 'pub_meeting_tree', 'business_agent', false),
        item('family_evening', 'Family evening', 'family_evening_tree', 'family_man', true),
      ],
    };
    const overridden = item(
      'family_evening',
      'Family evening',
      'worker_family_tree',
      'worker_agent',
      false,
    );
    overridden.explicit_override = true;
    overridden.overridden_source_type_ids = ['family_man'];
    const worker = {
      id: 'worker_agent',
      name: 'WorkerAgent',
      description: 'Works an assigned shift',
      parent_ids: ['family_man'],
      traits: [
        item('employment_role', 'Employment role', 'Employee', 'worker_agent', false),
        item('family_role', 'Family role', 'Parent or partner', 'family_man', true),
      ],
      routines: [
        item('family_dinner', 'Family dinner', 'Weekday evening', 'family_man', true),
        item('work_shift', 'Work shift', 'Weekday daytime', 'worker_agent', false),
      ],
      decisions: [overridden],
    };
    document.body.innerHTML = '<main id="agent-type-test"></main>';
    const evidence = {
      status: 'default_estimated',
      source: 'Default state rule',
      source_version: 'v1',
      source_date: null,
      url: null,
      place: 'global',
      population: 'Synthetic default population',
      language: null,
      original_title: null,
      english_title: null,
      search_source: null,
      uncertainty: 1,
      default_reason: 'Awaiting linked state and outcome data',
    };
    mountAgentTypeGraph(document.querySelector('#agent-type-test')!, {
      types: [family, business, worker],
      stateSystem: {
        agent_states: {
          version: 'agent-state-core-v1',
          status: 'draft',
          definitions: [
            {
              id: 'stress',
              name: 'Stress',
              group: 'emotion',
              description: 'Current stress load',
              value_range: { minimum: 0, maximum: 1, unit: 'normalized index' },
              initial_feature_ids: ['stress'],
              initial_evidence: evidence,
              event_effects: [
                {
                  event_id: 'exercise',
                  direction: 'decreases',
                  parameter_id: 'exercise_stress_effect',
                  formula: 'stress[t+1] = stress[t] - exercise_stress_effect',
                  evidence,
                },
              ],
              recovery: {
                mode: 'decay',
                parameter_id: 'stress_decay',
                formula: 'stress[t+1] = stress[t] × (1 - stress_decay)',
                evidence,
              },
              decision_modifiers: [
                {
                  decision_id: 'skip_lunch',
                  state_id: 'stress',
                  formula: 'P(skip_lunch) = base × f(stress)',
                  coefficient: null,
                  center: 0.5,
                  minimum_factor: 0,
                  maximum_factor: 2,
                  direction: 'increases',
                  evidence,
                },
              ],
              propagation: [
                {
                  target_state_id: 'health',
                  direction: 'decreases',
                  parameter_id: 'stress_health_effect',
                  formula: 'health[t+1] = health[t] - stress_health_effect × stress[t]',
                  evidence,
                },
              ],
            },
          ],
        },
        relationship_states: {
          version: 'relationship-state-v1',
          definitions: [
            {
              id: 'love',
              name: 'Love',
              description: 'Directed attachment toward one specific other agent',
              value_range: { minimum: 0, maximum: 1, unit: 'normalized index' },
              direction: 'source_to_target',
              event_effects: [],
              recovery: {
                mode: 'event_driven',
                parameter_id: null,
                formula: 'love[source,target,t+1] = interaction update',
                evidence,
              },
            },
          ],
        },
      },
      audit: {
        provider: 'openai_cli',
        model: 'gpt-5',
        generated_at: '2026-10-27T12:00:00Z',
        prompt_version: 'agent-behavior-proposal-v2',
      },
      renderDecisionTree(host, agentType) {
        host.innerHTML = `<p>Decision tree for ${agentType.name}</p>`;
      },
    });
  });
};

test('inheritance graph exposes parent to child edges and sourced inherited members', async ({
  page,
}) => {
  await page.goto('/');
  await mountGraph(page);

  await expect(page.getByRole('heading', { name: 'Agent type inheritance' })).toBeVisible();
  await expect(page.locator('[data-agent-type-edge="family_man:business_agent"]')).toHaveCount(1);
  await expect(page.locator('[data-agent-type-edge="family_man:worker_agent"]')).toHaveCount(1);

  const businessNode = page.getByRole('button', { name: 'BusinessAgent agent type' });
  await businessNode.focus();
  await page.keyboard.press('Enter');

  const detail = page.locator('[data-agent-type-detail]');
  await expect(detail.getByRole('heading', { name: 'BusinessAgent' })).toBeVisible();
  await expect(detail).toContainText('Pub business meeting');
  await expect(detail).toContainText('Family dinner');
  await expect(detail).toContainText('Inherited from FamilyMan');
  await expect(detail).toContainText('Own definition');
  await expect(detail).toContainText('OpenAI CLI');
  await expect(detail).toContainText('gpt-5');
  await expect(detail).toContainText('agent-behavior-proposal-v2');
  await detail.getByText('State definitions, formulas, and loops').click();
  await expect(detail).toContainText('Stress');
  await expect(detail).toContainText('P(skip_lunch) = base × f(stress)');
  await expect(detail).toContainText('Directed: source → target');
  await expect(businessNode).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: 'WorkerAgent agent type' }).click();
  await expect(detail).toContainText('Overrides FamilyMan');
  await expect(detail).toContainText('worker_family_tree');
});

test('graph and decision tree are modes in one view and selection is preserved', async ({
  page,
}) => {
  await page.goto('/');
  await mountGraph(page);
  await page.getByRole('button', { name: 'BusinessAgent agent type' }).click();

  await page.getByRole('button', { name: 'Decision tree view' }).click();
  await expect(page.locator('[data-agent-type-decision-host]')).toContainText(
    'Decision tree for BusinessAgent',
  );
  await expect(page.getByRole('button', { name: 'Decision tree view' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.getByRole('button', { name: 'Inheritance view' }).click();
  await expect(page.getByRole('button', { name: 'BusinessAgent agent type' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('[data-agent-type-detail]')).toContainText('BusinessAgent');
});

test('agent type proposals remain editable drafts until explicit confirmation', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { mountAgentTypeProposalPanel } = await import('/src/simulation/agent-type-graph.ts');
    const definition = (id: string, name: string, value: string) => ({
      id,
      name,
      definition: value,
      description: null,
      source_feature_ids: ['occupation'],
    });
    const family = {
      id: 'family_man',
      name: 'FamilyMan',
      description: 'Shared household role',
      parent_ids: [],
      traits: [definition('family_role', 'Family role', 'Parent or partner')],
      routines: [definition('family_dinner', 'Family dinner', 'Weekday evening')],
      decisions: [],
      overrides: [],
    };
    const business = {
      id: 'business_agent',
      name: 'BusinessAgent',
      description: 'Business role',
      parent_ids: ['family_man'],
      traits: [definition('employment_role', 'Employment role', 'Business owner')],
      routines: [],
      decisions: [definition('pub_meeting', 'Pub meeting', 'pub_meeting_tree')],
      overrides: [],
    };
    Object.assign(window, { proposalConfirmations: 0, confirmedAgentTypes: null });
    document.body.innerHTML = '<main id="agent-type-proposal-test"></main>';
    mountAgentTypeProposalPanel(document.querySelector('#agent-type-proposal-test')!, {
      async requestProposal(prompt) {
        return {
          schema_version: '1',
          id: 'work_roles',
          prompt,
          imported_feature_ids: ['occupation', 'household_composition'],
          types: [family, business],
          audit: {
            provider: 'openai_cli',
            model: 'gpt-5',
            generated_at: '2026-10-27T12:00:00Z',
            prompt_version: 'agent-types-v1',
          },
          status: 'awaiting_confirmation',
          revision: 0,
        };
      },
      async confirmProposal(draft) {
        Object.assign(window, {
          proposalConfirmations:
            (window as unknown as { proposalConfirmations: number }).proposalConfirmations + 1,
          confirmedAgentTypes: draft,
        });
      },
    });
  });

  await page.getByLabel('Proposal request').fill('Create work and family roles from imported data');
  await page.getByRole('button', { name: 'Propose from imported data' }).click();
  await expect(page.getByRole('heading', { name: 'Review agent type proposal' })).toBeVisible();
  await expect(page.locator('.agent-type-proposal-audit')).toContainText('OpenAI CLI');
  await expect(page.locator('.agent-type-proposal-audit')).toContainText('gpt-5');
  await expect(page.locator('.agent-type-proposal-audit')).toContainText('2026-10-27');
  expect(
    await page.evaluate(
      () => (window as unknown as { proposalConfirmations: number }).proposalConfirmations,
    ),
  ).toBe(0);

  await page.getByRole('button', { name: 'Add agent type' }).click();
  const newType = page.locator('.agent-type-proposal-type').last();
  const confirm = page.getByRole('button', { name: 'Confirm and save' });
  await expect(confirm).toBeDisabled();
  await newType.locator('input[data-draft-field="id"]').fill('student_agent');
  await newType.locator('input[data-draft-field="name"]').fill('StudentAgent');
  await newType.locator('textarea[data-draft-field="description"]').fill('Studies full time');
  await newType.getByLabel('FamilyMan').check();
  await newType.getByLabel('BusinessAgent').check();
  await newType.getByRole('button', { name: 'Add trait' }).click();
  const trait = page
    .locator('.agent-type-proposal-type')
    .last()
    .locator('[data-proposal-member-row]');
  await trait.locator('input[data-draft-field="id"]').fill('study_role');
  await trait.locator('input[data-draft-field="name"]').fill('Study role');
  await trait.locator('input[data-draft-field="definition"]').fill('Full-time student');
  await trait.locator('input[data-draft-field="source_feature_ids"]').fill('education, occupation');

  await expect(confirm).toBeEnabled();
  expect(
    await page.evaluate(
      () => (window as unknown as { proposalConfirmations: number }).proposalConfirmations,
    ),
  ).toBe(0);
  await confirm.click();
  await expect(page.getByRole('status')).toContainText('Proposal confirmed and saved');

  const confirmed = await page.evaluate(() => {
    const state = window as unknown as {
      proposalConfirmations: number;
      confirmedAgentTypes: {
        types: Array<{
          id: string;
          parent_ids: string[];
          traits: Array<{ source_feature_ids: string[] }>;
        }>;
      };
    };
    return {
      proposalConfirmations: state.proposalConfirmations,
      confirmedAgentTypes: state.confirmedAgentTypes,
    };
  });
  expect(confirmed.proposalConfirmations).toBe(1);
  expect(confirmed.confirmedAgentTypes.types[2].id).toBe('student_agent');
  expect(confirmed.confirmedAgentTypes.types[2].parent_ids).toEqual([
    'family_man',
    'business_agent',
  ]);
  expect(confirmed.confirmedAgentTypes.types[2].traits[0].source_feature_ids).toEqual([
    'education',
    'occupation',
  ]);
});

test('behavior proposal requires a reviewed schedule and preserves blocked decision drafts', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { mountAgentTypeProposalPanel } = await import('/src/simulation/agent-type-graph.ts');
    const workday = {
      id: 'workday',
      name: 'Workday',
      definition: 'Daily work activity awaiting a confirmed schedule',
      description: null,
      source_feature_ids: ['age', 'occupation'],
    };
    Object.assign(window, { behaviorConfirmations: 0, confirmedBehaviorProposal: null });
    document.body.innerHTML = '<main id="behavior-proposal-test"></main>';
    mountAgentTypeProposalPanel(document.querySelector('#behavior-proposal-test')!, {
      async requestProposal(prompt) {
        return {
          schema_version: '2',
          id: 'agent_types',
          prompt,
          imported_feature_ids: ['age', 'occupation'],
          types: [
            {
              id: 'person',
              name: 'Person',
              description: 'A working adult',
              parent_ids: [],
              traits: [],
              routines: [workday],
              decisions: [],
              overrides: [],
            },
          ],
          audit: {
            provider: 'openai_cli',
            model: 'gpt-5',
            generated_at: '2026-10-27T12:00:00Z',
            prompt_version: 'agent-behavior-proposal-v2',
          },
          status: 'awaiting_confirmation',
          revision: 3,
          routine_drafts: [
            {
              id: 'workday',
              name: 'Workday',
              agent_type_id: 'person',
              description: 'Regular assigned work',
              source_feature_ids: ['age', 'occupation'],
              evidence: {
                status: 'unknown',
                source_title: null,
                source_date: null,
                source_uri: null,
                note: 'No schedule was inferred',
              },
              steps: [
                {
                  id: 'work',
                  name: 'Work',
                  activity: 'Work at assigned workplace',
                  decision_tree_module_id: 'social_choice_module',
                  schedule: null,
                },
              ],
            },
          ],
          decision_tree_drafts: {
            version: 'proposal-1',
            trees: [
              {
                id: 'social_choice',
                version: 'proposal-1',
                name: 'Social choice',
                description: 'Choose whether to stay home',
                root_module_id: 'social_choice_module',
                agent_type_ids: ['person'],
                place_ids: [],
                source:
                  'OpenAI CLI proposal · model gpt-5 · prompt agent-behavior-proposal-v2 · awaiting human confirmation',
                status: 'blocked',
              },
            ],
            modules: [
              {
                id: 'social_choice_module',
                version: 'proposal-1',
                name: 'Social choice',
                description: '',
                entry_node: 'decide',
                nodes: [
                  {
                    id: 'decide',
                    label: 'Decide',
                    kind: 'decision',
                    description: '',
                    target_module_id: null,
                  },
                  {
                    id: 'stay_home',
                    label: 'Stay home',
                    kind: 'terminal',
                    description: '',
                    target_module_id: null,
                  },
                ],
                edges: [
                  {
                    id: 'stay_home_edge',
                    from_node: 'decide',
                    to_node: 'stay_home',
                    label: 'Stay home',
                    condition: '',
                    decision_id: null,
                    evidence_edge_id: null,
                  },
                ],
                source:
                  'OpenAI CLI proposal · model gpt-5 · prompt agent-behavior-proposal-v2 · awaiting human confirmation',
                status: 'blocked',
              },
            ],
          },
          decision_inputs: [
            {
              tree_id: 'social_choice',
              module_id: 'social_choice_module',
              edge_id: 'stay_home_edge',
              source_feature_ids: ['age'],
              outcome: 'Stay home',
              population_scope: 'people represented by the person agent type',
              place_scope: 'country',
              time_scope: 'day of week',
              decision_id: null,
              evidence_edge_id: null,
            },
          ],
          evidence_requirements: [
            {
              id: 'routine-workday-work',
              kind: 'routine_schedule',
              status: 'missing',
              target_id: 'workday.work',
              source_feature_ids: ['age', 'occupation'],
              outcome: 'Work at assigned workplace',
              population_scope: 'agent type person',
              place_scope: 'global',
              time_scope: 'weekly schedule',
              accepted_bases: ['measured', 'user_defined'],
              required_fields: [
                'days',
                'start_time',
                'end_time',
                'place_ids',
                'role_ids',
                'source_title_or_human_confirmation',
              ],
              matched_evidence_ids: [],
              message: 'Need a complete observed or explicitly user-defined schedule',
            },
            {
              id: 'decision-social_choice-social_choice_module-stay_home_edge',
              kind: 'decision_probability',
              status: 'missing',
              target_id: 'social_choice.social_choice_module.stay_home_edge',
              source_feature_ids: ['age'],
              outcome: 'Stay home',
              population_scope: 'people represented by the person agent type',
              place_scope: 'country',
              time_scope: 'day of week',
              accepted_bases: ['measured_joint', 'fitted_model'],
              required_fields: [
                'trait_and_outcome_joint_rows',
                'sample_size',
                'confidence_interval',
                'source',
                'source_date',
              ],
              matched_evidence_ids: [],
              message: 'Need measured joint data covering every factor',
            },
          ],
        };
      },
      async confirmProposal(draft) {
        const state = window as unknown as { behaviorConfirmations: number };
        Object.assign(window, {
          behaviorConfirmations: state.behaviorConfirmations + 1,
          confirmedBehaviorProposal: draft,
        });
      },
    });
  });

  await page.getByLabel('Proposal request').fill('Create work behavior from registry data');
  await page.getByRole('button', { name: 'Propose from imported data' }).click();

  const confirm = page.getByRole('button', { name: 'Confirm and save' });
  await expect(confirm).toBeDisabled();
  expect(
    await page.evaluate(
      () => (window as unknown as { behaviorConfirmations: number }).behaviorConfirmations,
    ),
  ).toBe(0);
  await expect(page.locator('.agent-type-proposal-audit')).toContainText(
    'agent-behavior-proposal-v2',
  );
  await expect(page.getByLabel('Registry features used')).toHaveValue('age, occupation');

  const blocked = page.locator(
    '[data-requirement-kind="decision_probability"][data-requirement-status="missing"]',
  );
  await expect(blocked).toContainText('Blocked: missing decision evidence');
  await expect(blocked).toContainText('age');
  await expect(blocked).toContainText('Stay home');
  await expect(blocked).toContainText('country');
  await expect(blocked).toContainText('day of week');
  await expect(blocked).toContainText('trait_and_outcome_joint_rows');
  await expect(blocked).toContainText('None');

  const treeJson = page.getByLabel('Decision tree drafts JSON');
  await treeJson.fill('{');
  await expect(page.locator('[data-proposal-validation]')).toContainText(
    'Decision tree drafts JSON is invalid',
  );
  await expect(confirm).toBeDisabled();
  const restoredRegistry = {
    version: 'reviewed-2',
    trees: [
      {
        id: 'social_choice',
        version: 'proposal-1',
        name: 'Social choice',
        description: 'Choose whether to stay home',
        root_module_id: 'social_choice_module',
        agent_type_ids: ['person'],
        place_ids: [],
        source: 'OpenAI CLI proposal reviewed by a human',
        status: 'blocked',
      },
    ],
    modules: [
      {
        id: 'social_choice_module',
        version: 'proposal-1',
        name: 'Social choice',
        description: '',
        entry_node: 'decide',
        nodes: [
          {
            id: 'decide',
            label: 'Decide',
            kind: 'decision',
            description: '',
            target_module_id: null,
          },
          {
            id: 'stay_home',
            label: 'Stay home',
            kind: 'terminal',
            description: '',
            target_module_id: null,
          },
        ],
        edges: [
          {
            id: 'stay_home_edge',
            from_node: 'decide',
            to_node: 'stay_home',
            label: 'Stay home',
            condition: '',
            decision_id: null,
            evidence_edge_id: null,
          },
        ],
        source: 'OpenAI CLI proposal reviewed by a human',
        status: 'blocked',
      },
    ],
  };
  await treeJson.fill(JSON.stringify(restoredRegistry, null, 2));

  const inputPlans = page.getByLabel('Decision input plans JSON');
  const editedInputPlans = JSON.parse(await inputPlans.inputValue()) as Array<{
    outcome: string;
  }>;
  editedInputPlans[0].outcome = 'Stay home during the observed period';
  await inputPlans.fill(JSON.stringify(editedInputPlans, null, 2));

  const routine = page.locator('.agent-type-proposal-routine');
  await routine.getByLabel('Evidence status').selectOption('user_defined');
  await routine.getByLabel('monday').check();
  await routine.getByLabel('tuesday').check();
  await routine.getByLabel('Start time').fill('09:00');
  await routine.getByLabel('End time').fill('17:00');
  await routine.getByLabel('Place IDs').fill('assigned_workplace');
  await routine.getByLabel('Role IDs').fill('worker');

  await expect(
    page.locator('[data-requirement-kind="routine_schedule"][data-requirement-status="matched"]'),
  ).toContainText('Matched routine schedule');
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByRole('status')).toContainText('Proposal confirmed and saved');

  const result = await page.evaluate(() => {
    const state = window as unknown as {
      behaviorConfirmations: number;
      confirmedBehaviorProposal: {
        schema_version: string;
        routine_drafts: Array<{
          evidence: { status: string };
          steps: Array<{
            schedule: {
              days: string[];
              start_time: string;
              end_time: string;
              place_ids: string[];
              role_ids: string[];
            };
          }>;
        }>;
        decision_tree_drafts: { version: string; trees: Array<{ status: string }> };
        decision_inputs: Array<{ outcome: string }>;
        evidence_requirements: Array<{ kind: string; status: string }>;
      };
    };
    return {
      behaviorConfirmations: state.behaviorConfirmations,
      confirmedBehaviorProposal: state.confirmedBehaviorProposal,
    };
  });
  expect(result.behaviorConfirmations).toBe(1);
  expect(result.confirmedBehaviorProposal.schema_version).toBe('2');
  expect(result.confirmedBehaviorProposal.routine_drafts[0].evidence.status).toBe('user_defined');
  expect(result.confirmedBehaviorProposal.routine_drafts[0].steps[0].schedule).toEqual({
    days: ['monday', 'tuesday'],
    start_time: '09:00',
    end_time: '17:00',
    ends_next_day: false,
    place_ids: ['assigned_workplace'],
    role_ids: ['worker'],
  });
  expect(result.confirmedBehaviorProposal.decision_tree_drafts.version).toBe('reviewed-2');
  expect(result.confirmedBehaviorProposal.decision_tree_drafts.trees[0].status).toBe('blocked');
  expect(result.confirmedBehaviorProposal.decision_inputs[0].outcome).toBe(
    'Stay home during the observed period',
  );
  expect(result.confirmedBehaviorProposal.evidence_requirements).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ kind: 'routine_schedule', status: 'matched' }),
      expect.objectContaining({ kind: 'decision_probability', status: 'missing' }),
    ]),
  );
});
