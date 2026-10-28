use crate::agent_types::{InProgressTimedAction, SampledTimedAction};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(untagged)]
pub enum DslValue {
    Number(f64),
    Bool(bool),
    Text(String),
}

impl DslValue {
    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Self::Number(value) => Some(*value),
            Self::Bool(value) => Some(f64::from(*value)),
            Self::Text(_) => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Bool(value) => Some(*value),
            Self::Number(value) => Some(*value != 0.0),
            Self::Text(value) => Some(!value.is_empty()),
        }
    }

    pub fn as_text(&self) -> Option<&str> {
        match self {
            Self::Text(value) => Some(value),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum Expr {
    Value(DslValue),
    Variable(String),
    Unary {
        operation: String,
        value: Box<Expr>,
    },
    Binary {
        operation: String,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Conditional {
        condition: Box<Expr>,
        when_true: Box<Expr>,
        when_false: Box<Expr>,
    },
    Call {
        function: String,
        arguments: Vec<Expr>,
    },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DistributionSpec {
    pub kind: String,
    pub parameters: BTreeMap<String, Expr>,
    pub categories: Vec<(String, Expr)>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct InitialAssignment {
    pub field: String,
    pub distribution: DistributionSpec,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AgentDefinition {
    pub id: String,
    pub parent: Option<String>,
    pub roles: BTreeSet<String>,
    pub traits: BTreeSet<String>,
    pub states: BTreeSet<String>,
    pub state_bounds: BTreeMap<String, ValueBounds>,
    pub initial: Vec<InitialAssignment>,
    pub routine: String,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct PlaceDefinition {
    pub id: String,
    pub states: BTreeMap<String, DslValue>,
    pub state_bounds: BTreeMap<String, ValueBounds>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ValueBounds {
    pub minimum: f64,
    pub maximum: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct PopulationMix {
    pub agent_type: String,
    pub probability: f64,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ChildGeneration {
    pub condition: Expr,
    pub count: Expr,
    pub age: DistributionSpec,
    pub agent_type: Expr,
    pub links: Vec<String>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct PopulationDefinition {
    pub size: usize,
    pub mix: Vec<PopulationMix>,
    pub child_generation: Option<ChildGeneration>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DecisionBranch {
    pub action: String,
    pub probability: Expr,
    pub condition: Option<Expr>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DecisionDefinition {
    pub id: String,
    pub branches: Vec<DecisionBranch>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DurationSpec {
    pub shape: String,
    pub minimum: f64,
    pub median: f64,
    pub maximum: f64,
    pub sigma: Option<f64>,
    pub truncatable: bool,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum TargetSelector {
    Random { place: String, filter: Option<Expr> },
    Friend { place: String },
    Enemy { place: String },
    Strongest { place: String, field: String },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum EffectScope {
    SelfAgent,
    Target,
    AllAt { place: String, filter: Option<Expr> },
    Place { place: String },
    RelationshipWithTarget,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct EffectDefinition {
    pub scope: EffectScope,
    pub field: String,
    pub operation: String,
    pub value: Expr,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct OutcomeDefinition {
    pub id: String,
    pub probability: Expr,
    pub condition: Option<Expr>,
    pub effects: Vec<EffectDefinition>,
    pub next_decision: Option<String>,
    pub target_next_decision: Option<String>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ActionDefinition {
    pub id: String,
    pub aggregate: String,
    pub duration: DurationSpec,
    pub long: bool,
    pub target: Option<TargetSelector>,
    pub outcomes: Vec<OutcomeDefinition>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum ReportMetric {
    Count,
    Mean {
        field: String,
    },
    Sum {
        field: String,
    },
    ActionCount {
        aggregate: String,
        window: String,
    },
    OutcomeCount {
        action: String,
        outcome: String,
        window: String,
    },
    ActionRates {
        per: f64,
        window: String,
    },
    FamilySize,
    KidsPerFamily,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ReportColumnDefinition {
    pub id: String,
    pub label: String,
    pub format: String,
    pub metric: ReportMetric,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ReportDefinition {
    pub id: String,
    pub title: String,
    pub group_by: String,
    pub display: String,
    pub record: String,
    pub columns: Vec<ReportColumnDefinition>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Program {
    pub id: String,
    pub version: String,
    pub tick_hours: f64,
    pub placeholder_label: String,
    pub uncertainty: String,
    pub results_title: String,
    pub results_subtitle: String,
    pub places: Vec<PlaceDefinition>,
    pub agents: Vec<AgentDefinition>,
    pub population: PopulationDefinition,
    pub decisions: Vec<DecisionDefinition>,
    pub actions: Vec<ActionDefinition>,
    pub reports: Vec<ReportDefinition>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslError {
    pub code: String,
    pub line: usize,
    pub column: usize,
    pub message: String,
}

impl DslError {
    pub fn new(code: &str, line: usize, message: impl Into<String>) -> Self {
        Self {
            code: code.to_owned(),
            line,
            column: 1,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for DslError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "{} at line {}: {}",
            self.code, self.line, self.message
        )
    }
}

impl std::error::Error for DslError {}

pub type DslResult<T> = Result<T, DslError>;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslRelationshipState {
    pub kind: String,
    pub source_id: String,
    pub target_id: String,
    pub values: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslAgentState {
    pub id: String,
    pub agent_type: String,
    pub roles: BTreeSet<String>,
    pub traits: BTreeMap<String, DslValue>,
    pub states: BTreeMap<String, DslValue>,
    pub current_decision: String,
    pub parent_id: Option<String>,
    pub household_id: String,
}

impl DslAgentState {
    pub fn value(&self, name: &str) -> Option<&DslValue> {
        self.traits.get(name).or_else(|| self.states.get(name))
    }

    pub fn place(&self) -> Option<&str> {
        self.states.get("location").and_then(DslValue::as_text)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslAgentTimeState {
    pub active_primary: Option<InProgressTimedAction>,
    pub deferred: Vec<SampledTimedAction>,
    pub occurrence_counts: BTreeMap<String, u64>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslPlaceState {
    pub id: String,
    pub states: BTreeMap<String, DslValue>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslRunState {
    pub completed_ticks: u64,
    pub agents: Vec<DslAgentState>,
    pub places: Vec<DslPlaceState>,
    pub relationships: Vec<DslRelationshipState>,
    pub time: Vec<DslAgentTimeState>,
}

#[derive(Clone, Debug)]
pub struct DslRunRequest {
    pub program: Program,
    pub seed: u64,
    pub ticks: u64,
    pub continuation: Option<DslRunState>,
}

impl DslRunRequest {
    pub fn new(program: Program, seed: u64, ticks: u64) -> Self {
        Self {
            program,
            seed,
            ticks,
            continuation: None,
        }
    }

    pub fn resume(program: Program, seed: u64, ticks: u64, state: DslRunState) -> Self {
        Self {
            program,
            seed,
            ticks,
            continuation: Some(state),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslPopulation {
    pub agents: Vec<DslAgentState>,
    pub relationships: Vec<DslRelationshipState>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslActionRecord {
    pub tick: u64,
    pub agent_id: String,
    pub action: String,
    pub outcome: String,
    pub place: String,
    pub target_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(untagged)]
pub enum DslReportValue {
    Number(f64),
    Text(String),
    Rates(BTreeMap<String, f64>),
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslReportRow {
    pub group_id: String,
    pub values: BTreeMap<String, DslReportValue>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslReportSnapshot {
    pub tick: u64,
    pub rows: Vec<DslReportRow>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslReport {
    pub id: String,
    pub title: String,
    pub group_by: String,
    pub display: String,
    pub record: String,
    pub columns: Vec<ReportColumnDefinition>,
    pub snapshots: Vec<DslReportSnapshot>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DslRunResult {
    pub completed_ticks: u64,
    pub state: DslRunState,
    pub actions: Vec<DslActionRecord>,
    pub results_title: String,
    pub results_subtitle: String,
    pub reports: Vec<DslReport>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextDslProtocolRequest {
    pub source: String,
    pub seed: u64,
    pub ticks: u64,
    #[serde(default)]
    pub continuation: Option<DslRunState>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextDslValidateRequest {
    pub source: String,
}
