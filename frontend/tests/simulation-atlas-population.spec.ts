import { expect, test } from '@playwright/test';

test('atlas generator selects a place and preserves evidence coverage', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { AtlasPopulationGenerator } = await import(
      '/src/simulation/atlas-population.ts'
    );
    Object.assign(window, { atlasPopulationRequest: null });
    document.body.innerHTML = '<main id="atlas-population-test"></main>';
    const generator = new AtlasPopulationGenerator(
      document.querySelector<HTMLElement>('#atlas-population-test')!,
      {
        agentTypes: () => [
          { id: 'person', name: 'Person' },
          { id: 'adult', name: 'Adult' },
          { id: 'household_reference', name: 'Household reference' },
        ],
        client: {
          async places() {
            return [
              { level: 'country', place: 'CN', label: 'China' },
              { level: 'city', place: '1816670', label: 'Beijing, CN' },
            ];
          },
          async materialize(request) {
            (window as unknown as { atlasPopulationRequest: unknown }).atlasPopulationRequest =
              request;
            return {
              selector: request.selector,
              scope: request.scope,
              materialization: {
                input_hash: 'deterministic-hash',
                population: {
                  agents: Array.from({ length: request.target_agents }, (_, index) => ({
                    agent_id: `agent-${index + 1}`,
                  })),
                },
              },
              feature_coverage: [
                {
                  feature_id: 'age',
                  measured_agents: request.target_agents,
                  imputed_agents: 0,
                  unknown_agents: 0,
                  sources: ['UN WPP'],
                },
                {
                  feature_id: 'income',
                  measured_agents: 0,
                  imputed_agents: request.target_agents,
                  unknown_agents: 0,
                  sources: ['World Bank WDI'],
                },
                {
                  feature_id: 'endurance',
                  measured_agents: 0,
                  imputed_agents: 0,
                  unknown_agents: request.target_agents,
                  sources: [],
                },
              ],
              agent_type_counts: {
                adult: request.target_agents,
                household_reference: request.target_agents / 2,
              },
              warnings: ['Household relationships remain unknown.'],
            };
          },
        },
      },
    );
    generator.mount();
  });

  const region = page.getByRole('region', { name: 'Generate population from atlas' });
  await expect(region.getByRole('heading', { name: 'Generate initial agents' })).toBeVisible();
  await expect(region.getByLabel('Agents')).toHaveValue('1000');
  await expect(region.getByLabel('Fallback type')).toHaveValue('person');
  await region.getByLabel('Place', { exact: true }).selectOption('country:CN');
  await region.getByLabel('Agents').fill('1000');
  await region.getByLabel('Seed').fill('73');
  await region.getByRole('button', { name: 'Add type rule' }).click();
  await region.getByLabel('Assigned type for rule 1').selectOption('adult');
  await region.getByLabel('Atlas field for rule 1').selectOption('age');
  await region.getByLabel('Match for rule 1').selectOption('at_least');
  await region.getByLabel('Value for rule 1').fill('18');
  await region.getByRole('button', { name: 'Add type rule' }).click();
  await region
    .getByLabel('Assigned type for rule 2')
    .selectOption('household_reference');
  await region
    .getByLabel('Atlas field for rule 2')
    .selectOption('relationship_to_reference');
  await region.getByLabel('Value for rule 2').fill('self');
  await region.getByRole('button', { name: 'Generate from atlas' }).click();
  await expect(region.getByRole('alert')).toContainText(
    'Confirm the type assignment rules before generating agents',
  );
  expect(
    await page.evaluate(
      () => (window as unknown as { atlasPopulationRequest: unknown }).atlasPopulationRequest,
    ),
  ).toBeNull();
  await region.getByLabel('Confirm these type assignment rules').check();
  await region.getByRole('button', { name: 'Generate from atlas' }).click();

  await expect(region.getByRole('status')).toContainText('1,000 agents generated for China');
  await expect(region.getByRole('status')).toContainText('1 measured features');
  await expect(region.getByRole('status')).toContainText('1 imputed features');
  await expect(region.getByRole('status')).toContainText('Missing: endurance');
  await expect(region.getByRole('status')).toContainText('adult 1,000');
  await expect(region.getByRole('status')).toContainText('household reference 500');
  await expect(region.getByRole('status')).toContainText('Household relationships remain unknown');
  expect(
    await page.evaluate(
      () => (window as unknown as { atlasPopulationRequest: unknown }).atlasPopulationRequest,
    ),
  ).toMatchObject({
    selector: { place: 'CN' },
    agent_type_id: 'person',
    type_assignment: {
      status: 'confirmed',
      fallback_agent_type_id: 'person',
      rules: [
        {
          agent_type_ids: ['adult'],
          conditions: [{ field: 'age', operator: 'at_least', value: 18 }],
        },
        {
          agent_type_ids: ['household_reference'],
          conditions: [
            { field: 'relationship_to_reference', operator: 'equals', value: 'self' },
          ],
        },
      ],
    },
  });
});
