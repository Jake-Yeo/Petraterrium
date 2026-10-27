use crate::error::{CoreError, CoreResult};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CsrMatrix {
    pub rows: usize,
    pub cols: usize,
    pub row_offsets: Vec<usize>,
    pub column_indices: Vec<usize>,
    pub weights: Vec<f64>,
}

impl CsrMatrix {
    pub fn validate(&self, path: &str) -> CoreResult<()> {
        if self.row_offsets.len() != self.rows + 1 {
            return Err(CoreError::at(
                "INVALID_CSR",
                "row_offsets length must equal rows + 1",
                format!("{path}.row_offsets"),
            ));
        }
        if self.row_offsets.first() != Some(&0) {
            return Err(CoreError::at(
                "INVALID_CSR",
                "row_offsets must start at zero",
                format!("{path}.row_offsets"),
            ));
        }
        if self.column_indices.len() != self.weights.len()
            || self.row_offsets.last() != Some(&self.weights.len())
        {
            return Err(CoreError::at(
                "INVALID_CSR",
                "CSR offsets, columns, and weights have inconsistent lengths",
                path,
            ));
        }
        if self.row_offsets.windows(2).any(|pair| pair[0] > pair[1]) {
            return Err(CoreError::at(
                "INVALID_CSR",
                "row_offsets must be monotonic",
                format!("{path}.row_offsets"),
            ));
        }
        if self
            .column_indices
            .iter()
            .any(|column| *column >= self.cols)
        {
            return Err(CoreError::at(
                "INVALID_CSR",
                "column index exceeds matrix dimensions",
                format!("{path}.column_indices"),
            ));
        }
        if self.weights.iter().any(|value| !value.is_finite()) {
            return Err(CoreError::at(
                "INVALID_CSR",
                "weights must be finite",
                format!("{path}.weights"),
            ));
        }
        Ok(())
    }

    pub fn matvec(&self, values: &[f64], path: &str) -> CoreResult<Vec<f64>> {
        self.validate(path)?;
        if values.len() != self.cols {
            return Err(CoreError::at(
                "INVALID_VECTOR",
                "Input vector length must equal CSR column count",
                path,
            ));
        }
        let mut result = vec![0.0; self.rows];
        for (row, result_value) in result.iter_mut().enumerate() {
            let start = self.row_offsets[row];
            let end = self.row_offsets[row + 1];
            for edge in start..end {
                *result_value += self.weights[edge] * values[self.column_indices[edge]];
            }
        }
        Ok(result)
    }

    pub fn normalized_matvec(&self, values: &[f64], path: &str) -> CoreResult<Vec<f64>> {
        let mut result = self.matvec(values, path)?;
        for (row, result_value) in result.iter_mut().enumerate() {
            let start = self.row_offsets[row];
            let end = self.row_offsets[row + 1];
            let weight: f64 = self.weights[start..end].iter().sum();
            if weight.abs() > 1e-15 {
                *result_value /= weight;
            }
        }
        Ok(result)
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CsrMatvecRequest {
    pub matrix: CsrMatrix,
    pub values: Vec<f64>,
    #[serde(default)]
    pub normalize_rows: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct CsrMatvecResult {
    pub values: Vec<f64>,
}

pub fn run_matvec(request: CsrMatvecRequest) -> CoreResult<CsrMatvecResult> {
    let values = if request.normalize_rows {
        request
            .matrix
            .normalized_matvec(&request.values, "matrix")?
    } else {
        request.matrix.matvec(&request.values, "matrix")?
    };
    Ok(CsrMatvecResult { values })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csr_matvec_applies_sparse_neighbor_weights() {
        let matrix = CsrMatrix {
            rows: 3,
            cols: 3,
            row_offsets: vec![0, 2, 3, 4],
            column_indices: vec![1, 2, 0, 1],
            weights: vec![0.5, 0.5, 1.0, 1.0],
        };
        let result = matrix.matvec(&[2.0, 4.0, 8.0], "network").unwrap();
        assert_eq!(result, vec![6.0, 2.0, 4.0]);
    }
}
