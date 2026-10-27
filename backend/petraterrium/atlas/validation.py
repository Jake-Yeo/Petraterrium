import hashlib
import json
import math
from datetime import date

import pycountry

from .contracts import ImportMetadata, MappingConfirmation, ValidationIssue, ValidationReport
from .database import IMPORT_FIELDS

IDENTIFIERS = {
    "geonameid",
    "city",
    "country_code",
    "admin1",
    "admin2",
    "unit",
    "behaviour",
    "outcome",
    "survey_weight",
    "observation_date",
}


def country_code(value) -> str:
    text = str(value).strip().upper()
    if text == "XK":
        return text
    country = pycountry.countries.get(alpha_2=text) or pycountry.countries.get(alpha_3=text)
    if country is None:
        raise ValueError("Country must be an ISO 3166 alpha-2 or alpha-3 code")
    return country.alpha_2


def numeric(value) -> float:
    if isinstance(value, bool):
        raise ValueError("Expected a number, not a boolean")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Value must be finite")
    return number


def validate_value(field: str, value, unit: str):
    if isinstance(value, str) and value.strip().startswith("{"):
        value = json.loads(value)
    if isinstance(value, dict):
        if len(value) < 2:
            raise ValueError("A distribution requires at least two labeled categories")
        result = {str(k): numeric(v) for k, v in value.items()}
        if any(not key.strip() for key in result):
            raise ValueError("Every distribution category must have a label")
        if any(number < 0 or number > 100 for number in result.values()):
            raise ValueError("Distribution percentages must be between 0 and 100")
        total = sum(result.values())
        if not math.isclose(total, 100, abs_tol=0.01):
            raise ValueError(f"Distribution sums to {total:g}%; expected 100% (tolerance 0.01)")
        return result, "percent"
    number = numeric(value)
    if field == "household_size" and 0 < number <= 30:
        return number, "people_per_household"
    if field == "income" and -100_000_000 <= number <= 1_000_000_000:
        if unit in ("", "percent"):
            raise ValueError(
                "A mean income requires explicit currency/time units, such as USD/year"
            )
        return number, unit
    if field in (
        "age_sex",
        "education",
        "ideology",
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
    ):
        raise ValueError(
            "Expected a percentage distribution, not a single coefficient or category code"
        )
    raise ValueError("Value is outside the permitted range")


def geography(conn, values: dict, metadata: ImportMetadata):
    raw_code = values.get("country_code") or metadata.country_code
    identity = values.get("geonameid")
    name = values.get("city")
    if identity not in (None, ""):
        if numeric(identity) != int(numeric(identity)):
            raise ValueError("geonameid must be an integer")
        identity = int(numeric(identity))
        city = conn.execute("SELECT * FROM cities WHERE geonameid=?", (identity,)).fetchone()
        if city is None or (raw_code and city["country_code"] != country_code(raw_code)):
            raise ValueError("geonameid must exist in the backbone and match the country")
        return "city", str(identity), city["country_code"]
    code = country_code(raw_code or "")
    if name not in (None, ""):
        rows = conn.execute(
            (
                "SELECT * FROM cities WHERE country_code=? AND (name=? COLLATE NOCASE OR"
                " asciiname=? COLLATE NOCASE)"
            ),
            (code, str(name), str(name)),
        ).fetchall()
        if values.get("admin1"):
            rows = [row for row in rows if row["admin1"] == str(values["admin1"])]
        if len(rows) != 1:
            raise ValueError(
                f"City name resolves to {len(rows)} matches; supply a stable geonameid"
            )
        return "city", str(rows[0]["geonameid"]), code
    if values.get("admin1") not in (None, ""):
        region = str(values["admin1"])
        if not conn.execute(
            "SELECT 1 FROM cities WHERE country_code=? AND admin1=?", (code, region)
        ).fetchone():
            raise ValueError("Region admin1 does not exist in this country backbone")
        return "region", code + ":" + region, code
    return "country", code, code


def validate_rows(
    conn,
    import_id: str,
    metadata: ImportMetadata,
    rows: list[dict],
    confirmation: MappingConfirmation,
):
    issues = []
    prepared = []
    missingness = {field: 0 for field in IMPORT_FIELDS}
    mappings = confirmation.mappings
    headers = set().union(*(row.keys() for row in rows))
    columns = [m.column for m in mappings]
    targets = [m.target for m in mappings if m.target]
    if metadata.kind == "behaviour":
        missingness = {
            target: 0
            for target in [
                "outcome",
                "survey_weight",
                *[target for target in targets if target.startswith("trait.")],
            ]
        }
    elif metadata.kind == "population":
        missingness = {"density_per_km2": 0}
    for field in IMPORT_FIELDS:
        if field in targets and any(target.startswith(field + ".") for target in targets):
            issues.append(
                ValidationIssue(
                    row=0,
                    field="mapping",
                    message=f"Map either {field} or its components, not both",
                )
            )
    if not confirmation.confirmed or any(m.ambiguous for m in mappings):
        issues.append(
            ValidationIssue(
                row=0,
                field="mapping",
                message=(
                    "Every ambiguous mapping must be resolved or explicitly ignored and confirmed"
                ),
            )
        )
    if len(columns) != len(set(columns)) or set(columns) != headers:
        issues.append(
            ValidationIssue(
                row=0, field="mapping", message="Confirm exactly one mapping for every input column"
            )
        )
    if len(targets) != len(set(targets)):
        issues.append(
            ValidationIssue(
                row=0, field="mapping", message="Two columns cannot map to the same target"
            )
        )
    for target in targets:
        root = target.split(".", 1)[0]
        if root not in {*IMPORT_FIELDS, *IDENTIFIERS, "trait", "density_per_km2"} or (
            root == "trait" and "." not in target
        ):
            issues.append(
                ValidationIssue(row=0, field="mapping", message=f"Unknown target: {target}")
            )
    digest = hashlib.sha256(
        json.dumps([m.model_dump() for m in mappings], sort_keys=True).encode()
    ).hexdigest()
    if issues:
        return ValidationReport(
            import_id=import_id,
            valid=False,
            total_rows=len(rows),
            observations=0,
            issues=issues,
            missingness=missingness,
            mapping_hash=digest,
        ), []
    seen = set()
    for index, row in enumerate(rows, 1):
        values = {}
        for mapping in mappings:
            value = row.get(mapping.column)
            if not mapping.target or value in (None, ""):
                continue
            target = mapping.target
            if "." in target and target.split(".", 1)[0] in IMPORT_FIELDS:
                root, label = target.split(".", 1)
                values.setdefault(root, {})[label] = value
            else:
                values[target] = value
        try:
            if (
                values.get("observation_date")
                and date.fromisoformat(str(values["observation_date"])) > metadata.source_date
            ):
                raise ValueError("Observation date is later than the declared data date")
            level, key, code = geography(conn, values, metadata)
        except (ValueError, TypeError) as exc:
            issues.append(ValidationIssue(row=index, field="geography/date", message=str(exc)))
            continue
        if metadata.kind == "behaviour":
            for target in missingness:
                if target not in values:
                    missingness[target] += 1
            try:
                traits = {k[6:]: v for k, v in values.items() if k.startswith("trait.")}
                outcome = values.get("outcome")
                if outcome is not None and numeric(outcome) not in (0, 1):
                    raise ValueError("Behaviour outcome must be 0 or 1")
                for value in traits.values():
                    if isinstance(value, (int, float)):
                        numeric(value)
                    elif isinstance(value, str):
                        try:
                            parsed = float(value)
                        except ValueError:
                            continue
                        if not math.isfinite(parsed):
                            raise ValueError("Trait values must be finite or explicitly missing")
                weight = numeric(values.get("survey_weight", 1))
                if weight <= 0:
                    raise ValueError("Survey weight must be positive")
                prepared.append(
                    {
                        "country_code": code,
                        "behaviour": str(values.get("behaviour", "action")),
                        "traits": traits,
                        "outcome": None if outcome is None else int(numeric(outcome)),
                        "weight": weight,
                    }
                )
            except (ValueError, TypeError) as exc:
                issues.append(ValidationIssue(row=index, field="behaviour", message=str(exc)))
            continue
        if metadata.kind == "population":
            if "density_per_km2" not in values:
                missingness["density_per_km2"] += 1
            try:
                density = numeric(values.get("density_per_km2"))
                if level != "city" or not 0 < density <= 10_000_000:
                    raise ValueError("Density requires a city id and a positive persons/km² value")
                prepared.append({"geonameid": int(key), "density": density})
            except (ValueError, TypeError) as exc:
                issues.append(ValidationIssue(row=index, field="density_per_km2", message=str(exc)))
            continue
        for field in IMPORT_FIELDS:
            value = values.get(field)
            if value in (None, ""):
                missingness[field] += 1
                continue
            try:
                result, unit = validate_value(field, value, str(values.get("unit", metadata.unit)))
                identity = (level, key, field)
                if identity in seen:
                    raise ValueError(
                        "Duplicate geography/field in this import; aggregate or resolve it first"
                    )
                seen.add(identity)
                prepared.append(
                    {
                        "geo_level": level,
                        "geo_key": key,
                        "field": field,
                        "value": result,
                        "unit": unit,
                    }
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                issues.append(ValidationIssue(row=index, field=field, message=str(exc)))
    if not prepared and not issues:
        issues.append(
            ValidationIssue(row=0, field="data", message="No usable observations were mapped")
        )
    return ValidationReport(
        import_id=import_id,
        valid=not issues,
        total_rows=len(rows),
        observations=len(prepared),
        issues=issues,
        missingness=missingness,
        mapping_hash=digest,
    ), prepared
