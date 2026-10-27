use petraterrium_engine::{Response, execute_json};
use std::io::{self, BufRead, Write};

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::stdout().lock();
    for line in stdin.lock().lines() {
        let response = match line {
            Ok(line) if !line.trim().is_empty() => execute_json(&line),
            Ok(_) => continue,
            Err(error) => Response::failure(petraterrium_engine::error::CoreError::new(
                "STDIN_READ_FAILED",
                error.to_string(),
            )),
        };
        let serialized = serde_json::to_string(&response).unwrap_or_else(|error| {
            format!(
                "{{\"protocol_version\":\"1\",\"engine_version\":\"0.1.0\",\"ok\":false,\"error\":{{\"code\":\"SERIALIZATION_FAILED\",\"message\":{:?}}}}}",
                error.to_string()
            )
        });
        if writeln!(stdout, "{serialized}").is_err() || stdout.flush().is_err() {
            break;
        }
    }
}
