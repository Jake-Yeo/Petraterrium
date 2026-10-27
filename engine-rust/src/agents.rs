use crate::agent_types::*;
use crate::agent_validation::validate_request;
use crate::csr::CsrMatrix;
use crate::error::{CoreError, CoreResult};
use crate::event_queue::EventQueue;
use crate::random::DeterministicRng;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
struct CompiledTransition {
    id: String,
    to_state: usize,
    rules: Vec<ProbabilityRule>,
    effects: Vec<TransitionEffect>,
}

#[derive(Clone)]
struct CompiledModule {
    id: String,
    entry_state: usize,
    state_names: Vec<String>,
    exit_states: BTreeSet<usize>,
    transitions: Vec<Vec<CompiledTransition>>,
}

struct CompiledProgram {
    modules: Vec<CompiledModule>,
    routes: BTreeMap<(usize, usize), usize>,
}

#[derive(Clone)]
struct AgentBatch {
    modules: Vec<usize>,
    states: Vec<usize>,
    places: Vec<usize>,
    traits: BTreeMap<String, Vec<f64>>,
    trait_dictionaries: BTreeMap<String, TraitDictionary>,
    memory: BTreeMap<String, Vec<f64>>,
}

impl AgentBatch {
    fn len(&self) -> usize {
        self.states.len()
    }

    fn shards(&self, place_count: usize) -> Vec<Vec<usize>> {
        let mut shards = vec![Vec::new(); place_count];
        for (agent, place) in self.places.iter().enumerate() {
            shards[*place].push(agent);
        }
        shards
    }
}

pub fn run(request: AgentProgramRequest) -> CoreResult<AgentProgramResult> {
    validate_request(&request)?;
    let program = compile_program(&request)?;
    let mut current = compile_agents(&request, &program)?;
    let mut rng = DeterministicRng::new(request.seed);
    let mut event_queue = EventQueue::default();
    let mut transition_counts = Vec::new();
    let mut routine_actions = Vec::new();
    let mut synchronization = Vec::new();
    for tick in 1..=request.ticks {
        let elapsed_hours = (tick - 1) as f64 * request.tick_hours;
        let absolute_hour = request.start_hour + elapsed_hours;
        let hour = absolute_hour.rem_euclid(24.0);
        let weekday = ((request.start_weekday as u64
            + (absolute_hour.div_euclid(24.0).floor() as u64))
            % 7) as u8;
        let neighbor_values = neighbor_state_values(&current, &program, request.network.as_ref())?;
        routine_actions.extend(schedule_lookup(
            tick,
            hour,
            weekday,
            &current,
            &program,
            &request.schedules,
        ));
        evaluate_meaningful_actions(
            tick,
            hour,
            weekday,
            &current,
            &request,
            &neighbor_values,
            &mut rng,
            &mut event_queue,
        )?;
        let (mut next, counts) = apply_modules(
            tick,
            hour,
            weekday,
            &current,
            &request,
            &program,
            &neighbor_values,
            &mut rng,
        )?;
        apply_routes(&mut next, &program);
        transition_counts.extend(counts);
        current = next;
        append_synchronization(tick, &request.synchronization, &mut synchronization);
    }
    let shard_populations = current
        .shards(request.places.len())
        .into_iter()
        .enumerate()
        .map(|(place_index, agents)| ShardPopulation {
            place_index,
            place: request.places[place_index].id.clone(),
            agents: agents.len(),
        })
        .collect();
    Ok(AgentProgramResult {
        seed: request.seed,
        ticks: request.ticks,
        agents: output_agents(current, &program),
        transition_counts,
        transition_evidence: transition_evidence(&program),
        events: event_queue.drain(),
        routine_actions,
        synchronization,
        shard_populations,
    })
}

fn transition_evidence(program: &CompiledProgram) -> Vec<TransitionEvidenceRecord> {
    let mut records = Vec::new();
    for module in &program.modules {
        for transitions in &module.transitions {
            for transition in transitions {
                for (rule_index, rule) in transition.rules.iter().enumerate() {
                    records.push(TransitionEvidenceRecord {
                        module: module.id.clone(),
                        transition: transition.id.clone(),
                        rule_index,
                        probability: rule.probability.expect("validated probability"),
                        provenance: rule.provenance.clone(),
                    });
                }
            }
        }
    }
    records
}

fn compile_program(request: &AgentProgramRequest) -> CoreResult<CompiledProgram> {
    let module_indices: BTreeMap<_, _> = request
        .modules
        .iter()
        .enumerate()
        .map(|(index, module)| (module.id.as_str(), index))
        .collect();
    let mut modules = Vec::with_capacity(request.modules.len());
    for module in &request.modules {
        let state_indices: BTreeMap<_, _> = module
            .states
            .iter()
            .enumerate()
            .map(|(index, state)| (state.as_str(), index))
            .collect();
        let mut transitions = vec![Vec::new(); module.states.len()];
        for transition in &module.transitions {
            let source = state_indices[transition.from_state.as_str()];
            transitions[source].push(CompiledTransition {
                id: transition.id.clone(),
                to_state: state_indices[transition.to_state.as_str()],
                rules: transition.rules.clone(),
                effects: transition.effects.clone(),
            });
        }
        modules.push(CompiledModule {
            id: module.id.clone(),
            entry_state: state_indices[module.entry_state.as_str()],
            state_names: module.states.clone(),
            exit_states: module
                .exit_states
                .iter()
                .map(|state| state_indices[state.as_str()])
                .collect(),
            transitions,
        });
    }
    let mut routes = BTreeMap::new();
    for route in &request.routes {
        let source_module = module_indices[route.from_module.as_str()];
        let exit_state = modules[source_module]
            .state_names
            .iter()
            .position(|state| state == &route.exit_state)
            .expect("validated route exit");
        routes.insert(
            (source_module, exit_state),
            module_indices[route.to_module.as_str()],
        );
    }
    Ok(CompiledProgram { modules, routes })
}

fn compile_agents(
    request: &AgentProgramRequest,
    program: &CompiledProgram,
) -> CoreResult<AgentBatch> {
    let module_indices: BTreeMap<_, _> = program
        .modules
        .iter()
        .enumerate()
        .map(|(index, module)| (module.id.as_str(), index))
        .collect();
    let mut modules = Vec::with_capacity(request.agents.module.len());
    let mut states = Vec::with_capacity(request.agents.state.len());
    for (agent, module_name) in request.agents.module.iter().enumerate() {
        let module_index = *module_indices.get(module_name.as_str()).ok_or_else(|| {
            CoreError::at(
                "UNKNOWN_AGENT_MODULE",
                format!("Agent {agent} references unknown module {module_name}"),
                format!("agents.module.{agent}"),
            )
        })?;
        let state_name = &request.agents.state[agent];
        let state_index = program.modules[module_index]
            .state_names
            .iter()
            .position(|state| state == state_name)
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_AGENT_STATE",
                    format!("Agent {agent} references unknown state {state_name}"),
                    format!("agents.state.{agent}"),
                )
            })?;
        modules.push(module_index);
        states.push(state_index);
    }
    let mut memory = request.agents.memory.clone();
    for module in &request.modules {
        for output in &module.outputs {
            if let Some(name) = output.strip_prefix("memory.") {
                memory
                    .entry(name.to_owned())
                    .or_insert_with(|| vec![0.0; states.len()]);
            }
        }
    }
    Ok(AgentBatch {
        modules,
        states,
        places: request.agents.place.clone(),
        traits: request.agents.traits.clone(),
        trait_dictionaries: request.agents.trait_dictionaries.clone(),
        memory,
    })
}

fn neighbor_state_values(
    batch: &AgentBatch,
    program: &CompiledProgram,
    network: Option<&CsrMatrix>,
) -> CoreResult<BTreeMap<String, Vec<f64>>> {
    let Some(network) = network else {
        return Ok(BTreeMap::new());
    };
    let state_names: BTreeSet<_> = program
        .modules
        .iter()
        .flat_map(|module| module.state_names.iter().cloned())
        .collect();
    let mut result = BTreeMap::new();
    for state_name in state_names {
        let indicator: Vec<f64> = (0..batch.len())
            .map(|agent| {
                let module = &program.modules[batch.modules[agent]];
                f64::from(module.state_names[batch.states[agent]] == state_name)
            })
            .collect();
        result.insert(
            state_name,
            network.normalized_matvec(&indicator, "network")?,
        );
    }
    Ok(result)
}

#[allow(clippy::too_many_arguments)]
fn apply_modules(
    tick: u64,
    hour: f64,
    weekday: u8,
    current: &AgentBatch,
    request: &AgentProgramRequest,
    program: &CompiledProgram,
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    rng: &mut DeterministicRng,
) -> CoreResult<(AgentBatch, Vec<TransitionCount>)> {
    let mut next = current.clone();
    let mut counts: BTreeMap<(usize, String), u64> = BTreeMap::new();
    for shard in current.shards(request.places.len()) {
        let mut partitions: BTreeMap<(usize, usize), Vec<usize>> = BTreeMap::new();
        for agent in shard {
            partitions
                .entry((current.modules[agent], current.states[agent]))
                .or_default()
                .push(agent);
        }
        for ((module_index, state_index), agents) in partitions {
            let module = &program.modules[module_index];
            if module.exit_states.contains(&state_index) {
                continue;
            }
            let transitions = &module.transitions[state_index];
            let mut probability_columns = Vec::with_capacity(transitions.len());
            for (transition_index, transition) in transitions.iter().enumerate() {
                probability_columns.push(resolve_transition_probability_batch(
                    &transition.rules,
                    &agents,
                    hour,
                    weekday,
                    current,
                    &request.places,
                    neighbor_values,
                    &format!(
                        "modules.{module_index}.state.{state_index}.transitions.{transition_index}"
                    ),
                )?);
            }
            for (batch_index, agent) in agents.into_iter().enumerate() {
                let probabilities: Vec<f64> = probability_columns
                    .iter()
                    .map(|column| column[batch_index])
                    .collect();
                let selected = rng.categorical(
                    &probabilities,
                    &format!("agents.{agent}.tick.{tick}.outgoing_probabilities"),
                )?;
                let transition = &transitions[selected];
                next.states[agent] = transition.to_state;
                apply_effects(agent, &transition.effects, &mut next, request.places.len())?;
                *counts
                    .entry((module_index, transition.id.clone()))
                    .or_default() += 1;
            }
        }
    }
    let result = counts
        .into_iter()
        .map(|((module_index, transition), count)| TransitionCount {
            tick,
            module: program.modules[module_index].id.clone(),
            transition,
            count,
        })
        .collect();
    Ok((next, result))
}

#[allow(clippy::too_many_arguments)]
fn resolve_transition_probability_batch(
    rules: &[ProbabilityRule],
    agents: &[usize],
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
) -> CoreResult<Vec<f64>> {
    agents
        .iter()
        .map(|agent| {
            resolve_transition_probability(
                rules,
                *agent,
                hour,
                weekday,
                batch,
                places,
                neighbor_values,
                path,
                false,
            )
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn resolve_transition_probability(
    rules: &[ProbabilityRule],
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
    unmatched_is_zero: bool,
) -> CoreResult<f64> {
    let mut matches = Vec::new();
    for (rule_index, rule) in rules.iter().enumerate() {
        if conditions_match(
            &rule.conditions,
            agent,
            hour,
            weekday,
            batch,
            places,
            neighbor_values,
            &format!("{path}.rules.{rule_index}.conditions"),
        )? {
            matches.push(rule);
        }
    }
    if matches.len() > 1 {
        return Err(CoreError::at(
            "AMBIGUOUS_PROBABILITY",
            "More than one probability rule matches this agent",
            path,
        ));
    }
    if let Some(probability) = matches.first().and_then(|rule| rule.probability) {
        return Ok(probability);
    }
    if unmatched_is_zero {
        Ok(0.0)
    } else {
        Err(CoreError::at(
            "UNKNOWN_PROBABILITY",
            "No evidence-backed probability rule matches this agent",
            path,
        ))
    }
}

#[allow(clippy::too_many_arguments)]
fn conditions_match(
    conditions: &[NumericCondition],
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
) -> CoreResult<bool> {
    for (index, condition) in conditions.iter().enumerate() {
        let actual = input_value(
            &condition.input,
            agent,
            hour,
            weekday,
            batch,
            places,
            neighbor_values,
            &format!("{path}.{index}.input"),
        )?;
        let matches = match condition.operator.as_str() {
            "eq" => (actual - condition.value).abs() <= 1e-12,
            "ne" => (actual - condition.value).abs() > 1e-12,
            "gt" => actual > condition.value,
            "gte" => actual >= condition.value,
            "lt" => actual < condition.value,
            "lte" => actual <= condition.value,
            _ => unreachable!("validated condition operator"),
        };
        if !matches {
            return Ok(false);
        }
    }
    Ok(true)
}

#[allow(clippy::too_many_arguments)]
fn input_value(
    input: &str,
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
) -> CoreResult<f64> {
    if input == "context.hour" {
        return Ok(hour);
    }
    if input == "context.weekday" {
        return Ok(weekday as f64);
    }
    if input == "place.index" {
        return Ok(batch.places[agent] as f64);
    }
    if let Some(name) = input.strip_prefix("trait.") {
        return batch
            .traits
            .get(name)
            .map(|column| column[agent])
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_INPUT",
                    format!("Unknown trait column {name}"),
                    path,
                )
            });
    }
    if let Some(name) = input.strip_prefix("memory.") {
        return batch
            .memory
            .get(name)
            .map(|column| column[agent])
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_INPUT",
                    format!("Unknown memory column {name}"),
                    path,
                )
            });
    }
    if let Some(name) = input.strip_prefix("place.") {
        return places[batch.places[agent]]
            .state
            .get(name)
            .copied()
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_INPUT",
                    format!("Unknown place-state field {name}"),
                    path,
                )
            });
    }
    if let Some(name) = input.strip_prefix("neighbor.") {
        return neighbor_values
            .get(name)
            .map(|column| column[agent])
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_INPUT",
                    format!("Unknown neighbor-state field {name}"),
                    path,
                )
            });
    }
    Err(CoreError::at(
        "UNKNOWN_INPUT",
        format!("Unknown module input {input}"),
        path,
    ))
}

fn apply_effects(
    agent: usize,
    effects: &[TransitionEffect],
    next: &mut AgentBatch,
    place_count: usize,
) -> CoreResult<()> {
    for effect in effects {
        if effect.target == "place" {
            let place = effect.value.round();
            if effect.operation != "set"
                || (place - effect.value).abs() > 1e-12
                || place < 0.0
                || place as usize >= place_count
            {
                return Err(CoreError::new(
                    "INVALID_PLACE_EFFECT",
                    "Place effects must set an integer index for an existing shard",
                ));
            }
            next.places[agent] = place as usize;
            continue;
        }
        let name = effect
            .target
            .strip_prefix("memory.")
            .expect("validated memory target");
        let column = next.memory.get_mut(name).expect("compiled output column");
        if effect.operation == "set" {
            column[agent] = effect.value;
        } else {
            column[agent] += effect.value;
        }
    }
    Ok(())
}

fn apply_routes(batch: &mut AgentBatch, program: &CompiledProgram) {
    for agent in 0..batch.len() {
        if let Some(target_module) = program
            .routes
            .get(&(batch.modules[agent], batch.states[agent]))
        {
            batch.modules[agent] = *target_module;
            batch.states[agent] = program.modules[*target_module].entry_state;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn evaluate_meaningful_actions(
    tick: u64,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    request: &AgentProgramRequest,
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    rng: &mut DeterministicRng,
    queue: &mut EventQueue,
) -> CoreResult<()> {
    for (action_index, action) in request.meaningful_actions.iter().enumerate() {
        for agent in 0..batch.len() {
            let probability = resolve_transition_probability(
                &action.rules,
                agent,
                hour,
                weekday,
                batch,
                &request.places,
                neighbor_values,
                &format!("meaningful_actions.{action_index}"),
                true,
            )?;
            let draw = rng.draw();
            if draw < probability {
                queue.push(ActionEvent {
                    tick,
                    agent_index: agent,
                    place_index: batch.places[agent],
                    action: action.id.clone(),
                });
            }
        }
    }
    Ok(())
}

fn schedule_lookup(
    tick: u64,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    program: &CompiledProgram,
    schedules: &[ScheduleRow],
) -> Vec<RoutineActionBatch> {
    let mut result = Vec::new();
    for schedule in schedules {
        if !schedule.weekdays.contains(&weekday) || !hour_matches(schedule, hour) {
            continue;
        }
        let agent_indices = (0..batch.len())
            .filter(|agent| {
                let module = &program.modules[batch.modules[*agent]];
                let state = &module.state_names[batch.states[*agent]];
                (schedule.modules.is_empty() || schedule.modules.contains(&module.id))
                    && (schedule.states.is_empty() || schedule.states.contains(state))
            })
            .collect::<Vec<_>>();
        if !agent_indices.is_empty() {
            result.push(RoutineActionBatch {
                tick,
                schedule: schedule.id.clone(),
                action: schedule.action.clone(),
                agent_indices,
            });
        }
    }
    result
}

fn hour_matches(schedule: &ScheduleRow, hour: f64) -> bool {
    if (schedule.start_hour - schedule.end_hour).abs() <= 1e-12 {
        return true;
    }
    if schedule.start_hour < schedule.end_hour {
        hour >= schedule.start_hour && hour < schedule.end_hour
    } else {
        hour >= schedule.start_hour || hour < schedule.end_hour
    }
}

fn append_synchronization(
    tick: u64,
    config: &SynchronizationConfig,
    output: &mut Vec<SynchronizationEnvelope>,
) {
    append_sync_kind(
        tick,
        "border",
        config.border_every_ticks,
        &config.border_payloads,
        output,
    );
    append_sync_kind(
        tick,
        "media",
        config.media_every_ticks,
        &config.media_payloads,
        output,
    );
    append_sync_kind(
        tick,
        "weekly_leader",
        config.weekly_leader_every_ticks,
        &config.weekly_leader_payloads,
        output,
    );
}

fn append_sync_kind(
    tick: u64,
    kind: &str,
    cadence: Option<u64>,
    payloads: &[serde_json::Value],
    output: &mut Vec<SynchronizationEnvelope>,
) {
    if cadence.is_some_and(|value| tick % value == 0) {
        output.push(SynchronizationEnvelope {
            tick,
            kind: kind.to_owned(),
            payloads: payloads.to_vec(),
        });
    }
}

fn output_agents(batch: AgentBatch, program: &CompiledProgram) -> AgentColumnsOutput {
    let module = batch
        .modules
        .iter()
        .map(|index| program.modules[*index].id.clone())
        .collect();
    let state = batch
        .modules
        .iter()
        .zip(&batch.states)
        .map(|(module_index, state_index)| {
            program.modules[*module_index].state_names[*state_index].clone()
        })
        .collect();
    AgentColumnsOutput {
        module,
        state,
        place: batch.places,
        traits: batch.traits,
        trait_dictionaries: batch.trait_dictionaries,
        memory: batch.memory,
    }
}
