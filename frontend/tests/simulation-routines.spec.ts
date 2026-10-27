import { expect, test } from '@playwright/test';

test('routine detail distinguishes type schedules, inheritance, evidence, and decision calls', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const modulePath = '/src/simulation/routines.ts';
    const { RoutineDetailView } = await import(modulePath);
    const host = document.createElement('section');
    host.id = 'routine-detail-test-host';
    document.body.replaceChildren(host);
    const familyDinner = {
      routine: {
        id: 'family_dinner',
        name: 'Family dinner',
        agent_type_id: 'family_man',
        description: 'Illustrative household dinner schedule.',
        evidence: {
          status: 'illustrative',
          source_title: null,
          source_date: null,
          source_uri: null,
          note: 'Example only; attach observed schedule data before treating it as measured.',
        },
        steps: [
          {
            id: 'family_dinner_at_home',
            name: 'Family dinner at home',
            activity: 'eat dinner with household members',
            schedule: {
              days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
              start_time: '18:00',
              end_time: '19:00',
              ends_next_day: false,
              place_ids: ['home'],
              role_ids: ['family_member'],
            },
            decision_tree_module_id: 'family_dinner_choice',
          },
        ],
      },
      source_type_id: 'family_man',
      inherited: true,
      explicit_override: false,
      overridden_source_type_ids: [],
    };
    const pubMeeting = {
      routine: {
        id: 'business_pub_meeting',
        name: 'Pub business meeting',
        agent_type_id: 'business_agent',
        description: 'Illustrative business meeting schedule.',
        evidence: {
          status: 'illustrative',
          source_title: null,
          source_date: null,
          source_uri: null,
          note: 'Example only; attach observed schedule data before treating it as measured.',
        },
        steps: [
          {
            id: 'meet_at_pub',
            name: 'Meet at pub',
            activity: 'meet another business agent',
            schedule: {
              days: ['friday'],
              start_time: '18:30',
              end_time: '20:30',
              ends_next_day: false,
              place_ids: ['pub'],
              role_ids: ['business_agent'],
            },
            decision_tree_module_id: 'pub_business_meeting',
          },
        ],
      },
      source_type_id: 'business_agent',
      inherited: false,
      explicit_override: false,
      overridden_source_type_ids: [],
    };
    const view = new RoutineDetailView(host, {
      onOpenDecisionTree: (moduleId: string) => {
        host.dataset.openedModule = moduleId;
      },
    });
    view.render({
      agent_type_id: 'business_agent',
      agent_type_name: 'BusinessAgent',
      routines: [familyDinner, pubMeeting],
    });
    Object.assign(window, { routineDetailView: view, familyDinner });
  });

  const detail = page.locator('#routine-detail-test-host');
  await expect(detail.getByRole('heading', { name: 'BusinessAgent routines' })).toBeVisible();
  await expect(detail).toContainText('Pub business meeting');
  await expect(detail).toContainText('Friday');
  await expect(detail).toContainText('18:30–20:30');
  await expect(detail).toContainText('pub');
  await expect(detail).toContainText('business_agent');
  await expect(detail).toContainText('Inherited from family_man');
  await expect(detail.getByText('Illustrative · not measured')).toHaveCount(2);
  await expect(detail).toContainText('attach observed schedule data');

  const openTree = detail.getByRole('button', {
    name: 'Open pub_business_meeting decision tree',
  });
  await openTree.focus();
  await page.keyboard.press('Enter');
  await expect(detail).toHaveAttribute('data-opened-module', 'pub_business_meeting');

  await page.evaluate(() => {
    const view = (window as unknown as { routineDetailView: { render: (value: unknown) => void } })
      .routineDetailView;
    const familyDinner = (window as unknown as { familyDinner: unknown }).familyDinner;
    view.render({
      agent_type_id: 'worker_agent',
      agent_type_name: 'WorkerAgent',
      routines: [familyDinner],
    });
  });

  await expect(detail.getByRole('heading', { name: 'WorkerAgent routines' })).toBeVisible();
  await expect(detail).toContainText('Family dinner');
  await expect(detail).not.toContainText('Pub business meeting');
});
