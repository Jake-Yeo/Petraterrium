use crate::agent_types::*;
use crate::agent_validation::validate_request;
use crate::csr::CsrMatrix;
use crate::error::{CoreError, CoreResult};
use crate::event_queue::EventQueue;
use crate::interactions::{
    InteractionAgentColumns, InteractionPlace, InteractionRequest, run_interactions,
};
use crate::random::DeterministicRng;
use crate::state_finance::{
    CashFlowColumns, FinanceColumns, StateColumns, advance_finance_columns, advance_state_columns,
};
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
    available_place_kinds: BTreeSet<String>,
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
    let completed_tick = request
        .continuation
        .as_ref()
        .map_or(0, |continuation| continuation.completed_tick);
    if let Some(continuation) = &request.continuation {
        let word_position = continuation
            .rng_word_position
            .parse::<u128>()
            .map_err(|_| {
                CoreError::at(
                    "INVALID_RNG_POSITION",
                    "Continuation RNG position must be an unsigned integer",
                    "continuation.rng_word_position",
                )
            })?;
        rng.set_word_position(word_position);
    }
    let final_tick = completed_tick.checked_add(request.ticks).ok_or_else(|| {
        CoreError::at(
            "TICK_OVERFLOW",
            "Continuation tick plus requested ticks exceeds the engine range",
            "ticks",
        )
    })?;
    let mut event_queue = EventQueue::default();
    let mut events = Vec::new();
    let mut transition_counts = Vec::new();
    let mut transition_outcomes = Vec::new();
    let mut routine_actions = Vec::new();
    let mut routine_unavailable = Vec::new();
    let mut location_transitions = Vec::new();
    let mut active_travel = request.continuation.as_ref().map_or_else(
        || vec![None; current.len()],
        |value| value.active_travel.clone(),
    );
    let mut interaction_events = Vec::new();
    let mut blocked_interactions = Vec::new();
    let mut interaction_relationships = request.continuation.as_ref().map_or_else(
        || request.interactions.relationships.clone(),
        |value| value.relationships.clone(),
    );
    let interaction_agent_ids = if request.agents.agent_ids.is_empty() {
        (0..current.len())
            .map(|index| format!("agent-{index}"))
            .collect()
    } else {
        request.agents.agent_ids.clone()
    };
    let mut synchronization = Vec::new();
    let mut state_ticks = Vec::new();
    for tick in completed_tick + 1..=final_tick {
        let elapsed_hours = (tick - 1) as f64 * request.tick_hours;
        let absolute_hour = request.start_hour + elapsed_hours;
        let hour = absolute_hour.rem_euclid(24.0);
        let weekday = ((request.start_weekday as u64
            + (absolute_hour.div_euclid(24.0).floor() as u64))
            % 7) as u8;
        let tick_routines = apply_schedules(
            tick,
            absolute_hour,
            request.start_weekday,
            request.tick_hours,
            &mut current,
            &program,
            &request.places,
            &request.schedules,
            &mut active_travel,
            &mut location_transitions,
            &mut routine_unavailable,
        )?;
        let neighbor_values = neighbor_state_values(&current, &program, request.network.as_ref())?;
        let decision_place_states = live_place_state_maps(&request.places, &current);
        routine_actions.extend(tick_routines.clone());
        evaluate_meaningful_actions(
            tick,
            hour,
            weekday,
            &current,
            &request,
            &neighbor_values,
            &decision_place_states,
            &mut rng,
            &mut event_queue,
        )?;
        let tick_events = event_queue.drain();
        events.extend(tick_events.clone());
        let (mut next, counts, outcomes) = apply_modules(
            tick,
            hour,
            weekday,
            &current,
            &request,
            &program,
            &neighbor_values,
            &decision_place_states,
            &mut rng,
            &mut routine_unavailable,
        )?;
        location_transitions.extend(module_location_transitions(
            tick, &current, &next, &outcomes,
        ));
        apply_routes(&mut next, &program);
        if !request.interactions.rules.is_empty() {
            let interaction_place_states = live_place_state_maps(&request.places, &next);
            let interaction_places = request
                .places
                .iter()
                .zip(interaction_place_states)
                .map(|(place, states)| InteractionPlace {
                    id: place.id.clone(),
                    kind: place.kind.clone(),
                    allows_in_person: place.allows_in_person,
                    states,
                })
                .collect();
            let result = run_interactions(InteractionRequest {
                seed: request.seed,
                tick,
                hour,
                weekday,
                agents: InteractionAgentColumns {
                    agent_ids: interaction_agent_ids.clone(),
                    place: next.places.clone(),
                    actions: interaction_actions(current.len(), &tick_routines, &tick_events),
                    traits: next.traits.clone(),
                    states: next.memory.clone(),
                },
                places: interaction_places,
                relationships: interaction_relationships,
                trees: request.interactions.trees.clone(),
                rules: request.interactions.rules.clone(),
            })
            .map_err(|error| CoreError::at(error.code, error.message, error.path))?;
            next.memory = result.states;
            interaction_relationships = result.relationships;
            interaction_events.extend(result.events);
            blocked_interactions.extend(result.blocked);
        }
        if let Some(receipt) = apply_state_dynamics(
            tick,
            &current,
            &mut next,
            &tick_routines,
            &tick_events,
            &outcomes,
            &request.state_dynamics,
        )? {
            state_ticks.push(receipt);
        }
        transition_counts.extend(counts);
        transition_outcomes.extend(outcomes);
        current = next;
        append_synchronization(tick, &request.synchronization, &mut synchronization);
    }
    let live_places = live_place_states(&request.places, &current.places);
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
        ticks: final_tick,
        continuation: AgentContinuation {
            completed_tick: final_tick,
            rng_word_position: rng.word_position().to_string(),
            active_travel,
            relationships: interaction_relationships.clone(),
            live_places: live_places.clone(),
        },
        agents: output_agents(current, &program),
        live_places,
        transition_counts,
        transition_outcomes,
        transition_evidence: transition_evidence(&program),
        events,
        routine_actions,
        routine_unavailable,
        location_transitions,
        interactions: interaction_events,
        blocked_interactions,
        relationships: interaction_relationships,
        synchronization,
        shard_populations,
        state_ticks,
    })
}

fn apply_state_dynamics(
    tick: u64,
    current: &AgentBatch,
    next: &mut AgentBatch,
    routines: &[RoutineActionBatch],
    events: &[ActionEvent],
    outcomes: &[AgentTransitionOutcome],
    program: &StateDynamicsProgram,
) -> CoreResult<Option<StateRuntimeTickReceipt>> {
    if program.events.is_empty()
        && program.state_rules.is_empty()
        && program.finance.is_none()
        && program.finance_rules.is_empty()
    {
        return Ok(None);
    }
    let occurrences = state_event_occurrences(routines, events, outcomes);
    let event_definitions: BTreeMap<_, _> = program
        .events
        .iter()
        .map(|event| (event.id.as_str(), event))
        .collect();
    let mut event_counts = BTreeMap::new();
    let rule_targets: BTreeSet<_> = program
        .state_rules
        .iter()
        .map(|rule| rule.target_state_id.as_str())
        .collect();
    let mut event_deltas = BTreeMap::new();
    for target in &rule_targets {
        let current_values = &current.memory[*target];
        let next_values = &next.memory[*target];
        event_deltas.insert(
            (*target).to_owned(),
            current_values
                .iter()
                .zip(next_values)
                .map(|(before, after)| after - before)
                .collect::<Vec<_>>(),
        );
    }
    let mut flows = zero_cash_flows(current.len());
    let mut event_effects = Vec::new();
    for (event_id, agents) in &occurrences {
        let Some(definition) = event_definitions.get(event_id.as_str()) else {
            continue;
        };
        event_counts.insert(event_id.clone(), agents.len() as u64);
        for agent in agents {
            for effect in &definition.effects {
                let state_id = effect.target.strip_prefix("memory.").ok_or_else(|| {
                    CoreError::at(
                        "INVALID_STATE_EVENT_TARGET",
                        "State dynamics event effects must target memory fields",
                        format!("state_dynamics.events.{event_id}.effects"),
                    )
                })?;
                let values = event_deltas.get_mut(state_id).ok_or_else(|| {
                    CoreError::at(
                        "MISSING_STATE_EVENT_RULE",
                        format!("State event {event_id} targets {state_id} without a state rule"),
                        format!("state_dynamics.events.{event_id}.effects"),
                    )
                })?;
                let current_value = current.memory[state_id][*agent] + values[*agent];
                let delta = match effect.operation.as_str() {
                    "add" => effect.value,
                    "subtract" => -effect.value,
                    "set" => effect.value - current_value,
                    "multiply" => current_value * effect.value - current_value,
                    _ => {
                        return Err(CoreError::at(
                            "INVALID_STATE_EVENT_OPERATION",
                            format!("Unsupported state event operation {}", effect.operation),
                            format!("state_dynamics.events.{event_id}.effects"),
                        ));
                    }
                };
                values[*agent] += delta;
                event_effects.push(AgentStateEventReceipt {
                    event: event_id.clone(),
                    agent_index: *agent,
                    target_state_id: state_id.to_owned(),
                    operation: effect.operation.clone(),
                    configured_value: effect.value,
                    delta,
                    evidence: definition.evidence.clone(),
                });
            }
            if let Some(columns) = &definition.cash_flow_by_agent {
                add_cash_flow_columns(&mut flows, *agent, columns);
            } else {
                add_cash_flow(&mut flows, *agent, &definition.cash_flow);
            }
        }
    }
    let mut state_rule_receipts = Vec::new();
    let mut agent_state_changes = Vec::new();
    if !program.state_rules.is_empty() {
        let result = advance_state_columns(
            &StateColumns {
                values: current.memory.clone(),
            },
            &StateColumns {
                values: event_deltas,
            },
            &program.state_rules,
        )?;
        for rule in &program.state_rules {
            next.memory.insert(
                rule.target_state_id.clone(),
                result.columns.values[&rule.target_state_id].clone(),
            );
        }
        state_rule_receipts = result.receipts;
        agent_state_changes = result.agent_state_changes;
    }
    let mut finance_changes = Vec::new();
    let finance_formula = if let Some(metadata) = &program.finance {
        let finance_result = advance_finance_columns(
            &finance_columns(next, metadata)?,
            &flows,
            &program.finance_rules,
        )?;
        write_finance_columns(next, &finance_result.columns);
        finance_changes = finance_result.finance_changes;
        Some(finance_result.formula)
    } else {
        None
    };
    Ok(Some(StateRuntimeTickReceipt {
        tick,
        event_counts,
        event_effects,
        state_rules: state_rule_receipts,
        agent_state_changes,
        finance_changes,
        finance_formula,
    }))
}

fn state_event_occurrences(
    routines: &[RoutineActionBatch],
    events: &[ActionEvent],
    outcomes: &[AgentTransitionOutcome],
) -> BTreeMap<String, Vec<usize>> {
    let mut result: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for routine in routines {
        result
            .entry(routine.action.clone())
            .or_default()
            .extend(&routine.agent_indices);
    }
    for event in events {
        result
            .entry(event.action.clone())
            .or_default()
            .push(event.agent_index);
    }
    for outcome in outcomes {
        result
            .entry(outcome.transition.clone())
            .or_default()
            .push(outcome.agent_index);
    }
    result
}

fn zero_cash_flows(agent_count: usize) -> CashFlowColumns {
    CashFlowColumns {
        wages: vec![0.0; agent_count],
        business_income: vec![0.0; agent_count],
        transfers: vec![0.0; agent_count],
        housing: vec![0.0; agent_count],
        food: vec![0.0; agent_count],
        transport: vec![0.0; agent_count],
        other_expenses: vec![0.0; agent_count],
        taxes: vec![0.0; agent_count],
        savings_contribution: vec![0.0; agent_count],
        savings_withdrawal: vec![0.0; agent_count],
        debt_draw: vec![0.0; agent_count],
        debt_repayment: vec![0.0; agent_count],
    }
}

fn add_cash_flow(flows: &mut CashFlowColumns, agent: usize, amount: &CashFlowAmounts) {
    flows.wages[agent] += amount.wages;
    flows.business_income[agent] += amount.business_income;
    flows.transfers[agent] += amount.transfers;
    flows.housing[agent] += amount.housing;
    flows.food[agent] += amount.food;
    flows.transport[agent] += amount.transport;
    flows.other_expenses[agent] += amount.other_expenses;
    flows.taxes[agent] += amount.taxes;
    flows.savings_contribution[agent] += amount.savings_contribution;
    flows.savings_withdrawal[agent] += amount.savings_withdrawal;
    flows.debt_draw[agent] += amount.debt_draw;
    flows.debt_repayment[agent] += amount.debt_repayment;
}

fn add_cash_flow_columns(flows: &mut CashFlowColumns, agent: usize, amounts: &CashFlowColumns) {
    flows.wages[agent] += amounts.wages[agent];
    flows.business_income[agent] += amounts.business_income[agent];
    flows.transfers[agent] += amounts.transfers[agent];
    flows.housing[agent] += amounts.housing[agent];
    flows.food[agent] += amounts.food[agent];
    flows.transport[agent] += amounts.transport[agent];
    flows.other_expenses[agent] += amounts.other_expenses[agent];
    flows.taxes[agent] += amounts.taxes[agent];
    flows.savings_contribution[agent] += amounts.savings_contribution[agent];
    flows.savings_withdrawal[agent] += amounts.savings_withdrawal[agent];
    flows.debt_draw[agent] += amounts.debt_draw[agent];
    flows.debt_repayment[agent] += amounts.debt_repayment[agent];
}

fn finance_columns(
    batch: &AgentBatch,
    metadata: &FinanceRuntimeMetadata,
) -> CoreResult<FinanceColumns> {
    let column = |name: &str| -> CoreResult<Vec<Option<f64>>> {
        batch
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
    Ok(FinanceColumns {
        currency: metadata.currency.clone(),
        money: column("finance.money")?,
        income: column("finance.income")?,
        expenses: column("finance.expenses")?,
        savings: column("finance.savings")?,
        debt: column("finance.debt")?,
        status: metadata.status.clone(),
        source: metadata.source.clone(),
    })
}

fn write_finance_columns(batch: &mut AgentBatch, finances: &FinanceColumns) {
    let values = |column: &[Option<f64>]| {
        column
            .iter()
            .map(|value| value.expect("validated known finance state"))
            .collect()
    };
    batch
        .memory
        .insert("finance.money".to_owned(), values(&finances.money));
    batch
        .memory
        .insert("finance.income".to_owned(), values(&finances.income));
    batch
        .memory
        .insert("finance.expenses".to_owned(), values(&finances.expenses));
    batch
        .memory
        .insert("finance.savings".to_owned(), values(&finances.savings));
    batch
        .memory
        .insert("finance.debt".to_owned(), values(&finances.debt));
}

fn interaction_actions(
    population: usize,
    routines: &[RoutineActionBatch],
    events: &[ActionEvent],
) -> Vec<Vec<String>> {
    let mut actions = vec![Vec::new(); population];
    for routine in routines {
        for agent in &routine.agent_indices {
            if !actions[*agent].contains(&routine.action) {
                actions[*agent].push(routine.action.clone());
            }
        }
    }
    for event in events {
        if !actions[event.agent_index].contains(&event.action) {
            actions[event.agent_index].push(event.action.clone());
        }
    }
    actions
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
            available_place_kinds: module.available_place_kinds.iter().cloned().collect(),
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
            same_place_normalized_matvec(network, &indicator, &batch.places)?,
        );
    }
    Ok(result)
}

fn live_place_state_maps(places: &[PlaceInput], batch: &AgentBatch) -> Vec<BTreeMap<String, f64>> {
    live_place_states(places, &batch.places)
        .into_iter()
        .map(|place| place.state)
        .collect()
}

fn same_place_normalized_matvec(
    network: &CsrMatrix,
    values: &[f64],
    places: &[usize],
) -> CoreResult<Vec<f64>> {
    network.validate("network")?;
    if values.len() != network.cols || places.len() != network.rows {
        return Err(CoreError::at(
            "INVALID_VECTOR",
            "Neighbor values and place columns must match the network dimensions",
            "network",
        ));
    }
    let mut result = vec![0.0; network.rows];
    for row in 0..network.rows {
        let mut total_weight = 0.0;
        for edge in network.row_offsets[row]..network.row_offsets[row + 1] {
            let neighbor = network.column_indices[edge];
            if places[row] != places[neighbor] {
                continue;
            }
            let weight = network.weights[edge];
            result[row] += weight * values[neighbor];
            total_weight += weight;
        }
        if total_weight.abs() > 1e-15 {
            result[row] /= total_weight;
        }
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
    place_states: &[BTreeMap<String, f64>],
    rng: &mut DeterministicRng,
    routine_unavailable: &mut Vec<RoutineUnavailableRecord>,
) -> CoreResult<(
    AgentBatch,
    Vec<TransitionCount>,
    Vec<AgentTransitionOutcome>,
)> {
    let mut next = current.clone();
    let mut counts: BTreeMap<(usize, String), u64> = BTreeMap::new();
    let mut outcomes = Vec::new();
    for shard in current.shards(request.places.len()) {
        let mut partitions: BTreeMap<(usize, usize), Vec<usize>> = BTreeMap::new();
        for agent in shard {
            let module = &program.modules[current.modules[agent]];
            let place = &request.places[current.places[agent]];
            if !module_is_available(module, place) {
                routine_unavailable.push(RoutineUnavailableRecord {
                    tick,
                    schedule: format!("decision-module:{}", module.id),
                    agent_index: agent,
                    current_place_index: current.places[agent],
                    destination_place_index: None,
                    decision_module: Some(module.id.clone()),
                    reason: module_unavailable_reason(module, place),
                });
                continue;
            }
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
                    place_states,
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
                let (rule_index, probability_rule) = matching_probability_rule(
                    &transition.rules,
                    agent,
                    hour,
                    weekday,
                    current,
                    &request.places,
                    place_states,
                    neighbor_values,
                    &format!("modules.{module_index}.state.{state_index}.transitions.{selected}"),
                )?
                .expect("validated transition probability matched");
                let probability = probability_rule
                    .probability
                    .expect("validated transition probability is present");
                outcomes.push(AgentTransitionOutcome {
                    tick,
                    agent_index: agent,
                    module: module.id.clone(),
                    transition: transition.id.clone(),
                    from_state: module.state_names[state_index].clone(),
                    to_state: module.state_names[transition.to_state].clone(),
                    rule_index,
                    probability,
                    provenance: probability_rule.provenance.clone(),
                });
                next.states[agent] = transition.to_state;
                apply_effects(
                    tick,
                    agent,
                    &module.id,
                    &transition.effects,
                    &mut next,
                    &request.places,
                    routine_unavailable,
                )?;
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
    Ok((next, result, outcomes))
}

#[allow(clippy::too_many_arguments)]
fn resolve_transition_probability_batch(
    rules: &[ProbabilityRule],
    agents: &[usize],
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    place_states: &[BTreeMap<String, f64>],
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
                place_states,
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
    place_states: &[BTreeMap<String, f64>],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
    unmatched_is_zero: bool,
) -> CoreResult<f64> {
    let matched = matching_probability_rule(
        rules,
        agent,
        hour,
        weekday,
        batch,
        places,
        place_states,
        neighbor_values,
        path,
    )?;
    if let Some(probability) = matched.and_then(|(_, rule)| rule.probability) {
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
fn matching_probability_rule<'a>(
    rules: &'a [ProbabilityRule],
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    place_states: &[BTreeMap<String, f64>],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
) -> CoreResult<Option<(usize, &'a ProbabilityRule)>> {
    let mut matches = Vec::new();
    for (rule_index, rule) in rules.iter().enumerate() {
        if conditions_match(
            &rule.conditions,
            agent,
            hour,
            weekday,
            batch,
            places,
            place_states,
            neighbor_values,
            &format!("{path}.rules.{rule_index}.conditions"),
        )? {
            matches.push((rule_index, rule));
        }
    }
    if matches.len() > 1 {
        return Err(CoreError::at(
            "AMBIGUOUS_PROBABILITY",
            "More than one probability rule matches this agent",
            path,
        ));
    }
    Ok(matches.first().copied())
}

#[allow(clippy::too_many_arguments)]
fn conditions_match(
    conditions: &[NumericCondition],
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    places: &[PlaceInput],
    place_states: &[BTreeMap<String, f64>],
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    path: &str,
) -> CoreResult<bool> {
    for (index, condition) in conditions.iter().enumerate() {
        if let Some(expected) = &condition.categorical_value {
            let actual = categorical_input_value(
                &condition.input,
                agent,
                batch,
                places,
                &format!("{path}.{index}.input"),
            )?;
            let matches = match condition.operator.as_str() {
                "eq" => actual == expected,
                "ne" => actual != expected,
                _ => unreachable!("validated categorical condition operator"),
            };
            if !matches {
                return Ok(false);
            }
            continue;
        }
        let actual = input_value(
            &condition.input,
            agent,
            hour,
            weekday,
            batch,
            place_states,
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

fn categorical_input_value<'a>(
    input: &str,
    agent: usize,
    batch: &AgentBatch,
    places: &'a [PlaceInput],
    path: &str,
) -> CoreResult<&'a str> {
    if input == "place.kind" {
        return Ok(places[batch.places[agent]].kind.as_str());
    }
    Err(CoreError::at(
        "UNKNOWN_INPUT",
        format!("Unknown categorical module input {input}"),
        path,
    ))
}

#[allow(clippy::too_many_arguments)]
fn input_value(
    input: &str,
    agent: usize,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    place_states: &[BTreeMap<String, f64>],
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
        return place_states[batch.places[agent]]
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

fn module_is_available(module: &CompiledModule, place: &PlaceInput) -> bool {
    if let Some(available_modules) = &place.available_decision_modules {
        return available_modules.contains(&module.id);
    }
    module.available_place_kinds.is_empty() || module.available_place_kinds.contains(&place.kind)
}

fn module_unavailable_reason(module: &CompiledModule, place: &PlaceInput) -> String {
    if place.available_decision_modules.is_some() {
        return format!(
            "Decision module {} unavailable at place {}",
            module.id, place.id
        );
    }
    let required = module
        .available_place_kinds
        .iter()
        .cloned()
        .collect::<Vec<_>>()
        .join(", ");
    format!(
        "Decision module {} unavailable at place kind {}; requires place kind {}",
        module.id, place.kind, required
    )
}

fn apply_effects(
    tick: u64,
    agent: usize,
    module_id: &str,
    effects: &[TransitionEffect],
    next: &mut AgentBatch,
    places: &[PlaceInput],
    routine_unavailable: &mut Vec<RoutineUnavailableRecord>,
) -> CoreResult<()> {
    for effect in effects {
        if effect.target == "place" {
            let place = effect.value.round();
            if effect.operation != "set"
                || (place - effect.value).abs() > 1e-12
                || place < 0.0
                || place as usize >= places.len()
            {
                return Err(CoreError::new(
                    "INVALID_PLACE_EFFECT",
                    "Place effects must set an integer index for an existing shard",
                ));
            }
            let destination = place as usize;
            if destination == next.places[agent] {
                continue;
            }
            if let Some(reason) = arrival_unavailable_reason(next, places, destination) {
                routine_unavailable.push(RoutineUnavailableRecord {
                    tick,
                    schedule: format!("decision-module:{module_id}"),
                    agent_index: agent,
                    current_place_index: next.places[agent],
                    destination_place_index: Some(destination),
                    decision_module: Some(module_id.to_owned()),
                    reason,
                });
                continue;
            }
            next.places[agent] = destination;
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
    place_states: &[BTreeMap<String, f64>],
    rng: &mut DeterministicRng,
    queue: &mut EventQueue,
) -> CoreResult<()> {
    let mut evaluated_groups = BTreeSet::new();
    for (action_index, action) in request.meaningful_actions.iter().enumerate() {
        if let Some(group) = &action.exclusive_choice_group {
            if evaluated_groups.insert(group.as_str()) {
                evaluate_exclusive_action_group(
                    tick,
                    hour,
                    weekday,
                    batch,
                    request,
                    neighbor_values,
                    place_states,
                    rng,
                    queue,
                    group,
                )?;
            }
            continue;
        }
        for agent in 0..batch.len() {
            let rule_path = format!("meaningful_actions.{action_index}");
            let matched = matching_probability_rule(
                &action.rules,
                agent,
                hour,
                weekday,
                batch,
                &request.places,
                place_states,
                neighbor_values,
                &rule_path,
            )?;
            let probability = matched
                .and_then(|(_, rule)| rule.probability)
                .unwrap_or(0.0);
            let draw = rng.draw();
            if draw < probability {
                let (rule_index, rule) = matched.expect("positive probability requires a rule");
                queue.push(ActionEvent {
                    tick,
                    agent_index: agent,
                    place_index: batch.places[agent],
                    action: action.id.clone(),
                    rule_index,
                    probability,
                    draw,
                    provenance: rule.provenance.clone(),
                });
            }
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn evaluate_exclusive_action_group(
    tick: u64,
    hour: f64,
    weekday: u8,
    batch: &AgentBatch,
    request: &AgentProgramRequest,
    neighbor_values: &BTreeMap<String, Vec<f64>>,
    place_states: &[BTreeMap<String, f64>],
    rng: &mut DeterministicRng,
    queue: &mut EventQueue,
    group: &str,
) -> CoreResult<()> {
    let branches = request
        .meaningful_actions
        .iter()
        .enumerate()
        .filter(|(_, action)| action.exclusive_choice_group.as_deref() == Some(group))
        .collect::<Vec<_>>();
    for agent in 0..batch.len() {
        let mut matching_rules = Vec::with_capacity(branches.len());
        let mut probabilities = Vec::with_capacity(branches.len());
        for (action_index, action) in &branches {
            let path = format!("meaningful_actions.{action_index}");
            let matched = matching_probability_rule(
                &action.rules,
                agent,
                hour,
                weekday,
                batch,
                &request.places,
                place_states,
                neighbor_values,
                &path,
            )?;
            probabilities.push(
                matched
                    .and_then(|(_, rule)| rule.probability)
                    .unwrap_or(0.0),
            );
            matching_rules.push(matched);
        }
        if matching_rules.iter().all(Option::is_none) {
            continue;
        }
        let path =
            format!("meaningful_actions.exclusive_choice_group.{group}.agents.{agent}.tick.{tick}");
        let (selected, draw) = rng.categorical_with_draw(&probabilities, &path)?;
        let (_, action) = branches[selected];
        let (rule_index, rule) = matching_rules[selected].ok_or_else(|| {
            CoreError::at(
                "INVALID_DISTRIBUTION",
                "Exclusive action choice selected an ineligible branch",
                &path,
            )
        })?;
        queue.push(ActionEvent {
            tick,
            agent_index: agent,
            place_index: batch.places[agent],
            action: action.id.clone(),
            rule_index,
            probability: probabilities[selected],
            draw,
            provenance: rule.provenance.clone(),
        });
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn apply_schedules(
    tick: u64,
    absolute_hour: f64,
    start_weekday: u8,
    tick_hours: f64,
    batch: &mut AgentBatch,
    program: &CompiledProgram,
    places: &[PlaceInput],
    schedules: &[ScheduleRow],
    active_travel: &mut [Option<ActiveTravelState>],
    location_transitions: &mut Vec<LocationTransitionRecord>,
    routine_unavailable: &mut Vec<RoutineUnavailableRecord>,
) -> CoreResult<Vec<RoutineActionBatch>> {
    let arrivals = complete_scheduled_travel(
        tick,
        batch,
        places,
        active_travel,
        location_transitions,
        routine_unavailable,
    );
    let mut result = Vec::new();
    let mut destination_changes = vec![None; batch.len()];
    let mut module_changes = vec![None; batch.len()];
    for schedule in schedules {
        let Some(occurrence) = schedule_occurrence(schedule, absolute_hour, start_weekday) else {
            continue;
        };
        let previous_occurrence =
            schedule_occurrence(schedule, absolute_hour - tick_hours, start_weekday);
        let starts_now = tick == 1 || previous_occurrence != Some(occurrence);
        let mut agent_indices = Vec::new();
        for agent in 0..batch.len() {
            if !schedule_is_eligible(schedule, agent)
                || !schedule_matches_agent(schedule, agent, batch, program)
            {
                continue;
            }
            let destination = schedule_destination(schedule, agent);
            if let Some(travel) = &active_travel[agent] {
                if starts_now
                    && destination
                        .is_some_and(|destination| destination != travel.destination_place_index)
                {
                    return Err(CoreError::at(
                        "AMBIGUOUS_SCHEDULE_DESTINATION",
                        format!(
                            "Agent {agent} has overlapping schedule destinations {} and {}",
                            travel.schedule, schedule.id
                        ),
                        "schedules",
                    ));
                }
                continue;
            }
            if starts_now
                && let Some(destination) = destination
                && batch.places[agent] != destination
            {
                if destination_changes[agent].is_some_and(|existing| existing != destination) {
                    return Err(CoreError::at(
                        "AMBIGUOUS_SCHEDULE_DESTINATION",
                        format!("Agent {agent} has more than one destination at tick {tick}"),
                        "schedules",
                    ));
                }
                destination_changes[agent] = Some(destination);
                let from_place = batch.places[agent];
                let explicit_plan = schedule
                    .travel_by_agent
                    .get(agent)
                    .and_then(|plan| plan.as_ref());
                let unavailable_reason = schedule
                    .unavailable_reason_by_agent
                    .get(agent)
                    .and_then(|reason| reason.as_deref());
                if let Some(reason) = unavailable_reason {
                    routine_unavailable.push(RoutineUnavailableRecord {
                        tick,
                        schedule: schedule.id.clone(),
                        agent_index: agent,
                        current_place_index: from_place,
                        destination_place_index: Some(destination),
                        decision_module: schedule_activation(schedule, agent).map(str::to_owned),
                        reason: reason.to_owned(),
                    });
                    continue;
                }
                if !schedule.travel_by_agent.is_empty() && explicit_plan.is_none() {
                    routine_unavailable.push(RoutineUnavailableRecord {
                        tick,
                        schedule: schedule.id.clone(),
                        agent_index: agent,
                        current_place_index: from_place,
                        destination_place_index: Some(destination),
                        decision_module: schedule_activation(schedule, agent).map(str::to_owned),
                        reason: "Travel unavailable because no confirmed route evidence applies"
                            .to_owned(),
                    });
                    continue;
                }
                if let Some(plan) = explicit_plan
                    && plan.from_place_index != from_place
                {
                    routine_unavailable.push(RoutineUnavailableRecord {
                        tick,
                        schedule: schedule.id.clone(),
                        agent_index: agent,
                        current_place_index: from_place,
                        destination_place_index: Some(destination),
                        decision_module: schedule_activation(schedule, agent).map(str::to_owned),
                        reason: format!(
                            "Decision unavailable because confirmed route {} starts at place {}, but the agent is at place {}",
                            plan.route_id, plan.from_place_index, from_place
                        ),
                    });
                    continue;
                }
                if let Some(reason) = closed_arrival_reason(places, destination) {
                    routine_unavailable.push(RoutineUnavailableRecord {
                        tick,
                        schedule: schedule.id.clone(),
                        agent_index: agent,
                        current_place_index: from_place,
                        destination_place_index: Some(destination),
                        decision_module: schedule_activation(schedule, agent).map(str::to_owned),
                        reason,
                    });
                    continue;
                }
                let travel_ticks = explicit_plan
                    .map(|plan| plan.travel_ticks)
                    .or(schedule.travel_ticks)
                    .unwrap_or(0);
                let provenance = explicit_plan.map(|plan| plan.provenance.clone());
                if travel_ticks == 0 {
                    if let Some(reason) = arrival_unavailable_reason(batch, places, destination) {
                        routine_unavailable.push(RoutineUnavailableRecord {
                            tick,
                            schedule: schedule.id.clone(),
                            agent_index: agent,
                            current_place_index: from_place,
                            destination_place_index: Some(destination),
                            decision_module: schedule_activation(schedule, agent)
                                .map(str::to_owned),
                            reason,
                        });
                        continue;
                    }
                    batch.places[agent] = destination;
                    location_transitions.push(LocationTransitionRecord {
                        tick,
                        agent_index: agent,
                        source: schedule.id.clone(),
                        phase: "schedule_move".to_owned(),
                        from_place_index: from_place,
                        to_place_index: destination,
                        destination_place_index: destination,
                        provenance,
                    });
                } else {
                    let travel_place = explicit_plan
                        .map(|plan| plan.travel_place_index)
                        .or(schedule.travel_place_index)
                        .unwrap_or(from_place);
                    if let Some(reason) = arrival_unavailable_reason(batch, places, travel_place) {
                        routine_unavailable.push(RoutineUnavailableRecord {
                            tick,
                            schedule: schedule.id.clone(),
                            agent_index: agent,
                            current_place_index: from_place,
                            destination_place_index: Some(destination),
                            decision_module: schedule_activation(schedule, agent)
                                .map(str::to_owned),
                            reason,
                        });
                        continue;
                    }
                    batch.places[agent] = travel_place;
                    location_transitions.push(LocationTransitionRecord {
                        tick,
                        agent_index: agent,
                        source: schedule.id.clone(),
                        phase: "travel_started".to_owned(),
                        from_place_index: from_place,
                        to_place_index: travel_place,
                        destination_place_index: destination,
                        provenance: provenance.clone(),
                    });
                    active_travel[agent] = Some(ActiveTravelState {
                        schedule: schedule.id.clone(),
                        destination_place_index: destination,
                        arrival_tick: tick.checked_add(travel_ticks).ok_or_else(|| {
                            CoreError::at(
                                "INVALID_SCHEDULE_TRAVEL_DURATION",
                                "Schedule travel duration exceeds the simulation tick range",
                                "schedules",
                            )
                        })?,
                        provenance,
                    });
                    continue;
                }
            }
            let at_destination =
                destination.is_none_or(|destination| batch.places[agent] == destination);
            let at_required_place = schedule.required_place_indices.is_empty()
                || schedule
                    .required_place_indices
                    .contains(&batch.places[agent]);
            if at_destination && at_required_place {
                let arrived_now = arrivals[agent].as_deref() == Some(schedule.id.as_str());
                if (starts_now || arrived_now)
                    && let Some(module_id) = schedule_activation(schedule, agent)
                {
                    let target_module = program
                        .modules
                        .iter()
                        .position(|module| module.id == module_id)
                        .expect("validated schedule module");
                    let place = &places[batch.places[agent]];
                    if !module_is_available(&program.modules[target_module], place) {
                        routine_unavailable.push(RoutineUnavailableRecord {
                            tick,
                            schedule: schedule.id.clone(),
                            agent_index: agent,
                            current_place_index: batch.places[agent],
                            destination_place_index: destination,
                            decision_module: Some(module_id.to_owned()),
                            reason: module_unavailable_reason(
                                &program.modules[target_module],
                                place,
                            ),
                        });
                        continue;
                    }
                    if module_changes[agent].is_some_and(|existing| existing != target_module) {
                        return Err(CoreError::at(
                            "AMBIGUOUS_SCHEDULE_MODULE",
                            format!("Agent {agent} has more than one scheduled decision module"),
                            "schedules",
                        ));
                    }
                    module_changes[agent] = Some(target_module);
                    batch.modules[agent] = target_module;
                    batch.states[agent] = program.modules[target_module].entry_state;
                }
                agent_indices.push(agent);
            }
        }
        if !agent_indices.is_empty() {
            result.push(RoutineActionBatch {
                tick,
                schedule: schedule.id.clone(),
                action: schedule.action.clone(),
                agent_indices,
            });
        }
    }
    Ok(result)
}

fn schedule_is_eligible(schedule: &ScheduleRow, agent: usize) -> bool {
    schedule.eligible_agent_indices.is_empty() || schedule.eligible_agent_indices.contains(&agent)
}

fn schedule_activation(schedule: &ScheduleRow, agent: usize) -> Option<&str> {
    schedule
        .activate_module_by_agent
        .get(agent)
        .and_then(|module| module.as_deref())
}

fn schedule_destination(schedule: &ScheduleRow, agent: usize) -> Option<usize> {
    schedule
        .destination_place_by_agent
        .get(agent)
        .copied()
        .flatten()
        .or(schedule.destination_place_index)
}

fn schedule_matches_agent(
    schedule: &ScheduleRow,
    agent: usize,
    batch: &AgentBatch,
    program: &CompiledProgram,
) -> bool {
    let module = &program.modules[batch.modules[agent]];
    let state = &module.state_names[batch.states[agent]];
    (schedule.modules.is_empty() || schedule.modules.contains(&module.id))
        && (schedule.states.is_empty() || schedule.states.contains(state))
}

fn closed_arrival_reason(places: &[PlaceInput], destination: usize) -> Option<String> {
    let place = &places[destination];
    (!place.accepts_arrivals).then(|| {
        format!(
            "Arrival unavailable because place {} does not accept arrivals",
            place.id
        )
    })
}

fn arrival_unavailable_reason(
    batch: &AgentBatch,
    places: &[PlaceInput],
    destination: usize,
) -> Option<String> {
    if let Some(reason) = closed_arrival_reason(places, destination) {
        return Some(reason);
    }
    let place = &places[destination];
    let occupancy = batch
        .places
        .iter()
        .filter(|place_index| **place_index == destination)
        .count();
    place.capacity.and_then(|capacity| {
        (occupancy >= capacity).then(|| {
            format!(
                "Arrival unavailable because place {} capacity {} is full",
                place.id, capacity
            )
        })
    })
}

fn complete_scheduled_travel(
    tick: u64,
    batch: &mut AgentBatch,
    places: &[PlaceInput],
    active_travel: &mut [Option<ActiveTravelState>],
    location_transitions: &mut Vec<LocationTransitionRecord>,
    routine_unavailable: &mut Vec<RoutineUnavailableRecord>,
) -> Vec<Option<String>> {
    let mut arrivals = vec![None; batch.len()];
    for agent in 0..batch.len() {
        if !active_travel[agent]
            .as_ref()
            .is_some_and(|travel| travel.arrival_tick <= tick)
        {
            continue;
        }
        let travel = active_travel[agent]
            .as_ref()
            .expect("arrival eligibility checked");
        if let Some(reason) =
            arrival_unavailable_reason(batch, places, travel.destination_place_index)
        {
            routine_unavailable.push(RoutineUnavailableRecord {
                tick,
                schedule: travel.schedule.clone(),
                agent_index: agent,
                current_place_index: batch.places[agent],
                destination_place_index: Some(travel.destination_place_index),
                decision_module: None,
                reason,
            });
            active_travel[agent]
                .as_mut()
                .expect("arrival eligibility checked")
                .arrival_tick = tick.saturating_add(1);
            continue;
        }
        let travel = active_travel[agent]
            .take()
            .expect("arrival eligibility checked");
        let from_place = batch.places[agent];
        batch.places[agent] = travel.destination_place_index;
        arrivals[agent] = Some(travel.schedule.clone());
        location_transitions.push(LocationTransitionRecord {
            tick,
            agent_index: agent,
            source: travel.schedule,
            phase: "travel_arrived".to_owned(),
            from_place_index: from_place,
            to_place_index: travel.destination_place_index,
            destination_place_index: travel.destination_place_index,
            provenance: travel.provenance,
        });
    }
    arrivals
}

fn schedule_occurrence(
    schedule: &ScheduleRow,
    absolute_hour: f64,
    start_weekday: u8,
) -> Option<i64> {
    let day = (absolute_hour / 24.0).floor() as i64;
    let hour = absolute_hour.rem_euclid(24.0);
    let weekday = (i64::from(start_weekday) + day).rem_euclid(7) as u8;
    if !schedule.weekdays.contains(&weekday) || !hour_matches(schedule, hour) {
        return None;
    }
    if schedule.start_hour > schedule.end_hour && hour < schedule.end_hour {
        Some(day - 1)
    } else {
        Some(day)
    }
}

fn module_location_transitions(
    tick: u64,
    current: &AgentBatch,
    next: &AgentBatch,
    outcomes: &[AgentTransitionOutcome],
) -> Vec<LocationTransitionRecord> {
    (0..current.len())
        .filter(|agent| current.places[*agent] != next.places[*agent])
        .map(|agent| {
            let source = outcomes
                .iter()
                .find(|outcome| outcome.agent_index == agent)
                .map(|outcome| outcome.transition.clone())
                .unwrap_or_else(|| "module_effect".to_owned());
            LocationTransitionRecord {
                tick,
                agent_index: agent,
                source,
                phase: "module_effect".to_owned(),
                from_place_index: current.places[agent],
                to_place_index: next.places[agent],
                destination_place_index: next.places[agent],
                provenance: None,
            }
        })
        .collect()
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
