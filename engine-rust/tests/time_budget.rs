use petraterrium_engine::agent_types::{
    ActionEvent, ActionTimeReceipt, AgentProgramRequest, DurationDistribution,
    InProgressTimedAction, ProbabilityProvenance, SampledTimedAction, TimedActionDefinition,
};
use petraterrium_engine::agents::run;
use petraterrium_engine::time_budget::{
    allocate_tick, sample_duration_hours, scale_probability_to_tick, summarize_daily_time,
    validate_tick_budget,
};
use serde_json::json;
use std::collections::BTreeMap;

fn provenance() -> ProbabilityProvenance {
    ProbabilityProvenance {
        source: "FAKE time-use diary fixture".to_owned(),
        version: "fixture-v1".to_owned(),
        status: "measured".to_owned(),
        uncertainty: 0.05,
        ..ProbabilityProvenance::default()
    }
}

fn duration(minimum: f64, median: f64, maximum: f64) -> DurationDistribution {
    DurationDistribution {
        duration_min_hours: minimum,
        duration_median_hours: median,
        duration_max_hours: maximum,
        shape: "triangular".to_owned(),
        shape_parameters: BTreeMap::new(),
        provenance: provenance(),
    }
}

fn definition(id: &str, priority: i32, passive: bool) -> TimedActionDefinition {
    TimedActionDefinition {
        action_id: id.to_owned(),
        category: id.to_owned(),
        duration: duration(0.1, 0.5, 1.0),
        duration_overrides: vec![],
        location_place_index_by_agent: vec![],
        priority,
        passive,
        interruptibility: "interruptible".to_owned(),
        interruption_outcome: "defer".to_owned(),
        emergency_interruptions: vec![],
    }
}

fn event(action: &str, tick: u64) -> ActionEvent {
    ActionEvent {
        tick,
        agent_index: 0,
        place_index: 0,
        action: action.to_owned(),
        rule_index: 0,
        probability: 1.0,
        draw: 0.0,
        provenance: provenance(),
    }
}

fn sampled(action: &str, priority: i32, sampled_duration_hours: f64) -> SampledTimedAction {
    SampledTimedAction {
        definition: definition(action, priority, false),
        event: event(action, 1),
        occurrence_index: 0,
        sampled_duration_hours,
        remaining_duration_hours: sampled_duration_hours,
        location_place_index: None,
        emit_event: true,
    }
}

#[test]
fn duration_sampling_is_seeded_by_agent_and_occurrence_and_stays_inside_the_range() {
    let distribution = duration(0.1, 0.5, 1.0);
    let first = sample_duration_hours(&distribution, 42, 0, "read", 0).unwrap();
    let repeated = sample_duration_hours(&distribution, 42, 0, "read", 0).unwrap();
    let other_agent = sample_duration_hours(&distribution, 42, 1, "read", 0).unwrap();
    let other_occurrence = sample_duration_hours(&distribution, 42, 0, "read", 1).unwrap();
    let other_seed = sample_duration_hours(&distribution, 43, 0, "read", 0).unwrap();

    assert_eq!(first, repeated);
    assert!((0.1..=1.0).contains(&first));
    assert_ne!(first, other_agent);
    assert_ne!(first, other_occurrence);
    assert_ne!(first, other_seed);
}

#[test]
fn priority_allocation_uses_sampled_durations_and_defers_the_first_action_that_does_not_fit() {
    let result = allocate_tick(
        1,
        1.0,
        None,
        vec![
            sampled("apply", 4, 0.2),
            sampled("snack", 3, 0.3),
            sampled("read", 2, 0.5),
            sampled("gym", 1, 1.0),
        ],
        "idle",
    )
    .unwrap();

    assert_eq!(
        result
            .receipt
            .primary_actions
            .iter()
            .map(|item| item.action.as_str())
            .collect::<Vec<_>>(),
        vec!["apply", "snack", "read"]
    );
    assert_eq!(result.deferred[0].event.action, "gym");
    assert!((result.receipt.used_hours - 1.0).abs() < 1e-12);
    assert_eq!(result.receipt.remaining_hours, 0.0);
}

#[test]
fn sampled_total_controls_fit_even_when_the_medians_would_fit() {
    let mut first = sampled("first", 2, 0.7);
    first.definition.duration = duration(0.1, 0.2, 0.8);
    let mut second = sampled("second", 1, 0.6);
    second.definition.duration = duration(0.1, 0.2, 0.8);

    let result = allocate_tick(1, 1.0, None, vec![first, second], "idle").unwrap();

    assert_eq!(result.receipt.primary_actions.len(), 1);
    assert_eq!(result.deferred.len(), 1);
    assert_eq!(result.deferred[0].event.action, "second");
}

#[test]
fn long_actions_continue_without_resampling_and_passive_actions_do_not_consume_budget() {
    let mut sleep = sampled("sleep", 2, 8.0);
    sleep.definition.duration = duration(6.0, 8.0, 10.0);
    let mut active: Option<InProgressTimedAction> = None;
    let mut receipts = Vec::new();
    for tick in 1..=8 {
        let candidates = if tick == 1 {
            vec![sleep.clone()]
        } else {
            vec![]
        };
        let result = allocate_tick(tick, 1.0, active, candidates, "idle").unwrap();
        receipts.push(result.receipt);
        active = result.active_primary;
    }
    assert!(active.is_none());
    assert!(receipts.iter().all(|receipt| receipt.used_hours == 1.0));

    let mut music = sampled("music", 1, 0.75);
    music.definition.passive = true;
    let passive = allocate_tick(9, 1.0, None, vec![music], "idle").unwrap();
    assert_eq!(passive.receipt.used_hours, 0.0);
    assert_eq!(passive.receipt.remaining_hours, 1.0);
    assert_eq!(passive.receipt.passive_actions.len(), 1);
}

#[test]
fn higher_priority_actions_record_interruptions_and_preserve_remaining_time_for_defer() {
    let mut read = sampled("read", 1, 3.0);
    read.definition.duration = duration(1.0, 2.0, 3.5);
    let first = allocate_tick(1, 1.0, None, vec![read], "idle").unwrap();
    let second = allocate_tick(
        2,
        1.0,
        first.active_primary,
        vec![sampled("alarm", 10, 0.25)],
        "idle",
    )
    .unwrap();

    assert_eq!(second.receipt.interruptions.len(), 1);
    assert_eq!(second.receipt.interruptions[0].interrupted_action, "read");
    assert_eq!(second.receipt.interruptions[0].interrupting_action, "alarm");
    assert!(second.receipt.interruptions[0].remaining_hours > 0.0);
    assert!(
        second
            .deferred
            .iter()
            .any(|item| item.event.action == "read")
    );
}

#[test]
fn explicit_over_budget_validation_names_actions_and_sampled_hours() {
    let receipt = ActionTimeReceipt {
        action: "work".to_owned(),
        category: "work".to_owned(),
        occurrence_index: 0,
        duration: duration(0.5, 0.75, 1.0),
        sampled_duration_hours: 0.75,
        hours_this_tick: 0.75,
        remaining_hours: 0.0,
        status: "completed".to_owned(),
        passive: false,
    };
    let second = ActionTimeReceipt {
        action: "eat".to_owned(),
        hours_this_tick: 0.5,
        sampled_duration_hours: 0.5,
        ..receipt.clone()
    };

    let error = validate_tick_budget(1.0, &[receipt, second]).unwrap_err();
    assert_eq!(error.code, "TICK_TIME_BUDGET_EXCEEDED");
    assert!(error.message.contains("work=0.75"));
    assert!(error.message.contains("eat=0.5"));
}

#[test]
fn a_complete_day_accounts_for_exactly_twenty_four_hours_including_idle() {
    let receipts = (1..=24)
        .map(|tick| {
            allocate_tick(tick, 1.0, None, vec![], "idle")
                .unwrap()
                .receipt
        })
        .collect::<Vec<_>>();

    let days = summarize_daily_time(&receipts, 0.0);

    assert_eq!(days.len(), 1);
    assert!(days[0].complete);
    assert!((days[0].accounted_hours - 24.0).abs() < 1e-12);
    assert_eq!(days[0].category_hours["idle"], 24.0);
}

fn runtime_value(ticks: u64) -> serde_json::Value {
    json!({
        "seed": 77,
        "ticks": ticks,
        "tick_hours": 1.0,
        "start_hour": 0.0,
        "places": [{"id": "global", "kind": "region"}],
        "agents": {
            "agent_ids": ["agent-0"],
            "module": ["idle"],
            "state": ["idle"],
            "place": [0]
        },
        "modules": [{
            "id": "idle",
            "entry_state": "idle",
            "exit_states": ["idle"],
            "states": ["idle"],
            "transitions": []
        }],
        "meaningful_actions": [{
            "id": "sleep",
            "rules": [{
                "conditions": [{"input": "context.hour", "operator": "eq", "value": 0.0}],
                "probability": 1.0,
                "provenance": {
                    "source": "FAKE sleep diary fixture",
                    "version": "fixture-v1",
                    "status": "measured",
                    "uncertainty": 0.05
                }
            }]
        }],
        "state_dynamics": {
            "time_execution": {
                "idle_category": "idle",
                "actions": [{
                    "action_id": "sleep",
                    "category": "sleep",
                    "duration": {
                        "duration_min_hours": 7.5,
                        "duration_median_hours": 8.0,
                        "duration_max_hours": 8.5,
                        "shape": "triangular",
                        "shape_parameters": {},
                        "provenance": {
                            "source": "FAKE sleep diary fixture",
                            "version": "fixture-v1",
                            "status": "measured",
                            "uncertainty": 0.05
                        }
                    },
                    "priority": 10,
                    "passive": false,
                    "interruptibility": "interruptible",
                    "interruption_outcome": "defer",
                    "emergency_interruptions": []
                }]
            }
        }
    })
}

fn runtime_request(ticks: u64) -> AgentProgramRequest {
    serde_json::from_value(runtime_value(ticks)).unwrap()
}

#[test]
fn agent_runtime_persists_one_sample_across_ticks_and_records_daily_accounting() {
    let first = run(runtime_request(24)).unwrap();
    let repeated = run(runtime_request(24)).unwrap();

    assert_eq!(first.time_ticks, repeated.time_ticks);
    let sleep_ticks = first
        .time_ticks
        .iter()
        .filter(|receipt| {
            receipt
                .primary_actions
                .iter()
                .any(|action| action.action == "sleep")
        })
        .collect::<Vec<_>>();
    assert!(sleep_ticks.len() >= 8);
    let sampled = sleep_ticks[0].primary_actions[0].sampled_duration_hours;
    assert!(
        sleep_ticks
            .iter()
            .all(|receipt| { receipt.primary_actions[0].sampled_duration_hours == sampled })
    );
    assert_eq!(first.daily_time.len(), 1);
    assert!(first.daily_time[0].complete);
    assert!((first.daily_time[0].accounted_hours - 24.0).abs() < 1e-9);
    assert!(first.daily_time[0].category_hours["sleep"] >= 7.5);
}

#[test]
fn runtime_rejects_a_timed_program_that_omits_an_action_distribution() {
    let mut request = runtime_value(1);
    request["state_dynamics"]["time_execution"]["actions"] = json!([]);
    let request = serde_json::from_value(request).unwrap();

    let error = run(request).unwrap_err();

    assert_eq!(error.code, "MISSING_ACTION_DURATION");
    assert!(error.message.contains("sleep"));
}

#[test]
fn time_state_and_daily_accounting_are_checkpoint_equivalent() {
    let linear = run(runtime_request(24)).unwrap();
    let first = run(runtime_request(5)).unwrap();
    let mut resumed = runtime_value(19);
    resumed["continuation"] = serde_json::to_value(first.continuation).unwrap();
    let second = run(serde_json::from_value(resumed).unwrap()).unwrap();

    assert_eq!(second.daily_time, linear.daily_time);
    assert_eq!(
        second.continuation.time_execution.daily_time,
        linear.daily_time
    );
    assert_eq!(
        second.continuation.time_execution.active_primary,
        linear.continuation.time_execution.active_primary
    );
    assert_eq!(
        second.continuation.time_execution.occurrence_counts,
        linear.continuation.time_execution.occurrence_counts
    );
}

#[test]
fn probability_time_units_scale_to_the_configured_tick() {
    let one_hour = scale_probability_to_tick(0.24, Some(24.0), 1.0).unwrap();
    let two_hours = scale_probability_to_tick(0.24, Some(24.0), 2.0).unwrap();

    assert!((one_hour - (1.0 - 0.76_f64.powf(1.0 / 24.0))).abs() < 1e-12);
    assert!((two_hours - (1.0 - 0.76_f64.powf(2.0 / 24.0))).abs() < 1e-12);
    assert!(two_hours > one_hour);
    assert_eq!(scale_probability_to_tick(0.24, None, 2.0).unwrap(), 0.24);
}

#[test]
fn exact_hour_conditions_match_the_tick_interval_that_contains_the_hour() {
    let mut request = runtime_value(12);
    request["tick_hours"] = json!(2.0);
    request["meaningful_actions"][0]["id"] = json!("breakfast");
    request["meaningful_actions"][0]["rules"][0]["conditions"][0]["value"] = json!(7.0);
    request["state_dynamics"]["time_execution"]["actions"][0]["action_id"] = json!("breakfast");
    request["state_dynamics"]["time_execution"]["actions"][0]["duration"] = json!({
        "duration_min_hours": 0.1,
        "duration_median_hours": 0.2,
        "duration_max_hours": 0.3,
        "shape": "triangular",
        "shape_parameters": {},
        "provenance": {
            "source": "FAKE breakfast diary fixture",
            "version": "fixture-v1",
            "status": "measured",
            "uncertainty": 0.05
        }
    });

    let result = run(serde_json::from_value(request).unwrap()).unwrap();

    assert_eq!(result.events.len(), 1);
    assert_eq!(result.events[0].action, "breakfast");
    assert_eq!(result.events[0].tick, 4);
}

#[test]
fn runtime_emits_time_receipts_only_for_declared_timeline_agents() {
    let mut request = runtime_value(24);
    request["agents"]["agent_ids"] = json!(["agent-0", "agent-1"]);
    request["agents"]["module"] = json!(["idle", "idle"]);
    request["agents"]["state"] = json!(["idle", "idle"]);
    request["agents"]["place"] = json!([0, 0]);
    request["state_dynamics"]["time_execution"]["receipt_agent_indices"] = json!([0]);

    let result = run(serde_json::from_value(request).unwrap()).unwrap();

    assert!(
        result
            .time_ticks
            .iter()
            .all(|receipt| receipt.agent_index == 0)
    );
    assert!(result.daily_time.iter().all(|day| day.agent_index == 0));
    assert_eq!(result.continuation.time_execution.active_primary.len(), 2);
    assert_eq!(
        result.continuation.time_execution.occurrence_counts.len(),
        2
    );
}
