use super::model::*;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rand_distr::{Binomial, Distribution};

pub fn sample_multinomial_counts(
    total: u64,
    probabilities: &[f64],
    seed: u64,
    key: &str,
) -> DslResult<Vec<u64>> {
    if probabilities.is_empty() {
        return Ok(Vec::new());
    }
    let sum = probabilities.iter().sum::<f64>();
    if probabilities
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
        || (sum - 1.0).abs() > 1e-9
    {
        return Err(DslError::new(
            "INVALID_DISTRIBUTION_SUM",
            1,
            format!("Distribution probabilities sum to {sum}, expected 1"),
        ));
    }
    let mut rng = ChaCha8Rng::seed_from_u64(derived_seed(seed, key));
    let mut remaining_total = total;
    let mut remaining_probability = 1.0;
    let mut counts = Vec::with_capacity(probabilities.len());
    for probability in probabilities.iter().take(probabilities.len() - 1) {
        let conditional = if remaining_probability <= f64::EPSILON {
            0.0
        } else {
            (probability / remaining_probability).clamp(0.0, 1.0)
        };
        let count = if remaining_total == 0 {
            0
        } else {
            Binomial::new(remaining_total, conditional)
                .map_err(|error| DslError::new("INVALID_DISTRIBUTION", 1, error.to_string()))?
                .sample(&mut rng)
        };
        counts.push(count);
        remaining_total -= count;
        remaining_probability = (remaining_probability - probability).max(0.0);
    }
    counts.push(remaining_total);
    Ok(counts)
}

fn derived_seed(seed: u64, key: &str) -> u64 {
    key.as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |value, byte| {
            (value ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
