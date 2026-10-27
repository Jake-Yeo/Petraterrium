use crate::error::{CoreError, CoreResult};
use crate::random::DeterministicRng;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Deserialize)]
pub struct AggregateDslRequest {
    pub seed: u64,
    pub ticks: u64,
    pub tick_hours: f64,
    #[serde(default = "default_snapshot_interval")]
    pub snapshot_every_ticks: u64,
    pub dsl: AggregateDsl,
}

fn default_snapshot_interval() -> u64 {
    1
}

#[derive(Clone, Debug, Deserialize)]
pub struct AggregateDsl {
    pub states: Vec<StateDefinition>,
    #[serde(default)]
    pub parameters: Vec<ParameterDefinition>,
    pub systems: Vec<SystemDefinition>,
    pub population: PopulationDefinition,
}

#[derive(Clone, Debug, Deserialize)]
pub struct StateDefinition {
    pub id: String,
    pub values: Vec<String>,
    pub initial: InitialDistribution,
}

#[derive(Clone, Debug, Deserialize)]
pub struct InitialDistribution {
    pub values: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ParameterDefinition {
    pub id: String,
    pub value: Option<f64>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SystemDefinition {
    pub id: String,
    pub state: String,
    pub transitions: Vec<TransitionDefinition>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct TransitionDefinition {
    pub id: String,
    pub from_state: String,
    pub to_state: String,
    pub probability: AggregateProbability,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AggregateProbability {
    pub base: Option<f64>,
    #[serde(default = "default_probability_mode")]
    pub mode: String,
    pub time_unit: String,
    pub parameter: Option<String>,
    pub source_state: Option<String>,
    pub mixing_parameter: Option<String>,
}

fn default_probability_mode() -> String {
    "probability".to_owned()
}

#[derive(Clone, Debug, Deserialize)]
pub struct PopulationDefinition {
    pub size: u64,
    pub places: Vec<String>,
    #[serde(default)]
    pub place_populations: BTreeMap<String, u64>,
    #[serde(default)]
    pub initial_state_overrides: BTreeMap<String, BTreeMap<String, BTreeMap<String, u64>>>,
}

#[derive(Clone, Debug)]
struct AggregateState {
    values: BTreeMap<String, Vec<Vec<u64>>>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AggregateSnapshot {
    pub tick: u64,
    pub states: BTreeMap<String, Vec<Vec<u64>>>,
    pub state_totals: BTreeMap<String, u64>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AggregateDslResult {
    pub seed: u64,
    pub tick_hours: f64,
    pub places: Vec<String>,
    pub state_values: BTreeMap<String, Vec<String>>,
    pub snapshots: Vec<AggregateSnapshot>,
}

pub fn run(request: AggregateDslRequest) -> CoreResult<AggregateDslResult> {
    validate_request(&request)?;
    let mut rng = DeterministicRng::new(request.seed);
    let mut state = initial_state(&request.dsl, &mut rng)?;
    let reference_mass = state_totals(&state);
    let parameters = parameter_values(&request.dsl.parameters);
    let mut snapshots = vec![snapshot(0, &state)];
    for tick in 1..=request.ticks {
        state = step(
            &request.dsl,
            &state,
            &parameters,
            request.tick_hours,
            &mut rng,
        )?;
        let observed_mass = state_totals(&state);
        if observed_mass != reference_mass {
            return Err(CoreError::new(
                "MASS_NOT_CONSERVED",
                format!(
                    "State totals changed from {reference_mass:?} to {observed_mass:?} at tick {tick}"
                ),
            ));
        }
        if tick % request.snapshot_every_ticks == 0 || tick == request.ticks {
            snapshots.push(snapshot(tick, &state));
        }
    }
    Ok(AggregateDslResult {
        seed: request.seed,
        tick_hours: request.tick_hours,
        places: request.dsl.population.places,
        state_values: request
            .dsl
            .states
            .into_iter()
            .map(|state| (state.id, state.values))
            .collect(),
        snapshots,
    })
}

fn validate_request(request: &AggregateDslRequest) -> CoreResult<()> {
    if request.ticks == 0 {
        return Err(CoreError::at(
            "INVALID_TICKS",
            "ticks must be at least one",
            "ticks",
        ));
    }
    if request.snapshot_every_ticks == 0 {
        return Err(CoreError::at(
            "INVALID_SNAPSHOT_INTERVAL",
            "snapshot_every_ticks must be at least one",
            "snapshot_every_ticks",
        ));
    }
    if !request.tick_hours.is_finite() || request.tick_hours <= 0.0 {
        return Err(CoreError::at(
            "INVALID_TICK_HOURS",
            "tick_hours must be a positive finite number",
            "tick_hours",
        ));
    }
    let dsl = &request.dsl;
    if dsl.population.places.is_empty() {
        return Err(CoreError::at(
            "INVALID_POPULATION",
            "population.places cannot be empty",
            "dsl.population.places",
        ));
    }
    let unique_places: BTreeSet<_> = dsl.population.places.iter().collect();
    if unique_places.len() != dsl.population.places.len() {
        return Err(CoreError::at(
            "DUPLICATE_PLACE",
            "population.places must be unique",
            "dsl.population.places",
        ));
    }
    let state_ids: BTreeSet<_> = dsl.states.iter().map(|state| state.id.as_str()).collect();
    if state_ids.len() != dsl.states.len() || dsl.states.is_empty() {
        return Err(CoreError::at(
            "INVALID_STATES",
            "State identifiers must be non-empty and unique",
            "dsl.states",
        ));
    }
    let parameter_values: BTreeMap<_, _> = dsl
        .parameters
        .iter()
        .map(|parameter| (parameter.id.as_str(), parameter.value))
        .collect();
    if parameter_values.len() != dsl.parameters.len() {
        return Err(CoreError::at(
            "DUPLICATE_PARAMETER",
            "Parameter identifiers must be unique",
            "dsl.parameters",
        ));
    }
    for (state_index, state) in dsl.states.iter().enumerate() {
        validate_state_definition(state, state_index)?;
    }
    for (system_index, system) in dsl.systems.iter().enumerate() {
        let state = dsl
            .states
            .iter()
            .find(|state| state.id == system.state)
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_STATE",
                    format!("System {} references state {}", system.id, system.state),
                    format!("dsl.systems.{system_index}.state"),
                )
            })?;
        for (transition_index, transition) in system.transitions.iter().enumerate() {
            if !state.values.contains(&transition.from_state)
                || !state.values.contains(&transition.to_state)
            {
                return Err(CoreError::at(
                    "UNKNOWN_STATE_VALUE",
                    format!(
                        "Transition {} references an unknown state value",
                        transition.id
                    ),
                    format!("dsl.systems.{system_index}.transitions.{transition_index}"),
                ));
            }
            validate_aggregate_probability(
                &transition.probability,
                &parameter_values,
                &state.values,
                &format!("dsl.systems.{system_index}.transitions.{transition_index}.probability"),
            )?;
        }
    }
    place_populations(&dsl.population)?;
    Ok(())
}

fn validate_state_definition(state: &StateDefinition, index: usize) -> CoreResult<()> {
    let path = format!("dsl.states.{index}");
    if state.values.len() < 2 {
        return Err(CoreError::at(
            "INVALID_STATE",
            "A state requires at least two values",
            format!("{path}.values"),
        ));
    }
    let unique: BTreeSet<_> = state.values.iter().collect();
    if unique.len() != state.values.len() {
        return Err(CoreError::at(
            "DUPLICATE_STATE_VALUE",
            "State values must be unique",
            format!("{path}.values"),
        ));
    }
    let mut probabilities = Vec::with_capacity(state.values.len());
    for value in &state.values {
        probabilities.push(*state.initial.values.get(value).ok_or_else(|| {
            CoreError::at(
                "MISSING_INITIAL_PROBABILITY",
                format!("Initial distribution does not contain {value}"),
                format!("{path}.initial.values"),
            )
        })?);
    }
    crate::random::validate_distribution(&probabilities, &format!("{path}.initial.values"))
}

fn validate_aggregate_probability(
    probability: &AggregateProbability,
    parameter_values: &BTreeMap<&str, Option<f64>>,
    state_values: &[String],
    path: &str,
) -> CoreResult<()> {
    if let Some(parameter) = &probability.parameter {
        let value = parameter_values
            .get(parameter.as_str())
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_PARAMETER",
                    format!("Unknown parameter {parameter}"),
                    format!("{path}.parameter"),
                )
            })?
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_PROBABILITY",
                    format!("Parameter {parameter} has no fitted value"),
                    format!("{path}.parameter"),
                )
            })?;
        validate_base_value(value, &probability.mode, &format!("{path}.parameter"))?;
    }
    if probability.parameter.is_none() && probability.base.is_none() {
        return Err(CoreError::at(
            "UNKNOWN_PROBABILITY",
            "A transition probability cannot be null",
            format!("{path}.base"),
        ));
    }
    if let Some(value) = probability.base {
        validate_base_value(value, &probability.mode, &format!("{path}.base"))?;
    }
    if probability.mode != "probability" && probability.mode != "hazard" {
        return Err(CoreError::at(
            "INVALID_PROBABILITY_MODE",
            "mode must be probability or hazard",
            format!("{path}.mode"),
        ));
    }
    period_hours(&probability.time_unit, &format!("{path}.time_unit"))?;
    if let Some(source_state) = &probability.source_state
        && !state_values.contains(source_state)
    {
        return Err(CoreError::at(
            "UNKNOWN_SOURCE_STATE",
            format!("Unknown source state {source_state}"),
            format!("{path}.source_state"),
        ));
    }
    if let Some(mixing_parameter) = &probability.mixing_parameter {
        let value = parameter_values
            .get(mixing_parameter.as_str())
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_PARAMETER",
                    format!("Unknown mixing parameter {mixing_parameter}"),
                    format!("{path}.mixing_parameter"),
                )
            })?
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_PROBABILITY",
                    format!("Mixing parameter {mixing_parameter} has no fitted value"),
                    format!("{path}.mixing_parameter"),
                )
            })?;
        if !(0.0..=1.0).contains(&value) {
            return Err(CoreError::at(
                "INVALID_MIXING_PARAMETER",
                "Mixing parameter must be between 0 and 1",
                format!("{path}.mixing_parameter"),
            ));
        }
    }
    Ok(())
}

fn validate_base_value(value: f64, mode: &str, path: &str) -> CoreResult<()> {
    if !value.is_finite() || value < 0.0 || mode == "probability" && value > 1.0 {
        return Err(CoreError::at(
            "INVALID_PROBABILITY",
            "Probability base is outside its valid range",
            path,
        ));
    }
    Ok(())
}

fn place_populations(population: &PopulationDefinition) -> CoreResult<Vec<u64>> {
    if population.place_populations.is_empty() {
        let places = population.places.len() as u64;
        let base = population.size / places;
        let remainder = population.size % places;
        return Ok((0..places)
            .map(|index| base + u64::from(index < remainder))
            .collect());
    }
    let mut result = Vec::with_capacity(population.places.len());
    for place in &population.places {
        result.push(*population.place_populations.get(place).ok_or_else(|| {
            CoreError::at(
                "MISSING_PLACE_POPULATION",
                format!("No population provided for {place}"),
                "dsl.population.place_populations",
            )
        })?);
    }
    Ok(result)
}

fn initial_state(dsl: &AggregateDsl, rng: &mut DeterministicRng) -> CoreResult<AggregateState> {
    let populations = place_populations(&dsl.population)?;
    let mut values = BTreeMap::new();
    for (state_index, definition) in dsl.states.iter().enumerate() {
        let probabilities: Vec<f64> = definition
            .values
            .iter()
            .map(|value| definition.initial.values[value])
            .collect();
        let mut place_counts = Vec::with_capacity(dsl.population.places.len());
        for (place_index, place) in dsl.population.places.iter().enumerate() {
            if let Some(override_values) = dsl
                .population
                .initial_state_overrides
                .get(place)
                .and_then(|states| states.get(&definition.id))
            {
                let counts: Vec<u64> = definition
                    .values
                    .iter()
                    .map(|value| *override_values.get(value).unwrap_or(&0))
                    .collect();
                if counts.iter().sum::<u64>() != populations[place_index] {
                    return Err(CoreError::at(
                        "INVALID_INITIAL_OVERRIDE",
                        format!(
                            "Initial state {} for {place} must sum to {}",
                            definition.id, populations[place_index]
                        ),
                        format!(
                            "dsl.population.initial_state_overrides.{place}.{}",
                            definition.id
                        ),
                    ));
                }
                place_counts.push(counts);
            } else {
                place_counts.push(rng.multinomial(
                    populations[place_index],
                    &probabilities,
                    &format!("dsl.states.{state_index}.initial.values"),
                )?);
            }
        }
        values.insert(definition.id.clone(), place_counts);
    }
    Ok(AggregateState { values })
}

fn parameter_values(parameters: &[ParameterDefinition]) -> BTreeMap<String, Option<f64>> {
    parameters
        .iter()
        .map(|parameter| (parameter.id.clone(), parameter.value))
        .collect()
}

fn step(
    dsl: &AggregateDsl,
    current: &AggregateState,
    parameters: &BTreeMap<String, Option<f64>>,
    tick_hours: f64,
    rng: &mut DeterministicRng,
) -> CoreResult<AggregateState> {
    let mut next = current.clone();
    for (system_index, system) in dsl.systems.iter().enumerate() {
        let definition = dsl
            .states
            .iter()
            .find(|definition| definition.id == system.state)
            .expect("validated state definition");
        let counts = &current.values[&system.state];
        let target = next.values.get_mut(&system.state).expect("validated state");
        let mut source_order = Vec::new();
        let mut grouped: BTreeMap<&str, Vec<(usize, &TransitionDefinition)>> = BTreeMap::new();
        for (transition_index, transition) in system.transitions.iter().enumerate() {
            if !grouped.contains_key(transition.from_state.as_str()) {
                source_order.push(transition.from_state.as_str());
            }
            grouped
                .entry(transition.from_state.as_str())
                .or_default()
                .push((transition_index, transition));
        }
        for source_name in source_order {
            let source_index = definition
                .values
                .iter()
                .position(|value| value == source_name)
                .expect("validated source state");
            let transitions = &grouped[source_name];
            for place_index in 0..dsl.population.places.len() {
                let mut probabilities = Vec::with_capacity(transitions.len() + 1);
                for (transition_index, transition) in transitions {
                    probabilities.push(resolve_probability(
                        &transition.probability,
                        definition,
                        counts,
                        place_index,
                        parameters,
                        tick_hours,
                        &format!(
                            "dsl.systems.{system_index}.transitions.{transition_index}.probability"
                        ),
                    )?);
                }
                let outgoing: f64 = probabilities.iter().sum();
                if outgoing > 1.0 + 1e-12 {
                    return Err(CoreError::at(
                        "OUTGOING_PROBABILITY_EXCEEDS_ONE",
                        format!("Outgoing probabilities from {source_name} sum to {outgoing:.12}"),
                        format!("dsl.systems.{system_index}.transitions"),
                    ));
                }
                probabilities.push((1.0 - outgoing).max(0.0));
                let moved = rng.multinomial(
                    counts[place_index][source_index],
                    &probabilities,
                    &format!(
                        "dsl.systems.{system_index}.transitions.{source_name}.place.{place_index}"
                    ),
                )?;
                let moved_total: u64 = moved[..transitions.len()].iter().sum();
                target[place_index][source_index] -= moved_total;
                for ((_, transition), count) in transitions.iter().zip(moved) {
                    let destination = definition
                        .values
                        .iter()
                        .position(|value| value == &transition.to_state)
                        .expect("validated destination state");
                    target[place_index][destination] += count;
                }
            }
        }
    }
    Ok(next)
}

fn resolve_probability(
    probability: &AggregateProbability,
    definition: &StateDefinition,
    counts: &[Vec<u64>],
    place_index: usize,
    parameters: &BTreeMap<String, Option<f64>>,
    tick_hours: f64,
    path: &str,
) -> CoreResult<f64> {
    let mut base = if let Some(parameter) = &probability.parameter {
        parameters
            .get(parameter)
            .copied()
            .flatten()
            .ok_or_else(|| {
                CoreError::at(
                    "UNKNOWN_PROBABILITY",
                    format!("Parameter {parameter} has no fitted value"),
                    format!("{path}.parameter"),
                )
            })?
    } else {
        probability.base.ok_or_else(|| {
            CoreError::at(
                "UNKNOWN_PROBABILITY",
                "Transition probability is null",
                format!("{path}.base"),
            )
        })?
    };
    if let Some(source_state) = &probability.source_state {
        let source_index = definition
            .values
            .iter()
            .position(|value| value == source_state)
            .expect("validated source state");
        let local_population: u64 = counts[place_index].iter().sum();
        let local = if local_population == 0 {
            0.0
        } else {
            counts[place_index][source_index] as f64 / local_population as f64
        };
        let global_source: u64 = counts.iter().map(|place| place[source_index]).sum();
        let global_population: u64 = counts.iter().flatten().sum();
        let global = if global_population == 0 {
            0.0
        } else {
            global_source as f64 / global_population as f64
        };
        let mixing = if let Some(parameter) = &probability.mixing_parameter {
            parameters
                .get(parameter)
                .copied()
                .flatten()
                .ok_or_else(|| {
                    CoreError::at(
                        "UNKNOWN_PROBABILITY",
                        format!("Mixing parameter {parameter} has no fitted value"),
                        format!("{path}.mixing_parameter"),
                    )
                })?
        } else {
            0.0
        };
        if !(0.0..=1.0).contains(&mixing) {
            return Err(CoreError::at(
                "INVALID_MIXING_PARAMETER",
                "Mixing parameter must be between 0 and 1",
                format!("{path}.mixing_parameter"),
            ));
        }
        base *= (1.0 - mixing) * local + mixing * global;
    }
    let exposure = if probability.time_unit == "event" {
        1.0
    } else {
        tick_hours / period_hours(&probability.time_unit, &format!("{path}.time_unit"))?
    };
    let scaled = if probability.mode == "hazard" {
        1.0 - (-base * exposure).exp()
    } else {
        1.0 - (1.0 - base.clamp(0.0, 1.0)).powf(exposure)
    };
    if !scaled.is_finite() {
        return Err(CoreError::at(
            "INVALID_PROBABILITY",
            "Scaled probability is not finite",
            path,
        ));
    }
    Ok(scaled.clamp(0.0, 1.0))
}

fn period_hours(unit: &str, path: &str) -> CoreResult<f64> {
    match unit {
        "event" | "hour" => Ok(1.0),
        "day" => Ok(24.0),
        "week" => Ok(168.0),
        "year" => Ok(8760.0),
        _ => Err(CoreError::at(
            "INVALID_TIME_UNIT",
            format!("Unknown time unit {unit}"),
            path,
        )),
    }
}

fn state_totals(state: &AggregateState) -> BTreeMap<String, u64> {
    state
        .values
        .iter()
        .map(|(state_id, values)| (state_id.clone(), values.iter().flatten().sum()))
        .collect()
}

fn snapshot(tick: u64, state: &AggregateState) -> AggregateSnapshot {
    AggregateSnapshot {
        tick,
        states: state.values.clone(),
        state_totals: state_totals(state),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(seed: u64) -> AggregateDslRequest {
        AggregateDslRequest {
            seed,
            ticks: 5,
            tick_hours: 24.0,
            snapshot_every_ticks: 1,
            dsl: AggregateDsl {
                states: vec![StateDefinition {
                    id: "health".to_owned(),
                    values: vec!["well".to_owned(), "sick".to_owned()],
                    initial: InitialDistribution {
                        values: BTreeMap::from([
                            ("well".to_owned(), 0.9),
                            ("sick".to_owned(), 0.1),
                        ]),
                    },
                }],
                parameters: vec![],
                systems: vec![SystemDefinition {
                    id: "illness".to_owned(),
                    state: "health".to_owned(),
                    transitions: vec![TransitionDefinition {
                        id: "recover".to_owned(),
                        from_state: "sick".to_owned(),
                        to_state: "well".to_owned(),
                        probability: AggregateProbability {
                            base: Some(0.2),
                            mode: "probability".to_owned(),
                            time_unit: "day".to_owned(),
                            parameter: None,
                            source_state: None,
                            mixing_parameter: None,
                        },
                    }],
                }],
                population: PopulationDefinition {
                    size: 1000,
                    places: vec!["A".to_owned(), "B".to_owned()],
                    place_populations: BTreeMap::from([
                        ("A".to_owned(), 600),
                        ("B".to_owned(), 400),
                    ]),
                    initial_state_overrides: BTreeMap::new(),
                },
            },
        }
    }

    #[test]
    fn aggregate_run_is_deterministic_and_conserves_mass() {
        let first = run(request(17)).unwrap();
        let second = run(request(17)).unwrap();
        assert_eq!(first, second);
        assert!(
            first
                .snapshots
                .iter()
                .all(|snapshot| snapshot.state_totals["health"] == 1000)
        );
    }

    #[test]
    fn null_parameter_is_rejected_before_tick_execution() {
        let mut invalid = request(17);
        invalid.dsl.parameters.push(ParameterDefinition {
            id: "recovery".to_owned(),
            value: None,
        });
        invalid.dsl.systems[0].transitions[0].probability.parameter = Some("recovery".to_owned());
        let error = run(invalid).unwrap_err();
        assert_eq!(error.code, "UNKNOWN_PROBABILITY");
    }

    #[test]
    fn represented_mass_can_differ_from_representative_agent_count() {
        let mut representative = request(17);
        representative.dsl.population.size = 100;
        let result = run(representative).unwrap();
        assert!(
            result
                .snapshots
                .iter()
                .all(|snapshot| snapshot.state_totals["health"] == 1000)
        );
    }
}
