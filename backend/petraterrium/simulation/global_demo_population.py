import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field

from ..atlas.feature_dump.priority_features import PACK_VERSION, PRIORITY_COUNTRY_CODES
from ..atlas.features import canonical_feature_registry
from ..atlas.regions import CANONICAL_REGIONS, country_region
from ..dsl import FeatureDistribution
from ..population import AgentRecord, PopulationTable
from .specialization import (
    CountrySpecializationDistribution,
    SpecializationCatalog,
    load_specialization_catalog,
    sample_specialization,
)

GLOBAL_DEMO_COUNTRIES = (*PRIORITY_COUNTRY_CODES, "CA", "AU")
GLOBAL_DEMO_POPULATION_ID = "global-default-demo"
GLOBAL_DEMO_VERSION = "global-default-demo-v1"
WPP_SOURCE_ID = "un_wpp_2024_countries"
EvidenceScope = Literal["country_measured", "regional_imputed", "estimated"]
MajorField = Literal[
    "age",
    "sex",
    "education",
    "specialization",
    "occupation",
    "personality",
    "values",
    "finance",
    "money",
    "income",
    "expenses",
    "savings",
    "debt",
    "wages",
    "prices",
    "costs",
    "currency",
]
PERSONALITY_FEATURES = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)
VALUE_FEATURES = (
    "ideology_economic",
    "ideology_state",
    "ideology_cultural",
    "generalized_trust",
    "religiosity",
    "risk_aversion",
    "time_preference",
    "schwartz_values",
)
FINANCE_COMPONENTS = (
    "money",
    "income",
    "expenses",
    "savings",
    "debt",
    "wages",
    "prices",
    "costs",
    "currency",
)
FIELD_SCOPE_TRAITS = {
    "age": "age_evidence_scope",
    "sex": "sex_evidence_scope",
    "education": "education_evidence_scope",
    "specialization": "specialization_evidence_scope",
    "occupation": "occupation_evidence_scope",
    "personality": "personality_evidence_scope",
    "values": "values_evidence_scope",
    "finance": "finance_evidence_scope",
    **{
        component: f"finance_{component}_evidence_scope"
        for component in FINANCE_COMPONENTS
    },
}
LOCAL_CURRENCY_PLACEHOLDERS = {
    "ppp",
    "current international dollar",
    "current international dollars",
    "current international dollars (ppp)",
    "unknown",
}
CANADIAN_SOURCE_MARKERS = (
    "statistics canada",
    "statistique canada",
    "statscan",
)
ISCED_YEARS = {
    "0": 0,
    "1": 6,
    "2": 9,
    "3": 12,
    "4": 13,
    "5": 14,
    "6": 16,
    "7": 18,
    "8": 21,
    "unknown": 0,
}


class GlobalDemoModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GlobalAgentProfile(GlobalDemoModel):
    agent_id: str
    index: int = Field(ge=0)
    seed: int
    country_code: str = Field(min_length=2, max_length=2)
    country_name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    country_population: int = Field(gt=0)
    country_population_share: float = Field(gt=0, le=1)
    country_allocation_agents: int = Field(gt=0)
    representative_population_weight: float = Field(gt=0)
    age: int = Field(ge=0, le=100)
    sex: str = Field(min_length=1)
    education_isced: str = Field(min_length=1)
    occupation_isco: str = Field(min_length=1)


class GlobalFinanceAssignment(GlobalDemoModel):
    evidence_scope: EvidenceScope
    source_place: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_status: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_date: str | None = None
    source_population: str = "Synthetic agents represented by the source distribution"
    uncertainty: float = Field(ge=0, le=1)
    currency: str = Field(min_length=1)
    local_currency: str | None = None
    price_level_ratio: float | None = Field(default=None, gt=0)
    wage_per_workday: float | None = Field(default=None, ge=0)
    money: float
    annual_income: float
    annual_expenses: float = Field(ge=0)
    savings: float = Field(ge=0)
    debt: float = Field(ge=0)


class MajorFieldCoverage(GlobalDemoModel):
    country_measured: list[str]
    regional_imputed: list[str]
    estimated: list[str]
    agent_counts: dict[EvidenceScope, int]


class DistributionSlice(GlobalDemoModel):
    agent_count: int = Field(ge=1)
    represented_population: float = Field(gt=0)
    distribution_type: Literal["numeric", "categorical"]
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    exact_value_shares: dict[str, float] = Field(default_factory=dict)
    categories: dict[str, float] = Field(default_factory=dict)


class DistributionComparison(GlobalDemoModel):
    global_distribution: DistributionSlice
    country_distributions: dict[str, DistributionSlice]
    region_distributions: dict[str, DistributionSlice]


class GlobalDemoDeviation(GlobalDemoModel):
    id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    countries: list[str]
    status: Literal["regional_imputed", "imputed", "estimated", "default_estimated"]
    reason: str = Field(min_length=1)
    full_version_requires: str = Field(min_length=1)


class CrossCountryRelationshipSummary(GlobalDemoModel):
    relationship_count: int = Field(ge=0)
    linked_agent_count: int = Field(ge=0)
    countries: list[str]
    country_pairs: dict[str, int]


class GlobalDemoSummary(GlobalDemoModel):
    total_agents: int = Field(ge=0)
    country_agent_counts: dict[str, int]
    region_agent_counts: dict[str, int]
    major_fields: dict[MajorField, MajorFieldCoverage]
    distribution_comparisons: dict[str, DistributionComparison]
    cross_country_relationships: CrossCountryRelationshipSummary
    deviations: list[GlobalDemoDeviation]


class GlobalDemoPopulation(GlobalDemoModel):
    population: PopulationTable
    summary: GlobalDemoSummary


FinanceResolver = Callable[[GlobalAgentProfile], GlobalFinanceAssignment | None]
AgentEnricher = Callable[[AgentRecord, GlobalAgentProfile], AgentRecord]


def default_registry_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "registry_feature_dump"


def default_city_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "city_feature_dump"


@lru_cache(maxsize=4)
def _wpp_manifest(registry_directory: str) -> dict[str, Any]:
    return json.loads((Path(registry_directory) / "manifest.json").read_text())


@lru_cache(maxsize=4)
def _country_populations(registry_directory: str) -> dict[str, dict[str, Any]]:
    path = Path(registry_directory) / "wpp_country_population.parquet"
    return {
        str(row["country_code"]): row
        for row in pq.read_table(path).to_pylist()
    }


@lru_cache(maxsize=4)
def _country_age_sex(registry_directory: str) -> dict[str, tuple[dict[str, Any], ...]]:
    path = Path(registry_directory) / "wpp_country_age_sex.parquet"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pq.read_table(path).to_pylist():
        grouped[str(row["country_code"])].append(row)
    return {
        code: tuple(sorted(rows, key=lambda row: (str(row["age"]), str(row["sex"]))))
        for code, rows in grouped.items()
    }


@lru_cache(maxsize=4)
def _priority_distributions(
    registry_directory: str,
) -> dict[tuple[str, str, str], FeatureDistribution]:
    path = Path(registry_directory) / "priority_feature_distributions.parquet"
    distributions = (
        FeatureDistribution.model_validate_json(row["distribution_json"])
        for row in pq.read_table(path).to_pylist()
    )
    return {
        (distribution.feature_id, distribution.level, distribution.place): distribution
        for distribution in distributions
    }


@lru_cache(maxsize=4)
def _largest_cities(city_directory: str) -> dict[str, dict[str, Any]]:
    path = Path(city_directory) / "cities.parquet"
    columns = [
        "geonameid",
        "name",
        "latitude",
        "longitude",
        "country_code",
        "population",
    ]
    result: dict[str, dict[str, Any]] = {}
    for row in pq.read_table(path, columns=columns).to_pylist():
        code = str(row["country_code"])
        existing = result.get(code)
        if existing is None or int(row["population"] or 0) > int(existing["population"] or 0):
            result[code] = row
    return result


def allocate_country_agents(
    target_agents: int,
    country_codes: tuple[str, ...],
    populations: dict[str, int],
) -> dict[str, int]:
    if target_agents < len(country_codes):
        raise ValueError("The global demo needs at least one agent per target country")
    if missing := [code for code in country_codes if populations.get(code, 0) <= 0]:
        raise ValueError(f"Missing positive WPP populations for {missing}")
    total_population = sum(populations[code] for code in country_codes)
    quotas = {
        code: target_agents * populations[code] / total_population for code in country_codes
    }
    allocations = {code: max(1, math.floor(quotas[code])) for code in country_codes}
    while sum(allocations.values()) > target_agents:
        removable = [code for code in country_codes if allocations[code] > 1]
        if not removable:
            raise ValueError("Unable to satisfy the one-agent-per-country constraint")
        selected = min(
            removable,
            key=lambda code: (quotas[code] - math.floor(quotas[code]), populations[code]),
        )
        allocations[selected] -= 1
    remainder_order = sorted(
        country_codes,
        key=lambda code: (
            -(quotas[code] - math.floor(quotas[code])),
            country_codes.index(code),
        ),
    )
    for index in range(target_agents - sum(allocations.values())):
        allocations[remainder_order[index % len(remainder_order)]] += 1
    return allocations


def _stable_agent_id(seed: int, index: int) -> str:
    identity = f"{GLOBAL_DEMO_POPULATION_ID}:{GLOBAL_DEMO_VERSION}:{seed}:{index}"
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def _sample_age_sex(
    rows: tuple[dict[str, Any], ...],
    count: int,
    rng: np.random.Generator,
) -> list[tuple[int, str]]:
    weights = np.asarray([float(row["population"]) for row in rows], dtype=np.float64)
    weights /= weights.sum()
    selected = rng.choice(len(rows), size=count, replace=True, p=weights)
    return [
        (
            100 if str(rows[int(index)]["age"]) == "100+" else int(rows[int(index)]["age"]),
            str(rows[int(index)]["sex"]),
        )
        for index in selected
    ]


def _distribution_for_country(
    feature_id: str,
    country_code: str,
    region: str,
    distributions: dict[tuple[str, str, str], FeatureDistribution],
) -> FeatureDistribution | None:
    if country_code in PRIORITY_COUNTRY_CODES:
        direct = distributions.get((feature_id, "country", country_code))
        if direct is not None:
            return direct
    return distributions.get((feature_id, "region", region))


def _source_scope(
    distribution: FeatureDistribution | None,
    country_code: str,
) -> EvidenceScope:
    if distribution is None:
        return "estimated"
    if distribution.level == "country" and distribution.place == country_code:
        if distribution.method != "fallback":
            return "country_measured"
    return "regional_imputed"


def _source_place(
    distribution: FeatureDistribution | None,
    country_code: str,
    region: str,
) -> str:
    scope = _source_scope(distribution, country_code)
    if scope in {"country_measured", "estimated"}:
        return country_code
    return region


def _source_id(
    feature_id: str,
    distribution: FeatureDistribution | None,
    country_code: str,
    region: str,
) -> str:
    if distribution is None:
        return f"estimated:{feature_id}:{country_code}"
    place = _source_place(distribution, country_code, region)
    level = "country" if place == country_code else "region"
    return f"{PACK_VERSION}:{distribution.feature_id}:{level}:{place}"


def _feature_provenance(
    feature_id: str,
    distribution: FeatureDistribution | None,
    country_code: str,
    region: str,
) -> dict[str, Any]:
    if distribution is None:
        return {
            "evidence_scope": "estimated",
            "source_place": country_code,
            "source_id": f"estimated:{country_code}",
            "source_status": "estimated",
            "source": "Global demo explicit wide-uncertainty estimate",
            "source_version": GLOBAL_DEMO_VERSION,
            "uncertainty": 1.0,
            "sampling_status": "estimated_individual_draw",
            "joint_data_status": "estimated_independent",
        }
    return {
        "evidence_scope": _source_scope(distribution, country_code),
        "source_place": _source_place(distribution, country_code, region),
        "source_id": _source_id(feature_id, distribution, country_code, region),
        "source_status": distribution.provenance.status,
        "source": distribution.provenance.source,
        "source_version": distribution.provenance.version,
        "source_date": distribution.provenance.source_date,
        "uncertainty": distribution.provenance.uncertainty,
        "distribution_level": distribution.level,
        "coverage_percent": distribution.coverage_percent,
        "method": distribution.method,
        "sampling_status": "imputed_individual_draw",
        "joint_data_status": "missing",
    }


def _allowed_education_values(age: int) -> set[str]:
    if age < 5:
        return {"0"}
    if age < 12:
        return {"0", "1"}
    if age < 15:
        return {"0", "1", "2"}
    if age < 18:
        return {"0", "1", "2", "3"}
    if age < 21:
        return {"0", "1", "2", "3", "4", "5"}
    return set(ISCED_YEARS)


def _sample_categorical(
    distribution: FeatureDistribution,
    rng: np.random.Generator,
    allowed: set[str] | None = None,
) -> str:
    values = {
        str(label): float(probability)
        for label, probability in distribution.values.items()
        if probability > 0 and (allowed is None or str(label) in allowed)
    }
    if not values:
        if allowed:
            return min(allowed)
        raise ValueError(f"Distribution {distribution.feature_id} has no positive values")
    labels = sorted(values)
    probabilities = np.asarray([values[label] for label in labels], dtype=np.float64)
    probabilities /= probabilities.sum()
    return str(rng.choice(labels, p=probabilities))


def _sample_continuous(
    feature_id: str,
    distribution: FeatureDistribution,
    rng: np.random.Generator,
) -> float:
    mean = float(distribution.mean or 0)
    deviation = float(distribution.standard_deviation or 0)
    if feature_id == "income" and mean > 0 and deviation > 0:
        sigma_squared = math.log1p((deviation / mean) ** 2)
        value = rng.lognormal(math.log(mean) - sigma_squared / 2, math.sqrt(sigma_squared))
    else:
        value = mean if deviation <= 0 else rng.normal(mean, deviation)
    definition = next(
        feature
        for feature in canonical_feature_registry().definitions
        if feature.id == feature_id
    )
    if definition.value_range is not None:
        value = float(
            np.clip(value, definition.value_range.minimum, definition.value_range.maximum)
        )
    if feature_id == "household_size":
        return float(max(1, round(value)))
    return round(float(value), 6)


def _sample_feature(
    feature_id: str,
    distribution: FeatureDistribution,
    age: int,
    rng: np.random.Generator,
) -> str | float:
    if feature_id == "education_isced":
        return _sample_categorical(distribution, rng, _allowed_education_values(age))
    if feature_id == "occupation_isco" and (age < 15 or age > 80):
        return "not_applicable"
    if distribution.values:
        return _sample_categorical(distribution, rng)
    return _sample_continuous(feature_id, distribution, rng)


def _group_scope(
    distributions: list[FeatureDistribution | None],
    country_code: str,
) -> EvidenceScope:
    scopes = {_source_scope(distribution, country_code) for distribution in distributions}
    if "estimated" in scopes:
        return "estimated"
    if "regional_imputed" in scopes:
        return "regional_imputed"
    return "country_measured"


def _group_traits(
    field: str,
    feature_ids: tuple[str, ...],
    feature_sources: dict[str, FeatureDistribution | None],
    country_code: str,
    region: str,
) -> dict[str, Any]:
    selected = [feature_sources[feature_id] for feature_id in feature_ids]
    scope = _group_scope(selected, country_code)
    source_place = (
        country_code
        if scope == "country_measured"
        else region
        if scope == "regional_imputed"
        else country_code
    )
    records = [
        _feature_provenance(feature_id, distribution, country_code, region)
        for feature_id, distribution in zip(feature_ids, selected, strict=True)
    ]
    statuses = sorted({str(record["source_status"]) for record in records})
    return {
        f"{field}_evidence_scope": scope,
        f"{field}_source_place": source_place,
        f"{field}_source_id": f"{PACK_VERSION}:{field}:{source_place}",
        f"{field}_source_status": statuses[0] if len(statuses) == 1 else "mixed",
        f"{field}_source_ids": [str(record["source_id"]) for record in records],
        f"{field}_sampling_status": "imputed_individual_draw",
    }


def _wpp_traits(
    country_code: str,
    country_name: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    wpp = manifest["wpp"]
    source_id = f"{WPP_SOURCE_ID}:{country_code}:{wpp['estimate_year']}"
    common = {
        "evidence_scope": "country_measured",
        "source_place": country_code,
        "source_id": source_id,
        "source_status": "present",
        "source": wpp["source"],
        "source_version": wpp["version"],
        "source_date": wpp["published_date"],
        "source_population": f"{country_name} de facto population in {wpp['estimate_year']}",
        "sampling_status": "imputed_individual_draw",
        "joint_data_status": "measured_age_sex_joint",
    }
    traits: dict[str, Any] = {}
    for field in ("age", "sex"):
        for key, value in common.items():
            traits[f"{field}_{key}"] = value
    return traits


def _is_local_currency(currency: str) -> bool:
    return currency.strip().casefold() not in LOCAL_CURRENCY_PLACEHOLDERS


def _finance_component_traits(
    assignment: GlobalFinanceAssignment,
    profile: GlobalAgentProfile,
) -> dict[str, Any]:
    traits: dict[str, Any] = {}
    component_status = (
        "estimated" if assignment.evidence_scope == "estimated" else "imputed"
    )
    sourced_components = ("money", "income", "expenses", "savings", "debt", "costs")
    for component in sourced_components:
        traits.update(
            {
                f"finance_{component}_evidence_scope": assignment.evidence_scope,
                f"finance_{component}_source_place": assignment.source_place,
                f"finance_{component}_source_id": assignment.source_id,
                f"finance_{component}_source_status": assignment.source_status,
                f"finance_{component}_status": component_status,
            }
        )
    derived_components = {
        "wages": (
            f"{assignment.source_id}:wage-per-workday",
            "Annual income divided across 260 workdays",
        ),
        "prices": (
            f"{assignment.source_id}:price-level-ratio",
            "National PPP conversion factor divided by official exchange rate",
        ),
    }
    for component, (source_id, method) in derived_components.items():
        traits.update(
            {
                f"finance_{component}_evidence_scope": "estimated",
                f"finance_{component}_source_place": assignment.source_place,
                f"finance_{component}_source_id": source_id,
                f"finance_{component}_source_status": "estimated",
                f"finance_{component}_status": "estimated",
                f"finance_{component}_method": method,
            }
        )
    local_currency = assignment.local_currency or assignment.currency
    currency_scope: EvidenceScope = (
        assignment.evidence_scope
        if _is_local_currency(local_currency)
        else "estimated"
    )
    traits.update(
        {
            "finance_currency_evidence_scope": currency_scope,
            "finance_currency_source_place": assignment.source_place,
            "finance_currency_source_id": assignment.source_id,
            "finance_currency_source_status": (
                assignment.source_status
                if currency_scope != "estimated"
                else "estimated"
            ),
            "finance_currency_status": (
                "present" if currency_scope != "estimated" else "estimated"
            ),
            "finance_local_currency": local_currency,
            "finance_accounting_unit": assignment.currency,
        }
    )
    return traits


def _validate_finance_source(
    assignment: GlobalFinanceAssignment,
    profile: GlobalAgentProfile,
) -> None:
    if assignment.evidence_scope == "country_measured":
        allowed = {profile.country_code.casefold(), profile.country_name.casefold()}
        if assignment.source_place.casefold() not in allowed:
            raise ValueError(
                f"Finance source {assignment.source_place!r} does not match "
                f"agent country {profile.country_code}"
            )
    if (
        assignment.evidence_scope == "regional_imputed"
        and assignment.source_place != profile.region
    ):
        raise ValueError(
            f"Regional finance source {assignment.source_place!r} does not match "
            f"agent region {profile.region!r}"
        )
    if assignment.evidence_scope == "estimated" and assignment.source_place not in {
        profile.country_code,
        profile.country_name,
        profile.region,
    }:
        raise ValueError(
            f"Estimated finance source {assignment.source_place!r} does not describe "
            f"agent country {profile.country_code} or region {profile.region!r}"
        )
    source_text = " ".join(
        (assignment.source, assignment.source_id, assignment.source_place)
    ).casefold()
    if profile.country_code != "CA" and any(
        marker in source_text for marker in CANADIAN_SOURCE_MARKERS
    ):
        raise ValueError(
            f"Canadian finance source cannot be assigned to agent country "
            f"{profile.country_code}"
        )


def _apply_finance(
    agent: AgentRecord,
    profile: GlobalAgentProfile,
    assignment: GlobalFinanceAssignment,
) -> AgentRecord:
    _validate_finance_source(assignment, profile)
    traits = {
        **agent.traits,
        **_finance_component_traits(assignment, profile),
        "finance_evidence_scope": assignment.evidence_scope,
        "finance_source_place": assignment.source_place,
        "finance_source_id": assignment.source_id,
        "finance_source_status": assignment.source_status,
        "finance_status": (
            "estimated" if assignment.evidence_scope == "estimated" else "imputed"
        ),
        "finance_source": assignment.source,
        "finance_source_version": assignment.source_version,
        "finance_source_date": assignment.source_date,
        "finance_source_population": assignment.source_population,
        "finance_uncertainty": assignment.uncertainty,
        "finance_currency": assignment.currency,
        "finance_local_currency": assignment.local_currency or assignment.currency,
        "finance_price_level_ratio": assignment.price_level_ratio or 1.0,
        "finance_wage_per_workday": (
            assignment.wage_per_workday
            if assignment.wage_per_workday is not None
            else assignment.annual_income / 260
        ),
        "finance_annual_income": assignment.annual_income,
        "finance_annual_expenses": assignment.annual_expenses,
        "finance_sampling_status": "imputed_individual_draw",
    }
    states = {
        **agent.states,
        "finance.money": str(assignment.money),
        "finance.income": "0.0",
        "finance.expenses": "0.0",
        "finance.annual_income": str(assignment.annual_income),
        "finance.annual_expenses": str(assignment.annual_expenses),
        "finance.savings": str(assignment.savings),
        "finance.debt": str(assignment.debt),
    }
    return agent.model_copy(update={"traits": traits, "states": states})


def _specialization_traits(
    country: CountrySpecializationDistribution,
    years_of_education: int,
    threshold_years: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    evidence_scope: EvidenceScope = (
        "country_measured" if country.evidence_status == "measured" else "estimated"
    )
    applicable = years_of_education >= threshold_years
    code, label = sample_specialization(country, rng) if applicable else (None, None)
    source_titles = " · ".join(
        dict.fromkeys(source.english_title for source in country.primary_sources)
    )
    return {
        "specialization": code,
        "specialization_label": label,
        "specialization_status": "present" if applicable else "not_applicable",
        "specialization_evidence_scope": evidence_scope,
        "specialization_source_place": country.country_code,
        "specialization_source_id": country.pipeline_attempt_id,
        "specialization_source_status": country.evidence_status,
        "specialization_source_evidence_status": country.source_evidence_status,
        "specialization_source": source_titles,
        "specialization_source_version": country.version,
        "specialization_source_date": str(country.reference_year),
        "specialization_source_population": country.population_basis,
        "specialization_uncertainty": country.uncertainty,
        "specialization_reasoning": country.reasoning,
        "specialization_mapping": country.mapping_notes,
        "specialization_licence": country.licence,
        "specialization_draft_status": country.draft_status,
        "specialization_pipeline_attempt_id": country.pipeline_attempt_id,
        "specialization_search_log_count": len(country.sources_tried),
        "specialization_sampling_status": "imputed_individual_draw",
    }


def _agent(
    profile: GlobalAgentProfile,
    city: dict[str, Any],
    feature_sources: dict[str, FeatureDistribution | None],
    specialization_distribution: CountrySpecializationDistribution,
    manifest: dict[str, Any],
    rng: np.random.Generator,
) -> AgentRecord:
    feature_provenance = {
        feature_id: _feature_provenance(
            feature_id,
            distribution,
            profile.country_code,
            profile.region,
        )
        for feature_id, distribution in feature_sources.items()
    }
    sampled = {
        feature_id: _sample_feature(feature_id, distribution, profile.age, rng)
        for feature_id, distribution in feature_sources.items()
        if distribution is not None
        and feature_id not in {"education_isced", "occupation_isco"}
    }
    sampled["education_isced"] = profile.education_isced
    sampled["occupation_isco"] = profile.occupation_isco
    education = str(sampled.get("education_isced", "unknown"))
    occupation = str(sampled.get("occupation_isco", "unknown"))
    years_of_education = min(
        ISCED_YEARS.get(education, 0),
        max(0, profile.age - 5),
    )
    specialization_threshold_years = 12
    specialization_traits = _specialization_traits(
        specialization_distribution,
        years_of_education,
        specialization_threshold_years,
        rng,
    )
    education_provenance = feature_provenance["education_isced"]
    occupation_provenance = feature_provenance["occupation_isco"]
    household_id = hashlib.sha256(f"household:{profile.agent_id}".encode()).hexdigest()[:20]
    traits: dict[str, Any] = {
        **sampled,
        **_wpp_traits(profile.country_code, profile.country_name, manifest),
        **_group_traits(
            "personality",
            PERSONALITY_FEATURES,
            feature_sources,
            profile.country_code,
            profile.region,
        ),
        **_group_traits(
            "values",
            VALUE_FEATURES,
            feature_sources,
            profile.country_code,
            profile.region,
        ),
        **specialization_traits,
        "age": profile.age,
        "sex": profile.sex,
        "country": profile.country_name,
        "country_id": profile.country_code,
        "region": profile.region,
        "city": str(city["name"]),
        "city_id": str(city["geonameid"]),
        "country_population": profile.country_population,
        "country_population_share": profile.country_population_share,
        "country_allocation_agents": profile.country_allocation_agents,
        "representative_population_weight": profile.representative_population_weight,
        "population_source_id": WPP_SOURCE_ID,
        "population_source_status": "present",
        "population_allocation_method": "constrained_hamilton",
        "agent_type": "person",
        "agent_types": ["person"],
        "education_isced": education,
        "years_of_education": years_of_education,
        "occupation_isco": occupation,
        "household_id": household_id,
        "family_status": "estimated_single_household",
        "family_relationships": {},
        "feature_provenance": feature_provenance,
        "education_evidence_scope": education_provenance["evidence_scope"],
        "education_source_place": education_provenance["source_place"],
        "education_source_id": education_provenance["source_id"],
        "education_source_status": education_provenance["source_status"],
        "education_status": "imputed",
        "education_source": education_provenance.get(
            "source", "No imported country education mapping"
        ),
        "education_mapping_version": education_provenance.get(
            "source_version", "unavailable"
        ),
        "education_source_date": education_provenance.get("source_date"),
        "education_source_population": (
            feature_sources["education_isced"].population
            if feature_sources["education_isced"] is not None
            else "No represented population"
        ),
        "education_uncertainty": education_provenance.get("uncertainty", 1),
        "education_default_reason": (
            "Synthetic age-constrained draw from a place marginal; no person-level "
            "age-by-education joint distribution is present"
        ),
        "specialization_threshold_years": specialization_threshold_years,
        "occupation_evidence_scope": occupation_provenance["evidence_scope"],
        "occupation_source_place": occupation_provenance["source_place"],
        "occupation_source_id": occupation_provenance["source_id"],
        "occupation_source_status": occupation_provenance["source_status"],
        "mbti_usage": "label_only",
    }
    log_tier: Literal["spotlight", "sampled", "mass"]
    if profile.index < 2:
        log_tier = "spotlight"
    elif profile.index < 50:
        log_tier = "sampled"
    else:
        log_tier = "mass"
    return AgentRecord(
        agent_id=profile.agent_id,
        place=profile.country_code,
        latitude=float(city["latitude"]),
        longitude=float(city["longitude"]),
        role="person",
        log_tier=log_tier,
        traits=traits,
        states={"location": f"home:{household_id}"},
        behaviour={},
        behaviour_provenance={},
        relationships=[],
        weight=1,
    )


def _evidence_scope(value: object) -> EvidenceScope:
    normalized = str(value)
    if normalized in {"country_measured", "regional_imputed", "estimated"}:
        return normalized
    raise ValueError(f"Unsupported global demo evidence scope {normalized!r}")


def _coverage_by_field(
    population: PopulationTable,
) -> dict[MajorField, MajorFieldCoverage]:
    country_scopes: dict[str, dict[str, set[EvidenceScope]]] = defaultdict(
        lambda: defaultdict(set)
    )
    agent_scope_counts: dict[str, Counter] = defaultdict(Counter)
    for agent in population.agents:
        country = str(agent.traits["country_id"])
        for field, trait_key in FIELD_SCOPE_TRAITS.items():
            scope = _evidence_scope(agent.traits[trait_key])
            country_scopes[field][country].add(scope)
            agent_scope_counts[field][scope] += 1
    precedence = {"country_measured": 0, "regional_imputed": 1, "estimated": 2}
    result: dict[MajorField, MajorFieldCoverage] = {}
    for field in FIELD_SCOPE_TRAITS:
        groups: dict[EvidenceScope, list[str]] = {
            "country_measured": [],
            "regional_imputed": [],
            "estimated": [],
        }
        for country, scopes in country_scopes[field].items():
            effective = max(scopes, key=lambda scope: precedence[scope])
            groups[effective].append(country)
        result[field] = MajorFieldCoverage(
            country_measured=sorted(groups["country_measured"]),
            regional_imputed=sorted(groups["regional_imputed"]),
            estimated=sorted(groups["estimated"]),
            agent_counts={
                "country_measured": agent_scope_counts[field]["country_measured"],
                "regional_imputed": agent_scope_counts[field]["regional_imputed"],
                "estimated": agent_scope_counts[field]["estimated"],
            },
        )
    return result


def _comparison_value(agent: AgentRecord, field: str) -> object | None:
    if field == "finance_money":
        return agent.states.get("finance.money")
    if field == "finance_annual_income":
        return agent.states.get("finance.annual_income")
    if field == "finance_annual_expenses":
        return agent.states.get("finance.annual_expenses")
    if field == "finance_currency":
        return agent.traits.get("finance_local_currency")
    return agent.traits.get(field)


def _distribution_slice(
    agents: list[AgentRecord],
    field: str,
    distribution_type: Literal["numeric", "categorical"],
) -> DistributionSlice | None:
    values: list[tuple[object, float]] = []
    for agent in agents:
        value = _comparison_value(agent, field)
        if value is None or str(value).strip().casefold() in {"", "unknown", "none"}:
            continue
        weight = float(agent.traits.get("representative_population_weight", agent.weight))
        values.append((value, weight))
    if not values:
        return None
    represented_population = sum(weight for _, weight in values)
    if distribution_type == "numeric":
        numeric = [(float(value), weight) for value, weight in values]
        exact_value_shares = {}
        if field == "age":
            exact_weights = Counter()
            for value, weight in numeric:
                exact_weights[int(value)] += weight
            exact_value_shares = {
                str(value): exact_weights[value] / represented_population
                for value in sorted(exact_weights)
            }
        return DistributionSlice(
            agent_count=len(numeric),
            represented_population=represented_population,
            distribution_type="numeric",
            mean=sum(value * weight for value, weight in numeric) / represented_population,
            minimum=min(value for value, _ in numeric),
            maximum=max(value for value, _ in numeric),
            exact_value_shares=exact_value_shares,
        )
    category_weights = Counter()
    for value, weight in values:
        category_weights[str(value)] += weight
    return DistributionSlice(
        agent_count=len(values),
        represented_population=represented_population,
        distribution_type="categorical",
        categories={
            category: weight / represented_population
            for category, weight in sorted(category_weights.items())
        },
    )


def _distribution_comparisons(
    population: PopulationTable,
) -> dict[str, DistributionComparison]:
    specifications: dict[str, tuple[Literal["numeric", "categorical"], str]] = {
        "age": ("numeric", "age"),
        "sex": ("categorical", "sex"),
        "education_isced": ("categorical", "education"),
        "occupation_isco": ("categorical", "occupation"),
        "specialization": ("categorical", "specialization"),
        "openness": ("numeric", "personality"),
        "ideology_economic": ("numeric", "values"),
        "finance_money": ("numeric", "money"),
        "finance_annual_income": ("numeric", "income"),
        "finance_annual_expenses": ("numeric", "expenses"),
        "finance_currency": ("categorical", "currency"),
    }
    result: dict[str, DistributionComparison] = {}
    for field, (distribution_type, coverage_field) in specifications.items():
        scope_key = FIELD_SCOPE_TRAITS[coverage_field]
        available = [
            agent
            for agent in population.agents
            if _evidence_scope(agent.traits[scope_key])
            in {"country_measured", "regional_imputed", "estimated"}
        ]
        global_distribution = _distribution_slice(available, field, distribution_type)
        if global_distribution is None:
            continue
        country_distributions = {}
        for country in sorted({str(agent.traits["country_id"]) for agent in available}):
            value = _distribution_slice(
                [
                    agent
                    for agent in available
                    if str(agent.traits["country_id"]) == country
                ],
                field,
                distribution_type,
            )
            if value is not None:
                country_distributions[country] = value
        region_distributions = {}
        for region in CANONICAL_REGIONS:
            value = _distribution_slice(
                [
                    agent
                    for agent in available
                    if str(agent.traits["region"]) == region
                ],
                field,
                distribution_type,
            )
            if value is not None:
                region_distributions[region] = value
        result[field] = DistributionComparison(
            global_distribution=global_distribution,
            country_distributions=country_distributions,
            region_distributions=region_distributions,
        )
    return result


def _cross_country_relationships(
    population: PopulationTable,
) -> CrossCountryRelationshipSummary:
    country_by_agent = {
        agent.agent_id: str(agent.traits["country_id"]) for agent in population.agents
    }
    country_pairs = Counter()
    linked_agents = set()
    countries = set()
    relationship_count = 0
    for agent in population.agents:
        source_country = country_by_agent[agent.agent_id]
        for relationship in agent.relationships:
            target_country = country_by_agent.get(relationship.target_id)
            if target_country is None or target_country == source_country:
                continue
            relationship_count += 1
            linked_agents.update((agent.agent_id, relationship.target_id))
            countries.update((source_country, target_country))
            country_pairs[f"{source_country}->{target_country}"] += 1
    return CrossCountryRelationshipSummary(
        relationship_count=relationship_count,
        linked_agent_count=len(linked_agents),
        countries=sorted(countries),
        country_pairs=dict(sorted(country_pairs.items())),
    )


def _coverage_deviations(
    population: PopulationTable,
    major_fields: dict[MajorField, MajorFieldCoverage],
    cross_country: CrossCountryRelationshipSummary,
) -> list[GlobalDemoDeviation]:
    deviations = []
    for field, coverage in major_fields.items():
        if coverage.regional_imputed:
            deviations.append(
                GlobalDemoDeviation(
                    id=f"{field}:regional-imputed",
                    field=field,
                    countries=coverage.regional_imputed,
                    status="regional_imputed",
                    reason="No eligible country distribution is installed for this field.",
                    full_version_requires=(
                        "A measured distribution from each listed country with compatible "
                        "definitions and provenance."
                    ),
                )
            )
        if coverage.estimated:
            reason = (
                "The executable distribution is a sourced estimate with wide "
                "uncertainty rather than a confirmed measured distribution."
            )
            full_version_requires = (
                "A confirmed same-country measured distribution with matching definitions."
            )
            if field == "specialization":
                reason = (
                    "The in-app pipeline produced an editable ISCED-F draft estimate "
                    "for the listed countries."
                )
                full_version_requires = (
                    "A confirmed same-country ISCED-F-compatible distribution, ideally "
                    "joint with age, sex, and education, with pipeline provenance."
                )
            deviations.append(
                GlobalDemoDeviation(
                    id=f"{field}:estimated",
                    field=field,
                    countries=coverage.estimated,
                    status=(
                        "estimated" if field == "specialization" else "default_estimated"
                    ),
                    reason=reason,
                    full_version_requires=full_version_requires,
                )
            )
    imputed_finance_countries = sorted(
        {
            str(agent.traits["country_id"])
            for agent in population.agents
            if agent.traits.get("finance_status") == "imputed"
        }
    )
    if imputed_finance_countries:
        deviations.append(
            GlobalDemoDeviation(
                id="finance:person-level-imputation",
                field="finance",
                countries=imputed_finance_countries,
                status="imputed",
                reason=(
                    "Individual balances, income, expenses, savings, and debt are "
                    "deterministic draws from place-level marginals, not linked records."
                ),
                full_version_requires=(
                    "Licensed, linked household microdata for each country with weights."
                ),
            )
        )
    if cross_country.relationship_count == 0:
        deviations.append(
            GlobalDemoDeviation(
                id="interactions:cross-country-missing",
                field="interactions",
                countries=sorted(
                    {str(agent.traits["country_id"]) for agent in population.agents}
                ),
                status="default_estimated",
                reason=(
                    "The generated population has no cross-country relationship links "
                    "until the configured global relationship pass is applied."
                ),
                full_version_requires=(
                    "Deterministic cross-country links plus a confirmed executable "
                    "interaction program in the run registry."
                ),
            )
        )
    return deviations


def summarize_global_demo(population: PopulationTable) -> GlobalDemoSummary:
    country_counts = Counter(str(agent.traits["country_id"]) for agent in population.agents)
    region_counts = Counter(str(agent.traits["region"]) for agent in population.agents)
    major_fields = _coverage_by_field(population)
    cross_country = _cross_country_relationships(population)
    return GlobalDemoSummary(
        total_agents=len(population.agents),
        country_agent_counts=dict(sorted(country_counts.items())),
        region_agent_counts={
            region: region_counts.get(region, 0) for region in CANONICAL_REGIONS
        },
        major_fields=major_fields,
        distribution_comparisons=_distribution_comparisons(population),
        cross_country_relationships=cross_country,
        deviations=_coverage_deviations(population, major_fields, cross_country),
    )


def _default_finance_assignment(
    profile: GlobalAgentProfile,
) -> GlobalFinanceAssignment:
    from .global_finance import (
        GlobalFinanceProfile,
        load_global_finance_pack,
        sample_global_finances,
    )

    sampled = sample_global_finances(
        GlobalFinanceProfile(
            agent_id=profile.agent_id,
            country_code=profile.country_code,
            region=profile.region,
        ),
        load_global_finance_pack(),
        seed=profile.seed,
    )
    return GlobalFinanceAssignment(
        evidence_scope=sampled.evidence_scope,
        source_place=sampled.source_place,
        source_id=f"{sampled.distribution_id}:{sampled.cell_id}",
        source_status=sampled.status,
        source=sampled.source,
        source_version=sampled.source_version,
        source_date=sampled.source_date,
        source_population=sampled.source_population,
        uncertainty=sampled.uncertainty,
        currency="PPP",
        local_currency=sampled.local_currency,
        price_level_ratio=sampled.price_level_ratio,
        wage_per_workday=sampled.values["income"] / 260,
        money=sampled.values["money"],
        annual_income=sampled.values["income"],
        annual_expenses=sampled.values["expenses"],
        savings=sampled.values["savings"],
        debt=sampled.values["debt"],
    )


def build_global_demo_population(
    target_agents: int = 1_000,
    seed: int = 1,
    registry_directory: Path | None = None,
    city_directory: Path | None = None,
    finance_resolver: FinanceResolver | None = None,
    agent_enricher: AgentEnricher | None = None,
    specialization_catalog: SpecializationCatalog | None = None,
) -> GlobalDemoPopulation:
    registry = str((registry_directory or default_registry_directory()).resolve())
    cities_path = str((city_directory or default_city_directory()).resolve())
    population_rows = _country_populations(registry)
    age_sex_rows = _country_age_sex(registry)
    distributions = _priority_distributions(registry)
    cities = _largest_cities(cities_path)
    manifest = _wpp_manifest(registry)
    specializations = specialization_catalog or load_specialization_catalog()
    populations = {
        code: int(population_rows[code]["population"]) for code in GLOBAL_DEMO_COUNTRIES
    }
    allocations = allocate_country_agents(target_agents, GLOBAL_DEMO_COUNTRIES, populations)
    represented_population = sum(populations.values())
    rng = np.random.default_rng(seed)
    agents: list[AgentRecord] = []
    for country_code in GLOBAL_DEMO_COUNTRIES:
        country_row = population_rows[country_code]
        country_name = str(country_row["country_name"])
        region = country_region(country_code)
        sources = {
            feature.id: _distribution_for_country(
                feature.id,
                country_code,
                region,
                distributions,
            )
            for feature in canonical_feature_registry().definitions
            if feature.id not in {"age", "sex"}
        }
        sampled_age_sex = _sample_age_sex(
            age_sex_rows[country_code],
            allocations[country_code],
            rng,
        )
        for age, sex in sampled_age_sex:
            index = len(agents)
            education_distribution = sources["education_isced"]
            occupation_distribution = sources["occupation_isco"]
            education = (
                _sample_categorical(
                    education_distribution,
                    rng,
                    _allowed_education_values(age),
                )
                if education_distribution is not None
                else min(_allowed_education_values(age))
            )
            occupation = (
                _sample_categorical(occupation_distribution, rng)
                if occupation_distribution is not None and 15 <= age <= 80
                else "not_applicable"
            )
            profile = GlobalAgentProfile(
                agent_id=_stable_agent_id(seed, index),
                index=index,
                seed=seed,
                country_code=country_code,
                country_name=country_name,
                region=region,
                country_population=populations[country_code],
                country_population_share=(
                    populations[country_code] / represented_population
                ),
                country_allocation_agents=allocations[country_code],
                representative_population_weight=(
                    populations[country_code] / allocations[country_code]
                ),
                age=age,
                sex=sex,
                education_isced=education,
                occupation_isco=occupation,
            )
            agent = _agent(
                profile,
                cities[country_code],
                sources,
                specializations.country(country_code),
                manifest,
                rng,
            )
            assignment = finance_resolver(profile) if finance_resolver is not None else None
            agent = _apply_finance(
                agent,
                profile,
                assignment or _default_finance_assignment(profile),
            )
            if agent_enricher is not None:
                agent = agent_enricher(agent, profile)
            agents.append(agent)
    population = PopulationTable(
        population_id=GLOBAL_DEMO_POPULATION_ID,
        version=GLOBAL_DEMO_VERSION,
        seed=seed,
        agents=agents,
    )
    return GlobalDemoPopulation(
        population=population,
        summary=summarize_global_demo(population),
    )
