mod expression;
mod model;
mod parser;
mod runtime;

pub use model::*;
pub use parser::parse_program;
pub use runtime::{run_program, sample_population};
