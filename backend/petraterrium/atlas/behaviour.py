import hashlib
import json

import numpy as np


def log_loss(outcomes, probabilities, weights):
    probabilities = np.clip(probabilities, 1e-12, 1 - 1e-12)
    return float(
        np.average(
            -outcomes * np.log(probabilities) - (1 - outcomes) * np.log1p(-probabilities),
            weights=weights,
        )
    )


def design(rows: list[dict], specification: dict | None = None):
    if specification is None:
        traits = sorted(set.intersection(*(set(row["traits"]) for row in rows)))
        if not traits or len(traits) > 20:
            raise ValueError("A fit requires 1–20 consistently observed traits")
        encoding = []
        for trait in traits:
            values = [row["traits"][trait] for row in rows]
            try:
                numeric = np.asarray([float(value) for value in values], dtype=float)
                if not np.isfinite(numeric).all():
                    raise ValueError("Non-finite trait value")
                encoding.append(
                    {
                        "trait": trait,
                        "kind": "numeric",
                        "mean": float(numeric.mean()),
                        "scale": float(numeric.std()) or 1,
                    }
                )
            except (ValueError, TypeError):
                categories = sorted({str(value) for value in values})
                if len(categories) > 30:
                    raise ValueError(
                        f"Trait {trait} has over 30 categories; "
                        "remove identifiers or supply a documented encoding"
                    ) from None
                encoding.append({"trait": trait, "kind": "categorical", "categories": categories})
        specification = {"encoding": encoding, "traits": traits}
    columns = [np.ones(len(rows))]
    for entry in specification["encoding"]:
        trait = entry["trait"]
        if any(trait not in row["traits"] for row in rows):
            raise ValueError("The new holdout does not contain all incumbent model traits")
        values = [row["traits"][trait] for row in rows]
        if entry["kind"] == "numeric":
            columns.append(
                np.clip((np.asarray(values, dtype=float) - entry["mean"]) / entry["scale"], -20, 20)
            )
        else:
            columns.extend(
                np.asarray([str(value) == category for value in values], dtype=float)
                for category in entry["categories"][1:]
            )
    return np.column_stack(columns), specification


def predict(rows: list[dict], specification: dict):
    matrix, _ = design(rows, specification)
    linear = np.clip(matrix @ np.asarray(specification["coefficients"]), -35, 35)
    return 1 / (1 + np.exp(-linear))


def fit(rows: list[dict], incumbent: dict | None = None) -> dict:
    labeled = [row for row in rows if row["outcome"] is not None and row["traits"]]
    result = {
        "fitted": False,
        "label_only": True,
        "active": True,
        "specification": {},
        "heldout_loss": None,
        "baseline_loss": None,
        "training_rows": 0,
        "heldout_rows": 0,
        "traits": sorted({trait for row in rows for trait in row["traits"]}),
    }
    if len(labeled) < 30:
        result["specification"]["reason"] = (
            "At least 30 linked trait/outcome observations are required;"
            " coefficients remain unavailable"
        )
        return result
    ordered = sorted(
        labeled,
        key=lambda row: hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(),
    )
    holdout = ordered[::5]
    training = [row for index, row in enumerate(ordered) if index % 5]
    if any(len({row["outcome"] for row in subset}) < 2 for subset in (training, holdout)):
        result["specification"]["reason"] = "Both outcomes must occur in training and held-out rows"
        return result
    matrix, specification = design(training)
    outcomes = np.asarray([row["outcome"] for row in training], dtype=float)
    weights = np.asarray([row["weight"] for row in training], dtype=float)
    weights /= weights.mean()
    coefficients = np.zeros(matrix.shape[1])
    penalty = np.eye(len(coefficients)) * 1e-3
    penalty[0, 0] = 0
    for _ in range(80):
        probabilities = 1 / (1 + np.exp(-np.clip(matrix @ coefficients, -35, 35)))
        gradient = matrix.T @ (weights * (probabilities - outcomes)) + penalty @ coefficients
        curvature = (
            matrix.T
            @ ((weights * np.maximum(probabilities * (1 - probabilities), 1e-7))[:, None] * matrix)
            + penalty
        )
        change = np.linalg.lstsq(curvature, gradient, rcond=None)[0]
        coefficients -= change
        if np.max(np.abs(change)) < 1e-7:
            break
    specification["coefficients"] = coefficients.tolist()
    specification["algorithm"] = "weighted-logit-irls-v1"
    specification["holdout"] = holdout
    truth = np.asarray([row["outcome"] for row in holdout], dtype=float)
    heldout_weights = np.asarray([row["weight"] for row in holdout], dtype=float)
    baseline = (
        predict(holdout, incumbent)
        if incumbent
        else np.full(len(holdout), np.average(outcomes, weights=weights))
    )
    baseline_loss = log_loss(truth, baseline, heldout_weights)
    candidate_loss = log_loss(truth, predict(holdout, specification), heldout_weights)
    better = candidate_loss < baseline_loss - 1e-6
    return {
        **result,
        "fitted": True,
        "label_only": False,
        "active": better,
        "specification": specification,
        "heldout_loss": candidate_loss,
        "baseline_loss": baseline_loss,
        "training_rows": len(training),
        "heldout_rows": len(holdout),
        "traits": specification["traits"],
    }


def store_models(conn, import_id: str, rows: list[dict], scope: str) -> None:
    current = conn.execute(
        "SELECT source_date,published_date FROM imports WHERE import_id=?", (import_id,)
    ).fetchone()
    groups = {}
    for row in rows:
        groups.setdefault((row["country_code"], row["behaviour"]), []).append(row)
    for (country, behaviour), observations in groups.items():
        incumbent = conn.execute(
            """SELECT m.* FROM models m JOIN imports v USING(import_id)
            WHERE m.country_code=? AND m.behaviour=? AND m.active=1 AND m.fitted=1
            AND v.status='committed' AND v.scope IN ('shared',?)
            AND v.source_date<=? AND v.published_date<=?
            ORDER BY (v.scope=?) DESC,m.id DESC LIMIT 1""",
            (country, behaviour, scope, current["source_date"], current["published_date"], scope),
        ).fetchone()
        try:
            result = fit(
                observations, json.loads(incumbent["specification_json"]) if incumbent else None
            )
        except (ValueError, TypeError, np.linalg.LinAlgError) as exc:
            result = {
                "fitted": False,
                "label_only": True,
                "active": False,
                "specification": {"reason": str(exc)},
                "heldout_loss": None,
                "baseline_loss": None,
                "training_rows": 0,
                "heldout_rows": 0,
                "traits": [],
            }
        if result["active"] and incumbent and not result["fitted"]:
            result["active"] = False
        conn.execute(
            """INSERT INTO models(import_id,country_code,behaviour,fitted,label_only,active,
            specification_json,heldout_loss,baseline_loss,training_rows,heldout_rows,traits_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                country,
                behaviour,
                result["fitted"],
                result["label_only"],
                result["active"],
                json.dumps(result["specification"]),
                result["heldout_loss"],
                result["baseline_loss"],
                result["training_rows"],
                result["heldout_rows"],
                json.dumps(result["traits"]),
            ),
        )
