import { expect, test } from '@playwright/test';

test('place tree opens recorded agent location, history, state, and co-location detail', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const { LocationsView } = await import('/src/simulation/locations.ts');
    const places = [
      {
        id: 'canada',
        name: 'Canada',
        level: 'country' as const,
        parent_id: null,
        child_ids: ['british-columbia'],
        current_agent_count: 0,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: null,
        state: { tax_rate: 0.2 },
      },
      {
        id: 'british-columbia',
        name: 'British Columbia',
        level: 'state' as const,
        parent_id: 'canada',
        child_ids: ['vancouver'],
        current_agent_count: 0,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: null,
        state: { tax_rate: 0.25 },
      },
      {
        id: 'vancouver',
        name: 'Vancouver',
        level: 'city' as const,
        parent_id: 'british-columbia',
        child_ids: ['kitsilano'],
        current_agent_count: 0,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: null,
        state: { air_quality: 0.8 },
      },
      {
        id: 'kitsilano',
        name: 'Kitsilano',
        level: 'district' as const,
        parent_id: 'vancouver',
        child_ids: ['home-1'],
        current_agent_count: 0,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: null,
        state: {},
      },
      {
        id: 'home-1',
        name: 'Home',
        level: 'building' as const,
        parent_id: 'kitsilano',
        child_ids: ['living-room', 'kitchen'],
        current_agent_count: 0,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: null,
        state: { contamination: 0.1 },
      },
      {
        id: 'living-room',
        name: 'Living room',
        level: 'room' as const,
        parent_id: 'home-1',
        child_ids: [],
        current_agent_count: 2,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: 5,
        state: { contamination: 0.3, occupancy: 2, crowd_density: 0.4 },
      },
      {
        id: 'kitchen',
        name: 'Kitchen',
        level: 'room' as const,
        parent_id: 'home-1',
        child_ids: [],
        current_agent_count: 1,
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: 3,
        state: { occupancy: 1, crowd_density: 1 / 3 },
      },
    ].map((place) => ({
      ...place,
      state_source:
        place.id === 'living-room' || place.id === 'kitchen'
          ? ('rust_numeric_core' as const)
          : ('location_registry' as const),
      runtime_place_id:
        place.id === 'living-room' || place.id === 'kitchen'
          ? `runtime-${place.id}`
          : null,
      runtime_place_kind:
        place.id === 'living-room' || place.id === 'kitchen' ? 'home' : null,
      evidence:
        place.id === 'living-room'
          ? {
              source_title: 'Measured household place panel',
              source_version: '2025',
              source_date: '2025-04-01',
              licence: 'Test',
              evidence_id: 'home-place-2025',
              status: 'measured' as const,
              uncertainty: 0.05,
            }
          : null,
      decision_trees:
        place.id === 'living-room'
          ? [
              {
                tree_id: 'family-dinner',
                tree_name: 'Family dinner',
                available: true,
                required_place_kinds: ['home'],
                reason: null,
              },
              {
                tree_id: 'bar-talk',
                tree_name: 'Bar talk',
                available: false,
                required_place_kinds: ['bar'],
                reason: 'Bar talk unavailable — agent is at Living room',
              },
            ]
          : [],
    }));
    const agents = [
      { agent_id: 'avery', display_name: 'Avery', current_location_id: 'living-room' },
      { agent_id: 'sam', display_name: 'Sam', current_location_id: 'living-room' },
      { agent_id: 'mira', display_name: 'Mira', current_location_id: 'kitchen' },
    ];
    const detail = (agentId: string) => {
      const agent = agents.find((item) => item.agent_id === agentId)!;
      const current = places.find((place) => place.id === agent.current_location_id)!;
      const coLocated = agents.filter(
        (item) =>
          item.agent_id !== agentId && item.current_location_id === agent.current_location_id,
      );
      return {
        agent_id: agent.agent_id,
        display_name: agent.display_name,
        current_location: current,
        ancestry:
          current.id === 'living-room'
            ? places.filter((place) => place.id !== 'kitchen')
            : places.filter((place) => place.id !== 'living-room'),
        history:
          agentId === 'avery'
            ? [
                {
                  tick: 4,
                  agent_id: 'avery',
                  from_location_id: 'kitchen',
                  to_location_id: 'living-room',
                  route_location_ids: ['kitchen', 'home-1', 'living-room'],
                },
              ]
            : [],
        co_located_agents: coLocated,
        elsewhere_agents: agents.filter(
          (item) =>
            item.agent_id !== agentId &&
            item.current_location_id !== agent.current_location_id,
        ),
        effective_place_state: {
          tax_rate: 0.25,
          air_quality: 0.8,
          contamination: current.id === 'living-room' ? 0.3 : 0.1,
          occupancy: current.current_agent_count,
          crowd_density:
            current.capacity === null ? 0 : current.current_agent_count / current.capacity,
        },
      };
    };
    const host = document.createElement('main');
    host.id = 'locations-test-host';
    document.body.replaceChildren(host);
    new LocationsView(host, {
      snapshot: async () => ({
        run_id: 'run-1',
        tick: 4,
        root_location_ids: ['canada'],
        places,
        agents,
      }),
      agentDetail: async (agentId: string) => detail(agentId),
    });
  });

  const view = page.locator('#locations-test-host');
  await expect(view.getByRole('heading', { name: 'Locations' })).toBeVisible();
  await expect(view.getByRole('treeitem')).toHaveCount(2);
  await view.getByRole('button', { name: 'Expand British Columbia' }).click();
  await view.getByRole('button', { name: 'Expand Vancouver' }).click();
  await view.getByRole('button', { name: 'Expand Kitsilano' }).click();
  await view.getByRole('button', { name: 'Expand Home' }).click();
  await expect(view.getByRole('treeitem')).toHaveCount(7);

  await view.getByRole('button', { name: /Living room room/ }).click();
  const placeDetail = view.getByRole('region', { name: 'Living room location detail' });
  await expect(placeDetail).toContainText('2');
  await expect(placeDetail).toContainText('Contamination');
  await expect(placeDetail).toContainText('Crowd Density');
  await expect(placeDetail).toContainText('Occupancy');
  await expect(placeDetail.getByRole('heading', { name: 'Live Rust place state' })).toBeVisible();
  await expect(placeDetail).toContainText('runtime-living-room');
  await expect(placeDetail).toContainText('Measured household place panel');
  await expect(placeDetail).toContainText('Bar talk unavailable — agent is at Living room');
  await expect(placeDetail.getByRole('button', { name: /Avery/ })).toBeVisible();
  await expect(placeDetail).not.toContainText('Mira');

  await placeDetail.getByRole('button', { name: /Avery/ }).focus();
  await page.keyboard.press('Enter');
  const agentDetail = view.getByRole('region', { name: 'Avery location detail' });
  await expect(agentDetail).toContainText('Canada');
  await expect(agentDetail).toContainText('Living room');
  await expect(agentDetail).toContainText('Crowd Density');
  await expect(agentDetail).toContainText('Occupancy');
  await expect(
    agentDetail.getByRole('heading', { name: 'Live Rust state at current place' }),
  ).toBeVisible();
  await expect(agentDetail).toContainText('Kitchen → Living room');
  await expect(agentDetail.getByRole('button', { name: /Sam/ })).toBeVisible();
  await expect(agentDetail.getByRole('heading', { name: 'Elsewhere' })).toBeVisible();
  await expect(agentDetail).toContainText('Family dinner');
  await expect(agentDetail).toContainText('Bar talk unavailable — agent is at Living room');
  await expect(agentDetail.getByRole('button', { name: /Mira.*Elsewhere/ })).toBeVisible();

  await agentDetail.getByRole('button', { name: /Sam/ }).click();
  await expect(view.getByRole('region', { name: 'Sam location detail' })).toBeVisible();
  await view.getByRole('button', { name: 'Back to Living room' }).click();
  await expect(view.getByRole('region', { name: 'Living room location detail' })).toBeVisible();
});
