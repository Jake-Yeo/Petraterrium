use crate::csr::CsrMatrix;
use crate::interactions::{
    BlockedInteraction, DirectedInteractionEvent, InteractionRelationship, InteractionRule,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentProgramRequest {
    pub seed: u64,
    pub ticks: u64,
    #[serde(default)]
    pub continuation: Option<AgentContinuation>,
    pub tick_hours: f64,
    #[serde(default)]
    pub start_hour: f64,
    #[serde(default)]
    pub start_weekday: u8,
    pub places: Vec<PlaceInput>,
    pub agents: AgentColumnsInput,
    pub modules: Vec<ModuleDefinition>,
    #[serde(default)]
    pub routes: Vec<ModuleRoute>,
    pub network: Option<CsrMatrix>,
    #[serde(default)]
    pub schedules: Vec<ScheduleRow>,
    #[serde(default)]
    pub meaningful_actions: Vec<MeaningfulAction>,
    #[serde(default)]
    pub interactions: InteractionProgram,
    #[serde(default)]
    pub synchronization: SynchronizationConfig,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AgentContinuation {
    pub completed_tick: u64,
    pub rng_word_position: String,
    pub active_travel: Vec<Option<ActiveTravelState>>,
    pub relationships: Vec<InteractionRelationship>,
    #[serde(default)]
    pub live_places: Vec<LivePlaceState>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ActiveTravelState {
    pub schedule: String,
    pub destination_place_index: usize,
    pub arrival_tick: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provenance: Option<Value>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlaceInput {
    pub id: String,
    #[serde(default = "default_place_kind")]
    pub kind: String,
    #[serde(default = "default_accepts_arrivals")]
    pub accepts_arrivals: bool,
    #[serde(default = "default_allows_in_person")]
    pub allows_in_person: bool,
    #[serde(default)]
    pub capacity: Option<usize>,
    #[serde(default)]
    pub state: BTreeMap<String, f64>,
    #[serde(default)]
    pub available_decision_modules: Option<Vec<String>>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LivePlaceState {
    pub place_index: usize,
    pub place_id: String,
    pub kind: String,
    pub accepts_arrivals: bool,
    pub allows_in_person: bool,
    pub capacity: Option<usize>,
    pub occupancy: usize,
    pub crowd_density: Option<f64>,
    pub state: BTreeMap<String, f64>,
}

pub fn live_place_states(places: &[PlaceInput], agent_places: &[usize]) -> Vec<LivePlaceState> {
    let mut occupancy = vec![0usize; places.len()];
    for place in agent_places {
        occupancy[*place] += 1;
    }
    places
        .iter()
        .enumerate()
        .map(|(place_index, place)| {
            let mut state = place.state.clone();
            state.insert("occupancy".to_owned(), occupancy[place_index] as f64);
            state.remove("crowd_density");
            let crowd_density = place
                .capacity
                .map(|capacity| occupancy[place_index] as f64 / capacity as f64);
            if let Some(value) = crowd_density {
                state.insert("crowd_density".to_owned(), value);
            }
            LivePlaceState {
                place_index,
                place_id: place.id.clone(),
                kind: place.kind.clone(),
                accepts_arrivals: place.accepts_arrivals,
                allows_in_person: place.allows_in_person,
                capacity: place.capacity,
                occupancy: occupancy[place_index],
                crowd_density,
                state,
            }
        })
        .collect()
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentColumnsInput {
    #[serde(default)]
    pub agent_ids: Vec<String>,
    pub module: Vec<String>,
    pub state: Vec<String>,
    pub place: Vec<usize>,
    #[serde(default)]
    pub traits: BTreeMap<String, Vec<f64>>,
    #[serde(default)]
    pub trait_dictionaries: BTreeMap<String, TraitDictionary>,
    #[serde(default)]
    pub memory: BTreeMap<String, Vec<f64>>,
}

fn default_place_kind() -> String {
    "place".to_owned()
}

fn default_allows_in_person() -> bool {
    true
}

fn default_accepts_arrivals() -> bool {
    true
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionProgram {
    #[serde(default)]
    pub relationships: Vec<InteractionRelationship>,
    #[serde(default)]
    pub trees: BTreeMap<String, Value>,
    #[serde(default)]
    pub rules: Vec<InteractionRule>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TraitDictionary {
    pub source: String,
    pub version: String,
    pub values: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleDefinition {
    pub id: String,
    pub entry_state: String,
    pub exit_states: Vec<String>,
    #[serde(default)]
    pub available_place_kinds: Vec<String>,
    #[serde(default)]
    pub inputs: Vec<String>,
    #[serde(default)]
    pub outputs: Vec<String>,
    pub states: Vec<String>,
    pub transitions: Vec<ModuleTransition>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleTransition {
    pub id: String,
    pub from_state: String,
    pub to_state: String,
    pub rules: Vec<ProbabilityRule>,
    #[serde(default)]
    pub effects: Vec<TransitionEffect>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProbabilityRule {
    #[serde(default)]
    pub conditions: Vec<NumericCondition>,
    pub probability: Option<f64>,
    pub provenance: ProbabilityProvenance,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ProbabilityProvenance {
    pub source: String,
    pub version: String,
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolution_status: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub source_places: Vec<String>,
    pub uncertainty: f64,
    #[serde(default)]
    pub source_date: Option<String>,
    #[serde(default)]
    pub evidence_id: Option<String>,
    #[serde(default)]
    pub evidence_kind: Option<String>,
    #[serde(default)]
    pub ci_low: Option<f64>,
    #[serde(default)]
    pub ci_high: Option<f64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NumericCondition {
    pub input: String,
    pub operator: String,
    pub value: f64,
    #[serde(default)]
    pub categorical_value: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TransitionEffect {
    pub target: String,
    pub operation: String,
    pub value: f64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleRoute {
    pub from_module: String,
    pub exit_state: String,
    pub to_module: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScheduleRow {
    pub id: String,
    pub action: String,
    pub weekdays: Vec<u8>,
    pub start_hour: f64,
    pub end_hour: f64,
    #[serde(default)]
    pub modules: Vec<String>,
    #[serde(default)]
    pub states: Vec<String>,
    #[serde(default)]
    pub eligible_agent_indices: Vec<usize>,
    #[serde(default)]
    pub required_place_indices: Vec<usize>,
    #[serde(default)]
    pub destination_place_index: Option<usize>,
    #[serde(default)]
    pub destination_place_by_agent: Vec<Option<usize>>,
    #[serde(default)]
    pub activate_module_by_agent: Vec<Option<String>>,
    #[serde(default)]
    pub travel_by_agent: Vec<Option<ScheduledTravelPlan>>,
    #[serde(default)]
    pub unavailable_reason_by_agent: Vec<Option<String>>,
    #[serde(default)]
    pub travel_place_index: Option<usize>,
    #[serde(default)]
    pub travel_ticks: Option<u64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScheduledTravelPlan {
    pub from_place_index: usize,
    pub travel_place_index: usize,
    pub travel_ticks: u64,
    pub route_id: String,
    pub provenance: Value,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeaningfulAction {
    pub id: String,
    pub rules: Vec<ProbabilityRule>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SynchronizationConfig {
    pub border_every_ticks: Option<u64>,
    pub media_every_ticks: Option<u64>,
    pub weekly_leader_every_ticks: Option<u64>,
    #[serde(default)]
    pub border_payloads: Vec<Value>,
    #[serde(default)]
    pub media_payloads: Vec<Value>,
    #[serde(default)]
    pub weekly_leader_payloads: Vec<Value>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AgentProgramResult {
    pub seed: u64,
    pub ticks: u64,
    pub continuation: AgentContinuation,
    pub agents: AgentColumnsOutput,
    pub live_places: Vec<LivePlaceState>,
    pub transition_counts: Vec<TransitionCount>,
    pub transition_outcomes: Vec<AgentTransitionOutcome>,
    pub transition_evidence: Vec<TransitionEvidenceRecord>,
    pub events: Vec<ActionEvent>,
    pub routine_actions: Vec<RoutineActionBatch>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub routine_unavailable: Vec<RoutineUnavailableRecord>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub location_transitions: Vec<LocationTransitionRecord>,
    pub interactions: Vec<DirectedInteractionEvent>,
    pub blocked_interactions: Vec<BlockedInteraction>,
    pub relationships: Vec<InteractionRelationship>,
    pub synchronization: Vec<SynchronizationEnvelope>,
    pub shard_populations: Vec<ShardPopulation>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct TransitionEvidenceRecord {
    pub module: String,
    pub transition: String,
    pub rule_index: usize,
    pub probability: f64,
    pub provenance: ProbabilityProvenance,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AgentColumnsOutput {
    pub module: Vec<String>,
    pub state: Vec<String>,
    pub place: Vec<usize>,
    pub traits: BTreeMap<String, Vec<f64>>,
    pub trait_dictionaries: BTreeMap<String, TraitDictionary>,
    pub memory: BTreeMap<String, Vec<f64>>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct TransitionCount {
    pub tick: u64,
    pub module: String,
    pub transition: String,
    pub count: u64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AgentTransitionOutcome {
    pub tick: u64,
    pub agent_index: usize,
    pub module: String,
    pub transition: String,
    pub from_state: String,
    pub to_state: String,
    pub rule_index: usize,
    pub probability: f64,
    pub provenance: ProbabilityProvenance,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct ActionEvent {
    pub tick: u64,
    pub agent_index: usize,
    pub place_index: usize,
    pub action: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct RoutineActionBatch {
    pub tick: u64,
    pub schedule: String,
    pub action: String,
    pub agent_indices: Vec<usize>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct RoutineUnavailableRecord {
    pub tick: u64,
    pub schedule: String,
    pub agent_index: usize,
    pub current_place_index: usize,
    pub destination_place_index: Option<usize>,
    pub decision_module: Option<String>,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct LocationTransitionRecord {
    pub tick: u64,
    pub agent_index: usize,
    pub source: String,
    pub phase: String,
    pub from_place_index: usize,
    pub to_place_index: usize,
    pub destination_place_index: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provenance: Option<Value>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct SynchronizationEnvelope {
    pub tick: u64,
    pub kind: String,
    pub payloads: Vec<Value>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct ShardPopulation {
    pub place_index: usize,
    pub place: String,
    pub agents: usize,
}
