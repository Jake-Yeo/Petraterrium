import { expect, test } from '@playwright/test';

const mountEditor = async (page: Parameters<typeof test>[0]['page']) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { InitialPopulationEditor } = await import('/src/simulation/initial-population.ts');
    const evidenceId = 'ca-household-joint-2024';
    const fieldEvidence = {
      age: evidenceId,
      sex: evidenceId,
      household_composition: evidenceId,
      family_relationships: evidenceId,
    };
    const member = (
      memberId: string,
      age: number,
      sex: string,
      relationship: 'self' | 'spouse' | 'child',
      agentTypes: string[],
    ) => ({
      member_id: memberId,
      age,
      sex,
      relationship_to_reference: relationship,
      agent_types: agentTypes,
      traits: {},
      states: { health: 'healthy' },
      field_evidence: fieldEvidence,
    });
    const draft = {
      population_id: 'canada-demo',
      version: '2026-10-27',
      seed: 23,
      target_agents: 4,
      household_templates: [
        {
          template_id: 'family-40-wife-two-kids',
          place: 'CA',
          country: 'Canada',
          region: 'Northern America',
          city: 'Vancouver',
          neighbourhood: 'Kitsilano',
          latitude: 49.2684,
          longitude: -123.1683,
          weight: 1,
          evidence_id: evidenceId,
          members: [
            member('reference', 40, 'male', 'self', ['BusinessAgent', 'FamilyMan']),
            member('spouse', 39, 'female', 'spouse', ['WorkerAgent', 'FamilyMan']),
            member('child-four', 4, 'female', 'child', ['StudentAgent', 'FamilyMember']),
            member('child-six', 6, 'male', 'child', ['StudentAgent', 'FamilyMember']),
          ],
        },
      ],
      evidence: [
        {
          evidence_id: evidenceId,
          source: 'Statistics Canada household microdata',
          source_version: '2021-census-pumf-v1',
          observed_at: '2021-05-11',
          licence: 'Statistics Canada Open Licence',
          place: 'CA',
          status: 'measured_joint',
          fields: ['age', 'sex', 'household_composition', 'family_relationships'],
          uncertainty: 'Weighted public-use microdata sample',
          url: null,
        },
      ],
    };
    Object.assign(window, {
      populationValidations: 0,
      populationSaves: 0,
      savedPopulation: null,
    });
    document.body.innerHTML = '<main id="population-editor-test"></main>';
    const editor = new InitialPopulationEditor(document.querySelector('#population-editor-test')!, {
      draft,
      client: {
        async validate() {
          (window as unknown as { populationValidations: number }).populationValidations += 1;
          return { valid: true, issues: [] };
        },
        async materialize(request) {
          (window as unknown as { populationSaves: number }).populationSaves += 1;
          return {
            input_hash: `seed-${request.seed}`,
            validation: { valid: true, issues: [] },
            population: {
              population_id: request.population_id,
              version: request.version,
              seed: request.seed,
              agents: request.household_templates[0].members.map((value) => ({
                agent_id: value.member_id,
                traits: { age: value.age },
              })),
            },
            provenance: {},
          };
        },
      },
      onSaved(result) {
        (window as unknown as { savedPopulation: unknown }).savedPopulation = result;
      },
    });
    editor.mount();
  });
};

test('joint family editor shows four separate members and saves only after validation', async ({
  page,
}) => {
  await mountEditor(page);

  const editor = page.getByRole('region', { name: 'Initial population setup' });
  await expect(editor.getByRole('heading', { name: 'Initial population' })).toBeVisible();
  await expect(editor.locator('[data-household-member]')).toHaveCount(4);
  await expect(editor.getByLabel('Name for reference')).toHaveCount(0);
  await expect(editor.getByLabel('Age for reference')).toHaveValue('40');
  await expect(editor.getByLabel('Age for child-four')).toHaveValue('4');
  await expect(editor.getByLabel('Age for child-six')).toHaveValue('6');
  await expect(editor).toContainText('Measured joint');
  await expect(editor).toContainText('Statistics Canada household microdata');

  await editor.getByRole('button', { name: 'Save initial population' }).click();
  await expect(editor.getByRole('status')).toContainText('4 initial agents saved');
  expect(
    await page.evaluate(
      () => (window as unknown as { populationValidations: number }).populationValidations,
    ),
  ).toBe(1);
  expect(
    await page.evaluate(() => (window as unknown as { populationSaves: number }).populationSaves),
  ).toBe(1);
});

test('impossible household errors block save before the run can use it', async ({ page }) => {
  await mountEditor(page);

  const editor = page.getByRole('region', { name: 'Initial population setup' });
  await editor.getByLabel('Age for reference').fill('5');
  await editor.getByRole('button', { name: 'Save initial population' }).click();

  await expect(editor.getByRole('alert')).toContainText('Parent reference is younger than 16');
  expect(
    await page.evaluate(
      () => (window as unknown as { populationValidations: number }).populationValidations,
    ),
  ).toBe(0);
  expect(
    await page.evaluate(() => (window as unknown as { populationSaves: number }).populationSaves),
  ).toBe(0);
});
