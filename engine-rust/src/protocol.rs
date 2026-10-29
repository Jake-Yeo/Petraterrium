use crate::agent_types::AgentProgramRequest;
use crate::aggregate::AggregateDslRequest;
use crate::csr::CsrMatvecRequest;
use crate::error::{CoreError, CoreResult};
use crate::interaction_trees::{InteractionTreeError, InteractionTreeRequest};
use crate::locations::{LocationError, LocationTickRequest};
use crate::text_dsl::{
    AggregateEvaluationProtocolRequest, DslRunRequest, TextDslProtocolRequest,
    TextDslValidateRequest, build_program_graph, evaluate_aggregate_function, parse_program,
    restrict_program_to_city, run_composition, run_exemplar_system, run_program,
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
                "entities": program.entities.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "policies": program.policies.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "roles": program.roles.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "role_distributions": program.role_distributions.iter().map(|item| &item.role).collect::<Vec<_>>(),
                "spotlights": program.archetypes.iter().filter(|item| item.spotlight).map(|item| &item.id).collect::<Vec<_>>(),
                "archetypes": program.archetypes.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "composition_archetypes": program.composition_archetypes.iter().map(|item| json!({"id": item.id, "level": item.level, "child_level": item.child_level})).collect::<Vec<_>>(),
                "weighted_populations": program.weighted_populations.iter().map(|item| &item.id).collect::<Vec<_>>(),
                "aggregate_functions": program.aggregate_functions,
                "compositions": program.compositions.iter().map(|item| json!({"id": item.id, "level": item.level, "cached": false})).collect::<Vec<_>>(),
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
            let exemplar_root = is_exemplar_request(&program, requested_composition.as_deref());
            if exemplar_root {
                if request.continuation.is_some() {
                    return Err(CoreError::new(
                        "EXEMPLAR_CONTINUATION_UNSUPPORTED",
                        "Exemplar composition runs do not accept a continuation checkpoint",
                    ));
                }
                let total = request.total_represented_pool.unwrap_or(6_999_999_999);
                if let Some(composition_id) = requested_composition.as_deref()
                    && program
                        .compositions
                        .iter()
                        .find(|composition| composition.id == composition_id)
                        .is_some_and(|composition| {
                            matches!(composition.level.as_str(), "municipality" | "city")
                        })
                {
                    restrict_program_to_city(&mut program, composition_id)
                        .map_err(text_dsl_error)?;
                }
                let source_hash = request
                    .dsl_source_hash
                    .clone()
                    .unwrap_or_else(|| "unversioned".to_owned());
                let system = run_exemplar_system(
                    program,
                    total,
                    request.seed,
                    request.ticks,
                    &source_hash,
                    request.exemplar_cache.clone(),
                    &request.exemplar_inputs,
                    &request.events,
                )
                .map_err(text_dsl_error)?;
                let mut value = serde_json::to_value(system.result)
                    .map_err(|error| CoreError::new("SERIALIZATION_FAILED", error.to_string()))?;
                if let Some(object) = value.as_object_mut() {
                    object.insert("exemplar_plan".to_owned(), json!(system.plan));
                    object.insert(
                        "exemplar_cache".to_owned(),
                        if system.cache_stats.relearned_exemplars.is_empty() {
                            json!({})
                        } else {
                            json!(system.cache)
                        },
                    );
                    object.insert("cache_stats".to_owned(), json!(system.cache_stats));
                    object.insert(
                        "leader_assignments".to_owned(),
                        json!(system.leader_assignments),
                    );
                    object.insert(
                        "unassigned_required_roles".to_owned(),
                        json!(system.unassigned_required_roles),
                    );
                    object.insert("total_represented_pool".to_owned(), json!(total));
                }
                return Ok(value);
            }
            let result = if let Some(composition_id) = requested_composition.as_deref() {
                if request.continuation.is_some() {
                    return Err(CoreError::new(
                        "COMPOSITION_CONTINUATION_UNSUPPORTED",
                        "Composition runs do not accept a continuation checkpoint",
                    ));
                }
                run_composition(program, composition_id, request.seed, request.ticks)
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
            serialize(result)
        }
        Request::EvaluateAggregate(request) => {
            let program = parse_program(&request.source).map_err(text_dsl_error)?;
            serialize(evaluate_aggregate_function(program, request).map_err(text_dsl_error)?)
        }
    }
}

fn is_exemplar_request(
    program: &crate::text_dsl::Program,
    requested_composition: Option<&str>,
) -> bool {
    requested_composition.map_or_else(
        || {
            program
                .compositions
                .iter()
                .find(|composition| composition.default_run)
                .is_some_and(|composition| composition.agent_pool.is_some())
        },
        |composition_id| {
            program
                .compositions
                .iter()
                .find(|composition| composition.id == composition_id)
                .is_some_and(|composition| {
                    composition.agent_pool.is_some()
                        || matches!(composition.level.as_str(), "municipality" | "city")
                })
        },
    )
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn omitted_composition_uses_declared_exemplar_default() {
        let source = include_str!("../dsl/default.dsl");
        let program = parse_program(source).unwrap();
        assert!(is_exemplar_request(&program, None));
        assert!(is_exemplar_request(&program, Some("Toronto")));
        assert!(!is_exemplar_request(&program, Some("UrbanLiberal")));
    }
}
