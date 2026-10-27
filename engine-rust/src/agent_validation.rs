use crate::agent_types::*;
use crate::error::{CoreError, CoreResult};
use std::collections::BTreeSet;

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
    validate_agent_columns(&request.agents, request.places.len())?;
    validate_modules(request)?;
    validate_schedules(request)?;
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
    for (action_index, action) in request.meaningful_actions.iter().enumerate() {
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

fn validate_agent_columns(agents: &AgentColumnsInput, place_count: usize) -> CoreResult<()> {
    let count = agents.state.len();
    if count == 0 || agents.module.len() != count || agents.place.len() != count {
        return Err(CoreError::at(
            "INVALID_AGENT_COLUMNS",
            "module, state, and place columns must have the same non-zero length",
            "agents",
        ));
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
    if module_ids.len() != request.modules.len() {
        return Err(CoreError::at(
            "DUPLICATE_MODULE",
            "Module identifiers must be unique",
            "modules",
        ));
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
            sources.insert(&transition.from_state);
            if transition.rules.is_empty() {
                return Err(CoreError::at(
                    "UNKNOWN_PROBABILITY",
                    "A transition requires at least one probability rule",
                    format!("{transition_path}.rules"),
                ));
            }
            for (rule_index, rule) in transition.rules.iter().enumerate() {
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
    let provenance = &rule.provenance;
    if provenance.source.trim().is_empty() || provenance.version.trim().is_empty() {
        return Err(CoreError::at(
            "MISSING_PROVENANCE",
            "Probability source and version are required",
            format!("{path}.provenance"),
        ));
    }
    let predictive = ["present", "measured"];
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
    for (index, schedule) in request.schedules.iter().enumerate() {
        let path = format!("schedules.{index}");
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
