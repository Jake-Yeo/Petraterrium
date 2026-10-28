from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..population import AgentRecord, PopulationTable
from .global_demo_population import (
    GLOBAL_DEMO_POPULATION_ID,
    DistributionSlice,
    GlobalDemoSummary,
    summarize_global_demo,
)
from .interactions import InteractionProgramDefinition


class InitialAgentSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InitialAgentSummaryLocation(Protocol):
    region: str | None


class InitialAgentSummaryRecord(Protocol):
    country: str
    location: InitialAgentSummaryLocation
    traits: Mapping[str, Any]


class InitialAgentFieldPlaceEvidence(InitialAgentSummaryModel):
    country: str
    country_code: str
    status: Literal[
        "measured",
        "own_country_inherited",
        "regional_imputed",
        "estimated",
    ]
    source: str | None = None
    source_place: str | None = None
    source_level: Literal["country", "region", "global"]
    source_version: str | None = None


class InitialAgentFieldCoverage(InitialAgentSummaryModel):
    measured: list[str]
    own_country_inherited: list[str]
    regional_imputed: list[str]
    estimated: list[str]
    place_evidence: list[InitialAgentFieldPlaceEvidence] = Field(default_factory=list)


class InitialAgentDistributionBin(InitialAgentSummaryModel):
    label: str
    percentage: float = Field(ge=0, le=100)
    estimated_agents: int = Field(ge=0)


class InitialAgentDistribution(InitialAgentSummaryModel):
    field_id: str
    label: str
    summary: str
    evidence_status: Literal[
        "measured",
        "own_country_inherited",
        "regional_imputed",
        "estimated",
    ]
    source: str | None = None
    source_place: str | None = None
    bins: list[InitialAgentDistributionBin]


class InitialAgentPlaceComparison(InitialAgentSummaryModel):
    comparison_id: str
    level: Literal["global", "country", "region"]
    place: str
    agent_count: int = Field(ge=0)
    distributions: list[InitialAgentDistribution]


class InitialAgentDeviation(InitialAgentSummaryModel):
    deviation_id: str
    field: str
    status: Literal["estimated", "regional_imputed", "omitted"]
    places: list[str]
    reason: str
    full_requirement: str


class InitialAgentGlobalInteractionSummary(InitialAgentSummaryModel):
    status: Literal["configured", "recorded", "unavailable"] = "unavailable"
    run_id: str | None = None
    participating_countries: list[str] = Field(default_factory=list)
    participating_regions: list[str] = Field(default_factory=list)
    cross_country_interactions: int = Field(default=0, ge=0)
    cross_region_interactions: int = Field(default=0, ge=0)


class InitialPopulationEvidenceSummary(InitialAgentSummaryModel):
    total_agents: int = Field(default=0, ge=0)
    country_agent_counts: dict[str, int]
    region_agent_counts: dict[str, int]
    fields: dict[str, InitialAgentFieldCoverage]
    comparisons: list[InitialAgentPlaceComparison] = Field(default_factory=list)
    deviations: list[InitialAgentDeviation] = Field(default_factory=list)
    interactions: InitialAgentGlobalInteractionSummary = Field(
        default_factory=InitialAgentGlobalInteractionSummary
    )


EVIDENCE_SCOPE_FIELDS = {
    "age": "age_evidence_scope",
    "sex": "sex_evidence_scope",
    "education": "education_evidence_scope",
    "specialization": "specialization_evidence_scope",
    "occupation": "occupation_evidence_scope",
    "personality": "personality_evidence_scope",
    "values": "values_evidence_scope",
    "finance": "finance_evidence_scope",
}
DIRECT_MEASURED_SCOPES = {"measured", "measured_joint"}
OWN_COUNTRY_SCOPES = {"country_measured", "measured_marginal"}
REGIONAL_IMPUTED_SCOPES = {"regional_imputed", "region_imputed", "inherited"}
FIELD_PROVENANCE_FEATURES = {
    "education": ("education_isced",),
    "occupation": ("occupation_isco",),
    "personality": (
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
    ),
    "values": (
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
        "generalized_trust",
        "religiosity",
        "risk_aversion",
        "time_preference",
        "schwartz_values",
    ),
}
COMPARISON_COVERAGE_FIELDS = {
    "age": "age",
    "sex": "sex",
    "education_isced": "education",
    "occupation_isco": "occupation",
    "specialization": "specialization",
    "openness": "personality",
    "ideology_economic": "values",
    "finance_money": "money",
    "finance_annual_income": "income",
    "finance_annual_expenses": "expenses",
    "finance_currency": "currency",
}
COMPARISON_LABELS = {
    "age": "Age",
    "sex": "Sex",
    "education_isced": "Education (ISCED)",
    "occupation_isco": "Occupation (ISCO)",
    "specialization": "Field of study (ISCED-F)",
    "openness": "Big Five openness",
    "ideology_economic": "Economic ideology",
    "finance_money": "Available money",
    "finance_annual_income": "Annual income",
    "finance_annual_expenses": "Annual expenses",
    "finance_currency": "Local currency",
}
FINANCE_DISPLAY_FIELDS = {
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
}


def population_evidence_summary(
    records: Sequence[InitialAgentSummaryRecord],
) -> InitialPopulationEvidenceSummary:
    country_counts = Counter(record.country for record in records)
    region_counts = Counter(record.location.region or "Unknown" for record in records)
    countries = sorted(country_counts)
    fields: dict[str, InitialAgentFieldCoverage] = {}
    for field, trait_key in EVIDENCE_SCOPE_FIELDS.items():
        statuses_by_country: dict[str, set[str]] = defaultdict(set)
        for record in records:
            statuses_by_country[record.country].add(
                str(record.traits.get(trait_key, "unknown")).strip().casefold()
            )
        measured = []
        own_country_inherited = []
        regional_imputed = []
        estimated = []
        for country in countries:
            statuses = statuses_by_country[country]
            if statuses and statuses <= DIRECT_MEASURED_SCOPES:
                measured.append(country)
            elif statuses and statuses <= DIRECT_MEASURED_SCOPES | OWN_COUNTRY_SCOPES:
                own_country_inherited.append(country)
            elif statuses and statuses <= (
                DIRECT_MEASURED_SCOPES
                | OWN_COUNTRY_SCOPES
                | REGIONAL_IMPUTED_SCOPES
            ):
                regional_imputed.append(country)
            else:
                estimated.append(country)
        fields[field] = InitialAgentFieldCoverage(
            measured=measured,
            own_country_inherited=own_country_inherited,
            regional_imputed=regional_imputed,
            estimated=estimated,
        )
    return InitialPopulationEvidenceSummary(
        total_agents=len(records),
        country_agent_counts=dict(sorted(country_counts.items())),
        region_agent_counts=dict(sorted(region_counts.items())),
        fields=fields,
    )


def is_global_demo_population(population: PopulationTable) -> bool:
    return population.population_id == GLOBAL_DEMO_POPULATION_ID and bool(
        population.agents
    ) and all(
        str(agent.traits.get("country_id", "")).strip()
        and str(agent.traits.get("region", "")).strip()
        for agent in population.agents
    )


def _country_names(population: PopulationTable) -> dict[str, str]:
    names = {}
    for agent in population.agents:
        country_code = str(agent.traits["country_id"])
        names[country_code] = str(agent.traits.get("country") or country_code)
    return names


def _country_agents(population: PopulationTable) -> dict[str, list[AgentRecord]]:
    grouped: dict[str, list[AgentRecord]] = defaultdict(list)
    for agent in population.agents:
        grouped[str(agent.traits["country_id"])].append(agent)
    return grouped


def _clean_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    if not normalized or normalized.casefold() in {"none", "unknown", "unavailable"}:
        return None
    return normalized


def _joined_values(values: Sequence[object]) -> str | None:
    unique = sorted(
        {
            normalized
            for value in values
            if (normalized := _clean_text(value)) is not None
        }
    )
    return " · ".join(unique) or None


def _field_feature_provenance(
    agent: AgentRecord,
    field: str,
) -> list[Mapping[str, Any]]:
    feature_provenance = agent.traits.get("feature_provenance")
    if not isinstance(feature_provenance, Mapping):
        return []
    records = []
    for feature_id in FIELD_PROVENANCE_FEATURES.get(field, ()):
        record = feature_provenance.get(feature_id)
        if isinstance(record, Mapping):
            records.append(record)
    return records


def _field_source_prefix(field: str) -> str:
    if field in FINANCE_DISPLAY_FIELDS - {"finance"}:
        return f"finance_{field}"
    return field


def _field_provenance(
    agent: AgentRecord,
    field: str,
    status: Literal[
        "measured",
        "own_country_inherited",
        "regional_imputed",
        "estimated",
    ],
) -> tuple[str | None, str | None, str | None]:
    traits = agent.traits
    prefix = _field_source_prefix(field)
    feature_records = _field_feature_provenance(agent, field)
    source_values: list[object] = [traits.get(f"{prefix}_source")]
    version_values: list[object] = [traits.get(f"{prefix}_source_version")]
    if field == "education":
        source_values.append(traits.get("education_source"))
        version_values.append(traits.get("education_mapping_version"))
    if field in FINANCE_DISPLAY_FIELDS:
        source_values.append(traits.get("finance_source"))
        version_values.append(traits.get("finance_source_version"))
    source_values.extend(record.get("source") for record in feature_records)
    version_values.extend(record.get("source_version") for record in feature_records)
    source_place = _clean_text(traits.get(f"{prefix}_source_place"))
    if source_place is None:
        source_place = _clean_text(traits.get(f"{field}_source_place"))
    return (
        _joined_values(source_values),
        source_place,
        _joined_values(version_values),
    )


def _coverage_status(
    summary: GlobalDemoSummary,
    field: str,
    country_code: str,
) -> Literal[
    "measured",
    "own_country_inherited",
    "regional_imputed",
    "estimated",
]:
    coverage = summary.major_fields[field]
    if country_code in coverage.country_measured:
        return "own_country_inherited"
    if country_code in coverage.regional_imputed:
        return "regional_imputed"
    return "estimated"


def _coverage_fields(
    summary: GlobalDemoSummary,
    country_names: Mapping[str, str],
    agents_by_country: Mapping[str, Sequence[AgentRecord]],
) -> dict[str, InitialAgentFieldCoverage]:
    fields = {}
    for field, coverage in summary.major_fields.items():
        own_country_inherited = sorted(
            country_names[code] for code in coverage.country_measured
        )
        regional_imputed = sorted(
            country_names[code] for code in coverage.regional_imputed
        )
        estimated = sorted(country_names[code] for code in coverage.estimated)
        place_evidence = []
        for country_code in sorted(summary.country_agent_counts):
            status = _coverage_status(summary, field, country_code)
            source, source_place, source_version = _field_provenance(
                agents_by_country[country_code][0], field, status
            )
            place_evidence.append(
                InitialAgentFieldPlaceEvidence(
                    country=country_names[country_code],
                    country_code=country_code,
                    status=status,
                    source=source,
                    source_place=source_place,
                    source_level=(
                        "country"
                        if status in {"measured", "own_country_inherited", "estimated"}
                        else "region"
                    ),
                    source_version=source_version,
                )
            )
        fields[field] = InitialAgentFieldCoverage(
            measured=[],
            own_country_inherited=own_country_inherited,
            regional_imputed=regional_imputed,
            estimated=estimated,
            place_evidence=place_evidence,
        )
    return fields


def _format_distribution_number(value: float | None) -> str:
    if value is None:
        return "Not resolved"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _distribution_bins(distribution: DistributionSlice) -> list[InitialAgentDistributionBin]:
    if distribution.distribution_type == "categorical":
        return [
            InitialAgentDistributionBin(
                label=label,
                percentage=min(100, max(0, share * 100)),
                estimated_agents=min(
                    distribution.agent_count,
                    max(0, round(share * distribution.agent_count)),
                ),
            )
            for label, share in distribution.categories.items()
        ]
    if distribution.exact_value_shares:
        return [
            InitialAgentDistributionBin(
                label=f"Age {value}",
                percentage=min(100, max(0, share * 100)),
                estimated_agents=min(
                    distribution.agent_count,
                    max(0, round(share * distribution.agent_count)),
                ),
            )
            for value, share in distribution.exact_value_shares.items()
        ]
    return [
        InitialAgentDistributionBin(
            label="Agents with resolved values",
            percentage=100,
            estimated_agents=distribution.agent_count,
        )
    ]


def _distribution_summary(distribution: DistributionSlice) -> str:
    if distribution.distribution_type == "categorical":
        return (
            f"Population-weighted shares across {distribution.agent_count:,} resolved agents"
        )
    return (
        f"Population-weighted mean {_format_distribution_number(distribution.mean)}; "
        f"range {_format_distribution_number(distribution.minimum)} to "
        f"{_format_distribution_number(distribution.maximum)} across "
        f"{distribution.agent_count:,} resolved agents"
    )


def _combined_status(
    summary: GlobalDemoSummary,
    field: str,
    country_codes: Sequence[str],
) -> Literal[
    "measured",
    "own_country_inherited",
    "regional_imputed",
    "estimated",
]:
    statuses = {
        _coverage_status(summary, field, country_code)
        for country_code in country_codes
    }
    if "estimated" in statuses:
        return "estimated"
    if "regional_imputed" in statuses:
        return "regional_imputed"
    if "own_country_inherited" in statuses:
        return "own_country_inherited"
    return "measured"


def _combined_provenance(
    summary: GlobalDemoSummary,
    field: str,
    country_codes: Sequence[str],
    agents_by_country: Mapping[str, Sequence[AgentRecord]],
) -> tuple[str | None, str | None]:
    sources = []
    source_places = []
    for country_code in country_codes:
        status = _coverage_status(summary, field, country_code)
        source, source_place, _ = _field_provenance(
            agents_by_country[country_code][0], field, status
        )
        sources.append(source)
        source_places.append(source_place)
    return _joined_values(sources), _joined_values(source_places)


def _distribution_view(
    field_id: str,
    distribution: DistributionSlice,
    summary: GlobalDemoSummary,
    country_codes: Sequence[str],
    agents_by_country: Mapping[str, Sequence[AgentRecord]],
) -> InitialAgentDistribution:
    coverage_field = COMPARISON_COVERAGE_FIELDS[field_id]
    source, source_place = _combined_provenance(
        summary, coverage_field, country_codes, agents_by_country
    )
    return InitialAgentDistribution(
        field_id=field_id,
        label=COMPARISON_LABELS[field_id],
        summary=_distribution_summary(distribution),
        evidence_status=_combined_status(summary, coverage_field, country_codes),
        source=source,
        source_place=source_place,
        bins=_distribution_bins(distribution),
    )


def _place_comparisons(
    summary: GlobalDemoSummary,
    country_names: Mapping[str, str],
    agents_by_country: Mapping[str, Sequence[AgentRecord]],
) -> list[InitialAgentPlaceComparison]:
    country_regions = {
        country_code: str(agents[0].traits["region"])
        for country_code, agents in agents_by_country.items()
    }
    all_country_codes = sorted(country_names)
    comparisons = [
        InitialAgentPlaceComparison(
            comparison_id="global:all",
            level="global",
            place="Global",
            agent_count=summary.total_agents,
            distributions=[
                _distribution_view(
                    field_id,
                    comparison.global_distribution,
                    summary,
                    all_country_codes,
                    agents_by_country,
                )
                for field_id, comparison in summary.distribution_comparisons.items()
            ],
        )
    ]
    for country_code, agent_count in sorted(summary.country_agent_counts.items()):
        distributions = [
            _distribution_view(
                field_id,
                comparison.country_distributions[country_code],
                summary,
                [country_code],
                agents_by_country,
            )
            for field_id, comparison in summary.distribution_comparisons.items()
            if country_code in comparison.country_distributions
        ]
        comparisons.append(
            InitialAgentPlaceComparison(
                comparison_id=f"country:{country_code}",
                level="country",
                place=country_names[country_code],
                agent_count=agent_count,
                distributions=distributions,
            )
        )
    for region, agent_count in summary.region_agent_counts.items():
        if agent_count == 0:
            continue
        region_country_codes = sorted(
            country_code
            for country_code, country_region in country_regions.items()
            if country_region == region
        )
        distributions = [
            _distribution_view(
                field_id,
                comparison.region_distributions[region],
                summary,
                region_country_codes,
                agents_by_country,
            )
            for field_id, comparison in summary.distribution_comparisons.items()
            if region in comparison.region_distributions
        ]
        comparisons.append(
            InitialAgentPlaceComparison(
                comparison_id=f"region:{region}",
                level="region",
                place=region,
                agent_count=agent_count,
                distributions=distributions,
            )
        )
    return comparisons


def _deviation_status(
    status: str,
) -> Literal["estimated", "regional_imputed", "omitted"]:
    if status == "regional_imputed":
        return "regional_imputed"
    if status in {"imputed", "estimated", "default_estimated"}:
        return "estimated"
    return "omitted"


def _cross_region_relationship_count(population: PopulationTable) -> int:
    region_by_agent = {
        agent.agent_id: str(agent.traits["region"]) for agent in population.agents
    }
    return sum(
        1
        for agent in population.agents
        for relationship in agent.relationships
        if relationship.target_id in region_by_agent
        and region_by_agent[relationship.target_id] != region_by_agent[agent.agent_id]
    )


def global_population_evidence_summary(
    population: PopulationTable,
    interaction_program: InteractionProgramDefinition | None,
) -> InitialPopulationEvidenceSummary:
    summary = summarize_global_demo(population)
    country_names = _country_names(population)
    agents_by_country = _country_agents(population)
    country_counts = {
        country_names[country_code]: count
        for country_code, count in summary.country_agent_counts.items()
    }
    participating_country_codes = summary.cross_country_relationships.countries
    participating_regions = sorted(
        {
            str(agents_by_country[country_code][0].traits["region"])
            for country_code in participating_country_codes
        }
    )
    interaction_configured = (
        summary.cross_country_relationships.relationship_count > 0
        and interaction_program is not None
        and interaction_program.status == "confirmed"
    )
    return InitialPopulationEvidenceSummary(
        total_agents=summary.total_agents,
        country_agent_counts=dict(sorted(country_counts.items())),
        region_agent_counts={
            region: count
            for region, count in summary.region_agent_counts.items()
            if count > 0
        },
        fields=_coverage_fields(
            summary, country_names, agents_by_country
        ),
        comparisons=_place_comparisons(
            summary, country_names, agents_by_country
        ),
        deviations=[
            InitialAgentDeviation(
                deviation_id=deviation.id,
                field=deviation.field,
                status=_deviation_status(deviation.status),
                places=[country_names.get(code, code) for code in deviation.countries],
                reason=deviation.reason,
                full_requirement=deviation.full_version_requires,
            )
            for deviation in summary.deviations
        ],
        interactions=InitialAgentGlobalInteractionSummary(
            status="configured" if interaction_configured else "unavailable",
            participating_countries=sorted(
                country_names[code] for code in participating_country_codes
            ),
            participating_regions=participating_regions,
            cross_country_interactions=(
                summary.cross_country_relationships.relationship_count
            ),
            cross_region_interactions=_cross_region_relationship_count(population),
        ),
    )


