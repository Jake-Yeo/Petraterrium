use crate::agent_types::AgentProgramRequest;
use crate::aggregate::AggregateDslRequest;
use crate::csr::CsrMatvecRequest;
use crate::error::{CoreError, CoreResult};
use crate::interaction_trees::{InteractionTreeError, InteractionTreeRequest};
use crate::locations::{LocationError, LocationTickRequest};
use crate::text_dsl::{
    AggregateEvaluationProtocolRequest, CachedCompositionProtocolRequest, DslRunRequest,
    TextDslProtocolRequest, TextDslValidateRequest, apply_actual_simulated_counts,
    build_population_plan, build_program_graph, configure_pool_run, evaluate_aggregate_function,
    evaluate_cached_composition, parse_program, pool_run_summary, run_composition, run_program,
    run_weighted_population,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const PROTOCOL_VERSION: &str = "1";
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Debug, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
pub enum Request {
    Health,
    RunAggregateDsl(AggregateDslRequest),
    RunAgents(AgentProgramRequest),
    RunLocationTick(LocationTickRequest),
    RunInteractionTree(InteractionTreeRequest),
    CsrMatvec(CsrMatvecRequest),
    ValidateTextDsl(TextDslValidateRequest),
    RunTextDsl(TextDslProtocolRequest),
    EvaluateAggregate(AggregateEvaluationProtocolRequest),
    EvaluateCachedComposition(CachedCompositionProtocolRequest),
}

#[derive(Debug, Serialize)]
pub struct Response {
    pub protocol_version: &'static str,
    pub engine_version: &'static str,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<CoreError>,
}

impl Response {
    pub fn success(value: Value) -> Self {
        Self {
            protocol_version: PROTOCOL_VERSION,
            engine_version: ENGINE_VERSION,
            ok: true,
            result: Some(value),
            error: None,
        }
    }

    pub fn failure(error: CoreError) -> Self {
        Self {
            protocol_version: PROTOCOL_VERSION,
            engine_version: ENGINE_VERSION,
            ok: false,
            result: None,
            error: Some(error),
        }
    }
}

pub fn execute(request: Request) -> CoreResult<Value> {
    match request {
        Request::Health => Ok(json!({
            "numeric_core": "rust",
            "llm_inside_tick": false,
            "update_mode": "double_buffered",
            "rng": "chacha8",
        })),
        Request::RunAggregateDsl(request) => serialize(crate::aggregate::run(request)?),
        Request::RunAgents(request) => serialize(crate::agents::run(request)?),
        Request::RunLocationTick(request) => {
            serialize(crate::locations::run_location_tick(request).map_err(location_error)?)
        }
        Request::RunInteractionTree(request) => {
            serialize(crate::interaction_trees::run(request).map_err(interaction_tree_error)?)
        }
        Request::CsrMatvec(request) => serialize(crate::csr::run_matvec(request)?),
        Request::ValidateTextDsl(request) => match parse_program(&request.source) {
            Ok(program) => {
                let graph = build_program_graph(&program).map_err(text_dsl_error)?;
                Ok(json!({
                "valid": true,
                "program_id": program.id,
                "version": program.version,
                "tick_hours": program.tick_hours,
                "adult_population": program.population.size,
                "entities": program.entities.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "policies": program.policies.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "roles": program.roles.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "role_distributions": program.role_distributions.iter().map(|item| &item.role).collect::<Vec<_>>(),
                "spotlights": program.archetypes.iter().filter(|item| item.spotlight).map(|item| &item.id).collect::<Vec<_>>(),
                "archetypes": program.archetypes.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "composition_archetypes": program.composition_archetypes.iter().map(|item| json!({"id": item.id, "level": item.level, "child_level": item.child_level})).collect::<Vec<_>>(),
                "weighted_populations": program.weighted_populations.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "aggregate_functions": program.aggregate_functions,
                "compositions": program.compositions.iter().map(|item| json!({"id": item.id, "level": item.level, "cached": item.cached.is_some()})).collect::<Vec<_>>(),
                "composition_populations": program.composition_populations.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "graph": graph,
                "diagnostics": [],
                }))
            }
            Err(error) => Ok(json!({
                "valid": false,
                "diagnostics": [error],
            })),
        },
        Request::RunTextDsl(request) => {
            let mut program = parse_program(&request.source).map_err(text_dsl_error)?;
            for (role, parameters) in &request.role_parameters {
                if let Some(distribution) = program
                    .role_distributions
                    .iter_mut()
                    .find(|distribution| distribution.role == *role)
                {
                    distribution.parameters.extend(parameters.clone());
                }
            }
            let requested_composition = request.composition_id.clone();
            let requested_composition_population = request.composition_population_id.clone();
            let composition_count = usize::from(request.population_id.is_some())
                + usize::from(requested_composition.is_some())
                + usize::from(requested_composition_population.is_some());
            let mut pool_id = None;
            let pool_root = requested_composition.as_deref().and_then(|composition_id| {
                program
                    .compositions
                    .iter()
                    .find(|composition| composition.id == composition_id)
                    .filter(|composition| composition.agent_pool.is_some())
                    .map(|composition| composition.id.clone())
                    .or_else(|| {
                        program
                            .compositions
                            .iter()
                            .find(|composition| composition.default_run)
                            .map(|composition| composition.id.clone())
                    })
            });
            if let Some(composition_id) = pool_root.as_deref() {
                pool_id = Some(
                    configure_pool_run(
                        &mut program,
                        composition_id,
                        request.total_represented_pool.unwrap_or(6_999_999_999),
                        request.detail.as_deref(),
                    )
                    .map_err(text_dsl_error)?,
                );
            }
            let mut population_allocations = pool_id
                .as_deref()
                .map(|id| build_population_plan(&program, id, request.seed, None))
                .transpose()
                .map_err(text_dsl_error)?
                .unwrap_or_default();
            let summary_program = program.clone();
            let result = if composition_count > 1 {
                return Err(CoreError::new(
                    "MULTIPLE_COMPOSITIONS",
                    "Choose one weighted population, composition, or composition population",
                ));
            } else if let Some(population_id) = request.population_id {
                if request.continuation.is_some() {
                    return Err(CoreError::new(
                        "WEIGHTED_CONTINUATION_UNSUPPORTED",
                        "Weighted archetype runs do not accept a continuation checkpoint",
                    ));
                }
                run_weighted_population(program, &population_id, request.seed, request.ticks)
                    .map_err(text_dsl_error)?
            } else if requested_composition.is_some() {
                if request.continuation.is_some() {
                    return Err(CoreError::new(
                        "COMPOSITION_CONTINUATION_UNSUPPORTED",
                        "Composition runs do not accept a continuation checkpoint",
                    ));
                }
                run_composition(
                    program,
                    pool_root
                        .as_deref()
                        .unwrap_or(requested_composition.as_deref().unwrap()),
                    request.seed,
                    request.ticks,
                )
                .map_err(text_dsl_error)?
            } else if let Some(population_id) = requested_composition_population.as_deref() {
                if request.continuation.is_some() {
                    return Err(CoreError::new(
                        "COMPOSITION_POPULATION_CONTINUATION_UNSUPPORTED",
                        "Weighted composition runs do not accept a continuation checkpoint",
                    ));
                }
                run_composition(program, population_id, request.seed, request.ticks)
                    .map_err(text_dsl_error)?
            } else {
                run_program(DslRunRequest {
                    program,
                    seed: request.seed,
                    ticks: request.ticks,
                    continuation: request.continuation,
                })
                .map_err(text_dsl_error)?
            };
            apply_actual_simulated_counts(&mut population_allocations, &result.state);
            let pool_summary = pool_id
                .as_ref()
                .map(|_| pool_run_summary(&summary_program, &result.state));
            let mut value = serde_json::to_value(result)
                .map_err(|error| CoreError::new("SERIALIZATION_FAILED", error.to_string()))?;
            if let Some(object) = value.as_object_mut() {
                object.insert(
                    "population_allocations".to_owned(),
                    serde_json::to_value(population_allocations).map_err(|error| {
                        CoreError::new("SERIALIZATION_FAILED", error.to_string())
                    })?,
                );
                object.insert("pool_summary".to_owned(), json!(pool_summary));
                object.insert(
                    "total_represented_pool".to_owned(),
                    json!(request.total_represented_pool.unwrap_or(6_999_999_999)),
                );
                object.insert(
                    "detail".to_owned(),
                    json!(request.detail.unwrap_or_else(|| "medium".to_owned())),
                );
            }
            Ok(value)
        }
        Request::EvaluateAggregate(request) => {
            let program = parse_program(&request.source).map_err(text_dsl_error)?;
            serialize(evaluate_aggregate_function(program, request).map_err(text_dsl_error)?)
        }
        Request::EvaluateCachedComposition(request) => {
            let program = parse_program(&request.source).map_err(text_dsl_error)?;
            serialize(evaluate_cached_composition(program, request).map_err(text_dsl_error)?)
        }
    }
}

fn text_dsl_error(error: crate::text_dsl::DslError) -> CoreError {
    CoreError::at(error.code, error.message, format!("line.{}", error.line))
}

fn location_error(error: LocationError) -> CoreError {
    CoreError::at(error.code, error.message, error.path)
}

fn interaction_tree_error(error: InteractionTreeError) -> CoreError {
    CoreError::at(error.code, error.message, error.path)
}

fn serialize<T: Serialize>(value: T) -> CoreResult<Value> {
    serde_json::to_value(value).map_err(|error| {
        CoreError::new(
            "SERIALIZATION_FAILED",
            format!("Could not serialize engine result: {error}"),
        )
    })
}

pub fn execute_json(line: &str) -> Response {
    let request = match serde_json::from_str::<Request>(line) {
        Ok(request) => request,
        Err(error) => {
            return Response::failure(CoreError::new(
                "INVALID_REQUEST",
                format!("Could not parse request: {error}"),
            ));
        }
    };
    match execute(request) {
        Ok(result) => Response::success(result),
        Err(error) => Response::failure(error),
    }
}
