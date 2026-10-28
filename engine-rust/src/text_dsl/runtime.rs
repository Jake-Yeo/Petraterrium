use super::expression::evaluate;
use super::model::*;
use super::parser::{merged_fields, merged_initial, merged_roles, resolved_routine};
use crate::agent_types::{
    ActionEvent, DurationDistribution, ProbabilityProvenance, SampledTimedAction,
    TimedActionDefinition,
};
use crate::time_budget::{allocate_agent_tick, sample_duration_hours};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::{Beta, Distribution, LogNormal, Normal, Poisson};
use std::collections::{BTreeMap, BTreeSet};

pub fn sample_population(program: &Program, seed: u64) -> DslResult<DslPopulation> {
    let agents_by_id = program
        .agents
        .iter()
        .map(|agent| (agent.id.as_str(), agent))
        .collect::<BTreeMap<_, _>>();
    let mut agents = Vec::new();
    for index in 0..program.population.size {
        let agent_type = choose_population_type(program, seed, index)?;
        agents.push(sample_agent(
            &agents_by_id,
            agent_type,
            seed,
            &format!("adult-{index:04}"),
            None,
            format!("household-{index:04}"),
            BTreeMap::new(),
        )?);
    }
    let mut relationships = Vec::new();
    if let Some(rule) = &program.population.child_generation {
        let adults = agents.clone();
        for adult in &adults {
            let context = agent_context(adult, None, None, 0, program.tick_hours);
            if !evaluate(&rule.condition, &context)?
                .as_bool()
                .unwrap_or(false)
            {
                continue;
            }
            let count = evaluate(&rule.count, &context)?
                .as_f64()
                .unwrap_or(0.0)
                .max(0.0)
                .round() as usize;
            for child_index in 0..count {
                let child_id = format!("{}-child-{child_index}", adult.id);
                let age = sample_distribution(
                    &rule.age,
                    &context,
                    keyed_seed(seed, &format!("{child_id}:generated_age")),
                )?;
                let mut child_context = context.clone();
                child_context.insert("age".to_owned(), age.clone());
                let agent_type = evaluate(&rule.agent_type, &child_context)?
                    .as_text()
                    .ok_or_else(|| {
                        DslError::new(
                            "INVALID_CHILD_TYPE",
                            rule.line,
                            "Generated child type must resolve to an agent type",
                        )
                    })?
                    .to_owned();
                let mut overrides = BTreeMap::new();
                overrides.insert("age".to_owned(), age);
                let child = sample_agent(
                    &agents_by_id,
                    &agent_type,
                    seed,
                    &child_id,
                    Some(adult.id.clone()),
                    adult.household_id.clone(),
                    overrides,
                )?;
                relationships.push(DslRelationshipState {
                    kind: "parent".to_owned(),
                    source_id: adult.id.clone(),
                    target_id: child.id.clone(),
                    values: BTreeMap::new(),
                });
                agents.push(child);
            }
        }
    }
    Ok(DslPopulation {
        agents,
        relationships,
    })
}

pub fn run_program(request: DslRunRequest) -> DslResult<DslRunResult> {
    let program = request.program;
    let mut state = if let Some(state) = request.continuation {
        state
    } else {
        let population = sample_population(&program, request.seed)?;
        DslRunState {
            completed_ticks: 0,
            time: population
                .agents
                .iter()
                .map(|_| DslAgentTimeState {
                    active_primary: None,
                    deferred: Vec::new(),
                    occurrence_counts: BTreeMap::new(),
                })
                .collect(),
            agents: population.agents,
            places: program
                .places
                .iter()
                .map(|place| DslPlaceState {
                    id: place.id.clone(),
                    states: place.states.clone(),
                })
                .collect(),
            relationships: population.relationships,
        }
    };
    if state.agents.len() != state.time.len() {
        return Err(DslError::new(
            "INVALID_CHECKPOINT",
            1,
            "Checkpoint time rows must match agents",
        ));
    }
    let decisions = program
        .decisions
        .iter()
        .map(|decision| (decision.id.as_str(), decision))
        .collect::<BTreeMap<_, _>>();
    let actions = program
        .actions
        .iter()
        .map(|action| (action.id.as_str(), action))
        .collect::<BTreeMap<_, _>>();
    let mut action_records = Vec::new();
    let mut reports = program
        .reports
        .iter()
        .map(|definition| DslReport {
            id: definition.id.clone(),
            title: definition.title.clone(),
            group_by: definition.group_by.clone(),
            display: definition.display.clone(),
            record: definition.record.clone(),
            columns: definition.columns.clone(),
            snapshots: Vec::new(),
        })
        .collect::<Vec<_>>();
    let run_start_tick = state.completed_ticks + 1;
    let final_tick = state.completed_ticks + request.ticks;
    for tick in state.completed_ticks + 1..=final_tick {
        let snapshot = state.clone();
        let mut completed_actions = Vec::new();
        for agent_index in 0..state.agents.len() {
            let time = &mut state.time[agent_index];
            let mut candidates = std::mem::take(&mut time.deferred);
            if time.active_primary.is_none() && candidates.is_empty() {
                if let Some(action) = select_action(
                    &program,
                    &snapshot,
                    &decisions,
                    &actions,
                    agent_index,
                    request.seed,
                    tick,
                )? {
                    let occurrence = time.occurrence_counts.entry(action.id.clone()).or_default();
                    let occurrence_index = *occurrence;
                    *occurrence += 1;
                    let definition = timed_definition(action, &program);
                    let duration = sample_duration_hours(
                        &definition.duration,
                        request.seed,
                        agent_index,
                        &action.id,
                        occurrence_index,
                    )
                    .map_err(core_error)?;
                    candidates.push(SampledTimedAction {
                        definition,
                        event: ActionEvent {
                            tick,
                            agent_index,
                            place_index: 0,
                            action: action.id.clone(),
                            rule_index: 0,
                            probability: 1.0,
                            draw: 0.0,
                            provenance: placeholder_provenance(&program),
                        },
                        occurrence_index,
                        sampled_duration_hours: duration,
                        remaining_duration_hours: duration,
                        location_place_index: None,
                        emit_event: true,
                    });
                }
            }
            let allocation = allocate_agent_tick(
                agent_index,
                tick,
                program.tick_hours,
                time.active_primary.take(),
                candidates,
                "idle",
            )
            .map_err(core_error)?;
            for receipt in &allocation.receipt.primary_actions {
                if receipt.status == "completed" {
                    completed_actions.push((
                        agent_index,
                        receipt.action.clone(),
                        receipt.occurrence_index,
                    ));
                }
            }
            time.active_primary = allocation.active_primary;
            time.deferred = allocation.deferred;
        }
        let mut effects = Vec::new();
        let mut self_decisions = vec![None; state.agents.len()];
        let mut target_decisions = vec![None; state.agents.len()];
        for (agent_index, action_id, occurrence_index) in completed_actions {
            let action = actions[action_id.as_str()];
            let target = select_target(
                action,
                &snapshot,
                agent_index,
                request.seed,
                tick,
                occurrence_index,
            )?;
            if action.target.is_some() && target.is_none() {
                continue;
            }
            let outcome = select_outcome(
                action,
                &snapshot,
                agent_index,
                target,
                request.seed,
                tick,
                occurrence_index,
            )?;
            if let Some(next) = &outcome.next_decision {
                self_decisions[agent_index] = Some(next.clone());
            }
            if let (Some(target_index), Some(next)) = (target, &outcome.target_next_decision) {
                target_decisions[target_index] = Some(next.clone());
            }
            for effect in &outcome.effects {
                effects.extend(expand_effect(effect, &snapshot, agent_index, target)?);
            }
            let place = snapshot.agents[agent_index]
                .place()
                .unwrap_or("Unknown")
                .to_owned();
            action_records.push(DslActionRecord {
                tick,
                agent_id: snapshot.agents[agent_index].id.clone(),
                action: action.id.clone(),
                outcome: outcome.id.clone(),
                place,
                target_id: target.map(|index| snapshot.agents[index].id.clone()),
            });
        }
        for (index, decision) in target_decisions
            .into_iter()
            .zip(self_decisions)
            .enumerate()
            .map(|(index, (target, own))| (index, target.or(own)))
        {
            if let Some(decision) = decision {
                state.agents[index].current_decision = decision;
            }
        }
        effects.sort_by(|left, right| left.key.cmp(&right.key));
        for effect in effects {
            apply_effect(&program, &mut state, effect)?;
        }
        state.completed_ticks = tick;
        record_reports(
            &program,
            &state,
            &action_records,
            tick,
            run_start_tick,
            final_tick,
            &mut reports,
        );
    }
    Ok(DslRunResult {
        completed_ticks: state.completed_ticks,
        state,
        actions: action_records,
        results_title: program.results_title,
        results_subtitle: program.results_subtitle,
        reports,
    })
}

fn choose_population_type<'a>(program: &'a Program, seed: u64, index: usize) -> DslResult<&'a str> {
    let mut values = program.population.mix.iter().collect::<Vec<_>>();
    values.sort_by(|left, right| left.agent_type.cmp(&right.agent_type));
    let selected = weighted_index(
        &values
            .iter()
            .map(|item| item.probability)
            .collect::<Vec<_>>(),
        keyed_draw(seed, &format!("adult-{index}:agent_type")),
    )?;
    Ok(&values[selected].agent_type)
}

#[allow(clippy::too_many_arguments)]
fn sample_agent(
    agents: &BTreeMap<&str, &AgentDefinition>,
    agent_type: &str,
    seed: u64,
    id: &str,
    parent_id: Option<String>,
    household_id: String,
    overrides: BTreeMap<String, DslValue>,
) -> DslResult<DslAgentState> {
    let definition = agents.get(agent_type).ok_or_else(|| {
        DslError::new(
            "UNKNOWN_AGENT",
            1,
            format!("Unknown generated agent type {agent_type}"),
        )
    })?;
    let fields = merged_fields(definition, agents)?;
    let mut values = BTreeMap::new();
    for assignment in merged_initial(definition, agents)? {
        let value = overrides.get(&assignment.field).cloned().map_or_else(
            || {
                sample_distribution(
                    &assignment.distribution,
                    &values,
                    keyed_seed(seed, &format!("{id}:{}", assignment.field)),
                )
            },
            Ok,
        )?;
        values.insert(assignment.field.clone(), value);
    }
    let mut traits = BTreeMap::new();
    let mut states = BTreeMap::new();
    for field in fields {
        let value = values.get(&field).cloned().ok_or_else(|| {
            DslError::new(
                "MISSING_INITIAL_VALUE",
                definition.line,
                format!("Agent {agent_type} does not initialize {field}"),
            )
        })?;
        if merged_state_fields(definition, agents)?.contains(&field) {
            states.insert(field, value);
        } else {
            traits.insert(field, value);
        }
    }
    Ok(DslAgentState {
        id: id.to_owned(),
        agent_type: agent_type.to_owned(),
        roles: merged_roles(definition, agents)?,
        traits,
        states,
        current_decision: resolved_routine(definition, agents)?.to_owned(),
        parent_id,
        household_id,
    })
}

fn merged_state_fields(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<BTreeSet<String>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_state_fields(agents[parent.as_str()], agents)?
    } else {
        BTreeSet::new()
    };
    result.extend(agent.states.iter().cloned());
    Ok(result)
}

fn merged_state_bounds(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<BTreeMap<String, ValueBounds>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_state_bounds(agents[parent.as_str()], agents)?
    } else {
        BTreeMap::new()
    };
    result.extend(agent.state_bounds.clone());
    Ok(result)
}

fn sample_distribution(
    distribution: &DistributionSpec,
    context: &BTreeMap<String, DslValue>,
    seed: u64,
) -> DslResult<DslValue> {
    let mut rng = ChaCha8Rng::seed_from_u64(seed);
    let parameter = |name: &str| -> DslResult<f64> {
        distribution
            .parameters
            .get(name)
            .ok_or_else(|| {
                DslError::new(
                    "MISSING_DISTRIBUTION_PARAMETER",
                    distribution.line,
                    format!("{} needs {name}", distribution.kind),
                )
            })
            .and_then(|expression| {
                evaluate(expression, context)?.as_f64().ok_or_else(|| {
                    DslError::new(
                        "INVALID_DISTRIBUTION_PARAMETER",
                        distribution.line,
                        format!("{name} must be numeric"),
                    )
                })
            })
    };
    let value = match distribution.kind.as_str() {
        "Bernoulli" => DslValue::Bool(rng.r#gen::<f64>() < parameter("p")?.clamp(0.0, 1.0)),
        "Categorical" => {
            let mut entries = distribution.categories.iter().collect::<Vec<_>>();
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            let weights = entries
                .iter()
                .map(|(_, expression)| {
                    evaluate(expression, context)?.as_f64().ok_or_else(|| {
                        DslError::new(
                            "INVALID_DISTRIBUTION_PARAMETER",
                            distribution.line,
                            "Categorical probability must be numeric",
                        )
                    })
                })
                .collect::<DslResult<Vec<_>>>()?;
            let total = weights.iter().sum::<f64>();
            if (total - 1.0).abs() > 1e-9 {
                return Err(DslError::new(
                    "PROBABILITIES_NOT_ONE",
                    distribution.line,
                    format!("Categorical probabilities total {total}"),
                ));
            }
            DslValue::Text(entries[weighted_index(&weights, rng.r#gen())?].0.clone())
        }
        "Normal" => {
            let mean = parameter("mean")?;
            let standard_deviation = parameter("sd")?;
            let minimum = parameter("min")?;
            let maximum = parameter("max")?;
            let normal = Normal::new(mean, standard_deviation).map_err(|error| {
                DslError::new("INVALID_DISTRIBUTION", distribution.line, error.to_string())
            })?;
            let mut sampled = mean.clamp(minimum, maximum);
            for _ in 0..64 {
                let candidate = normal.sample(&mut rng);
                if (minimum..=maximum).contains(&candidate) {
                    sampled = candidate;
                    break;
                }
            }
            DslValue::Number(sampled)
        }
        "LogNormal" => {
            let mean = parameter("mean")?;
            let standard_deviation = parameter("sd")?;
            let minimum = parameter("min")?;
            let maximum = distribution
                .parameters
                .get("max")
                .map(|_| parameter("max"))
                .transpose()?
                .unwrap_or(f64::MAX);
            let lognormal = LogNormal::new(mean, standard_deviation).map_err(|error| {
                DslError::new("INVALID_DISTRIBUTION", distribution.line, error.to_string())
            })?;
            DslValue::Number(lognormal.sample(&mut rng).clamp(minimum, maximum))
        }
        "Uniform" => {
            let minimum = parameter("min")?;
            let maximum = parameter("max")?;
            DslValue::Number(minimum + rng.r#gen::<f64>() * (maximum - minimum))
        }
        "Beta" => {
            let beta = Beta::new(parameter("alpha")?, parameter("beta")?).map_err(|error| {
                DslError::new("INVALID_DISTRIBUTION", distribution.line, error.to_string())
            })?;
            DslValue::Number(beta.sample(&mut rng))
        }
        "Poisson" => {
            let lambda = parameter("lambda")?;
            let cap = distribution
                .parameters
                .get("cap")
                .map(|_| parameter("cap"))
                .transpose()?
                .unwrap_or(f64::MAX);
            if lambda <= 0.0 {
                DslValue::Number(0.0)
            } else {
                let poisson = Poisson::new(lambda).map_err(|error| {
                    DslError::new("INVALID_DISTRIBUTION", distribution.line, error.to_string())
                })?;
                DslValue::Number(poisson.sample(&mut rng).min(cap).round())
            }
        }
        _ => {
            return Err(DslError::new(
                "UNKNOWN_DISTRIBUTION",
                distribution.line,
                format!("Unknown distribution {}", distribution.kind),
            ));
        }
    };
    Ok(value)
}

fn select_action<'a>(
    program: &'a Program,
    state: &DslRunState,
    decisions: &BTreeMap<&str, &'a DecisionDefinition>,
    actions: &BTreeMap<&str, &'a ActionDefinition>,
    agent_index: usize,
    seed: u64,
    tick: u64,
) -> DslResult<Option<&'a ActionDefinition>> {
    let agent = &state.agents[agent_index];
    let decision = decisions
        .get(agent.current_decision.as_str())
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_DECISION",
                1,
                format!("Unknown active decision {}", agent.current_decision),
            )
        })?;
    let context = agent_context(
        agent,
        None,
        state
            .places
            .iter()
            .find(|place| agent.place() == Some(place.id.as_str())),
        tick,
        program.tick_hours,
    );
    let mut candidates = decision.branches.iter().collect::<Vec<_>>();
    candidates.sort_by(|left, right| left.action.cmp(&right.action));
    let weights = candidates
        .iter()
        .map(|branch| {
            if branch
                .condition
                .as_ref()
                .map(|condition| evaluate(condition, &context))
                .transpose()?
                .is_some_and(|value| !value.as_bool().unwrap_or(false))
            {
                return Ok(0.0);
            }
            let weight = evaluate(&branch.probability, &context)?
                .as_f64()
                .ok_or_else(|| {
                    DslError::new(
                        "INVALID_DECISION_PROBABILITY",
                        branch.line,
                        "Decision probability must be numeric",
                    )
                })?;
            if !weight.is_finite() || weight < 0.0 {
                return Err(DslError::new(
                    "INVALID_DECISION_PROBABILITY",
                    branch.line,
                    "Decision probability weights must be finite and non-negative",
                ));
            }
            Ok(weight)
        })
        .collect::<DslResult<Vec<_>>>()?;
    if weights.iter().sum::<f64>() <= 1e-15 {
        return Ok(None);
    }
    let selected = weighted_index(
        &weights,
        keyed_draw(
            seed,
            &format!("{}:{tick}:decision:{}", agent.id, decision.id),
        ),
    )?;
    Ok(Some(actions[candidates[selected].action.as_str()]))
}

fn timed_definition(action: &ActionDefinition, program: &Program) -> TimedActionDefinition {
    let mut shape_parameters = BTreeMap::new();
    if let Some(sigma) = action.duration.sigma {
        shape_parameters.insert("sigma".to_owned(), sigma);
    }
    TimedActionDefinition {
        action_id: action.id.clone(),
        category: action.aggregate.clone(),
        duration: DurationDistribution {
            duration_min_hours: action.duration.minimum,
            duration_median_hours: action.duration.median,
            duration_max_hours: action.duration.maximum,
            shape: action.duration.shape.clone(),
            shape_parameters,
            provenance: placeholder_provenance(program),
        },
        duration_overrides: Vec::new(),
        location_place_index_by_agent: Vec::new(),
        priority: 0,
        passive: false,
        interruptibility: "interruptible".to_owned(),
        interruption_outcome: "defer".to_owned(),
        emergency_interruptions: Vec::new(),
    }
}

fn placeholder_provenance(program: &Program) -> ProbabilityProvenance {
    ProbabilityProvenance {
        source: program.placeholder_label.clone(),
        version: program.version.clone(),
        status: "default_estimated".to_owned(),
        resolution_status: None,
        source_places: Vec::new(),
        uncertainty: 1.0,
        source_date: None,
        evidence_id: None,
        evidence_kind: Some("placeholder".to_owned()),
        ci_low: Some(0.0),
        ci_high: Some(1.0),
    }
}

fn select_target(
    action: &ActionDefinition,
    state: &DslRunState,
    source_index: usize,
    seed: u64,
    tick: u64,
    occurrence: u64,
) -> DslResult<Option<usize>> {
    let Some(selector) = &action.target else {
        return Ok(None);
    };
    let source = &state.agents[source_index];
    let place = match selector {
        TargetSelector::Random { place, .. }
        | TargetSelector::Friend { place }
        | TargetSelector::Enemy { place }
        | TargetSelector::Strongest { place, .. } => place,
    };
    let mut candidates = state
        .agents
        .iter()
        .enumerate()
        .filter(|(index, agent)| *index != source_index && agent.place() == Some(place.as_str()))
        .filter(|(_, agent)| match selector {
            TargetSelector::Random { filter, .. } => filter
                .as_ref()
                .map(|filter| {
                    let mut context = agent_context(source, Some(agent), None, tick, 1.0);
                    context.insert("agent".to_owned(), DslValue::Text(agent.id.clone()));
                    context.insert("self".to_owned(), DslValue::Text(source.id.clone()));
                    evaluate(filter, &context)
                        .ok()
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                })
                .unwrap_or(true),
            TargetSelector::Friend { .. } => {
                relationship_exists(state, &source.id, &agent.id, "friend")
            }
            TargetSelector::Enemy { .. } => {
                relationship_exists(state, &source.id, &agent.id, "enemy")
            }
            TargetSelector::Strongest { .. } => true,
        })
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Ok(None);
    }
    if let TargetSelector::Strongest { field, .. } = selector {
        candidates.sort_by(|(_, left_agent), (_, right_agent)| {
            let left = left_agent
                .value(field)
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0);
            let right = right_agent
                .value(field)
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0);
            right
                .total_cmp(&left)
                .then_with(|| left_agent.id.cmp(&right_agent.id))
        });
        return Ok(Some(candidates[0].0));
    }
    candidates.sort_by(|(_, left), (_, right)| left.id.cmp(&right.id));
    let draw = keyed_draw(
        seed,
        &format!("{}:{tick}:{}:{occurrence}:target", source.id, action.id),
    );
    Ok(Some(
        candidates[(draw * candidates.len() as f64) as usize % candidates.len()].0,
    ))
}

fn select_outcome<'a>(
    action: &'a ActionDefinition,
    state: &DslRunState,
    source_index: usize,
    target: Option<usize>,
    seed: u64,
    tick: u64,
    occurrence: u64,
) -> DslResult<&'a OutcomeDefinition> {
    let source = &state.agents[source_index];
    let target_agent = target.map(|index| &state.agents[index]);
    let place = state
        .places
        .iter()
        .find(|place| source.place() == Some(place.id.as_str()));
    let context = agent_context(source, target_agent, place, tick, 1.0);
    let mut outcomes = action.outcomes.iter().collect::<Vec<_>>();
    outcomes.sort_by(|left, right| left.id.cmp(&right.id));
    let weights = outcomes
        .iter()
        .map(|outcome| {
            if outcome
                .condition
                .as_ref()
                .map(|condition| evaluate(condition, &context))
                .transpose()?
                .is_some_and(|value| !value.as_bool().unwrap_or(false))
            {
                return Ok(0.0);
            }
            evaluate(&outcome.probability, &context)?
                .as_f64()
                .ok_or_else(|| {
                    DslError::new(
                        "INVALID_OUTCOME_PROBABILITY",
                        outcome.line,
                        "Outcome probability must be numeric",
                    )
                })
        })
        .collect::<DslResult<Vec<_>>>()?;
    let selected = weighted_index(
        &weights,
        keyed_draw(
            seed,
            &format!("{}:{tick}:{}:{occurrence}:outcome", source.id, action.id),
        ),
    )?;
    Ok(outcomes[selected])
}

#[derive(Clone)]
enum PendingTarget {
    Agent(usize),
    Place(usize),
    Relationship(usize, usize),
}

#[derive(Clone)]
struct PendingEffect {
    key: String,
    target: PendingTarget,
    field: String,
    operation: String,
    value: DslValue,
}

fn expand_effect(
    effect: &EffectDefinition,
    state: &DslRunState,
    source_index: usize,
    target_index: Option<usize>,
) -> DslResult<Vec<PendingEffect>> {
    let source = &state.agents[source_index];
    let target = target_index.map(|index| &state.agents[index]);
    let place = state
        .places
        .iter()
        .find(|place| source.place() == Some(place.id.as_str()));
    let context = agent_context(source, target, place, state.completed_ticks + 1, 1.0);
    let value = evaluate(&effect.value, &context)?;
    let mut targets = Vec::new();
    match &effect.scope {
        EffectScope::SelfAgent => targets.push(PendingTarget::Agent(source_index)),
        EffectScope::Target => {
            if let Some(index) = target_index {
                targets.push(PendingTarget::Agent(index));
            }
        }
        EffectScope::AllAt { place, filter } => {
            for (index, agent) in state.agents.iter().enumerate() {
                if agent.place() != Some(place.as_str()) {
                    continue;
                }
                if filter.as_ref().is_some_and(|filter| {
                    let mut context =
                        agent_context(agent, Some(source), None, state.completed_ticks + 1, 1.0);
                    context.insert("agent".to_owned(), DslValue::Text(agent.id.clone()));
                    context.insert("self".to_owned(), DslValue::Text(source.id.clone()));
                    !evaluate(filter, &context)
                        .ok()
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                }) {
                    continue;
                }
                targets.push(PendingTarget::Agent(index));
            }
        }
        EffectScope::Place { place } => {
            if let Some(index) = state.places.iter().position(|item| item.id == *place) {
                targets.push(PendingTarget::Place(index));
            }
        }
        EffectScope::RelationshipWithTarget => {
            if let Some(index) = target_index {
                targets.push(PendingTarget::Relationship(source_index, index));
            }
        }
    }
    Ok(targets
        .into_iter()
        .map(|target| PendingEffect {
            key: format!("{}:{}:{}", source.id, effect.line, effect.field),
            target,
            field: effect.field.clone(),
            operation: effect.operation.clone(),
            value: value.clone(),
        })
        .collect())
}

fn apply_effect(
    program: &Program,
    state: &mut DslRunState,
    effect: PendingEffect,
) -> DslResult<()> {
    match effect.target {
        PendingTarget::Agent(index) => {
            let agent = &mut state.agents[index];
            let definitions = program
                .agents
                .iter()
                .map(|item| (item.id.as_str(), item))
                .collect::<BTreeMap<_, _>>();
            let bounds = definitions
                .get(agent.agent_type.as_str())
                .map(|definition| merged_state_bounds(definition, &definitions))
                .transpose()?
                .and_then(|values| values.get(&effect.field).cloned());
            if let Some(current) = agent.states.get_mut(&effect.field) {
                apply_value(current, &effect.operation, &effect.value, bounds.as_ref())?;
            } else if let Some(current) = agent.traits.get_mut(&effect.field) {
                apply_value(current, &effect.operation, &effect.value, None)?;
            } else {
                agent.states.insert(effect.field, effect.value);
            }
        }
        PendingTarget::Place(index) => {
            let bounds = program
                .places
                .iter()
                .find(|item| item.id == state.places[index].id)
                .and_then(|item| item.state_bounds.get(&effect.field));
            let current = state.places[index]
                .states
                .entry(effect.field.clone())
                .or_insert(DslValue::Number(0.0));
            apply_value(current, &effect.operation, &effect.value, bounds)?;
        }
        PendingTarget::Relationship(source, target) => {
            let source_id = state.agents[source].id.clone();
            let target_id = state.agents[target].id.clone();
            let relationship_index = state
                .relationships
                .iter()
                .position(|item| item.source_id == source_id && item.target_id == target_id)
                .unwrap_or_else(|| {
                    state.relationships.push(DslRelationshipState {
                        kind: "interaction".to_owned(),
                        source_id: source_id.clone(),
                        target_id: target_id.clone(),
                        values: BTreeMap::new(),
                    });
                    state.relationships.len() - 1
                });
            let relationship = &mut state.relationships[relationship_index];
            let current = relationship.values.entry(effect.field).or_default();
            let next = apply_number(
                *current,
                &effect.operation,
                effect.value.as_f64().unwrap_or(0.0),
            )?;
            *current = next;
        }
    }
    Ok(())
}

fn apply_value(
    current: &mut DslValue,
    operation: &str,
    value: &DslValue,
    bounds: Option<&ValueBounds>,
) -> DslResult<()> {
    if operation == "=" {
        *current = value.clone();
        clamp_value(current, bounds);
        return Ok(());
    }
    let left = current.as_f64().ok_or_else(|| {
        DslError::new(
            "TYPE_ERROR",
            1,
            "Numeric effect requires numeric current value",
        )
    })?;
    let right = value.as_f64().ok_or_else(|| {
        DslError::new(
            "TYPE_ERROR",
            1,
            "Numeric effect requires numeric effect value",
        )
    })?;
    *current = DslValue::Number(apply_number(left, operation, right)?);
    clamp_value(current, bounds);
    Ok(())
}

fn clamp_value(value: &mut DslValue, bounds: Option<&ValueBounds>) {
    let (DslValue::Number(number), Some(bounds)) = (value, bounds) else {
        return;
    };
    *number = number.clamp(bounds.minimum, bounds.maximum);
}

fn apply_number(current: f64, operation: &str, value: f64) -> DslResult<f64> {
    match operation {
        "+=" => Ok(current + value),
        "-=" => Ok(current - value),
        "*=" => Ok(current * value),
        "=" => Ok(value),
        _ => Err(DslError::new(
            "UNKNOWN_EFFECT_OPERATION",
            1,
            format!("Unknown effect operation {operation}"),
        )),
    }
}

fn agent_context(
    agent: &DslAgentState,
    target: Option<&DslAgentState>,
    place: Option<&DslPlaceState>,
    tick: u64,
    tick_hours: f64,
) -> BTreeMap<String, DslValue> {
    let mut values = BTreeMap::new();
    values.extend(agent.traits.clone());
    values.extend(agent.states.clone());
    values.insert("agent".to_owned(), DslValue::Text(agent.id.clone()));
    values.insert("self".to_owned(), DslValue::Text(agent.id.clone()));
    values.insert("tick".to_owned(), DslValue::Number(tick as f64));
    values.insert(
        "hour".to_owned(),
        DslValue::Number(((tick.saturating_sub(1)) as f64 * tick_hours) % 24.0),
    );
    values.insert(
        "day".to_owned(),
        DslValue::Number(((tick.saturating_sub(1)) as f64 * tick_hours / 24.0).floor()),
    );
    for role in &agent.roles {
        values.insert(format!("role.{role}"), DslValue::Bool(true));
    }
    if let Some(target) = target {
        values.insert("target".to_owned(), DslValue::Text(target.id.clone()));
        for (name, value) in target.traits.iter().chain(&target.states) {
            values.insert(format!("target.{name}"), value.clone());
        }
    }
    if let Some(place) = place {
        for (name, value) in &place.states {
            values.insert(format!("place.{name}"), value.clone());
        }
    }
    values
}

fn relationship_exists(state: &DslRunState, source: &str, target: &str, kind: &str) -> bool {
    state.relationships.iter().any(|item| {
        item.kind == kind
            && ((item.source_id == source && item.target_id == target)
                || (item.source_id == target && item.target_id == source))
    })
}

#[allow(clippy::too_many_arguments)]
fn record_reports(
    program: &Program,
    state: &DslRunState,
    actions: &[DslActionRecord],
    tick: u64,
    run_start_tick: u64,
    final_tick: u64,
    reports: &mut [DslReport],
) {
    let ticks_per_day = (24.0 / program.tick_hours).round().max(1.0) as u64;
    for (definition, report) in program.reports.iter().zip(reports) {
        let should_record = match definition.record.as_str() {
            "tick" => true,
            "daily" => tick % ticks_per_day == 0 || tick == final_tick,
            "final" => tick == final_tick,
            _ => false,
        };
        if should_record {
            report.snapshots.push(DslReportSnapshot {
                tick,
                rows: report_rows(
                    program,
                    definition,
                    state,
                    actions,
                    tick,
                    run_start_tick,
                    ticks_per_day,
                ),
            });
        }
    }
}

fn report_rows(
    program: &Program,
    definition: &ReportDefinition,
    state: &DslRunState,
    actions: &[DslActionRecord],
    tick: u64,
    run_start_tick: u64,
    ticks_per_day: u64,
) -> Vec<DslReportRow> {
    report_groups(program, definition, state)
        .into_iter()
        .map(|(group_id, indices)| {
            let values = definition
                .columns
                .iter()
                .map(|column| {
                    (
                        column.id.clone(),
                        report_value(
                            program,
                            definition,
                            column,
                            state,
                            actions,
                            tick,
                            run_start_tick,
                            ticks_per_day,
                            &group_id,
                            &indices,
                        ),
                    )
                })
                .collect();
            DslReportRow { group_id, values }
        })
        .collect()
}

fn report_groups(
    program: &Program,
    definition: &ReportDefinition,
    state: &DslRunState,
) -> Vec<(String, Vec<usize>)> {
    match definition.group_by.as_str() {
        "place" => program
            .places
            .iter()
            .map(|place| {
                (
                    place.id.clone(),
                    state
                        .agents
                        .iter()
                        .enumerate()
                        .filter(|(_, agent)| agent.place() == Some(place.id.as_str()))
                        .map(|(index, _)| index)
                        .collect(),
                )
            })
            .collect(),
        "agent_type" => program
            .agents
            .iter()
            .map(|agent_type| {
                (
                    agent_type.id.clone(),
                    state
                        .agents
                        .iter()
                        .enumerate()
                        .filter(|(_, agent)| agent.agent_type == agent_type.id)
                        .map(|(index, _)| index)
                        .collect(),
                )
            })
            .collect(),
        _ => vec![("All".to_owned(), (0..state.agents.len()).collect())],
    }
}

#[allow(clippy::too_many_arguments)]
fn report_value(
    program: &Program,
    definition: &ReportDefinition,
    column: &ReportColumnDefinition,
    state: &DslRunState,
    actions: &[DslActionRecord],
    tick: u64,
    run_start_tick: u64,
    ticks_per_day: u64,
    group_id: &str,
    indices: &[usize],
) -> DslReportValue {
    let ids = indices
        .iter()
        .map(|index| state.agents[*index].id.as_str())
        .collect::<BTreeSet<_>>();
    match &column.metric {
        ReportMetric::Count => DslReportValue::Number(indices.len() as f64),
        ReportMetric::Mean { field } => {
            let values = numeric_values(state, indices, field);
            DslReportValue::Number(if values.is_empty() {
                0.0
            } else {
                values.iter().sum::<f64>() / values.len() as f64
            })
        }
        ReportMetric::Sum { field } => {
            DslReportValue::Number(numeric_values(state, indices, field).iter().sum::<f64>())
        }
        ReportMetric::ActionCount { aggregate, window } => {
            let selected = selected_actions(
                definition,
                actions,
                tick,
                run_start_tick,
                ticks_per_day,
                window,
                group_id,
                &ids,
            );
            DslReportValue::Number(
                selected
                    .iter()
                    .filter(|record| action_aggregate(program, record) == aggregate)
                    .count() as f64,
            )
        }
        ReportMetric::OutcomeCount {
            action,
            outcome,
            window,
        } => {
            let selected = selected_actions(
                definition,
                actions,
                tick,
                run_start_tick,
                ticks_per_day,
                window,
                group_id,
                &ids,
            );
            DslReportValue::Number(
                selected
                    .iter()
                    .filter(|record| record.action == *action && record.outcome == *outcome)
                    .count() as f64,
            )
        }
        ReportMetric::ActionRates { per, window } => {
            let selected = selected_actions(
                definition,
                actions,
                tick,
                run_start_tick,
                ticks_per_day,
                window,
                group_id,
                &ids,
            );
            let mut counts = BTreeMap::new();
            for record in selected {
                *counts
                    .entry(action_aggregate(program, record).to_owned())
                    .or_insert(0_u64) += 1;
            }
            DslReportValue::Rates(
                counts
                    .into_iter()
                    .map(|(action, count)| {
                        (
                            action,
                            if indices.is_empty() {
                                0.0
                            } else {
                                count as f64 / indices.len() as f64 * per
                            },
                        )
                    })
                    .collect(),
            )
        }
        ReportMetric::FamilySize => DslReportValue::Number(average_family_size(state, indices)),
        ReportMetric::KidsPerFamily => DslReportValue::Number(average_kids_per_family(state, &ids)),
    }
}

fn numeric_values(state: &DslRunState, indices: &[usize], field: &str) -> Vec<f64> {
    indices
        .iter()
        .filter_map(|index| state.agents[*index].value(field)?.as_f64())
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn selected_actions<'a>(
    definition: &ReportDefinition,
    actions: &'a [DslActionRecord],
    tick: u64,
    run_start_tick: u64,
    ticks_per_day: u64,
    window: &str,
    group_id: &str,
    ids: &BTreeSet<&str>,
) -> Vec<&'a DslActionRecord> {
    let first_tick = match window {
        "tick" => tick,
        "day" => tick.saturating_sub(ticks_per_day - 1).max(run_start_tick),
        _ => run_start_tick,
    };
    actions
        .iter()
        .filter(|record| {
            (first_tick..=tick).contains(&record.tick)
                && if definition.group_by == "place" {
                    record.place == group_id
                } else if definition.group_by == "agent_type" {
                    ids.contains(record.agent_id.as_str())
                } else {
                    true
                }
        })
        .collect()
}

fn action_aggregate<'a>(program: &'a Program, record: &'a DslActionRecord) -> &'a str {
    program
        .actions
        .iter()
        .find(|action| action.id == record.action)
        .map(|action| action.aggregate.as_str())
        .unwrap_or(record.action.as_str())
}

fn average_family_size(state: &DslRunState, indices: &[usize]) -> f64 {
    let households = indices
        .iter()
        .map(|index| state.agents[*index].household_id.as_str())
        .collect::<BTreeSet<_>>();
    if households.is_empty() {
        0.0
    } else {
        state
            .agents
            .iter()
            .filter(|agent| households.contains(agent.household_id.as_str()))
            .count() as f64
            / households.len() as f64
    }
}

fn average_kids_per_family(state: &DslRunState, ids: &BTreeSet<&str>) -> f64 {
    let families = state
        .relationships
        .iter()
        .filter(|relationship| {
            relationship.kind == "parent" && ids.contains(relationship.source_id.as_str())
        })
        .map(|relationship| relationship.source_id.as_str())
        .collect::<BTreeSet<_>>();
    if families.is_empty() {
        0.0
    } else {
        state
            .relationships
            .iter()
            .filter(|relationship| {
                relationship.kind == "parent" && families.contains(relationship.source_id.as_str())
            })
            .count() as f64
            / families.len() as f64
    }
}

fn weighted_index(weights: &[f64], draw: f64) -> DslResult<usize> {
    let total = weights.iter().sum::<f64>();
    if weights.is_empty()
        || weights
            .iter()
            .any(|weight| !weight.is_finite() || *weight < 0.0)
        || total <= 0.0
    {
        return Err(DslError::new(
            "INVALID_PROBABILITY_DISTRIBUTION",
            1,
            "Probability weights need a positive finite total",
        ));
    }
    let threshold = draw * total;
    let mut cumulative = 0.0;
    for (index, weight) in weights.iter().enumerate() {
        cumulative += weight;
        if threshold < cumulative || index + 1 == weights.len() {
            return Ok(index);
        }
    }
    Ok(weights.len() - 1)
}

fn keyed_seed(seed: u64, key: &str) -> u64 {
    let mut hash = 0xcbf29ce484222325u64 ^ seed;
    for byte in key.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

fn keyed_draw(seed: u64, key: &str) -> f64 {
    ChaCha8Rng::seed_from_u64(keyed_seed(seed, key)).r#gen()
}

fn core_error(error: crate::error::CoreError) -> DslError {
    DslError::new(&error.code, 1, error.message)
}
