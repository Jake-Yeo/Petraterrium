from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..atlas.regions import CANONICAL_REGIONS, country_languages
from .default_dsl import DefaultActionDefinition, _validate_exclusive_action_choices
from .finance_initialization import FinanceInitializationCatalog

AUDIT_SCHEMA_VERSION = "prompt1-source-audit-v3"
PERSONALITY_FEATURES = {
    "agreeableness",
    "conscientiousness",
    "extraversion",
    "neuroticism",
    "openness",
}
VALUE_FEATURES = {
    "generalized_trust",
    "ideology_cultural",
    "ideology_economic",
    "ideology_state",
    "religiosity",
    "risk_aversion",
    "schwartz_values",
    "time_preference",
}
MAJOR_FIELDS = (
    "age",
    "sex",
    "education",
    "specialization",
    "occupation",
    "personality",
    "values",
    "finance",
)
SOURCE_REQUIREMENTS = (
    "title",
    "english_title",
    "source",
    "date",
    "population",
    "place",
    "language",
    "discovery_source",
)


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactReceipt(AuditModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceInventoryRecord(AuditModel):
    source_id: str
    title: str | None
    english_title: str | None
    source: str | None
    date: str | None
    population: str | None
    place: str | None
    language: str | None
    discovery_source: str | None
    url: str | None
    supports: tuple[str, ...]
    missing_required_metadata: tuple[str, ...]


class FieldSourceAudit(AuditModel):
    field: str
    geographic_scope: Literal["own_country_source", "regional_imputed", "unknown", "mixed"]
    raw_scope_labels: tuple[str, ...]
    source_statuses: tuple[str, ...]
    sampling_statuses: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_places: tuple[str, ...]
    sources: tuple[str, ...]
    source_dates: tuple[str, ...]
    source_versions: tuple[str, ...]
    individual_values_measured: bool
    measurement_description: str
    foreign_country_source: bool
    canadian_source_leakage: bool
    missing_item_provenance: tuple[str, ...]


class CountrySourceAudit(AuditModel):
    country_code: str
    country_name: str
    region: str
    agent_count: int = Field(ge=1)
    finance_currency: str
    finance_accounting_unit: str
    fields: dict[str, FieldSourceAudit]


class LocalLanguageSearchAudit(AuditModel):
    country_code: str
    registry_languages: tuple[str, ...]
    recorded_languages: tuple[str, ...]
    fields_with_item_level_search_trace: tuple[str, ...]
    fields_missing_item_level_search_trace: tuple[str, ...]
    has_non_english_local_trace: bool
    status: Literal["complete", "incomplete"]


class EvidenceInventory(AuditModel):
    state_initialization_statuses: dict[str, int]
    state_evidence_statuses: dict[str, int]
    relationship_evidence_statuses: dict[str, int]
    action_evidence_statuses: dict[str, int]
    numeric_coefficients_with_unknown_evidence: tuple[str, ...]
    default_actions_without_source_ids: tuple[str, ...]


class SpecializationEvidenceAudit(AuditModel):
    total_agents: int = Field(ge=1)
    missing_value_count: int = Field(ge=0)
    threshold_years: tuple[int, ...]
    status_counts: dict[str, int]
    evidence_scope_counts: dict[str, int]
    source_status_counts: dict[str, int]
    country_status_counts: dict[str, dict[str, int]]
    unknown_country_codes: tuple[str, ...]
    threshold_status_mismatch_count: int = Field(ge=0)
    required_data: str


class DslSourceOfTruthItem(AuditModel):
    domain: str
    status: Literal["dsl_defined", "mixed", "runtime_hardcoded", "missing"]
    dsl_definition_ids: tuple[str, ...]
    dsl_formula_count: int = Field(ge=0)
    executable_parameter_count: int = Field(ge=0)
    runtime_files: tuple[str, ...]
    runtime_symbols: tuple[str, ...]
    outside_dsl_behaviors: tuple[str, ...]
    unresolved_items: tuple[str, ...]


class DslSourceOfTruthAudit(AuditModel):
    result: Literal["complete", "incomplete"]
    represented_country_codes: tuple[str, ...]
    decision_tree_country_codes: tuple[str, ...]
    decision_tree_uncovered_country_codes: tuple[str, ...]
    items: tuple[DslSourceOfTruthItem, ...]


class MissingRegisterAudit(AuditModel):
    entries_found: tuple[str, ...]
    entries_absent: tuple[str, ...]


class AuditFinding(AuditModel):
    finding_id: str
    status: Literal["pass", "gap", "risk"]
    summary: str
    affected_countries: tuple[str, ...] = ()
    affected_fields: tuple[str, ...] = ()
    logged_in_missing: bool = False


class Prompt1SourceAudit(AuditModel):
    schema_version: str
    audit_scope: str
    verification_boundary: str
    result: Literal["complete", "incomplete", "failed"]
    artifacts: dict[str, ArtifactReceipt]
    dsl_version: str
    dsl_content_hash: str
    total_agents: int
    country_agent_counts: dict[str, int]
    region_agent_counts: dict[str, int]
    countries: tuple[CountrySourceAudit, ...]
    source_inventory: tuple[SourceInventoryRecord, ...]
    local_language_search: tuple[LocalLanguageSearchAudit, ...]
    evidence_inventory: EvidenceInventory
    specialization_evidence: SpecializationEvidenceAudit
    dsl_source_of_truth: DslSourceOfTruthAudit
    missing_register: MissingRegisterAudit
    findings: tuple[AuditFinding, ...]


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "defaults" / "base-v1.json"


def default_finance_pack_path() -> Path:
    return Path(__file__).resolve().parent / "defaults" / "global-finance-wdi-v1.json"


def default_missing_path() -> Path:
    return _repository_root() / "MISSING.md"


def _artifact_receipt(path: Path) -> ArtifactReceipt:
    payload = path.read_bytes()
    return ArtifactReceipt(path=str(path), sha256=hashlib.sha256(payload).hexdigest())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _unique(values: list[Any] | tuple[Any, ...] | set[Any]) -> tuple[str, ...]:
    return tuple(sorted({_text(value) for value in values if _text(value) is not None}))


def _source_inventory(default_sources: list[dict[str, Any]]) -> tuple[SourceInventoryRecord, ...]:
    records = []
    for source in default_sources:
        normalized = {
            "title": _text(source.get("original_title")),
            "english_title": _text(source.get("english_title")),
            "source": _text(source.get("publisher")),
            "date": _text(source.get("publication_date")),
            "population": _text(source.get("population")),
            "place": _text(source.get("place")),
            "language": _text(source.get("language")),
            "discovery_source": _text(source.get("discovery_source")),
        }
        records.append(
            SourceInventoryRecord(
                source_id=str(source["id"]),
                **normalized,
                url=_text(source.get("url")),
                supports=tuple(str(item) for item in source.get("supports", [])),
                missing_required_metadata=tuple(
                    key for key in SOURCE_REQUIREMENTS if normalized[key] is None
                ),
            )
        )
    return tuple(sorted(records, key=lambda record: record.source_id))


def _prefixed_record(traits: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "scope": traits.get(f"{prefix}_evidence_scope", "unknown"),
        "status": traits.get(f"{prefix}_source_status", "unknown"),
        "sampling": traits.get(f"{prefix}_sampling_status", "unknown"),
        "source_id": traits.get(f"{prefix}_source_id"),
        "source_place": traits.get(f"{prefix}_source_place"),
        "source": traits.get(f"{prefix}_source"),
        "source_date": traits.get(f"{prefix}_source_date"),
        "source_version": traits.get(f"{prefix}_source_version"),
        "population": traits.get(f"{prefix}_source_population"),
        "language": traits.get(f"{prefix}_language"),
        "title": traits.get(f"{prefix}_original_title"),
        "english_title": traits.get(f"{prefix}_english_title"),
        "discovery_source": traits.get(f"{prefix}_search_source"),
    }


def _feature_records(traits: dict[str, Any], feature_ids: set[str]) -> list[dict[str, Any]]:
    provenance = traits.get("feature_provenance", {})
    return [
        {
            "scope": record.get("evidence_scope", "unknown"),
            "status": record.get("source_status", "unknown"),
            "sampling": record.get("sampling_status", "unknown"),
            "source_id": record.get("source_id"),
            "source_place": record.get("source_place"),
            "source": record.get("source"),
            "source_date": record.get("source_date"),
            "source_version": record.get("source_version"),
            "population": None,
            "language": None,
            "title": None,
            "english_title": None,
            "discovery_source": None,
        }
        for feature_id, record in provenance.items()
        if feature_id in feature_ids
    ]


def _records_for_field(traits: dict[str, Any], field: str) -> list[dict[str, Any]]:
    if field in {"age", "sex", "education", "specialization", "finance"}:
        return [_prefixed_record(traits, field)]
    if field == "occupation":
        provenance = traits.get("feature_provenance", {}).get("occupation_isco", {})
        return [
            {
                "scope": traits.get("occupation_evidence_scope", "unknown"),
                "status": traits.get("occupation_source_status", "unknown"),
                "sampling": provenance.get("sampling_status", "unknown"),
                "source_id": traits.get("occupation_source_id"),
                "source_place": traits.get("occupation_source_place"),
                "source": provenance.get("source"),
                "source_date": provenance.get("source_date"),
                "source_version": provenance.get("source_version"),
                "population": None,
                "language": None,
                "title": None,
                "english_title": None,
                "discovery_source": None,
            }
        ]
    if field == "personality":
        return _feature_records(traits, PERSONALITY_FEATURES)
    if field == "values":
        return _feature_records(traits, VALUE_FEATURES)
    raise ValueError(f"Unsupported major field {field}")


def _geographic_scope(scopes: tuple[str, ...]) -> str:
    normalized = set(scopes)
    if not normalized or "unknown" in normalized:
        return "unknown"
    if normalized <= {"country_measured", "estimated"}:
        return "own_country_source"
    if normalized == {"regional_imputed"}:
        return "regional_imputed"
    return "mixed"


def _measurement_description(
    field: str,
    geographic_scope: str,
    statuses: tuple[str, ...],
    sampling: tuple[str, ...],
) -> str:
    if geographic_scope == "unknown":
        return "No usable source is attached."
    if geographic_scope in {"regional_imputed", "mixed"}:
        return "At least one value is inherited from a regional archetype and is imputed."
    if field == "finance":
        return "Own-country macro or marginal inputs; every person-level finance value is imputed."
    if "imputed_individual_draw" in sampling:
        quality = ", ".join(statuses)
        return f"Own-country source with a synthetic individual draw; source status: {quality}."
    return "Own-country source; individual measurement is not established by this manifest."


def _missing_item_provenance(records: list[dict[str, Any]]) -> tuple[str, ...]:
    missing = set()
    field_map = {
        "source": "source",
        "date": "source_date",
        "population": "population",
        "place": "source_place",
        "language": "language",
        "title": "title",
        "english_title": "english_title",
        "discovery_source": "discovery_source",
    }
    for requirement, key in field_map.items():
        if any(_text(record.get(key)) is None for record in records):
            missing.add(requirement)
    return tuple(sorted(missing))


def _field_audit(
    field: str,
    records: list[dict[str, Any]],
    country_code: str,
    country_name: str,
    region: str,
) -> FieldSourceAudit:
    scopes = _unique([record.get("scope") for record in records])
    statuses = _unique([record.get("status") for record in records])
    sampling = _unique([record.get("sampling") for record in records])
    source_places = _unique([record.get("source_place") for record in records])
    sources = _unique([record.get("source") for record in records])
    scope = _geographic_scope(scopes)
    allowed_country_places = {country_code.casefold(), country_name.casefold()}
    foreign_country_source = any(
        place.casefold() not in allowed_country_places
        for place in source_places
        if scope == "own_country_source"
    ) or any(place != region for place in source_places if scope == "regional_imputed")
    searchable = " ".join(
        _text(record.get(key)) or ""
        for record in records
        for key in ("source_id", "source_place", "source", "source_version", "title")
    ).casefold()
    canadian_source_leakage = country_code != "CA" and any(
        marker in searchable for marker in ("statistics canada", "statistique canada", "statscan")
    )
    return FieldSourceAudit(
        field=field,
        geographic_scope=scope,
        raw_scope_labels=scopes,
        source_statuses=statuses,
        sampling_statuses=sampling,
        source_ids=_unique([record.get("source_id") for record in records]),
        source_places=source_places,
        sources=sources,
        source_dates=_unique([record.get("source_date") for record in records]),
        source_versions=_unique([record.get("source_version") for record in records]),
        individual_values_measured=False,
        measurement_description=_measurement_description(field, scope, statuses, sampling),
        foreign_country_source=foreign_country_source,
        canadian_source_leakage=canadian_source_leakage,
        missing_item_provenance=_missing_item_provenance(records),
    )


def _specialization_pipeline_records(
    specialization_pipeline: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {}
    for country in (specialization_pipeline or {}).get("countries", ()):
        country_code = str(country["country_code"])
        country_records = []
        for source in country.get("sources_tried", ()):
            if not source.get("result_used"):
                continue
            country_records.append(
                {
                    "scope": (
                        "country_measured"
                        if country.get("evidence_status") == "measured"
                        else "estimated"
                    ),
                    "status": country.get("evidence_status"),
                    "sampling": "imputed_individual_draw",
                    "source_id": country.get("pipeline_attempt_id"),
                    "source_place": country_code,
                    "source": source.get("english_title"),
                    "source_date": source.get("publication_date")
                    or country.get("reference_year"),
                    "source_version": country.get("version"),
                    "population": country.get("population_basis"),
                    "language": source.get("language"),
                    "title": source.get("original_title"),
                    "english_title": source.get("english_title"),
                    "discovery_source": source.get("discovery_method"),
                }
            )
        records[country_code] = country_records
    return records


def _country_audits(
    agents: list[dict[str, Any]],
    specialization_pipeline: dict[str, Any] | None,
) -> tuple[CountrySourceAudit, ...]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for agent in agents:
        grouped[str(agent["place"])].append(agent)
    specialization_records = _specialization_pipeline_records(specialization_pipeline)
    audits = []
    for country_code, country_agents in sorted(grouped.items()):
        traits = country_agents[0]["traits"]
        country_name = str(traits["country"])
        region = str(traits["region"])
        field_records = {
            field: (
                specialization_records.get(country_code, [])
                if field == "specialization" and country_code in specialization_records
                else [
                    record
                    for agent in country_agents
                    for record in _records_for_field(agent["traits"], field)
                ]
            )
            for field in MAJOR_FIELDS
        }
        audits.append(
            CountrySourceAudit(
                country_code=country_code,
                country_name=country_name,
                region=region,
                agent_count=len(country_agents),
                finance_currency=str(traits.get("finance_currency", "unknown")),
                finance_accounting_unit=str(traits.get("finance_accounting_unit", "unknown")),
                fields={
                    field: _field_audit(
                        field,
                        records,
                        country_code,
                        country_name,
                        region,
                    )
                    for field, records in field_records.items()
                },
            )
        )
    return tuple(audits)


def _local_language_audits(
    countries: tuple[CountrySourceAudit, ...],
    agents: list[dict[str, Any]],
    specialization_pipeline: dict[str, Any] | None,
) -> tuple[LocalLanguageSearchAudit, ...]:
    representative = {str(agent["place"]): agent["traits"] for agent in reversed(agents)}
    specialization_searches = {
        str(country["country_code"]): tuple(country.get("sources_tried", ()))
        for country in (specialization_pipeline or {}).get("countries", ())
    }
    audits = []
    for country in countries:
        traits = representative[country.country_code]
        traced_fields = []
        recorded_languages = set()
        for field in MAJOR_FIELDS:
            records = _records_for_field(traits, field)
            if records and all(
                _text(record.get("language"))
                and _text(record.get("discovery_source"))
                and _text(record.get("title"))
                and _text(record.get("english_title"))
                for record in records
            ):
                traced_fields.append(field)
            recorded_languages.update(
                str(record["language"]) for record in records if _text(record.get("language"))
            )
        specialization_sources = specialization_searches.get(country.country_code, ())
        if specialization_sources and all(
            _text(source.get("language"))
            and _text(source.get("original_title"))
            and _text(source.get("english_title"))
            and _text(source.get("discovery_method"))
            and _text(source.get("query"))
            for source in specialization_sources
        ):
            traced_fields.append("specialization")
        recorded_languages.update(
            str(source["language"])
            for source in specialization_sources
            if _text(source.get("language"))
        )
        traced_fields = [field for field in MAJOR_FIELDS if field in set(traced_fields)]
        registry_languages = tuple(country_languages().get(country.country_code, ()))
        non_english = set(registry_languages) - {"en"}
        audits.append(
            LocalLanguageSearchAudit(
                country_code=country.country_code,
                registry_languages=registry_languages,
                recorded_languages=tuple(sorted(recorded_languages)),
                fields_with_item_level_search_trace=tuple(traced_fields),
                fields_missing_item_level_search_trace=tuple(
                    field for field in MAJOR_FIELDS if field not in traced_fields
                ),
                has_non_english_local_trace=bool(non_english & recorded_languages),
                status="complete" if len(traced_fields) == len(MAJOR_FIELDS) else "incomplete",
            )
        )
    return tuple(audits)


def _evidence_inventory(content: dict[str, Any]) -> EvidenceInventory:
    state_initialization = Counter()
    state_evidence = Counter()
    relationship_evidence = Counter()
    numeric_unknown = []
    for state in content["agent_states"]["definitions"]:
        initial = state.get("initial_evidence")
        if initial:
            state_initialization[str(initial.get("status", "missing"))] += 1
        evidence_rows = [state.get("recovery", {}).get("evidence")]
        for section in ("decision_modifiers", "propagation", "event_effects"):
            for row in state.get(section, []):
                evidence = row.get("evidence")
                evidence_rows.append(evidence)
                if row.get("coefficient") is not None and evidence.get("status") == "unknown":
                    numeric_unknown.append(
                        f"{state['id']}:{section}:{row.get('parameter_id', row.get('decision_id'))}"
                    )
        for evidence in evidence_rows:
            if evidence:
                state_evidence[str(evidence.get("status", "missing"))] += 1
    for state in content["relationship_states"]["definitions"]:
        evidence_rows = [state.get("recovery", {}).get("evidence")]
        evidence_rows.extend(row.get("evidence") for row in state.get("event_effects", []))
        for evidence in evidence_rows:
            if evidence:
                relationship_evidence[str(evidence.get("status", "missing"))] += 1
    actions = content["default_actions"]
    action_statuses = Counter(str(action["evidence"]["status"]) for action in actions)
    no_source_ids = tuple(
        sorted(action["id"] for action in actions if not action["evidence"]["source_ids"])
    )
    return EvidenceInventory(
        state_initialization_statuses=dict(sorted(state_initialization.items())),
        state_evidence_statuses=dict(sorted(state_evidence.items())),
        relationship_evidence_statuses=dict(sorted(relationship_evidence.items())),
        action_evidence_statuses=dict(sorted(action_statuses.items())),
        numeric_coefficients_with_unknown_evidence=tuple(sorted(numeric_unknown)),
        default_actions_without_source_ids=no_source_ids,
    )


def _specialization_evidence_audit(
    agents: list[dict[str, Any]],
) -> SpecializationEvidenceAudit:
    statuses = Counter()
    evidence_scopes = Counter()
    source_statuses = Counter()
    country_statuses: dict[str, Counter[str]] = defaultdict(Counter)
    unknown_countries = set()
    thresholds = set()
    missing_value_count = 0
    mismatch_count = 0
    for agent in agents:
        country_code = str(agent["place"])
        traits = agent["traits"]
        status = str(traits.get("specialization_status", "missing"))
        evidence_scope = str(traits.get("specialization_evidence_scope", "missing"))
        source_status = str(traits.get("specialization_source_status", "missing"))
        threshold = int(traits.get("specialization_threshold_years", -1))
        years = int(traits.get("years_of_education", -1))
        applicable = years >= threshold
        expected_status = "present" if applicable else "not_applicable"
        specialization = _text(traits.get("specialization"))
        value_matches_threshold = bool(specialization) if applicable else specialization is None
        provenance_is_executable = (
            evidence_scope in {"country_measured", "estimated"}
            and source_status in {"measured", "estimated"}
            and _text(traits.get("specialization_source_id")) is not None
            and _text(traits.get("specialization_source_place"))
            in {country_code, _text(traits.get("country"))}
            and _text(traits.get("specialization_source")) is not None
            and _text(traits.get("specialization_source_version")) is not None
            and _text(traits.get("specialization_source_date")) is not None
            and int(traits.get("specialization_search_log_count", 0)) > 0
        )
        statuses[status] += 1
        evidence_scopes[evidence_scope] += 1
        source_statuses[source_status] += 1
        country_statuses[country_code][status] += 1
        thresholds.add(threshold)
        missing_value_count += specialization is None
        mismatch_count += status != expected_status or not value_matches_threshold
        if not provenance_is_executable or (applicable and specialization is None):
            unknown_countries.add(country_code)
    return SpecializationEvidenceAudit(
        total_agents=len(agents),
        missing_value_count=missing_value_count,
        threshold_years=tuple(sorted(thresholds)),
        status_counts=dict(sorted(statuses.items())),
        evidence_scope_counts=dict(sorted(evidence_scopes.items())),
        source_status_counts=dict(sorted(source_statuses.items())),
        country_status_counts={
            country_code: dict(sorted(country_counts.items()))
            for country_code, country_counts in sorted(country_statuses.items())
        },
        unknown_country_codes=tuple(sorted(unknown_countries)),
        threshold_status_mismatch_count=mismatch_count,
        required_data=(
            "Further refinement requires place-specific age/sex/education joint "
            "field-of-study or vocational distribution data with an ISCED-F-compatible "
            "mapping, weights, and provenance."
        ),
    )


def _relative_runtime_path(path: Path) -> str:
    return str(path.resolve().relative_to(_repository_root()))


def _state_formula_inventory(
    content: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    formulas = []
    for section_name in ("agent_states", "relationship_states"):
        for state in content[section_name]["definitions"]:
            for collection in ("decision_modifiers", "propagation", "event_effects"):
                for index, row in enumerate(state.get(collection, [])):
                    if not row.get("formula"):
                        continue
                    identity = f"{section_name}:{state['id']}:{collection}:{index}"
                    formulas.append(identity)
            if state.get("recovery", {}).get("formula"):
                formulas.append(f"{section_name}:{state['id']}:recovery")
    catalog = content["agent_states"]
    definition_ids = {str(state["id"]) for state in catalog["definitions"]}
    runtime_rules = catalog.get("runtime_rules", [])
    runtime_targets = [str(rule.get("target_state_id", "")) for rule in runtime_rules]
    runtime_ids = [f"agent_states:{target}:runtime" for target in runtime_targets if target]
    unresolved = []
    missing_targets = sorted(definition_ids - set(runtime_targets))
    unknown_targets = sorted(set(runtime_targets) - definition_ids)
    duplicate_targets = sorted(
        target for target, count in Counter(runtime_targets).items() if target and count > 1
    )
    unresolved.extend(f"{target}: no runtime state rule" for target in missing_targets)
    unresolved.extend(
        f"{target}: runtime rule has no state definition" for target in unknown_targets
    )
    unresolved.extend(f"{target}: duplicate runtime state rules" for target in duplicate_targets)
    expected_coefficients: dict[str, dict[str, float]] = defaultdict(dict)
    for source_state in catalog["definitions"]:
        for propagation in source_state.get("propagation", []):
            coefficient = propagation.get("coefficient")
            if coefficient is not None:
                expected_coefficients[str(propagation["target_state_id"])][
                    str(source_state["id"])
                ] = float(coefficient)
    for rule in runtime_rules:
        target = str(rule.get("target_state_id", "missing-target"))
        missing_fields = [
            field
            for field in ("formula", "intercept", "minimum", "maximum", "evidence")
            if rule.get(field) is None
        ]
        if missing_fields:
            unresolved.append(
                f"{target}: runtime rule lacks {', '.join(sorted(missing_fields))}"
            )
        actual_coefficients = {
            str(source): float(value)
            for source, value in rule.get("coefficients", {}).items()
        }
        if actual_coefficients != expected_coefficients.get(target, {}):
            unresolved.append(f"{target}: runtime coefficients differ from declared propagation")
    return formulas, runtime_ids, unresolved


def _finance_rule_inventory(
    content: dict[str, Any],
) -> tuple[list[str], list[str], int]:
    ledger = content.get("finance_rules", {})
    rules = ledger.get("rules", [])
    required_targets = {
        "finance.money",
        "finance.income",
        "finance.expenses",
        "finance.savings",
        "finance.debt",
    }
    targets = [str(rule.get("target", "")) for rule in rules]
    unresolved = []
    if ledger.get("status") != "confirmed":
        unresolved.append("finance ledger is not confirmed")
    unresolved.extend(
        f"{target}: no DSL ledger rule" for target in sorted(required_targets - set(targets))
    )
    unresolved.extend(
        f"{target}: duplicate DSL ledger rules"
        for target, count in sorted(Counter(targets).items())
        if target and count > 1
    )
    for rule in rules:
        identity = str(rule.get("id", "missing-id"))
        missing = [
            field
            for field in ("id", "target", "terms", "formula", "evidence")
            if not rule.get(field)
        ]
        if missing:
            unresolved.append(f"{identity}: ledger rule lacks {', '.join(sorted(missing))}")
    return (
        [f"ledger:{rule.get('id', 'missing-id')}" for rule in rules],
        unresolved,
        sum(len(rule.get("terms", {})) for rule in rules),
    )


def _cash_flow_is_configured(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("formula")) and float(value.get("multiplier", 0)) != 0
    return float(value or 0) != 0


def _expression_node_count(expression: Any) -> int:
    return 1 + sum(_expression_node_count(argument) for argument in expression.args)


def _finance_initialization_inventory(
    content: dict[str, Any], managed_sections: tuple[str, ...]
) -> tuple[list[str], int, int, list[str]]:
    unresolved = []
    payload = content.get("finance_initialization")
    if payload is None:
        return [], 0, 0, ["finance_initialization is absent from the shipped manifest"]
    if "finance_initialization" not in managed_sections:
        unresolved.append("finance_initialization is not a managed manifest section")
    try:
        catalog = FinanceInitializationCatalog.model_validate(payload)
    except ValueError as error:
        message = " ".join(str(error).split())
        return [], 0, 0, [f"finance_initialization fails schema validation: {message}"]
    definition_ids = [
        f"finance-initialization:{program.id}:{output_id}"
        for program in catalog.programs.values()
        for output_id in sorted(program.outputs)
    ]
    formula_count = sum(len(program.outputs) for program in catalog.programs.values())
    expression_node_count = sum(
        _expression_node_count(output.expression)
        for program in catalog.programs.values()
        for output in program.outputs.values()
    )
    if not catalog.programs:
        unresolved.append("finance_initialization contains no programs")
    return definition_ids, formula_count, expression_node_count, unresolved


def _action_choice_inventory(
    actions: list[dict[str, Any]],
) -> tuple[tuple[str, ...], list[str]]:
    unresolved = []
    validated_actions = []
    for action in actions:
        try:
            validated_actions.append(
                DefaultActionDefinition.model_validate_json(json.dumps(action))
            )
        except ValueError as error:
            action_id = str(action.get("id", "missing-id"))
            message = " ".join(str(error).split())
            unresolved.append(f"{action_id}: action definition fails validation: {message}")
    if len(validated_actions) == len(actions):
        try:
            _validate_exclusive_action_choices(validated_actions)
        except ValueError as error:
            unresolved.append(str(error))
    midday_branches = {
        action.id: action
        for action in validated_actions
        if action.exclusive_choice_group == "midday_meal"
    }
    expected_midday_branches = {"eat_lunch", "skip_lunch"}
    if set(midday_branches) != expected_midday_branches:
        unresolved.append(
            "midday_meal must contain exactly eat_lunch and skip_lunch as exclusive branches"
        )
    elif any(not action.runtime_rules for action in midday_branches.values()):
        unresolved.append("midday_meal branches require executable runtime rules")
    definition_ids = tuple(
        f"exclusive-choice:midday_meal:{action_id}"
        for action_id in sorted(midday_branches)
    )
    return definition_ids, unresolved


def _interaction_parameter_count(program: dict[str, Any]) -> int:
    count = 0
    for relationship in program.get("relationship_evidence", []):
        count += sum(name in relationship for name in ("weight", "trust", "similarity"))
    for rule in program.get("rules", []):
        count += int(bool(rule.get("base_factor")))
        count += sum(
            len(rule.get(name, {}))
            for name in (
                "relationship_factors",
                "colocation_factors",
                "place_factors",
            )
        )
        count += len(rule.get("context_factors", []))
        count += len(rule.get("time_factors", []))
    return count


def _dsl_source_of_truth_audit(
    content: dict[str, Any],
    countries: tuple[CountrySourceAudit, ...],
    managed_sections: tuple[str, ...],
) -> DslSourceOfTruthAudit:
    repository = _repository_root()
    state_compiler = repository / "backend/petraterrium/simulation/runtime_state_compiler.py"
    decision_compiler = repository / "backend/petraterrium/simulation/runtime_decision_compiler.py"
    finance_runtime = repository / "backend/petraterrium/simulation/global_finance.py"
    canada_finance_runtime = repository / "backend/petraterrium/simulation/default_finance.py"
    finance_interpreter = (
        repository / "backend/petraterrium/simulation/finance_initialization.py"
    )
    rust_runtime = repository / "engine-rust/src/agents.rs"
    rust_state_finance = repository / "engine-rust/src/state_finance.rs"
    state_formulas, state_runtime_rules, state_unresolved = _state_formula_inventory(content)
    ledger_rules, ledger_unresolved, ledger_parameter_count = _finance_rule_inventory(content)
    (
        finance_initialization_rules,
        finance_initialization_formula_count,
        finance_initialization_parameter_count,
        finance_initialization_unresolved,
    ) = _finance_initialization_inventory(content, managed_sections)
    actions = content["default_actions"]
    action_ids = tuple(sorted(str(action["id"]) for action in actions))
    exclusive_choice_ids, exclusive_choice_unresolved = _action_choice_inventory(actions)
    actions_without_rules = tuple(
        sorted(str(action["id"]) for action in actions if not action.get("runtime_rules"))
    )
    action_unresolved = [
        (
            f"{action_id}: no runtime probability rule, routine step, or "
            "decision-tree branch selects this event in the shipped default run"
        )
        for action_id in actions_without_rules
    ]
    action_unresolved.extend(exclusive_choice_unresolved)
    cash_actions = tuple(
        sorted(
            str(action["id"])
            for action in actions
            if any(
                _cash_flow_is_configured(value)
                for name, value in action.get("cash_flow", {}).items()
                if name != "basis"
            )
        )
    )
    cash_parameters = sum(
        _cash_flow_is_configured(value)
        for action in actions
        for name, value in action.get("cash_flow", {}).items()
        if name != "basis"
    )
    decision_registry = content["decision_trees"]
    decision_trees = decision_registry["trees"]
    represented = tuple(country.country_code for country in countries)
    global_tree = any(not tree.get("place_ids") for tree in decision_trees)
    decision_places = {
        str(place)
        for tree in decision_trees
        for place in tree.get("place_ids", [])
        if str(place) in represented
    }
    covered = set(represented) if global_tree else decision_places
    uncovered = tuple(sorted(set(represented) - covered))
    decision_ids = tuple(sorted(str(tree["id"]) for tree in decision_trees))
    decision_edge_count = sum(
        len(module.get("edges", [])) for module in decision_registry["modules"]
    )
    decision_runtime_text = decision_compiler.read_text(encoding="utf-8")
    has_runtime_baseline = "def _baseline_module" in decision_runtime_text
    interaction_trees = content["interaction_trees"]
    interaction_program = content.get("interaction_program", {})
    interaction_rules = interaction_program.get("rules", [])
    relationship_evidence = interaction_program.get("relationship_evidence", [])
    interaction_ids = tuple(
        sorted(
            [str(tree["id"]) for tree in interaction_trees]
            + [f"rule:{rule['id']}" for rule in interaction_rules]
            + [
                f"relationship:{relationship['kind']}"
                for relationship in relationship_evidence
            ]
        )
    )
    interaction_transitions = sum(len(tree["transitions"]) for tree in interaction_trees)
    manifest_relationships = [
        relationship
        for agent in content["initial_population"]["population"]["agents"]
        for relationship in agent.get("relationships", [])
    ]
    registered_relationship_evidence = {
        str(relationship["provenance"]["evidence_id"])
        for relationship in relationship_evidence
    }
    unresolved_relationships = sorted(
        {
            str(relationship.get("evidence_id") or "missing-evidence-id")
            for relationship in manifest_relationships
            if relationship.get("evidence_id") not in registered_relationship_evidence
        }
    )
    interaction_unresolved = []
    if interaction_program.get("status") != "confirmed":
        interaction_unresolved.append("the shipped interaction program is not confirmed")
    if not interaction_rules:
        interaction_unresolved.append("the shipped interaction program contains no rules")
    if not manifest_relationships:
        interaction_unresolved.append("the shipped population contains no relationship edges")
    interaction_unresolved.extend(
        f"relationship evidence is not registered: {item}"
        for item in unresolved_relationships
    )
    items = (
        DslSourceOfTruthItem(
            domain="state_formulas",
            status="mixed" if state_unresolved else "dsl_defined",
            dsl_definition_ids=tuple(state_formulas + state_runtime_rules),
            dsl_formula_count=len(state_formulas) + len(state_runtime_rules),
            executable_parameter_count=len(state_runtime_rules),
            runtime_files=(
                _relative_runtime_path(state_compiler),
                _relative_runtime_path(rust_state_finance),
            ),
            runtime_symbols=("_state_rules", "advance_state_columns"),
            outside_dsl_behaviors=(),
            unresolved_items=tuple(state_unresolved),
        ),
        DslSourceOfTruthItem(
            domain="finance_initialization",
            status=(
                "mixed" if finance_initialization_unresolved else "dsl_defined"
            ),
            dsl_definition_ids=tuple(finance_initialization_rules),
            dsl_formula_count=finance_initialization_formula_count,
            executable_parameter_count=finance_initialization_parameter_count,
            runtime_files=(
                _relative_runtime_path(finance_interpreter),
                _relative_runtime_path(finance_runtime),
                _relative_runtime_path(canada_finance_runtime),
            ),
            runtime_symbols=(
                "FinanceInitializationCatalog",
                "evaluate_finance_initialization",
            ),
            outside_dsl_behaviors=(),
            unresolved_items=tuple(finance_initialization_unresolved),
        ),
        DslSourceOfTruthItem(
            domain="finance_tick_accounting",
            status="mixed" if ledger_unresolved else "dsl_defined",
            dsl_definition_ids=tuple(
                ledger_rules + [f"cash_flow:{action_id}" for action_id in cash_actions]
            ),
            dsl_formula_count=len(ledger_rules) + cash_parameters,
            executable_parameter_count=ledger_parameter_count + cash_parameters,
            runtime_files=(
                _relative_runtime_path(state_compiler),
                _relative_runtime_path(rust_state_finance),
            ),
            runtime_symbols=("_finance_rules", "advance_finance_columns"),
            outside_dsl_behaviors=(),
            unresolved_items=tuple(ledger_unresolved),
        ),
        DslSourceOfTruthItem(
            domain="action_formulas",
            status="mixed" if action_unresolved else "dsl_defined",
            dsl_definition_ids=tuple((*action_ids, *exclusive_choice_ids)),
            dsl_formula_count=sum(bool(action.get("formula")) for action in actions),
            executable_parameter_count=sum(
                len(action.get("runtime_rules", [])) for action in actions
            ),
            runtime_files=(
                _relative_runtime_path(state_compiler),
                _relative_runtime_path(rust_runtime),
            ),
            runtime_symbols=(
                "_meaningful_actions",
                "_event_payload",
                "evaluate_meaningful_actions",
                "evaluate_exclusive_action_group",
                "apply_state_dynamics",
            ),
            outside_dsl_behaviors=(),
            unresolved_items=tuple(action_unresolved),
        ),
        DslSourceOfTruthItem(
            domain="decision_programs",
            status="mixed" if uncovered else "dsl_defined",
            dsl_definition_ids=decision_ids,
            dsl_formula_count=decision_edge_count,
            executable_parameter_count=sum(
                len(item.get("coefficients", {}))
                for item in content["coefficient_registry"]["defaults"]
            ),
            runtime_files=(_relative_runtime_path(decision_compiler),),
            runtime_symbols=(
                ("compile_runtime_decisions", "_baseline_module")
                if has_runtime_baseline
                else ("compile_runtime_decisions",)
            ),
            outside_dsl_behaviors=(
                (
                    "_baseline_module synthesizes a probability-1 self-loop for agents "
                    "outside the confirmed tree scope"
                ),
            )
            if uncovered and has_runtime_baseline
            else (),
            unresolved_items=tuple(
                f"{country_code}: no confirmed shipped decision tree" for country_code in uncovered
            ),
        ),
        DslSourceOfTruthItem(
            domain="interactions",
            status="mixed" if interaction_unresolved else "dsl_defined",
            dsl_definition_ids=interaction_ids,
            dsl_formula_count=interaction_transitions + len(interaction_rules),
            executable_parameter_count=(
                interaction_transitions + _interaction_parameter_count(interaction_program)
            ),
            runtime_files=(
                _relative_runtime_path(
                    repository / "backend/petraterrium/simulation/run_preparation.py"
                ),
                _relative_runtime_path(rust_runtime),
            ),
            runtime_symbols=(
                "_interaction_payload",
                "run_interactions",
            ),
            outside_dsl_behaviors=(),
            unresolved_items=tuple(interaction_unresolved),
        ),
    )
    return DslSourceOfTruthAudit(
        result=(
            "complete" if all(item.status == "dsl_defined" for item in items) else "incomplete"
        ),
        represented_country_codes=represented,
        decision_tree_country_codes=tuple(sorted(covered)),
        decision_tree_uncovered_country_codes=uncovered,
        items=items,
    )


def _missing_register_audit(text: str) -> MissingRegisterAudit:
    requirements = {
        "country_feature_imputations": "Direct country evidence for every global-demo feature",
        "individual_finance_microdata": "Linked individual finance data outside Canada",
        "fitted_action_coefficients": "Fitted daily action and state-transition coefficients",
        "specialization_joint_data": "qualification, age, and sex joints",
        "local_language_search_logs": "local-language search",
        "local_currency_and_cost_of_living": "local currency",
        "cross_country_interaction_proof": "cross-country interaction",
        "global_and_place_distribution_comparison": "distribution comparison",
        "dsl_single_source": "DSL single source",
    }
    found = tuple(sorted(key for key, phrase in requirements.items() if phrase in text))
    absent = tuple(sorted(set(requirements) - set(found)))
    return MissingRegisterAudit(entries_found=found, entries_absent=absent)


def _findings(
    countries: tuple[CountrySourceAudit, ...],
    searches: tuple[LocalLanguageSearchAudit, ...],
    evidence: EvidenceInventory,
    specialization: SpecializationEvidenceAudit,
    dsl: DslSourceOfTruthAudit,
    missing: MissingRegisterAudit,
    region_counts: dict[str, int],
) -> tuple[AuditFinding, ...]:
    country_codes = tuple(country.country_code for country in countries)
    leakage = tuple(
        country.country_code
        for country in countries
        if any(field.canadian_source_leakage for field in country.fields.values())
    )
    foreign_sources = tuple(
        country.country_code
        for country in countries
        if any(field.foreign_country_source for field in country.fields.values())
    )
    regional = tuple(
        country.country_code
        for country in countries
        if any(
            field.geographic_scope in {"regional_imputed", "mixed"}
            for field in country.fields.values()
        )
    )
    measurement_risk = tuple(
        country.country_code
        for country in countries
        if any(
            field.geographic_scope == "own_country_source"
            and set(field.source_statuses) != {"present"}
            for field in country.fields.values()
        )
    )
    non_local_currency = tuple(
        country.country_code
        for country in countries
        if country.finance_currency in {"PPP", "unknown"}
    )
    incomplete_searches = tuple(
        search.country_code for search in searches if search.status == "incomplete"
    )
    dsl_items = {item.domain: item for item in dsl.items}
    findings = [
        AuditFinding(
            finding_id="global_population",
            status="pass"
            if len(countries) > 1 and sum(value > 0 for value in region_counts.values()) > 1
            else "gap",
            summary=(
                f"The shipped population contains {len(countries)} countries and "
                f"{sum(value > 0 for value in region_counts.values())} populated canonical regions."
            ),
            affected_countries=country_codes,
        ),
        AuditFinding(
            finding_id="canadian_source_leakage",
            status="gap" if leakage else "pass",
            summary=(
                "Canadian provenance appears on non-Canadian agents."
                if leakage
                else "No non-Canadian agent field names a Canadian source."
            ),
            affected_countries=leakage,
        ),
        AuditFinding(
            finding_id="foreign_country_source_place",
            status="gap" if foreign_sources else "pass",
            summary=(
                "At least one source place conflicts with its country or canonical region."
                if foreign_sources
                else (
                    "Every audited source place matches its own country or labelled "
                    "canonical region."
                )
            ),
            affected_countries=foreign_sources,
        ),
        AuditFinding(
            finding_id="regional_imputations",
            status="gap" if regional else "pass",
            summary="Some major fields use labelled regional archetypes.",
            affected_countries=regional,
            logged_in_missing="country_feature_imputations" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="individual_finance_imputation",
            status="gap",
            summary=(
                "All initial person-level money, income, expenses, savings, and debt "
                "values are synthetic imputations."
            ),
            affected_countries=country_codes,
            affected_fields=("finance",),
            logged_in_missing="individual_finance_microdata" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="specialization_evidence",
            status="gap" if specialization.unknown_country_codes else "pass",
            summary=(
                (
                    f"Specialization lacks executable own-country provenance in "
                    f"{len(specialization.unknown_country_codes)} represented countries."
                )
                if specialization.unknown_country_codes
                else (
                    f"{specialization.status_counts.get('present', 0)} qualified agents "
                    "have a specialization sampled from an own-country measured or "
                    "estimated pipeline distribution; "
                    f"{specialization.status_counts.get('not_applicable', 0)} agents are "
                    "structurally not applicable below the education threshold."
                )
            ),
            affected_countries=specialization.unknown_country_codes,
            affected_fields=("specialization",),
            logged_in_missing="specialization_joint_data" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="specialization_threshold_status",
            status=(
                "risk" if specialization.threshold_status_mismatch_count else "pass"
            ),
            summary=(
                "Every specialization status matches the recorded education threshold."
                if not specialization.threshold_status_mismatch_count
                else (
                    f"{specialization.threshold_status_mismatch_count} specialization "
                    "statuses conflict with the recorded education threshold."
                )
            ),
            affected_countries=(
                specialization.unknown_country_codes
                if specialization.threshold_status_mismatch_count
                else ()
            ),
            affected_fields=("specialization",),
        ),
        AuditFinding(
            finding_id="local_currency_and_cost_of_living",
            status="gap",
            summary=(
                "PPP is a comparison unit, not local currency; explicit country price "
                "and cost-of-living evidence is absent."
            ),
            affected_countries=non_local_currency,
            affected_fields=("finance",),
            logged_in_missing="local_currency_and_cost_of_living" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="local_language_search_trace",
            status="gap" if incomplete_searches else "pass",
            summary=(
                "Item-level language, original title, translation, and discovery-source "
                "traces are incomplete."
            ),
            affected_countries=incomplete_searches,
            affected_fields=MAJOR_FIELDS,
            logged_in_missing="local_language_search_logs" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="country_measured_label_semantics",
            status="risk" if measurement_risk else "pass",
            summary=(
                "The raw country_measured label describes source geography for some "
                "estimated or imputed evidence; it must not be read as person-level "
                "measurement."
            ),
            affected_countries=measurement_risk,
        ),
        AuditFinding(
            finding_id="unknown_state_evidence",
            status="gap" if evidence.state_evidence_statuses.get("unknown", 0) else "pass",
            summary=(
                f"{evidence.state_evidence_statuses.get('unknown', 0)} state evidence links and "
                f"{evidence.relationship_evidence_statuses.get('unknown', 0)} relationship "
                "evidence links are explicitly unknown."
            ),
            logged_in_missing="fitted_action_coefficients" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="default_action_search_trace",
            status="gap" if evidence.default_actions_without_source_ids else "pass",
            summary=(
                f"{len(evidence.default_actions_without_source_ids)} default action "
                "definitions use stated reasons but no source IDs or per-place search logs."
            ),
            affected_fields=evidence.default_actions_without_source_ids,
            logged_in_missing="fitted_action_coefficients" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="numeric_unknown_evidence",
            status="risk" if evidence.numeric_coefficients_with_unknown_evidence else "pass",
            summary=(
                f"{len(evidence.numeric_coefficients_with_unknown_evidence)} numeric state "
                "coefficient is attached to evidence marked unknown."
            ),
            affected_fields=evidence.numeric_coefficients_with_unknown_evidence,
        ),
        AuditFinding(
            finding_id="cross_country_interaction_acceptance",
            status="gap",
            summary=(
                "The static default manifest does not contain a receipt proving an "
                "interaction between agents from different countries."
            ),
            affected_countries=country_codes,
            logged_in_missing="cross_country_interaction_proof" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="distribution_comparison_acceptance",
            status="gap",
            summary=(
                "The static default manifest does not store the required global versus "
                "country and region distribution comparison receipt."
            ),
            affected_countries=country_codes,
            logged_in_missing="global_and_place_distribution_comparison" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_state_formulas",
            status=(
                "pass"
                if next(item for item in dsl.items if item.domain == "state_formulas").status
                == "dsl_defined"
                else "gap"
            ),
            summary=(
                "Every shipped agent-state definition has a DSL-owned executable runtime "
                "rule; unfitted hypotheses remain visible as evidence gaps."
                if dsl_items["state_formulas"].status == "dsl_defined"
                else "At least one shipped agent state lacks a complete DSL runtime rule."
            ),
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_finance_initialization",
            status=(
                "pass"
                if next(
                    item for item in dsl.items if item.domain == "finance_initialization"
                ).status
                == "dsl_defined"
                else "gap"
            ),
            summary=(
                "The shipped manifest contains validated Canada and global finance "
                "initialization programs whose formulas are executed by the shared "
                "finance expression interpreter."
                if dsl_items["finance_initialization"].status == "dsl_defined"
                else (
                    "At least one finance initialization program is absent, invalid, "
                    "or outside the managed DSL manifest."
                )
            ),
            affected_fields=("finance",),
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_finance_tick_accounting",
            status=(
                "pass"
                if dsl_items["finance_tick_accounting"].status == "dsl_defined"
                else "gap"
            ),
            summary=(
                "All five finance ledgers and action cash-flow formulas are DSL-owned and "
                "executed by a generic weighted-input interpreter."
                if dsl_items["finance_tick_accounting"].status == "dsl_defined"
                else "At least one finance ledger lacks a complete DSL accounting rule."
            ),
            affected_fields=("finance",),
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_action_formulas",
            status=(
                "pass"
                if next(item for item in dsl.items if item.domain == "action_formulas").status
                == "dsl_defined"
                else "gap"
            ),
            summary=(
                "Every shipped action has an executable DSL selection rule; eat_lunch and "
                "skip_lunch are validated complementary branches of the exclusive "
                "midday_meal categorical choice."
                if dsl_items["action_formulas"].status == "dsl_defined"
                else "At least one shipped action or exclusive choice is not executable."
            ),
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_decision_programs",
            status="gap" if dsl.decision_tree_uncovered_country_codes else "pass",
            summary=(
                "The confirmed shipped decision tree has global place scope."
                if not dsl.decision_tree_uncovered_country_codes
                else (
                    (
                        "The confirmed shipped decision tree is not global; uncovered "
                        "countries receive a runtime-synthesized baseline self-loop."
                    )
                    if dsl_items["decision_programs"].outside_dsl_behaviors
                    else (
                        "The confirmed shipped decision tree is not global; uncovered "
                        "countries are blocked because they have no applicable tree."
                    )
                )
            ),
            affected_countries=dsl.decision_tree_uncovered_country_codes,
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="dsl_single_source_interactions",
            status=(
                "pass"
                if next(item for item in dsl.items if item.domain == "interactions").status
                == "dsl_defined"
                else "gap"
            ),
            summary=(
                "The shipped DSL contains the interaction outcome tree, confirmed rule, "
                "numeric factors, relationship evidence, and seeded relationship edges."
                if dsl_items["interactions"].status == "dsl_defined"
                else (
                    "At least one interaction rule, factor, evidence record, or relationship "
                    "edge is absent or unresolved in the shipped DSL."
                )
            ),
            logged_in_missing="dsl_single_source" in missing.entries_found,
        ),
        AuditFinding(
            finding_id="missing_register_completeness",
            status="gap" if missing.entries_absent else "pass",
            summary=(
                f"MISSING.md omits {len(missing.entries_absent)} Prompt 1 source or "
                "demo-acceptance gaps."
            ),
            affected_fields=missing.entries_absent,
        ),
    ]
    return tuple(findings)


def audit_prompt1_sources(
    manifest_path: Path | None = None,
    finance_pack_path: Path | None = None,
    missing_path: Path | None = None,
) -> Prompt1SourceAudit:
    manifest_file = (manifest_path or default_manifest_path()).resolve()
    finance_file = (finance_pack_path or default_finance_pack_path()).resolve()
    missing_file = (missing_path or default_missing_path()).resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    json.loads(finance_file.read_text(encoding="utf-8"))
    missing_text = missing_file.read_text(encoding="utf-8")
    content = manifest["content"]
    agents = content["initial_population"]["population"]["agents"]
    specialization_pipeline = content.get("specialization_pipeline")
    countries = _country_audits(agents, specialization_pipeline)
    searches = _local_language_audits(
        countries,
        agents,
        specialization_pipeline,
    )
    evidence = _evidence_inventory(content)
    specialization = _specialization_evidence_audit(agents)
    dsl = _dsl_source_of_truth_audit(
        content,
        countries,
        tuple(str(section) for section in manifest["managed_sections"]),
    )
    missing = _missing_register_audit(missing_text)
    country_counts = dict(sorted(Counter(str(agent["place"]) for agent in agents).items()))
    observed_regions = Counter(str(agent["traits"]["region"]) for agent in agents)
    region_counts = {region: observed_regions.get(region, 0) for region in CANONICAL_REGIONS}
    findings = _findings(
        countries,
        searches,
        evidence,
        specialization,
        dsl,
        missing,
        region_counts,
    )
    result = (
        "failed"
        if any(
            finding.status == "gap"
            and finding.finding_id
            in {"global_population", "canadian_source_leakage", "foreign_country_source_place"}
            for finding in findings
        )
        else "incomplete"
        if any(finding.status != "pass" for finding in findings)
        else "complete"
    )
    return Prompt1SourceAudit(
        schema_version=AUDIT_SCHEMA_VERSION,
        audit_scope=(
            "Static audit of the checked-in Prompt 1 default manifest, finance pack, "
            "and gap register."
        ),
        verification_boundary=(
            "Metadata consistency only; source URLs, publications, and empirical claims "
            "were not independently re-researched or network-verified."
        ),
        result=result,
        artifacts={
            "default_manifest": _artifact_receipt(manifest_file),
            "finance_pack": _artifact_receipt(finance_file),
            "missing_register": _artifact_receipt(missing_file),
            "finance_population_builder": _artifact_receipt(
                _repository_root() / "backend/petraterrium/simulation/global_finance.py"
            ),
            "finance_initialization_interpreter": _artifact_receipt(
                _repository_root()
                / "backend/petraterrium/simulation/finance_initialization.py"
            ),
            "decision_runtime": _artifact_receipt(
                _repository_root() / "backend/petraterrium/simulation/runtime_decision_compiler.py"
            ),
            "rust_agent_runtime": _artifact_receipt(
                _repository_root() / "engine-rust/src/agents.rs"
            ),
            "interaction_default_generator": _artifact_receipt(
                _repository_root() / "backend/petraterrium/simulation/global_demo_interactions.py"
            ),
        },
        dsl_version=str(manifest["dsl_version"]),
        dsl_content_hash=str(manifest["content_hash"]),
        total_agents=len(agents),
        country_agent_counts=country_counts,
        region_agent_counts=region_counts,
        countries=countries,
        source_inventory=_source_inventory(content["default_sources"]),
        local_language_search=searches,
        evidence_inventory=evidence,
        specialization_evidence=specialization,
        dsl_source_of_truth=dsl,
        missing_register=missing,
        findings=findings,
    )


def main() -> None:
    print(audit_prompt1_sources().model_dump_json(indent=2))


if __name__ == "__main__":
    main()
