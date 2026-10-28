use crate::agent_types::*;
use crate::error::{CoreError, CoreResult};
use crate::state_finance::{
    CashFlowColumns, FinanceColumns, StateColumns, advance_finance_columns, advance_state_columns,
};
use crate::time_budget::validate_duration_distribution;
use std::collections::{BTreeMap, BTreeSet};

pub fn validate_request(request: &AgentProgramRequest) -> CoreResult<()> {
    if request.ticks == 0 {
        return Err(CoreError::at(
            "INVALID_TICKS",
            "ticks must be at least one",
            "ticks",
        ));
    }
    if !request.tick_hours.is_finite() || request.tick_hours <= 0.0 {
        return Err(CoreError::at(
            "INVALID_TICK_HOURS",
            "tick_hours must be a positive finite number",
            "tick_hours",
        ));
    }
    if !request.start_hour.is_finite() || request.start_hour < 0.0 || request.start_hour >= 24.0 {
        return Err(CoreError::at(
            "INVALID_START_HOUR",
            "start_hour must be between 0 inclusive and 24 exclusive",
            "start_hour",
        ));
    }
    if request.start_weekday > 6 {
        return Err(CoreError::at(
            "INVALID_WEEKDAY",
            "start_weekday must be between 0 and 6",
            "start_weekday",
        ));
    }
    if request.places.is_empty() {
        return Err(CoreError::at(
            "INVALID_PLACES",
            "At least one place shard is required",
            "places",
        ));
    }
    let place_ids: BTreeSet<_> = request.places.iter().map(|place| &place.id).collect();
    if place_ids.len() != request.places.len()
        || request
            .places
            .iter()
            .any(|place| place.id.trim().is_empty())
    {
        return Err(CoreError::at(
            "DUPLICATE_PLACE",
            "Place identifiers must be non-empty and unique",
            "places",
        ));
    }
    if request
        .places
        .iter()
        .flat_map(|place| place.state.values())
        .any(|value| !value.is_finite())
    {
        return Err(CoreError::at(
            "INVALID_PLACE_STATE",
            "Place-state values must be finite",
            "places",
        ));
    }
    if let Some((index, _)) = request
        .places
        .iter()
        .enumerate()
        .find(|(_, place)| place.kind.trim().is_empty() || place.capacity == Some(0))
    {
        return Err(CoreError::at(
            "INVALID_PLACE_PROFILE",
            "Place kind must be non-empty and capacity must be at least one",
            format!("places.{index}"),
        ));
    }
    validate_agent_columns(&request.agents, request.places.len())?;
    let mut occupancy = vec![0usize; request.places.len()];
    for place in &request.agents.place {
        occupancy[*place] += 1;
    }
    if let Some((index, place)) = request.places.iter().enumerate().find(|(index, place)| {
        place
            .capacity
            .is_some_and(|limit| occupancy[*index] > limit)
    }) {
        return Err(CoreError::at(
            "INITIAL_PLACE_CAPACITY_EXCEEDED",
            format!(
                "Initial occupancy {} exceeds place {} capacity {}",
                occupancy[index],
                place.id,
                place.capacity.expect("capacity checked"),
            ),
            format!("places.{index}.capacity"),
        ));
    }
    validate_continuation(request)?;
    validate_modules(request)?;
    validate_schedules(request)?;
    validate_state_dynamics(request)?;
    let action_ids: BTreeSet<_> = request
        .meaningful_actions
        .iter()
        .map(|action| &action.id)
        .collect();
    if action_ids.len() != request.meaningful_actions.len() {
        return Err(CoreError::at(
            "DUPLICATE_ACTION",
            "Meaningful action identifiers must be unique",
            "meaningful_actions",
        ));
    }
    let mut exclusive_choice_groups = BTreeMap::new();
    for (action_index, action) in request.meaningful_actions.iter().enumerate() {
        if let Some(group) = &action.exclusive_choice_group {
            if group.trim().is_empty() {
                return Err(CoreError::at(
                    "INVALID_ACTION_CHOICE_GROUP",
                    "Exclusive action choice group identifiers cannot be empty",
                    format!("meaningful_actions.{action_index}.exclusive_choice_group"),
                ));
            }
            *exclusive_choice_groups
                .entry(group.as_str())
                .or_insert(0usize) += 1;
            if action
                .rules
                .iter()
                .any(|rule| rule.time_unit_hours.is_some())
            {
                return Err(CoreError::at(
                    "INVALID_CATEGORICAL_TIME_UNIT",
                    "Exclusive-choice probabilities are shares and cannot declare a time unit",
                    format!("meaningful_actions.{action_index}.rules"),
                ));
            }
        }
        if action.rules.is_empty() {
            return Err(CoreError::at(
                "MISSING_ACTION_PROBABILITY",
                "Meaningful action requires at least one probability rule",
                format!("meaningful_actions.{action_index}.rules"),
            ));
        }
        for (rule_index, rule) in action.rules.iter().enumerate() {
            validate_rule(
                rule,
                &format!("meaningful_actions.{action_index}.rules.{rule_index}"),
            )?;
        }
    }
    if let Some((group, _)) = exclusive_choice_groups
        .iter()
        .find(|(_, branch_count)| **branch_count < 2)
    {
        return Err(CoreError::at(
            "INVALID_ACTION_CHOICE_GROUP",
            format!("Exclusive action choice group {group} requires at least two branches"),
            format!("meaningful_actions.exclusive_choice_group.{group}"),
        ));
    }
    validate_time_execution(request)?;
    if let Some(network) = &request.network {
        network.validate("network")?;
        if network.rows != request.agents.state.len() || network.cols != request.agents.state.len()
        {
            return Err(CoreError::at(
                "INVALID_NETWORK_DIMENSIONS",
                "Agent network must be square with one row per agent",
                "network",
            ));
        }
        for row in 0..network.rows {
            for edge in network.row_offsets[row]..network.row_offsets[row + 1] {
                let column = network.column_indices[edge];
                if request.agents.place[row] != request.agents.place[column] {
                    return Err(CoreError::at(
                        "CROSS_SHARD_NETWORK_EDGE",
                        "Cross-place influence must enter through an explicit border synchronization payload",
                        format!("network.column_indices.{edge}"),
                    ));
                }
            }
        }
    }
    validate_sync_cadence(
        request.synchronization.border_every_ticks,
        "synchronization.border_every_ticks",
    )?;
    validate_sync_cadence(
        request.synchronization.media_every_ticks,
        "synchronization.media_every_ticks",
    )?;
    validate_sync_cadence(
        request.synchronization.weekly_leader_every_ticks,
        "synchronization.weekly_leader_every_ticks",
    )?;
    Ok(())
}

fn validate_time_execution(request: &AgentProgramRequest) -> CoreResult<()> {
    let continuation = request
        .continuation
        .as_ref()
        .map(|value| &value.time_execution);
    let Some(program) = request.state_dynamics.time_execution.as_ref() else {
        if continuation.is_some_and(|value| {
            !value.active_primary.is_empty()
                || !value.deferred.is_empty()
                || !value.pending_actions.is_empty()
                || !value.occurrence_counts.is_empty()
                || !value.daily_time.is_empty()
        }) {
            return Err(CoreError::at(
                "MISSING_TIME_EXECUTION_PROGRAM",
                "A continuation with timed actions requires its time execution program",
                "state_dynamics.time_execution",
            ));
        }
        return Ok(());
    };
    if program.idle_category.trim().is_empty() {
        return Err(CoreError::at(
            "INVALID_IDLE_CATEGORY",
            "Time execution idle category cannot be empty",
            "state_dynamics.time_execution.idle_category",
        ));
    }
    if let Some(indices) = &program.receipt_agent_indices {
        let unique = indices.iter().copied().collect::<BTreeSet<_>>();
        if unique.len() != indices.len()
            || indices
                .iter()
                .any(|index| *index >= request.agents.state.len())
        {
            return Err(CoreError::at(
                "INVALID_TIME_RECEIPT_AGENTS",
                "Time receipt agent indices must be unique and inside the population",
                "state_dynamics.time_execution.receipt_agent_indices",
            ));
        }
    }
    let action_ids = program
        .actions
        .iter()
        .map(|action| action.action_id.as_str())
        .collect::<BTreeSet<_>>();
    if action_ids.len() != program.actions.len() {
        return Err(CoreError::at(
            "DUPLICATE_TIMED_ACTION",
            "Timed action identifiers must be unique",
            "state_dynamics.time_execution.actions",
        ));
    }
    let meaningful_ids = request
        .meaningful_actions
        .iter()
        .map(|action| action.id.as_str())
        .collect::<BTreeSet<_>>();
    let missing = meaningful_ids
        .difference(&action_ids)
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(CoreError::at(
            "MISSING_ACTION_DURATION",
            format!(
                "Meaningful actions require duration distributions: {}",
                missing.join(", ")
            ),
            "state_dynamics.time_execution.actions",
        ));
    }
    for (index, action) in program.actions.iter().enumerate() {
        let path = format!("state_dynamics.time_execution.actions.{index}");
        if action.action_id.trim().is_empty() || action.category.trim().is_empty() {
            return Err(CoreError::at(
                "INVALID_TIMED_ACTION",
                "Timed actions require non-empty action and category identifiers",
                &path,
            ));
        }
        validate_duration_distribution(&action.duration, &format!("{path}.duration"))?;
        let mut override_ids = BTreeSet::new();
        let mut overridden_agents = BTreeSet::new();
        for (override_index, duration_override) in action.duration_overrides.iter().enumerate() {
            let override_path = format!("{path}.duration_overrides.{override_index}");
            if duration_override.id.trim().is_empty()
                || !override_ids.insert(duration_override.id.as_str())
                || duration_override.eligible_agent_indices.is_empty()
            {
                return Err(CoreError::at(
                    "INVALID_DURATION_OVERRIDE",
                    "Duration overrides require a unique id and at least one eligible agent",
                    &override_path,
                ));
            }
            validate_duration_distribution(
                &duration_override.duration,
                &format!("{override_path}.duration"),
            )?;
            let unique_agents = duration_override
                .eligible_agent_indices
                .iter()
                .copied()
                .collect::<BTreeSet<_>>();
            if unique_agents.len() != duration_override.eligible_agent_indices.len()
                || unique_agents
                    .iter()
                    .any(|agent| *agent >= request.agents.state.len())
                || unique_agents
                    .iter()
                    .any(|agent| !overridden_agents.insert(*agent))
            {
                return Err(CoreError::at(
                    "INVALID_DURATION_OVERRIDE",
                    "Duration override agents must be unique, in range, and appear in one override",
                    format!("{override_path}.eligible_agent_indices"),
                ));
            }
        }
        if !action.location_place_index_by_agent.is_empty()
            && (action.location_place_index_by_agent.len() != request.agents.state.len()
                || action
                    .location_place_index_by_agent
                    .iter()
                    .flatten()
                    .any(|place| *place >= request.places.len()))
        {
            return Err(CoreError::at(
                "INVALID_TIMED_ACTION_LOCATIONS",
                "Timed action locations must contain one valid optional place per agent",
                format!("{path}.location_place_index_by_agent"),
            ));
        }
        if !matches!(
            action.interruptibility.as_str(),
            "interruptible" | "protected" | "uninterruptible"
        ) {
            return Err(CoreError::at(
                "INVALID_INTERRUPTIBILITY",
                "Interruptibility must be interruptible, protected, or uninterruptible",
                format!("{path}.interruptibility"),
            ));
        }
        if !matches!(action.interruption_outcome.as_str(), "defer" | "cancel") {
            return Err(CoreError::at(
                "INVALID_INTERRUPTION_OUTCOME",
                "Interruption outcome must be defer or cancel",
                format!("{path}.interruption_outcome"),
            ));
        }
        if action
            .emergency_interruptions
            .iter()
            .any(|identity| !action_ids.contains(identity.as_str()))
        {
            return Err(CoreError::at(
                "UNKNOWN_EMERGENCY_INTERRUPTION",
                "Emergency interruption rules must reference a timed action",
                format!("{path}.emergency_interruptions"),
            ));
        }
    }
    let Some(continuation) = continuation else {
        return Ok(());
    };
    let agent_count = request.agents.state.len();
    for (name, length) in [
        ("active_primary", continuation.active_primary.len()),
        ("occurrence_counts", continuation.occurrence_counts.len()),
    ] {
        if length != 0 && length != agent_count {
            return Err(CoreError::at(
                "INVALID_TIME_CONTINUATION",
                format!("Time continuation {name} must have one row per agent"),
                format!("continuation.time_execution.{name}"),
            ));
        }
    }
    if continuation
        .deferred
        .iter()
        .any(|action| action.event.agent_index >= agent_count)
    {
        return Err(CoreError::at(
            "INVALID_TIME_CONTINUATION",
            "Deferred action references an agent outside the population",
            "continuation.time_execution.deferred",
        ));
    }
    if continuation.pending_actions.iter().any(|action| {
        action.agent_index >= agent_count || !action_ids.contains(action.action.as_str())
    }) {
        return Err(CoreError::at(
            "INVALID_TIME_CONTINUATION",
            "Pending action references an unknown action or an agent outside the population",
            "continuation.time_execution.pending_actions",
        ));
    }
    if continuation.daily_time.iter().any(|day| {
        day.agent_index >= agent_count
            || !day.accounted_hours.is_finite()
            || day.accounted_hours < 0.0
            || day.accounted_hours > 24.0 + 1e-9
    }) {
        return Err(CoreError::at(
            "INVALID_TIME_CONTINUATION",
            "Daily time accounting references an invalid agent or exceeds 24 hours",
            "continuation.time_execution.daily_time",
        ));
    }
    Ok(())
}

fn validate_state_dynamics(request: &AgentProgramRequest) -> CoreResult<()> {
    let dynamics = &request.state_dynamics;
    let population = request.agents.state.len();
    let event_ids: BTreeSet<_> = dynamics
        .events
        .iter()
        .map(|event| event.id.as_str())
        .collect();
    if event_ids.len() != dynamics.events.len()
        || dynamics
            .events
            .iter()
            .any(|event| event.id.trim().is_empty())
    {
        return Err(CoreError::at(
            "DUPLICATE_STATE_EVENT",
            "State dynamics event identifiers must be non-empty and unique",
            "state_dynamics.events",
        ));
    }
    let rule_targets: BTreeSet<_> = dynamics
        .state_rules
        .iter()
        .map(|rule| rule.target_state_id.as_str())
        .collect();
    for (event_index, event) in dynamics.events.iter().enumerate() {
        if event.evidence.status.trim().is_empty()
            || event.evidence.source.trim().is_empty()
            || event.evidence.source_version.trim().is_empty()
            || !event.evidence.uncertainty.is_finite()
            || !(0.0..=1.0).contains(&event.evidence.uncertainty)
        {
            return Err(CoreError::at(
                "INVALID_STATE_EVENT_EVIDENCE",
                "State event evidence requires a source, version, status, and uncertainty from zero to one",
                format!("state_dynamics.events.{event_index}.evidence"),
            ));
        }
        if event
            .cash_flow
            .values()
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        {
            return Err(CoreError::at(
                "INVALID_STATE_EVENT_CASH_FLOW",
                "State event cash flows must be finite and non-negative",
                format!("state_dynamics.events.{event_index}.cash_flow"),
            ));
        }
        if let Some(columns) = &event.cash_flow_by_agent {
            let values = [
                &columns.wages,
                &columns.business_income,
                &columns.transfers,
                &columns.housing,
                &columns.food,
                &columns.transport,
                &columns.other_expenses,
                &columns.taxes,
                &columns.savings_contribution,
                &columns.savings_withdrawal,
                &columns.debt_draw,
                &columns.debt_repayment,
            ];
            if values.iter().any(|column| {
                column.len() != population
                    || column
                        .iter()
                        .any(|value| !value.is_finite() || *value < 0.0)
            }) {
                return Err(CoreError::at(
                    "INVALID_STATE_EVENT_AGENT_CASH_FLOW",
                    "Per-agent cash-flow columns must contain one finite non-negative value per agent",
                    format!("state_dynamics.events.{event_index}.cash_flow_by_agent"),
                ));
            }
        }
        for (effect_index, effect) in event.effects.iter().enumerate() {
            let state_id = effect.target.strip_prefix("memory.").ok_or_else(|| {
                CoreError::at(
                    "INVALID_STATE_EVENT_TARGET",
                    "State dynamics event effects must target memory fields",
                    format!("state_dynamics.events.{event_index}.effects.{effect_index}.target"),
                )
            })?;
            if !rule_targets.contains(state_id) {
                return Err(CoreError::at(
                    "MISSING_STATE_EVENT_RULE",
                    format!(
                        "State event {} targets {state_id} without a state rule",
                        event.id
                    ),
                    format!("state_dynamics.events.{event_index}.effects.{effect_index}.target"),
                ));
            }
            if !matches!(
                effect.operation.as_str(),
                "add" | "subtract" | "set" | "multiply"
            ) || !effect.value.is_finite()
            {
                return Err(CoreError::at(
                    "INVALID_STATE_EVENT_OPERATION",
                    "State event operations must be add, subtract, set, or multiply with a finite value",
                    format!("state_dynamics.events.{event_index}.effects.{effect_index}"),
                ));
            }
        }
    }
    if !dynamics.state_rules.is_empty() {
        let event_deltas = StateColumns {
            values: rule_targets
                .iter()
                .map(|target| ((*target).to_owned(), vec![0.0; population]))
                .collect(),
        };
        advance_state_columns(
            &StateColumns {
                values: request.agents.memory.clone(),
            },
            &event_deltas,
            &dynamics.state_rules,
        )?;
    }
    if let Some(metadata) = &dynamics.finance {
        if metadata.currency.len() != population
            || metadata.status.len() != population
            || metadata.source.len() != population
            || metadata
                .currency
                .iter()
                .any(|value| value.trim().is_empty())
            || metadata.status.iter().any(|value| value.trim().is_empty())
            || metadata.source.iter().any(|value| value.trim().is_empty())
        {
            return Err(CoreError::at(
                "INVALID_FINANCE_METADATA",
                "Finance metadata must provide non-empty currency, status, and source for every agent",
                "state_dynamics.finance",
            ));
        }
        let memory_column = |name: &str| -> CoreResult<Vec<Option<f64>>> {
            request
                .agents
                .memory
                .get(name)
                .map(|values| values.iter().copied().map(Some).collect())
                .ok_or_else(|| {
                    CoreError::at(
                        "UNKNOWN_FINANCE_STATE",
                        format!("Finance runtime requires memory column {name}"),
                        "state_dynamics.finance",
                    )
                })
        };
        let finances = FinanceColumns {
            currency: metadata.currency.clone(),
            money: memory_column("finance.money")?,
            income: memory_column("finance.income")?,
            expenses: memory_column("finance.expenses")?,
            savings: memory_column("finance.savings")?,
            debt: memory_column("finance.debt")?,
            status: metadata.status.clone(),
            source: metadata.source.clone(),
        };
        let zeros = vec![0.0; population];
        advance_finance_columns(
            &finances,
            &CashFlowColumns {
                wages: zeros.clone(),
                business_income: zeros.clone(),
                transfers: zeros.clone(),
                housing: zeros.clone(),
                food: zeros.clone(),
                transport: zeros.clone(),
                other_expenses: zeros.clone(),
                taxes: zeros.clone(),
                savings_contribution: zeros.clone(),
                savings_withdrawal: zeros.clone(),
                debt_draw: zeros.clone(),
                debt_repayment: zeros,
            },
            &dynamics.finance_rules,
        )?;
    }
    Ok(())
}

fn validate_continuation(request: &AgentProgramRequest) -> CoreResult<()> {
    let Some(continuation) = &request.continuation else {
        return Ok(());
    };
    if continuation.rng_word_position.parse::<u128>().is_err() {
        return Err(CoreError::at(
            "INVALID_RNG_POSITION",
            "Continuation RNG position must be an unsigned integer",
            "continuation.rng_word_position",
        ));
    }
    if continuation.active_travel.len() != request.agents.state.len() {
        return Err(CoreError::at(
            "INVALID_TRAVEL_CONTINUATION",
            "Travel continuation must contain one value per agent",
            "continuation.active_travel",
        ));
    }
    for (agent, travel) in continuation.active_travel.iter().enumerate() {
        let Some(travel) = travel else {
            continue;
        };
        if travel.schedule.trim().is_empty()
            || travel.destination_place_index >= request.places.len()
            || travel.arrival_tick <= continuation.completed_tick
        {
            return Err(CoreError::at(
                "INVALID_TRAVEL_CONTINUATION",
                "Active travel requires a schedule, existing destination, and future arrival tick",
                format!("continuation.active_travel.{agent}"),
            ));
        }
    }
    if !continuation.live_places.is_empty() {
        let expected = live_place_states(&request.places, &request.agents.place);
        if continuation.live_places.len() != expected.len() {
            return Err(CoreError::at(
                "INVALID_PLACE_CONTINUATION",
                "Continuation live place state must contain every runtime place",
                "continuation.live_places",
            ));
        }
        for (index, (place, expected_place)) in
            continuation.live_places.iter().zip(expected).enumerate()
        {
            let occupancy = place.state.get("occupancy").copied();
            let expected_density = place
                .capacity
                .map(|capacity| place.occupancy as f64 / capacity as f64);
            let coherent_density = match (place.crowd_density, expected_density) {
                (Some(actual), Some(expected)) => actual == expected,
                (None, None) => true,
                _ => false,
            };
            let state_density = place.state.get("crowd_density").copied();
            let coherent_state_density = match (state_density, expected_density) {
                (Some(actual), Some(expected)) => actual == expected,
                (None, None) => true,
                _ => false,
            };
            if place.place_index != index
                || place.place_id != expected_place.place_id
                || place.kind != expected_place.kind
                || place.occupancy != expected_place.occupancy
                || occupancy != Some(place.occupancy as f64)
                || !coherent_density
                || !coherent_state_density
                || place.state.values().any(|value| !value.is_finite())
            {
                return Err(CoreError::at(
                    "INVALID_PLACE_CONTINUATION",
                    "Continuation live place state must match continued identities and occupancy",
                    format!("continuation.live_places.{index}"),
                ));
            }
        }
    }
    Ok(())
}

fn validate_agent_columns(agents: &AgentColumnsInput, place_count: usize) -> CoreResult<()> {
    let count = agents.state.len();
    if count == 0 || agents.module.len() != count || agents.place.len() != count {
        return Err(CoreError::at(
            "INVALID_AGENT_COLUMNS",
            "module, state, and place columns must have the same non-zero length",
            "agents",
        ));
    }
    if !agents.agent_ids.is_empty() {
        let unique_ids: BTreeSet<_> = agents.agent_ids.iter().collect();
        if agents.agent_ids.len() != count
            || unique_ids.len() != count
            || agents.agent_ids.iter().any(|value| value.trim().is_empty())
        {
            return Err(CoreError::at(
                "INVALID_AGENT_IDS",
                "agent_ids must contain one unique non-empty identifier per agent",
                "agents.agent_ids",
            ));
        }
    }
    if agents.place.iter().any(|place| *place >= place_count) {
        return Err(CoreError::at(
            "UNKNOWN_AGENT_PLACE",
            "Agent place index exceeds the place shard count",
            "agents.place",
        ));
    }
    for (name, column) in agents.traits.iter().chain(&agents.memory) {
        if column.len() != count {
            return Err(CoreError::at(
                "INVALID_AGENT_COLUMN",
                format!("Column {name} must contain one value per agent"),
                format!("agents.{name}"),
            ));
        }
        if column.iter().any(|value| !value.is_finite()) {
            return Err(CoreError::at(
                "INVALID_AGENT_COLUMN",
                format!("Column {name} contains a non-finite value"),
                format!("agents.{name}"),
            ));
        }
    }
    for (name, dictionary) in &agents.trait_dictionaries {
        let column = agents.traits.get(name).ok_or_else(|| {
            CoreError::at(
                "UNKNOWN_CATEGORICAL_TRAIT",
                format!("Dictionary {name} does not have a matching trait column"),
                format!("agents.trait_dictionaries.{name}"),
            )
        })?;
        if dictionary.source.trim().is_empty() || dictionary.version.trim().is_empty() {
            return Err(CoreError::at(
                "INVALID_CATEGORICAL_DICTIONARY",
                format!("Dictionary {name} requires source and version provenance"),
                format!("agents.trait_dictionaries.{name}"),
            ));
        }
        let labels: BTreeSet<_> = dictionary.values.iter().collect();
        if dictionary.values.is_empty()
            || labels.len() != dictionary.values.len()
            || dictionary.values.iter().any(|value| value.is_empty())
        {
            return Err(CoreError::at(
                "INVALID_CATEGORICAL_DICTIONARY",
                format!("Dictionary {name} requires unique non-empty ordered labels"),
                format!("agents.trait_dictionaries.{name}.values"),
            ));
        }
        if column.iter().any(|value| {
            value.fract() != 0.0 || *value < 0.0 || *value >= dictionary.values.len() as f64
        }) {
            return Err(CoreError::at(
                "INVALID_CATEGORICAL_CODE",
                format!("Trait {name} contains a code outside its dictionary"),
                format!("agents.traits.{name}"),
            ));
        }
    }
    Ok(())
}

fn validate_modules(request: &AgentProgramRequest) -> CoreResult<()> {
    if request.modules.is_empty() {
        return Err(CoreError::at(
            "MISSING_MODULES",
            "At least one Markov module is required",
            "modules",
        ));
    }
    let module_ids: BTreeSet<_> = request.modules.iter().map(|module| &module.id).collect();
    let action_ids = request
        .state_dynamics
        .time_execution
        .as_ref()
        .map(|program| {
            program
                .actions
                .iter()
                .map(|action| action.action_id.as_str())
                .collect::<BTreeSet<_>>()
        })
        .unwrap_or_default();
    if module_ids.len() != request.modules.len() {
        return Err(CoreError::at(
            "DUPLICATE_MODULE",
            "Module identifiers must be unique",
            "modules",
        ));
    }
    for (place_index, place) in request.places.iter().enumerate() {
        let Some(available_modules) = &place.available_decision_modules else {
            continue;
        };
        let unique_modules: BTreeSet<_> = available_modules.iter().collect();
        if unique_modules.len() != available_modules.len()
            || available_modules
                .iter()
                .any(|module_id| !module_ids.contains(module_id))
        {
            return Err(CoreError::at(
                "INVALID_PLACE_DECISION_MODULES",
                "Place decision modules must be unique existing module identifiers",
                format!("places.{place_index}.available_decision_modules"),
            ));
        }
    }
    for (module_index, module) in request.modules.iter().enumerate() {
        let path = format!("modules.{module_index}");
        if module.states.is_empty() {
            return Err(CoreError::at(
                "MISSING_MODULE_STATES",
                "A module requires at least one state",
                format!("{path}.states"),
            ));
        }
        let state_names: BTreeSet<_> = module.states.iter().collect();
        if state_names.len() != module.states.len() {
            return Err(CoreError::at(
                "DUPLICATE_MODULE_STATE",
                "Module state identifiers must be unique",
                format!("{path}.states"),
            ));
        }
        if !state_names.contains(&module.entry_state) {
            return Err(CoreError::at(
                "UNKNOWN_ENTRY_STATE",
                "Module entry state is not declared",
                format!("{path}.entry_state"),
            ));
        }
        if module
            .exit_states
            .iter()
            .any(|state| !state_names.contains(state))
        {
            return Err(CoreError::at(
                "UNKNOWN_EXIT_STATE",
                "Module exit state is not declared",
                format!("{path}.exit_states"),
            ));
        }
        let input_names: BTreeSet<_> = module.inputs.iter().collect();
        let output_names: BTreeSet<_> = module.outputs.iter().collect();
        let available_place_kinds: BTreeSet<_> = module.available_place_kinds.iter().collect();
        if available_place_kinds.len() != module.available_place_kinds.len()
            || module
                .available_place_kinds
                .iter()
                .any(|kind| kind.trim().is_empty())
        {
            return Err(CoreError::at(
                "INVALID_MODULE_PLACE_KINDS",
                "Available module place kinds must be unique and non-empty",
                format!("{path}.available_place_kinds"),
            ));
        }
        if input_names.len() != module.inputs.len() || output_names.len() != module.outputs.len() {
            return Err(CoreError::at(
                "DUPLICATE_MODULE_INTERFACE",
                "Module input and output names must be unique",
                &path,
            ));
        }
        let transition_ids: BTreeSet<_> = module
            .transitions
            .iter()
            .map(|transition| &transition.id)
            .collect();
        if transition_ids.len() != module.transitions.len() {
            return Err(CoreError::at(
                "DUPLICATE_TRANSITION",
                "Transition identifiers must be unique within a module",
                format!("{path}.transitions"),
            ));
        }
        let mut sources = BTreeSet::new();
        for (transition_index, transition) in module.transitions.iter().enumerate() {
            let transition_path = format!("{path}.transitions.{transition_index}");
            if !state_names.contains(&transition.from_state)
                || !state_names.contains(&transition.to_state)
            {
                return Err(CoreError::at(
                    "UNKNOWN_MODULE_STATE",
                    format!("Transition {} references an unknown state", transition.id),
                    &transition_path,
                ));
            }
            if transition
                .action_id
                .as_deref()
                .is_some_and(|action_id| !action_ids.contains(action_id))
            {
                return Err(CoreError::at(
                    "UNKNOWN_TRANSITION_ACTION",
                    format!(
                        "Transition {} emits an unknown meaningful action",
                        transition.id
                    ),
                    format!("{transition_path}.action_id"),
                ));
            }
            sources.insert(&transition.from_state);
            if transition.rules.is_empty() {
                return Err(CoreError::at(
                    "UNKNOWN_PROBABILITY",
                    "A transition requires at least one probability rule",
                    format!("{transition_path}.rules"),
                ));
            }
            for (rule_index, rule) in transition.rules.iter().enumerate() {
                if rule.time_unit_hours.is_some() {
                    return Err(CoreError::at(
                        "INVALID_CATEGORICAL_TIME_UNIT",
                        "Module transition probabilities are shares and cannot declare a time unit",
                        format!("{transition_path}.rules.{rule_index}.time_unit_hours"),
                    ));
                }
                validate_rule(rule, &format!("{transition_path}.rules.{rule_index}"))?;
                for condition in &rule.conditions {
                    if !input_names.contains(&condition.input) {
                        return Err(CoreError::at(
                            "UNDECLARED_MODULE_INPUT",
                            format!("Condition input {} is not declared", condition.input),
                            format!("{transition_path}.rules.{rule_index}.conditions"),
                        ));
                    }
                }
            }
            for (effect_index, effect) in transition.effects.iter().enumerate() {
                validate_effect(
                    effect,
                    &output_names,
                    &format!("{transition_path}.effects.{effect_index}"),
                )?;
            }
        }
        for state in &module.states {
            if !module.exit_states.contains(state) && !sources.contains(state) {
                return Err(CoreError::at(
                    "MODULE_DEAD_END",
                    format!("Non-exit state {state} has no outgoing transitions"),
                    format!("{path}.transitions"),
                ));
            }
        }
    }
    let mut route_keys = BTreeSet::new();
    for (route_index, route) in request.routes.iter().enumerate() {
        let source = request
            .modules
            .iter()
            .find(|module| module.id == route.from_module)
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_ROUTE_MODULE",
                    format!("Unknown source module {}", route.from_module),
                    format!("routes.{route_index}.from_module"),
                )
            })?;
        if !source.exit_states.contains(&route.exit_state) {
            return Err(CoreError::at(
                "UNKNOWN_ROUTE_EXIT",
                format!(
                    "State {} is not an exit of {}",
                    route.exit_state, route.from_module
                ),
                format!("routes.{route_index}.exit_state"),
            ));
        }
        if !module_ids.contains(&route.to_module) {
            return Err(CoreError::at(
                "UNKNOWN_ROUTE_MODULE",
                format!("Unknown target module {}", route.to_module),
                format!("routes.{route_index}.to_module"),
            ));
        }
        if !route_keys.insert((&route.from_module, &route.exit_state)) {
            return Err(CoreError::at(
                "AMBIGUOUS_MODULE_ROUTE",
                "A module exit can have only one route",
                format!("routes.{route_index}"),
            ));
        }
    }
    Ok(())
}

fn validate_rule(rule: &ProbabilityRule, path: &str) -> CoreResult<()> {
    let probability = rule.probability.ok_or_else(|| {
        CoreError::at(
            "UNKNOWN_PROBABILITY",
            "Probability is null and cannot execute",
            format!("{path}.probability"),
        )
    })?;
    if !probability.is_finite() || !(0.0..=1.0).contains(&probability) {
        return Err(CoreError::at(
            "INVALID_PROBABILITY",
            "Probability must be a finite value between 0 and 1",
            format!("{path}.probability"),
        ));
    }
    if rule
        .time_unit_hours
        .is_some_and(|value| !value.is_finite() || value <= 0.0)
    {
        return Err(CoreError::at(
            "INVALID_PROBABILITY_TIME_UNIT",
            "Probability time unit must be a positive finite number of hours",
            format!("{path}.time_unit_hours"),
        ));
    }
    let provenance = &rule.provenance;
    if provenance.source.trim().is_empty() || provenance.version.trim().is_empty() {
        return Err(CoreError::at(
            "MISSING_PROVENANCE",
            "Probability source and version are required",
            format!("{path}.provenance"),
        ));
    }
    let predictive = ["present", "measured", "default_estimated", "fitted"];
    if !predictive.contains(&provenance.status.as_str()) {
        return Err(CoreError::at(
            "NON_PREDICTIVE_EVIDENCE",
            format!(
                "Evidence status {} cannot drive a transition",
                provenance.status
            ),
            format!("{path}.provenance.status"),
        ));
    }
    if let Some(resolution_status) = provenance.resolution_status.as_deref() {
        if !["direct", "inherited", "imputed"].contains(&resolution_status) {
            return Err(CoreError::at(
                "INVALID_RESOLUTION_STATUS",
                format!("Unknown evidence resolution status {resolution_status}"),
                format!("{path}.provenance.resolution_status"),
            ));
        }
        if resolution_status == "imputed" && provenance.status != "default_estimated" {
            return Err(CoreError::at(
                "NON_PREDICTIVE_EVIDENCE",
                "Imputed measured or fitted evidence cannot drive a transition",
                format!("{path}.provenance.resolution_status"),
            ));
        }
    }
    if !provenance.uncertainty.is_finite() || !(0.0..=1.0).contains(&provenance.uncertainty) {
        return Err(CoreError::at(
            "INVALID_UNCERTAINTY",
            "Evidence uncertainty must be between 0 and 1",
            format!("{path}.provenance.uncertainty"),
        ));
    }
    match (provenance.ci_low, provenance.ci_high) {
        (Some(ci_low), Some(ci_high))
            if ci_low.is_finite()
                && ci_high.is_finite()
                && (0.0..=1.0).contains(&ci_low)
                && (0.0..=1.0).contains(&ci_high)
                && ci_low <= probability
                && probability <= ci_high => {}
        (None, None) => {}
        _ => {
            return Err(CoreError::at(
                "INVALID_CONFIDENCE_INTERVAL",
                "Confidence bounds must both be present, ordered, and contain the probability",
                format!("{path}.provenance"),
            ));
        }
    }
    for (condition_index, condition) in rule.conditions.iter().enumerate() {
        if condition.categorical_value.is_some()
            && (condition.input != "place.kind"
                || !["eq", "ne"].contains(&condition.operator.as_str()))
        {
            return Err(CoreError::at(
                "INVALID_CATEGORICAL_CONDITION",
                "Categorical conditions support place.kind with eq or ne",
                format!("{path}.conditions.{condition_index}"),
            ));
        }
        if !condition.value.is_finite() {
            return Err(CoreError::at(
                "INVALID_CONDITION",
                "Condition value must be finite",
                format!("{path}.conditions.{condition_index}.value"),
            ));
        }
        if !["eq", "ne", "gt", "gte", "lt", "lte"].contains(&condition.operator.as_str()) {
            return Err(CoreError::at(
                "INVALID_CONDITION_OPERATOR",
                format!("Unknown condition operator {}", condition.operator),
                format!("{path}.conditions.{condition_index}.operator"),
            ));
        }
    }
    Ok(())
}

pub fn validate_probability_rule(rule: &ProbabilityRule, path: &str) -> CoreResult<()> {
    validate_rule(rule, path)
}

fn validate_effect(
    effect: &TransitionEffect,
    outputs: &BTreeSet<&String>,
    path: &str,
) -> CoreResult<()> {
    if !outputs.contains(&effect.target) {
        return Err(CoreError::at(
            "UNDECLARED_MODULE_OUTPUT",
            format!("Effect target {} is not declared", effect.target),
            format!("{path}.target"),
        ));
    }
    if effect.target != "place" && !effect.target.starts_with("memory.") {
        return Err(CoreError::at(
            "INVALID_EFFECT_TARGET",
            "Effect target must be place or a memory column",
            format!("{path}.target"),
        ));
    }
    if effect.operation != "set" && effect.operation != "add" {
        return Err(CoreError::at(
            "INVALID_EFFECT_OPERATION",
            "Effect operation must be set or add",
            format!("{path}.operation"),
        ));
    }
    if !effect.value.is_finite() {
        return Err(CoreError::at(
            "INVALID_EFFECT_VALUE",
            "Effect value must be finite",
            format!("{path}.value"),
        ));
    }
    Ok(())
}

fn validate_schedules(request: &AgentProgramRequest) -> CoreResult<()> {
    let schedule_ids: BTreeSet<_> = request
        .schedules
        .iter()
        .map(|schedule| &schedule.id)
        .collect();
    if schedule_ids.len() != request.schedules.len() {
        return Err(CoreError::at(
            "DUPLICATE_SCHEDULE",
            "Schedule identifiers must be unique",
            "schedules",
        ));
    }
    let timed_action_ids = request
        .state_dynamics
        .time_execution
        .as_ref()
        .map(|program| {
            program
                .actions
                .iter()
                .map(|action| action.action_id.as_str())
                .collect::<BTreeSet<_>>()
        })
        .unwrap_or_default();
    for (index, schedule) in request.schedules.iter().enumerate() {
        let path = format!("schedules.{index}");
        if schedule.id.trim().is_empty() || schedule.action.trim().is_empty() {
            return Err(CoreError::at(
                "INVALID_SCHEDULE",
                "Schedule identifiers and actions must be non-empty",
                &path,
            ));
        }
        match (
            schedule.timed_action_id.as_deref(),
            schedule.timed_action_provenance.as_ref(),
        ) {
            (Some(action_id), Some(provenance)) if timed_action_ids.contains(action_id) => {
                validate_rule(
                    &ProbabilityRule {
                        conditions: vec![],
                        probability: Some(1.0),
                        time_unit_hours: None,
                        provenance: provenance.clone(),
                    },
                    &format!("{path}.timed_action_provenance"),
                )?;
            }
            (None, None) => {}
            (Some(_), Some(_)) => {
                return Err(CoreError::at(
                    "UNKNOWN_SCHEDULE_TIMED_ACTION",
                    "Scheduled timed action must reference a declared duration",
                    format!("{path}.timed_action_id"),
                ));
            }
            _ => {
                return Err(CoreError::at(
                    "INVALID_SCHEDULE_TIMED_ACTION",
                    "Scheduled timed action id and provenance must be supplied together",
                    &path,
                ));
            }
        }
        if schedule.weekdays.is_empty() || schedule.weekdays.iter().any(|day| *day > 6) {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_WEEKDAYS",
                "Schedule weekdays must contain values from 0 through 6",
                format!("{path}.weekdays"),
            ));
        }
        if !schedule.start_hour.is_finite()
            || !schedule.end_hour.is_finite()
            || schedule.start_hour < 0.0
            || schedule.start_hour >= 24.0
            || schedule.end_hour < 0.0
            || schedule.end_hour > 24.0
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_HOURS",
                "Schedule hours must fall within a day",
                path,
            ));
        }
        let required_places: BTreeSet<_> = schedule.required_place_indices.iter().collect();
        if required_places.len() != schedule.required_place_indices.len()
            || schedule
                .required_place_indices
                .iter()
                .any(|place| *place >= request.places.len())
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_PLACES",
                "Required schedule places must be unique existing place indices",
                format!("{path}.required_place_indices"),
            ));
        }
        let eligible_agents: BTreeSet<_> = schedule.eligible_agent_indices.iter().collect();
        if eligible_agents.len() != schedule.eligible_agent_indices.len()
            || schedule
                .eligible_agent_indices
                .iter()
                .any(|agent| *agent >= request.agents.state.len())
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_AGENTS",
                "Eligible schedule agents must be unique existing agent indices",
                format!("{path}.eligible_agent_indices"),
            ));
        }
        if schedule
            .destination_place_index
            .is_some_and(|place| place >= request.places.len())
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_DESTINATION",
                "Schedule destination must reference an existing place index",
                format!("{path}.destination_place_index"),
            ));
        }
        if !schedule.destination_place_by_agent.is_empty()
            && schedule.destination_place_by_agent.len() != request.agents.state.len()
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_DESTINATION_COLUMN",
                "Per-agent schedule destinations must contain one value per agent",
                format!("{path}.destination_place_by_agent"),
            ));
        }
        if schedule
            .destination_place_by_agent
            .iter()
            .flatten()
            .any(|place| *place >= request.places.len())
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_DESTINATION",
                "Per-agent schedule destinations must reference existing place indices",
                format!("{path}.destination_place_by_agent"),
            ));
        }
        if !schedule.activate_module_by_agent.is_empty()
            && schedule.activate_module_by_agent.len() != request.agents.state.len()
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_MODULE_COLUMN",
                "Per-agent schedule modules must contain one value per agent",
                format!("{path}.activate_module_by_agent"),
            ));
        }
        if !schedule.travel_by_agent.is_empty()
            && schedule.travel_by_agent.len() != request.agents.state.len()
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_TRAVEL_COLUMN",
                "Per-agent travel plans must contain one value per agent",
                format!("{path}.travel_by_agent"),
            ));
        }
        if !schedule.unavailable_reason_by_agent.is_empty()
            && schedule.unavailable_reason_by_agent.len() != request.agents.state.len()
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_UNAVAILABLE_COLUMN",
                "Per-agent unavailable reasons must contain one value per agent",
                format!("{path}.unavailable_reason_by_agent"),
            ));
        }
        for (agent, plan) in schedule.travel_by_agent.iter().enumerate() {
            let Some(plan) = plan else {
                continue;
            };
            if plan.from_place_index >= request.places.len()
                || plan.travel_place_index >= request.places.len()
            {
                return Err(CoreError::at(
                    "INVALID_SCHEDULE_TRAVEL_PLACE",
                    "Travel plans must reference existing source and transit places",
                    format!("{path}.travel_by_agent.{agent}"),
                ));
            }
            if plan.travel_ticks == 0 {
                return Err(CoreError::at(
                    "INVALID_SCHEDULE_TRAVEL_DURATION",
                    "Travel plans require at least one travel tick",
                    format!("{path}.travel_by_agent.{agent}.travel_ticks"),
                ));
            }
            if plan.route_id.trim().is_empty() {
                return Err(CoreError::at(
                    "INVALID_SCHEDULE_TRAVEL_ROUTE",
                    "Travel plans require a route ID",
                    format!("{path}.travel_by_agent.{agent}.route_id"),
                ));
            }
            if schedule
                .unavailable_reason_by_agent
                .get(agent)
                .is_some_and(Option::is_some)
            {
                return Err(CoreError::at(
                    "AMBIGUOUS_SCHEDULE_TRAVEL",
                    "A schedule cannot provide both a travel plan and an unavailable reason",
                    format!("{path}.travel_by_agent.{agent}"),
                ));
            }
        }
        let module_ids: BTreeSet<_> = request.modules.iter().map(|module| &module.id).collect();
        if schedule
            .activate_module_by_agent
            .iter()
            .flatten()
            .any(|module| !module_ids.contains(module))
        {
            return Err(CoreError::at(
                "UNKNOWN_SCHEDULE_MODULE",
                "Per-agent schedule modules must reference existing modules",
                format!("{path}.activate_module_by_agent"),
            ));
        }
        let effective_destinations = (0..request.agents.state.len())
            .filter_map(|agent| {
                schedule
                    .destination_place_by_agent
                    .get(agent)
                    .copied()
                    .flatten()
                    .or(schedule.destination_place_index)
            })
            .collect::<Vec<_>>();
        if schedule
            .travel_place_index
            .is_some_and(|place| place >= request.places.len())
        {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_TRAVEL_PLACE",
                "Schedule travel place must reference an existing place index",
                format!("{path}.travel_place_index"),
            ));
        }
        if effective_destinations.is_empty()
            && (schedule.travel_place_index.is_some() || schedule.travel_ticks.is_some())
        {
            return Err(CoreError::at(
                "MISSING_SCHEDULE_DESTINATION",
                "Travel configuration requires an explicit schedule destination",
                &path,
            ));
        }
        if schedule.travel_place_index.is_some() && schedule.travel_ticks.unwrap_or(0) == 0 {
            return Err(CoreError::at(
                "INVALID_SCHEDULE_TRAVEL_DURATION",
                "A travel place requires at least one travel tick",
                format!("{path}.travel_ticks"),
            ));
        }
        if !schedule.required_place_indices.is_empty()
            && effective_destinations
                .iter()
                .any(|destination| !schedule.required_place_indices.contains(destination))
        {
            return Err(CoreError::at(
                "SCHEDULE_DESTINATION_NOT_ALLOWED",
                "Schedule destination must be one of its required action places",
                format!("{path}.required_place_indices"),
            ));
        }
    }
    Ok(())
}

fn validate_sync_cadence(cadence: Option<u64>, path: &str) -> CoreResult<()> {
    if cadence == Some(0) {
        return Err(CoreError::at(
            "INVALID_SYNC_CADENCE",
            "Synchronization cadence must be at least one tick",
            path,
        ));
    }
    Ok(())
}
