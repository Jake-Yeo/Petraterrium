use crate::agent_types::{
    ActionEvent, ActionInterruptionReceipt, ActionTimeReceipt, DailyTimeAccounting,
    DurationDistribution, InProgressTimedAction, SampledTimedAction, TickTimeReceipt,
};
use crate::error::{CoreError, CoreResult};
use crate::random::DeterministicRng;
use std::collections::BTreeMap;

const EPSILON: f64 = 1e-9;

#[derive(Clone, Debug)]
pub struct TickAllocation {
    pub receipt: TickTimeReceipt,
    pub active_primary: Option<InProgressTimedAction>,
    pub deferred: Vec<SampledTimedAction>,
    pub executed_events: Vec<ActionEvent>,
}

pub fn validate_duration_distribution(
    distribution: &DurationDistribution,
    path: &str,
) -> CoreResult<()> {
    let values = [
        distribution.duration_min_hours,
        distribution.duration_median_hours,
        distribution.duration_max_hours,
    ];
    if values.iter().any(|value| !value.is_finite())
        || distribution.duration_min_hours < 0.0
        || distribution.duration_median_hours <= 0.0
        || distribution.duration_max_hours <= distribution.duration_min_hours
        || distribution.duration_min_hours > distribution.duration_median_hours
        || distribution.duration_median_hours > distribution.duration_max_hours
    {
        return Err(CoreError::at(
            "INVALID_DURATION_DISTRIBUTION",
            "Duration requires finite minimum <= median <= maximum, a positive median, and maximum greater than minimum",
            path,
        ));
    }
    if distribution
        .shape_parameters
        .values()
        .any(|value| !value.is_finite())
    {
        return Err(CoreError::at(
            "INVALID_DURATION_SHAPE",
            "Duration shape parameters must be finite",
            path,
        ));
    }
    match distribution.shape.as_str() {
        "triangular" => {}
        "uniform" => {
            let midpoint =
                (distribution.duration_min_hours + distribution.duration_max_hours) / 2.0;
            if (distribution.duration_median_hours - midpoint).abs() > EPSILON {
                return Err(CoreError::at(
                    "INVALID_DURATION_SHAPE",
                    "Uniform duration median must equal the midpoint of its bounds",
                    path,
                ));
            }
        }
        "lognormal" => {
            if distribution
                .shape_parameters
                .get("sigma")
                .is_none_or(|sigma| !sigma.is_finite() || *sigma <= 0.0)
            {
                return Err(CoreError::at(
                    "INVALID_DURATION_SHAPE",
                    "Lognormal duration requires a positive finite sigma parameter",
                    path,
                ));
            }
        }
        shape => {
            return Err(CoreError::at(
                "INVALID_DURATION_SHAPE",
                format!("Unsupported duration shape {shape}"),
                path,
            ));
        }
    }
    let provenance = &distribution.provenance;
    if provenance.source.trim().is_empty()
        || provenance.version.trim().is_empty()
        || matches!(
            provenance.status.as_str(),
            "" | "missing" | "unknown" | "unmeasured"
        )
    {
        return Err(CoreError::at(
            "INVALID_DURATION_EVIDENCE",
            "Duration evidence must identify a measured or estimated source and version",
            path,
        ));
    }
    Ok(())
}

pub fn sample_duration_hours(
    distribution: &DurationDistribution,
    run_seed: u64,
    agent_index: usize,
    action_id: &str,
    occurrence_index: u64,
) -> CoreResult<f64> {
    validate_duration_distribution(distribution, "duration")?;
    let seed = keyed_seed(run_seed, agent_index, action_id, occurrence_index);
    let mut rng = DeterministicRng::new(seed);
    let minimum = distribution.duration_min_hours;
    let median = distribution.duration_median_hours;
    let maximum = distribution.duration_max_hours;
    let sampled = match distribution.shape.as_str() {
        "uniform" => minimum + rng.draw() * (maximum - minimum),
        "triangular" => sample_triangular(minimum, median, maximum, rng.draw()),
        "lognormal" => {
            let sigma = distribution.shape_parameters["sigma"];
            sample_truncated_lognormal(minimum, median, maximum, sigma, &mut rng)
        }
        _ => unreachable!("validated duration shape"),
    };
    Ok(sampled.clamp(minimum, maximum))
}

pub fn scale_probability_to_tick(
    probability: f64,
    time_unit_hours: Option<f64>,
    tick_hours: f64,
) -> CoreResult<f64> {
    if !probability.is_finite() || !(0.0..=1.0).contains(&probability) {
        return Err(CoreError::at(
            "INVALID_PROBABILITY",
            "Probability must be finite and between zero and one",
            "probability",
        ));
    }
    if !tick_hours.is_finite() || tick_hours <= 0.0 {
        return Err(CoreError::at(
            "INVALID_TICK_HOURS",
            "Tick budget must be a positive finite number of hours",
            "tick_hours",
        ));
    }
    let Some(time_unit_hours) = time_unit_hours else {
        return Ok(probability);
    };
    if !time_unit_hours.is_finite() || time_unit_hours <= 0.0 {
        return Err(CoreError::at(
            "INVALID_PROBABILITY_TIME_UNIT",
            "Probability time unit must be a positive finite number of hours",
            "probability.time_unit_hours",
        ));
    }
    if probability == 0.0 || probability == 1.0 {
        return Ok(probability);
    }
    Ok(1.0 - (1.0 - probability).powf(tick_hours / time_unit_hours))
}

fn keyed_seed(run_seed: u64, agent_index: usize, action_id: &str, occurrence_index: u64) -> u64 {
    let mut hash = 0xcbf29ce484222325u64 ^ run_seed;
    for byte in action_id.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash ^= (agent_index as u64).rotate_left(17);
    hash = hash.wrapping_mul(0x9e3779b97f4a7c15);
    hash ^ occurrence_index.rotate_left(31)
}

fn sample_triangular(minimum: f64, median: f64, maximum: f64, draw: f64) -> f64 {
    let width = maximum - minimum;
    let midpoint = (minimum + maximum) / 2.0;
    let mode = if median < midpoint {
        maximum - 2.0 * (maximum - median).powi(2) / width
    } else if median > midpoint {
        minimum + 2.0 * (median - minimum).powi(2) / width
    } else {
        midpoint
    }
    .clamp(minimum, maximum);
    let mode_probability = (mode - minimum) / width;
    if draw < mode_probability {
        minimum + (draw * width * (mode - minimum)).sqrt()
    } else {
        maximum - ((1.0 - draw) * width * (maximum - mode)).sqrt()
    }
}

fn sample_truncated_lognormal(
    minimum: f64,
    median: f64,
    maximum: f64,
    sigma: f64,
    rng: &mut DeterministicRng,
) -> f64 {
    for _ in 0..64 {
        let first = rng.draw().max(f64::MIN_POSITIVE);
        let second = rng.draw();
        let standard_normal =
            (-2.0 * first.ln()).sqrt() * (2.0 * std::f64::consts::PI * second).cos();
        let sampled = (median.ln() + sigma * standard_normal).exp();
        if sampled >= minimum && sampled <= maximum {
            return sampled;
        }
    }
    median.clamp(minimum, maximum)
}

pub fn allocate_tick(
    tick: u64,
    tick_hours: f64,
    active_primary: Option<InProgressTimedAction>,
    candidates: Vec<SampledTimedAction>,
    idle_category: &str,
) -> CoreResult<TickAllocation> {
    allocate_agent_tick(
        0,
        tick,
        tick_hours,
        active_primary,
        candidates,
        idle_category,
    )
}

pub fn allocate_agent_tick(
    agent_index: usize,
    tick: u64,
    tick_hours: f64,
    mut active_primary: Option<InProgressTimedAction>,
    candidates: Vec<SampledTimedAction>,
    idle_category: &str,
) -> CoreResult<TickAllocation> {
    if !tick_hours.is_finite() || tick_hours <= 0.0 {
        return Err(CoreError::at(
            "INVALID_TICK_HOURS",
            "Tick budget must be a positive finite number of hours",
            "tick_hours",
        ));
    }
    let mut primary_candidates = Vec::new();
    let mut passive_actions = Vec::new();
    let mut executed_events = Vec::new();
    for candidate in candidates {
        validate_sampled_action(&candidate)?;
        if candidate.definition.passive {
            if candidate.emit_event {
                executed_events.push(event_at_tick(&candidate.event, tick));
            }
            passive_actions.push(action_receipt(
                &candidate,
                candidate.sampled_duration_hours,
                0.0,
                "passive",
            ));
        } else {
            primary_candidates.push(candidate);
        }
    }
    sort_candidates(&mut primary_candidates);
    let mut deferred = Vec::new();
    let mut interruptions = Vec::new();
    let mut primary_actions = Vec::new();
    let mut remaining_budget = tick_hours;

    if let Some(current) = active_primary.take() {
        validate_sampled_action(&current)?;
        let interrupting_index = primary_candidates
            .iter()
            .position(|candidate| can_interrupt(&current, candidate));
        if let Some(interrupting_index) = interrupting_index {
            let interrupting = primary_candidates.remove(interrupting_index);
            interruptions.push(ActionInterruptionReceipt {
                interrupted_action: current.definition.action_id.clone(),
                interrupting_action: interrupting.definition.action_id.clone(),
                remaining_hours: current.remaining_duration_hours,
                outcome: current.definition.interruption_outcome.clone(),
            });
            if current.definition.interruption_outcome == "defer" {
                deferred.push(current);
            }
            primary_candidates.insert(0, interrupting);
        } else {
            let (updated, receipt) = consume_active(current, remaining_budget);
            remaining_budget -= receipt.hours_this_tick;
            primary_actions.push(receipt);
            active_primary = updated;
            if active_primary.is_some() {
                deferred.append(&mut primary_candidates);
            }
        }
    }

    if active_primary.is_none() {
        let mut pending = primary_candidates.into_iter();
        while let Some(mut candidate) = pending.next() {
            if remaining_budget <= EPSILON {
                deferred.push(candidate);
                deferred.extend(pending);
                break;
            }
            let fits = candidate.remaining_duration_hours <= remaining_budget + EPSILON;
            let is_long = candidate.sampled_duration_hours > tick_hours + EPSILON;
            if !fits && !is_long {
                deferred.push(candidate);
                deferred.extend(pending);
                break;
            }
            let consumed = candidate.remaining_duration_hours.min(remaining_budget);
            candidate.remaining_duration_hours =
                (candidate.remaining_duration_hours - consumed).max(0.0);
            if candidate.emit_event {
                executed_events.push(event_at_tick(&candidate.event, tick));
                candidate.emit_event = false;
            }
            let status = if candidate.remaining_duration_hours <= EPSILON {
                "completed"
            } else {
                "continuing"
            };
            primary_actions.push(action_receipt(
                &candidate,
                consumed,
                candidate.remaining_duration_hours,
                status,
            ));
            remaining_budget -= consumed;
            if candidate.remaining_duration_hours > EPSILON {
                active_primary = Some(candidate);
                deferred.extend(pending);
                break;
            }
        }
    }

    let used_hours = tick_hours - remaining_budget.max(0.0);
    validate_tick_budget(tick_hours, &primary_actions)?;
    sort_candidates(&mut deferred);
    let continuing_action = active_primary
        .as_ref()
        .map(|action| action_receipt(action, 0.0, action.remaining_duration_hours, "continuing"));
    let receipt = TickTimeReceipt {
        tick,
        agent_index,
        budget_hours: tick_hours,
        used_hours,
        remaining_hours: remaining_budget.max(0.0),
        idle_category: idle_category.to_owned(),
        primary_actions,
        passive_actions,
        interruptions,
        deferred_actions: deferred
            .iter()
            .map(|candidate| candidate.definition.action_id.clone())
            .collect(),
        continuing_action,
    };
    Ok(TickAllocation {
        receipt,
        active_primary,
        deferred,
        executed_events,
    })
}

fn validate_sampled_action(action: &SampledTimedAction) -> CoreResult<()> {
    validate_duration_distribution(&action.definition.duration, "time_execution.actions")?;
    let sampled = action.sampled_duration_hours;
    if !sampled.is_finite()
        || sampled < action.definition.duration.duration_min_hours - EPSILON
        || sampled > action.definition.duration.duration_max_hours + EPSILON
        || !action.remaining_duration_hours.is_finite()
        || action.remaining_duration_hours < 0.0
        || action.remaining_duration_hours > sampled + EPSILON
    {
        return Err(CoreError::at(
            "INVALID_SAMPLED_DURATION",
            format!(
                "Action {} sampled {} hours outside [{}, {}] or has invalid remaining time {}",
                action.definition.action_id,
                sampled,
                action.definition.duration.duration_min_hours,
                action.definition.duration.duration_max_hours,
                action.remaining_duration_hours,
            ),
            "time_execution.actions",
        ));
    }
    Ok(())
}

fn sort_candidates(candidates: &mut [SampledTimedAction]) {
    candidates.sort_by(|left, right| {
        right
            .definition
            .priority
            .cmp(&left.definition.priority)
            .then_with(|| left.definition.action_id.cmp(&right.definition.action_id))
            .then_with(|| left.event.agent_index.cmp(&right.event.agent_index))
            .then_with(|| left.occurrence_index.cmp(&right.occurrence_index))
    });
}

fn can_interrupt(current: &InProgressTimedAction, incoming: &SampledTimedAction) -> bool {
    let defined_emergency = current
        .definition
        .emergency_interruptions
        .contains(&incoming.definition.action_id);
    defined_emergency
        || current.definition.interruptibility == "interruptible"
            && incoming.definition.priority > current.definition.priority
}

fn consume_active(
    mut active: InProgressTimedAction,
    budget: f64,
) -> (Option<InProgressTimedAction>, ActionTimeReceipt) {
    let consumed = active.remaining_duration_hours.min(budget);
    active.remaining_duration_hours = (active.remaining_duration_hours - consumed).max(0.0);
    let status = if active.remaining_duration_hours <= EPSILON {
        "completed"
    } else {
        "continuing"
    };
    let receipt = action_receipt(&active, consumed, active.remaining_duration_hours, status);
    let next = (active.remaining_duration_hours > EPSILON).then_some(active);
    (next, receipt)
}

fn action_receipt(
    action: &SampledTimedAction,
    hours_this_tick: f64,
    remaining_hours: f64,
    status: &str,
) -> ActionTimeReceipt {
    ActionTimeReceipt {
        action: action.definition.action_id.clone(),
        category: action.definition.category.clone(),
        occurrence_index: action.occurrence_index,
        duration: action.definition.duration.clone(),
        sampled_duration_hours: action.sampled_duration_hours,
        hours_this_tick,
        remaining_hours,
        status: status.to_owned(),
        passive: action.definition.passive,
    }
}

fn event_at_tick(event: &ActionEvent, tick: u64) -> ActionEvent {
    let mut value = event.clone();
    value.tick = tick;
    value
}

pub fn validate_tick_budget(tick_hours: f64, actions: &[ActionTimeReceipt]) -> CoreResult<()> {
    let primary = actions
        .iter()
        .filter(|action| !action.passive)
        .collect::<Vec<_>>();
    let total = primary
        .iter()
        .map(|action| action.hours_this_tick)
        .sum::<f64>();
    if !total.is_finite() || total > tick_hours + EPSILON {
        let details = primary
            .iter()
            .map(|action| format!("{}={}", action.action, action.hours_this_tick))
            .collect::<Vec<_>>()
            .join(", ");
        return Err(CoreError::at(
            "TICK_TIME_BUDGET_EXCEEDED",
            format!(
                "Sampled primary action time {total} exceeds tick budget {tick_hours}: {details}"
            ),
            "time_execution",
        ));
    }
    Ok(())
}

pub fn summarize_daily_time(
    receipts: &[TickTimeReceipt],
    start_hour: f64,
) -> Vec<DailyTimeAccounting> {
    let mut by_agent_day: BTreeMap<(usize, u64), BTreeMap<String, f64>> = BTreeMap::new();
    for receipt in receipts {
        let mut absolute_hour = start_hour + (receipt.tick - 1) as f64 * receipt.budget_hours;
        for action in &receipt.primary_actions {
            add_segment(
                &mut by_agent_day,
                receipt.agent_index,
                &mut absolute_hour,
                action.hours_this_tick,
                &action.category,
            );
        }
        add_segment(
            &mut by_agent_day,
            receipt.agent_index,
            &mut absolute_hour,
            receipt.remaining_hours,
            &receipt.idle_category,
        );
    }
    by_agent_day
        .into_iter()
        .map(|((agent_index, day_index), category_hours)| {
            let accounted_hours = category_hours.values().sum::<f64>();
            DailyTimeAccounting {
                agent_index,
                day_index,
                complete: (accounted_hours - 24.0).abs() <= EPSILON,
                accounted_hours,
                category_hours,
            }
        })
        .collect()
}

pub fn merge_daily_time(
    existing: &mut Vec<DailyTimeAccounting>,
    updates: Vec<DailyTimeAccounting>,
) {
    let mut merged = existing
        .drain(..)
        .map(|day| ((day.agent_index, day.day_index), day.category_hours))
        .collect::<BTreeMap<_, _>>();
    for update in updates {
        let categories = merged
            .entry((update.agent_index, update.day_index))
            .or_default();
        for (category, hours) in update.category_hours {
            *categories.entry(category).or_default() += hours;
        }
    }
    *existing = merged
        .into_iter()
        .map(|((agent_index, day_index), category_hours)| {
            let accounted_hours = category_hours.values().sum::<f64>();
            DailyTimeAccounting {
                agent_index,
                day_index,
                complete: (accounted_hours - 24.0).abs() <= EPSILON,
                accounted_hours,
                category_hours,
            }
        })
        .collect();
}

fn add_segment(
    by_agent_day: &mut BTreeMap<(usize, u64), BTreeMap<String, f64>>,
    agent_index: usize,
    absolute_hour: &mut f64,
    mut hours: f64,
    category: &str,
) {
    while hours > EPSILON {
        let day_index = absolute_hour.div_euclid(24.0).floor() as u64;
        let hour_in_day = absolute_hour.rem_euclid(24.0);
        let part = hours.min(24.0 - hour_in_day);
        *by_agent_day
            .entry((agent_index, day_index))
            .or_default()
            .entry(category.to_owned())
            .or_default() += part;
        *absolute_hour += part;
        hours -= part;
    }
}
