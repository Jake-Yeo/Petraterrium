use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LocationLevel {
    Country,
    Region,
    State,
    City,
    District,
    Building,
    Room,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LocationPlace {
    pub id: String,
    pub name: String,
    pub level: LocationLevel,
    pub parent_id: Option<String>,
    pub accepts_arrivals: bool,
    pub allows_in_person: bool,
    pub capacity: Option<usize>,
    #[serde(default)]
    pub state: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocationAgentColumns {
    pub agent_ids: Vec<String>,
    pub current_location_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocationMovement {
    pub agent_index: usize,
    pub destination_location_id: String,
    pub expected_parent_id: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocationHistoryRecord {
    pub tick: u64,
    pub agent_id: String,
    pub from_location_id: String,
    pub to_location_id: String,
    pub route_location_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LocationTickRequest {
    pub tick: u64,
    pub places: Vec<LocationPlace>,
    pub agents: LocationAgentColumns,
    #[serde(default)]
    pub movements: Vec<LocationMovement>,
    #[serde(default)]
    pub history: Vec<LocationHistoryRecord>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct AppliedLocationMovement {
    pub tick: u64,
    pub agent_index: usize,
    pub agent_id: String,
    pub from_location_id: String,
    pub to_location_id: String,
    pub route_location_ids: Vec<String>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct LocationTickResult {
    pub tick: u64,
    pub current_location_ids: Vec<String>,
    pub movements: Vec<AppliedLocationMovement>,
    pub history: Vec<LocationHistoryRecord>,
    pub co_located_agent_indices: Vec<Vec<usize>>,
    pub effective_place_state: BTreeMap<String, Vec<Option<f64>>>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct LocationError {
    pub code: String,
    pub message: String,
    pub path: String,
}

impl LocationError {
    fn at(code: &str, message: impl Into<String>, path: impl Into<String>) -> Self {
        Self {
            code: code.to_owned(),
            message: message.into(),
            path: path.into(),
        }
    }
}

struct CompiledLocations<'a> {
    places: &'a [LocationPlace],
    indices: BTreeMap<&'a str, usize>,
}

impl<'a> CompiledLocations<'a> {
    fn new(places: &'a [LocationPlace]) -> Result<Self, LocationError> {
        if places.is_empty() {
            return Err(LocationError::at(
                "EMPTY_LOCATION_REGISTRY",
                "At least one location is required",
                "places",
            ));
        }
        let mut indices = BTreeMap::new();
        for (index, place) in places.iter().enumerate() {
            if place.id.trim().is_empty() {
                return Err(LocationError::at(
                    "EMPTY_LOCATION_ID",
                    "Location ids cannot be empty",
                    format!("places.{index}.id"),
                ));
            }
            if indices.insert(place.id.as_str(), index).is_some() {
                return Err(LocationError::at(
                    "DUPLICATE_LOCATION_ID",
                    format!("Location id {} is duplicated", place.id),
                    format!("places.{index}.id"),
                ));
            }
            if place.capacity == Some(0) {
                return Err(LocationError::at(
                    "INVALID_LOCATION_CAPACITY",
                    format!("Location {} has zero capacity", place.id),
                    format!("places.{index}.capacity"),
                ));
            }
            if place.state.values().any(|value| !value.is_finite()) {
                return Err(LocationError::at(
                    "NON_FINITE_PLACE_STATE",
                    format!("Location {} has non-finite state", place.id),
                    format!("places.{index}.state"),
                ));
            }
        }
        let compiled = Self { places, indices };
        compiled.validate_hierarchy()?;
        Ok(compiled)
    }

    fn index(&self, location_id: &str, path: impl Into<String>) -> Result<usize, LocationError> {
        self.indices.get(location_id).copied().ok_or_else(|| {
            LocationError::at(
                "UNKNOWN_LOCATION",
                format!("Unknown location {location_id}"),
                path,
            )
        })
    }

    fn validate_hierarchy(&self) -> Result<(), LocationError> {
        for (index, place) in self.places.iter().enumerate() {
            match (&place.level, &place.parent_id) {
                (LocationLevel::Country, None) => {}
                (LocationLevel::Country, Some(_)) => {
                    return Err(LocationError::at(
                        "COUNTRY_WITH_PARENT",
                        format!("Country {} cannot have a parent", place.id),
                        format!("places.{index}.parent_id"),
                    ));
                }
                (_, None) => {
                    return Err(LocationError::at(
                        "MISSING_LOCATION_PARENT",
                        format!("Location {} requires a parent", place.id),
                        format!("places.{index}.parent_id"),
                    ));
                }
                (level, Some(parent_id)) => {
                    let parent_index =
                        self.index(parent_id, format!("places.{index}.parent_id"))?;
                    let parent = &self.places[parent_index];
                    if !valid_parent(level, &parent.level) {
                        return Err(LocationError::at(
                            "INVALID_LOCATION_PARENT",
                            format!(
                                "Location {} at level {:?} cannot have parent {} at level {:?}",
                                place.id, place.level, parent.id, parent.level
                            ),
                            format!("places.{index}.parent_id"),
                        ));
                    }
                }
            }
        }
        Ok(())
    }

    fn ancestry_indices(&self, start: usize) -> Vec<usize> {
        let mut ancestry = vec![start];
        let mut cursor = start;
        while let Some(parent_id) = self.places[cursor].parent_id.as_deref() {
            cursor = self.indices[parent_id];
            ancestry.push(cursor);
        }
        ancestry
    }

    fn route(&self, source: usize, destination: usize) -> Vec<String> {
        let source_ancestry = self.ancestry_indices(source);
        let destination_ancestry = self.ancestry_indices(destination);
        let destination_positions: BTreeMap<usize, usize> = destination_ancestry
            .iter()
            .enumerate()
            .map(|(position, index)| (*index, position))
            .collect();
        let shared_parent = source_ancestry
            .iter()
            .enumerate()
            .find_map(|(position, index)| {
                destination_positions
                    .get(index)
                    .map(|other_position| (position, *other_position))
            });
        let (source_path, destination_path) = match shared_parent {
            Some((source_common, destination_common)) => (
                &source_ancestry[..=source_common],
                &destination_ancestry[..destination_common],
            ),
            None => (&source_ancestry[..], &destination_ancestry[..]),
        };
        source_path
            .iter()
            .chain(destination_path.iter().rev())
            .map(|index| self.places[*index].id.clone())
            .collect()
    }

    fn effective_state(&self, location_index: usize) -> BTreeMap<String, f64> {
        let mut ancestry = self.ancestry_indices(location_index);
        ancestry.reverse();
        let mut state = BTreeMap::new();
        for index in ancestry {
            state.extend(self.places[index].state.clone());
        }
        state
    }
}

fn valid_parent(level: &LocationLevel, parent: &LocationLevel) -> bool {
    matches!(
        (level, parent),
        (LocationLevel::Region, LocationLevel::Country)
            | (LocationLevel::State, LocationLevel::Country)
            | (LocationLevel::City, LocationLevel::Region)
            | (LocationLevel::City, LocationLevel::State)
            | (LocationLevel::District, LocationLevel::City)
            | (LocationLevel::Building, LocationLevel::District)
            | (LocationLevel::Room, LocationLevel::Building)
    )
}

fn validate_agents(
    agents: &LocationAgentColumns,
    locations: &CompiledLocations<'_>,
) -> Result<Vec<usize>, LocationError> {
    if agents.agent_ids.is_empty() {
        return Err(LocationError::at(
            "EMPTY_AGENT_BATCH",
            "At least one agent is required",
            "agents.agent_ids",
        ));
    }
    if agents.agent_ids.len() != agents.current_location_ids.len() {
        return Err(LocationError::at(
            "MISALIGNED_AGENT_LOCATION_COLUMNS",
            "Agent ids and current location ids must have equal lengths",
            "agents.current_location_ids",
        ));
    }
    let unique: BTreeSet<_> = agents.agent_ids.iter().collect();
    if unique.len() != agents.agent_ids.len() {
        return Err(LocationError::at(
            "DUPLICATE_AGENT_ID",
            "Agent ids must be unique",
            "agents.agent_ids",
        ));
    }
    agents
        .current_location_ids
        .iter()
        .enumerate()
        .map(|(index, id)| locations.index(id, format!("agents.current_location_ids.{index}")))
        .collect()
}

fn validate_movements(
    request: &LocationTickRequest,
    locations: &CompiledLocations<'_>,
    current_indices: &[usize],
) -> Result<Vec<usize>, LocationError> {
    let mut next_indices = current_indices.to_vec();
    let mut moved_agents = BTreeSet::new();
    for (movement_index, movement) in request.movements.iter().enumerate() {
        if movement.agent_index >= request.agents.agent_ids.len() {
            return Err(LocationError::at(
                "UNKNOWN_MOVEMENT_AGENT",
                format!("Agent index {} is outside the batch", movement.agent_index),
                format!("movements.{movement_index}.agent_index"),
            ));
        }
        if !moved_agents.insert(movement.agent_index) {
            return Err(LocationError::at(
                "DUPLICATE_AGENT_MOVEMENT",
                format!("Agent {} has more than one movement", movement.agent_index),
                format!("movements.{movement_index}.agent_index"),
            ));
        }
        let destination = locations.index(
            &movement.destination_location_id,
            format!("movements.{movement_index}.destination_location_id"),
        )?;
        let destination_place = &request.places[destination];
        if !destination_place.accepts_arrivals {
            return Err(LocationError::at(
                "ARRIVAL_NOT_ALLOWED",
                format!("Location {} does not accept arrivals", destination_place.id),
                format!("movements.{movement_index}.destination_location_id"),
            ));
        }
        if movement.expected_parent_id != destination_place.parent_id {
            return Err(LocationError::at(
                "ARRIVAL_PARENT_MISMATCH",
                format!(
                    "Location {} has parent {:?}, not {:?}",
                    destination_place.id, destination_place.parent_id, movement.expected_parent_id
                ),
                format!("movements.{movement_index}.expected_parent_id"),
            ));
        }
        if current_indices[movement.agent_index] == destination {
            return Err(LocationError::at(
                "UNCHANGED_LOCATION",
                format!(
                    "Agent {} is already at {}",
                    request.agents.agent_ids[movement.agent_index], destination_place.id
                ),
                format!("movements.{movement_index}.destination_location_id"),
            ));
        }
        next_indices[movement.agent_index] = destination;
    }
    let mut occupancy = vec![0usize; request.places.len()];
    for location_index in &next_indices {
        occupancy[*location_index] += 1;
    }
    for (index, place) in request.places.iter().enumerate() {
        if place
            .capacity
            .is_some_and(|capacity| occupancy[index] > capacity)
        {
            return Err(LocationError::at(
                "LOCATION_CAPACITY_EXCEEDED",
                format!(
                    "Location {} capacity is {:?}, requested occupancy is {}",
                    place.id, place.capacity, occupancy[index]
                ),
                format!("places.{index}.capacity"),
            ));
        }
    }
    Ok(next_indices)
}

fn co_located_agents(places: &[LocationPlace], location_indices: &[usize]) -> Vec<Vec<usize>> {
    let mut occupants = vec![Vec::new(); places.len()];
    for (agent_index, location_index) in location_indices.iter().enumerate() {
        occupants[*location_index].push(agent_index);
    }
    location_indices
        .iter()
        .enumerate()
        .map(|(agent_index, location_index)| {
            if !places[*location_index].allows_in_person {
                return Vec::new();
            }
            occupants[*location_index]
                .iter()
                .copied()
                .filter(|other_index| *other_index != agent_index)
                .collect()
        })
        .collect()
}

fn effective_state_columns(
    locations: &CompiledLocations<'_>,
    location_indices: &[usize],
) -> BTreeMap<String, Vec<Option<f64>>> {
    let agent_states: Vec<_> = location_indices
        .iter()
        .map(|index| locations.effective_state(*index))
        .collect();
    let keys: BTreeSet<_> = agent_states
        .iter()
        .flat_map(|state| state.keys().cloned())
        .collect();
    keys.into_iter()
        .map(|key| {
            let values = agent_states
                .iter()
                .map(|state| state.get(&key).copied())
                .collect();
            (key, values)
        })
        .collect()
}

pub fn face_to_face_allowed(
    places: &[LocationPlace],
    current_location_ids: &[String],
    first_agent: usize,
    second_agent: usize,
) -> Result<bool, LocationError> {
    let locations = CompiledLocations::new(places)?;
    if first_agent >= current_location_ids.len() || second_agent >= current_location_ids.len() {
        return Err(LocationError::at(
            "UNKNOWN_COLOCATION_AGENT",
            "Co-location agent index is outside the batch",
            "current_location_ids",
        ));
    }
    let first_location = locations.index(
        &current_location_ids[first_agent],
        format!("current_location_ids.{first_agent}"),
    )?;
    let second_location = locations.index(
        &current_location_ids[second_agent],
        format!("current_location_ids.{second_agent}"),
    )?;
    Ok(first_agent != second_agent
        && first_location == second_location
        && places[first_location].allows_in_person)
}

pub fn run_location_tick(
    request: LocationTickRequest,
) -> Result<LocationTickResult, LocationError> {
    let locations = CompiledLocations::new(&request.places)?;
    let current_indices = validate_agents(&request.agents, &locations)?;
    let next_indices = validate_movements(&request, &locations, &current_indices)?;
    let mut applied = Vec::with_capacity(request.movements.len());
    let mut history = request.history.clone();
    for movement in &request.movements {
        let source = current_indices[movement.agent_index];
        let destination = next_indices[movement.agent_index];
        let route = locations.route(source, destination);
        let record = LocationHistoryRecord {
            tick: request.tick,
            agent_id: request.agents.agent_ids[movement.agent_index].clone(),
            from_location_id: request.places[source].id.clone(),
            to_location_id: request.places[destination].id.clone(),
            route_location_ids: route.clone(),
        };
        applied.push(AppliedLocationMovement {
            tick: request.tick,
            agent_index: movement.agent_index,
            agent_id: record.agent_id.clone(),
            from_location_id: record.from_location_id.clone(),
            to_location_id: record.to_location_id.clone(),
            route_location_ids: route,
        });
        history.push(record);
    }
    let current_location_ids = next_indices
        .iter()
        .map(|index| request.places[*index].id.clone())
        .collect();
    Ok(LocationTickResult {
        tick: request.tick,
        current_location_ids,
        movements: applied,
        history,
        co_located_agent_indices: co_located_agents(&request.places, &next_indices),
        effective_place_state: effective_state_columns(&locations, &next_indices),
    })
}
