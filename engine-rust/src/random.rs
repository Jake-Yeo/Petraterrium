use crate::error::{CoreError, CoreResult};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::{Binomial, Distribution};

pub struct DeterministicRng {
    inner: ChaCha8Rng,
}

impl DeterministicRng {
    pub fn new(seed: u64) -> Self {
        Self {
            inner: ChaCha8Rng::seed_from_u64(seed),
        }
    }

    pub fn draw(&mut self) -> f64 {
        self.inner.r#gen::<f64>()
    }

    pub fn set_word_position(&mut self, position: u128) {
        self.inner.set_word_pos(position);
    }

    pub fn word_position(&self) -> u128 {
        self.inner.get_word_pos()
    }

    pub fn categorical(&mut self, probabilities: &[f64], path: &str) -> CoreResult<usize> {
        self.categorical_with_draw(probabilities, path)
            .map(|(index, _)| index)
    }

    pub fn categorical_with_draw(
        &mut self,
        probabilities: &[f64],
        path: &str,
    ) -> CoreResult<(usize, f64)> {
        validate_distribution(probabilities, path)?;
        let draw = self.draw();
        let mut cumulative = 0.0;
        for (index, probability) in probabilities.iter().enumerate() {
            cumulative += probability;
            if draw < cumulative || index + 1 == probabilities.len() {
                return Ok((index, draw));
            }
        }
        Err(CoreError::at(
            "INVALID_DISTRIBUTION",
            "Categorical distribution has no selectable outcome",
            path,
        ))
    }

    pub fn multinomial(
        &mut self,
        count: u64,
        probabilities: &[f64],
        path: &str,
    ) -> CoreResult<Vec<u64>> {
        validate_distribution(probabilities, path)?;
        let mut remaining_count = count;
        let mut remaining_probability = 1.0;
        let mut result = vec![0; probabilities.len()];
        for index in 0..probabilities.len().saturating_sub(1) {
            if remaining_count == 0 {
                break;
            }
            let conditional = if remaining_probability <= 1e-15 {
                0.0
            } else {
                (probabilities[index] / remaining_probability).clamp(0.0, 1.0)
            };
            let distribution = Binomial::new(remaining_count, conditional)
                .map_err(|error| CoreError::at("INVALID_DISTRIBUTION", error.to_string(), path))?;
            let sampled = distribution.sample(&mut self.inner);
            result[index] = sampled;
            remaining_count -= sampled;
            remaining_probability -= probabilities[index];
        }
        if let Some(last) = result.last_mut() {
            *last = remaining_count;
        }
        Ok(result)
    }
}

pub fn validate_distribution(probabilities: &[f64], path: &str) -> CoreResult<()> {
    if probabilities.is_empty() {
        return Err(CoreError::at(
            "INVALID_DISTRIBUTION",
            "Distribution must contain at least one outcome",
            path,
        ));
    }
    if probabilities
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0 || *value > 1.0)
    {
        return Err(CoreError::at(
            "INVALID_DISTRIBUTION",
            "Probabilities must be finite values between 0 and 1",
            path,
        ));
    }
    let total: f64 = probabilities.iter().sum();
    if (total - 1.0).abs() > 1e-9 {
        return Err(CoreError::at(
            "INVALID_DISTRIBUTION",
            format!("Probabilities sum to {total:.12}, expected 1"),
            path,
        ));
    }
    Ok(())
}
