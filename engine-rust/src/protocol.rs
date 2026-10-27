use crate::agent_types::AgentProgramRequest;
use crate::aggregate::AggregateDslRequest;
use crate::csr::CsrMatvecRequest;
use crate::error::{CoreError, CoreResult};
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
    CsrMatvec(CsrMatvecRequest),
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
        Request::CsrMatvec(request) => serialize(crate::csr::run_matvec(request)?),
    }
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
