use crate::csr::CsrMatrix;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentProgramRequest {
    pub seed: u64,
    pub ticks: u64,
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
    pub synchronization: SynchronizationConfig,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlaceInput {
    pub id: String,
    #[serde(default)]
    pub state: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentColumnsInput {
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
    pub agents: AgentColumnsOutput,
    pub transition_counts: Vec<TransitionCount>,
    pub transition_evidence: Vec<TransitionEvidenceRecord>,
    pub events: Vec<ActionEvent>,
    pub routine_actions: Vec<RoutineActionBatch>,
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
