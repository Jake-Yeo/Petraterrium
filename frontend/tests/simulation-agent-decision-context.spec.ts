import { expect, test } from '@playwright/test';

test('uses typed agent context and leaves unavailable place and time inputs unknown', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { prepareAgentDecisionContext, renderDecisionContextLimitations } =
      await import('/src/simulation/agent-decision-context.ts');
    const prepared = prepareAgentDecisionContext(
      {
        agent_id: 'agent-1',
        display_name: 'Morgan Lee',
        agent_types: ['worker'],
        age: 40,
        sex: 'female',
        country: 'Canada',
        city: 'Vancouver',
        current_location: 'home:1',
        household_id: 'household-1',
        household_size: 1,
        family_status: 'household',
        location: {
          country: 'Canada',
          region: 'British Columbia',
          city: 'Vancouver',
          neighbourhood: null,
          specific_place: 'home:1',
        },
        household: null,
        family_relationships: [],
        traits: {
          region: 'north-america',
          country_id: 'CA',
          city_id: 'vancouver',
          extraversion: 0.75,
          place_attributes: { transit_access: 'high' },
          time: { hour: 18 },
          context: { weather: 'rain' },
        },
        initial_states: {
          location: 'home:1',
          place_contamination: '0.8',
          time_weekday: 'friday',
          context_crowding: 'high',
        },
        occupation: 'Engineer',
        income: 90000,
        education: 'ISCED 6',
        health: 'healthy',
        routines: [],
        decision_trees: [],
        representative_weight: 1,
      },
      {
        id: 'leave_home',
        decision_id: 'go_out',
        domain: 'social',
        from_state: 'home',
        to_state: 'outside',
        label: 'Leave home',
        formula: {
          id: 'leave_home_probability',
          name: 'Leave home probability',
          combination: 'product',
          factors: [
            {
              id: 'extraversion',
              name: 'Extraversion',
              input_kind: 'trait',
              input_key: 'extraversion',
            },
            {
              id: 'transit',
              name: 'Transit access',
              input_kind: 'place',
              input_key: 'transit_access',
            },
            {
              id: 'contamination',
              name: 'Contamination',
              input_kind: 'place',
              input_key: 'contamination',
            },
            {
              id: 'hour',
              name: 'Hour',
              input_kind: 'time',
              input_key: 'hour',
            },
            {
              id: 'weekday',
              name: 'Weekday',
              input_kind: 'time',
              input_key: 'weekday',
            },
            {
              id: 'location',
              name: 'Location',
              input_kind: 'context',
              input_key: 'location',
            },
            {
              id: 'weather',
              name: 'Weather',
              input_kind: 'context',
              input_key: 'weather',
            },
            {
              id: 'crowding',
              name: 'Crowding',
              input_kind: 'context',
              input_key: 'crowding',
            },
          ],
        },
        source: {
          kind: 'none',
          label: 'no source attached — estimated / unknown',
          reason: 'Test fixture',
        },
      },
    );
    document.body.innerHTML = '<main id="decision-context-test"></main>';
    const host = document.querySelector<HTMLElement>('#decision-context-test')!;
    renderDecisionContextLimitations(host, prepared.limitations);
    host.dataset.request = JSON.stringify(prepared.request);
  });

  const host = page.locator('#decision-context-test');
  const request = JSON.parse((await host.getAttribute('data-request')) ?? '{}');
  expect(request.place).toEqual({
    region_id: 'north-america',
    country_id: 'CA',
    city_id: 'vancouver',
  });
  expect(request.traits).toEqual({
    region: 'north-america',
    country_id: 'CA',
    city_id: 'vancouver',
    extraversion: 0.75,
  });
  expect(request.place_attributes).toEqual({ transit_access: 'high' });
  expect(request.time).toEqual({ hour: 18 });
  expect(request.context).toEqual({
    location: 'home:1',
    place_contamination: '0.8',
    time_weekday: 'friday',
    context_crowding: 'high',
    weather: 'rain',
  });
  await expect(host.getByRole('note', { name: 'Preview limitations' })).toContainText(
    'contamination',
  );
  await expect(host.getByRole('note', { name: 'Preview limitations' })).toContainText('weekday');
  await expect(host.getByRole('note', { name: 'Preview limitations' })).toContainText('crowding');
  await expect(host.getByRole('note', { name: 'Preview limitations' })).not.toContainText(
    'transit_access',
  );
});
