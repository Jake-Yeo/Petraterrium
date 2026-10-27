use serde::Serialize;
use std::fmt::{Display, Formatter};

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CoreError {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
}

impl CoreError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            path: None,
        }
    }

    pub fn at(
        code: impl Into<String>,
        message: impl Into<String>,
        path: impl Into<String>,
    ) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            path: Some(path.into()),
        }
    }
}

impl Display for CoreError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        if let Some(path) = &self.path {
            write!(formatter, "{} at {}: {}", self.code, path, self.message)
        } else {
            write!(formatter, "{}: {}", self.code, self.message)
        }
    }
}

impl std::error::Error for CoreError {}

pub type CoreResult<T> = Result<T, CoreError>;
