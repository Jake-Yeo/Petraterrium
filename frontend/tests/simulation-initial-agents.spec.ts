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
            age: 40,
            relationship: 'self',
            agent_types: ['BusinessAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-sam',
            age: 41,
            relationship: 'spouse',
            agent_types: ['WorkerAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-mira',
            age: 4,
            relationship: 'daughter',
            agent_types: ['StudentAgent', 'FamilyMember'],
          },
          {
            agent_id: 'agent-noah',
            age: 6,
            relationship: 'son',
            agent_types: ['StudentAgent', 'FamilyMember'],
          },
        ],
      },
      family_relationships: [
        {
          target_agent_id: 'agent-sam',
          relationship: 'spouse',
          age: 41,
          weight: 0.95,
        },
      ],
      traits: { big_five_extraversion: 0.72 },
      initial_states: { health: '0.9', location: 'home:household-1' },
      education_profile: {
        years_of_education: 16,
        isced_level: 6,
        country_label: "Bachelor's degree",
        country_code: 'CA',
        specialization: 'business',
        specialization_threshold_years: 12,
        specialization_status: 'present',
        provenance: {
          status: 'measured_marginal',
          source: 'Imported Canadian education mapping',
          source_version: '2023-v1',
          source_date: '2023-12-31',
          url: null,
          place: 'CA',
          population: 'Canadian residents',
          language: 'en',
          original_title: null,
          english_title: null,
          search_source: 'Statistics Canada',
          uncertainty: 0.04,
          default_reason: null,
        },
      },
      state_vector: {
        catalog_version: 'agent-state-core-v1',
        values: [
          {
            state_id: 'health',
            value: 0.9,
            status: 'present',
            evidence: {
              status: 'simulated',
              source: 'Initial population materialization',
              source_version: 'v1',
              source_date: null,
              url: null,
              place: 'CA',
              population: 'Synthetic agent',
              language: null,
              original_title: null,
              english_title: null,
              search_source: null,
              uncertainty: 0,
              default_reason: null,
            },
          },
        ],
      },
      finances: {
        currency: 'CAD',
        status: 'measured_joint',
        source_distribution_id: 'ca-finance-2023',
        source_cell_id: 'owner-40',
        money: null,
        income: null,
        expenses: null,
        savings: null,
        debt: null,
        evidence: null,
        formula: 'money[t+1] = money[t] + wages + business_income + transfers - expenses',
      },
      occupation: 'Founder',
      health: '0.9',
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
    const financeEvidence = {
      status: 'measured_joint',
      source: 'Imported Canadian finance joint table',
      source_version: '2023-v1',
      source_date: '2023-12-31',
      url: null,
      place: 'CA',
      population: 'Canadian residents',
      language: 'en',
      original_title: null,
      english_title: null,
      search_source: 'Statistics Canada',
      uncertainty: 0.06,
      default_reason: null,
      currency: 'CAD',
    };
    detail.finances.evidence = financeEvidence;
    detail.finances.money = { value: 40000, evidence: financeEvidence };
    detail.finances.income = { value: 125000, evidence: financeEvidence };
    detail.finances.expenses = { value: 70000, evidence: financeEvidence };
    detail.finances.savings = { value: 80000, evidence: financeEvidence };
    detail.finances.debt = { value: 20000, evidence: financeEvidence };
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
        evidence_summary: {
          country_agent_counts: { Canada: 1 },
          region_agent_counts: { 'Northern America': 1 },
          fields: {
            age: {
              measured: [],
              own_country_inherited: ['Canada'],
              regional_imputed: [],
              estimated: [],
            },
            sex: {
              measured: [],
              own_country_inherited: ['Canada'],
              regional_imputed: [],
              estimated: [],
            },
            education: {
              measured: [],
              own_country_inherited: ['Canada'],
              regional_imputed: [],
              estimated: [],
            },
            occupation: {
              measured: [],
              own_country_inherited: [],
              regional_imputed: [],
              estimated: ['Canada'],
            },
            personality: {
              measured: [],
              own_country_inherited: ['Canada'],
              regional_imputed: [],
              estimated: [],
            },
            values: {
              measured: [],
              own_country_inherited: [],
              regional_imputed: ['Canada'],
              estimated: [],
            },
            finance: {
              measured: [],
              own_country_inherited: ['Canada'],
              regional_imputed: [],
              estimated: [],
            },
          },
        },
      }),
      detail: async () => detail,
    };
    new InitialAgentsView(host, client);
  });

  const view = page.locator('#initial-agents-test-host');
  await expect(view.getByRole('heading', { name: 'Initial agents' })).toBeVisible();
  const evidenceSummary = view.getByRole('region', { name: 'Global population evidence' });
  await expect(evidenceSummary).toContainText('Canada1');
  await expect(evidenceSummary).toContainText('Northern America1');
  await expect(evidenceSummary).toContainText('Values');
  await expect(evidenceSummary).toContainText('Regional imputedCanada');
  await expect(evidenceSummary).toContainText('Occupation');
  await expect(evidenceSummary).toContainText('EstimatedCanada');
  await expect(view.getByRole('button', { name: /Open agent-avery/ })).toContainText(
    'BusinessAgent',
  );
  await view.getByLabel('Agent type').selectOption('WorkerAgent');
  await expect(view).toContainText('No initial agents match');
  await view.getByRole('button', { name: 'Reset filters' }).click();
  await view.getByRole('button', { name: /Open agent-avery/ }).focus();
  await page.keyboard.press('Enter');

  await expect(view.getByRole('heading', { name: 'agent-avery' })).toBeVisible();
  await expect(view).toContainText('Founder');
  await expect(view).toContainText("Bachelor's degree");
  await expect(view.getByRole('region', { name: 'Household household-1' })).toContainText(
    'agent-mira',
  );
  await expect(view.getByRole('region', { name: 'Household household-1' })).toContainText(
    'agent-noah',
  );
  await expect(view.getByRole('button', { name: 'Open Business weekday routine' })).toBeVisible();
  await expect(
    view.getByRole('button', { name: 'Open Business social decisions decision tree' }),
  ).toBeVisible();
  const interactionContext = view.getByRole('region', { name: 'Pre-run interaction context' });
  await expect(interactionContext).toContainText('agent-sam');
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
      education_profile: {
        years_of_education: null,
        isced_level: null,
        country_label: 'Years of education unavailable',
        country_code: 'CA',
        specialization: null,
        specialization_threshold_years: 40,
        specialization_status: 'awaiting_data',
        provenance: {
          status: 'unknown',
          source: 'No imported country education mapping',
          source_version: 'unavailable',
          source_date: null,
          url: null,
          place: 'CA',
          population: 'No represented population',
          language: null,
          original_title: null,
          english_title: null,
          search_source: null,
          uncertainty: 1,
          default_reason: 'Education data is missing',
        },
      },
      state_vector: { catalog_version: 'agent-state-core-v1', values: [] },
      finances: {
        currency: 'XXX',
        status: 'unknown',
        source_distribution_id: null,
        source_cell_id: null,
        money: null,
        income: null,
        expenses: null,
        savings: null,
        debt: null,
        evidence: null,
        formula: 'money[t+1] = money[t] + income - expenses',
      },
      occupation: null,
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
    const missingFinanceEvidence = {
      status: 'unknown',
      source: 'No matching imported finance distribution',
      source_version: 'unavailable',
      source_date: null,
      url: null,
      place: 'CA',
      population: 'No represented population',
      language: null,
      original_title: null,
      english_title: null,
      search_source: null,
      uncertainty: 1,
      default_reason: 'Finance data is missing',
      currency: 'XXX',
    };
    detail.finances.evidence = missingFinanceEvidence;
    detail.finances.money = { value: null, evidence: missingFinanceEvidence };
    detail.finances.income = { value: null, evidence: missingFinanceEvidence };
    detail.finances.expenses = { value: null, evidence: missingFinanceEvidence };
    detail.finances.savings = { value: null, evidence: missingFinanceEvidence };
    detail.finances.debt = { value: null, evidence: missingFinanceEvidence };
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
  await view.getByRole('button', { name: /Open agent-one/ }).click();
  const interactions = view.getByRole('region', { name: 'Pre-run interaction context' });
  await expect(interactions).toContainText('No program');
  await expect(interactions).toContainText('No confirmed interaction program exists');
  await expect(interactions).toContainText(
    'No interaction frequency or history exists before a run',
  );
});
