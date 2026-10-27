from collections import defaultdict
from math import inf
from statistics import NormalDist
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..dsl import Evidence, FeatureDefinition, FeatureDistribution, FeatureRegistry

type PlaceLevel = Literal["global", "region", "subregion", "country", "city"]
type FilterOperator = Literal["eq", "in", "gt", "gte", "lt", "lte", "between"]
type ResolutionStatus = Literal[
    "present",
    "inherited",
    "imputed",
    "missing",
    "unknown",
    "label_only",
    "literature_estimate",
    "hint_only",
]


class JointEstimateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlaceSelector(JointEstimateModel):
    level: PlaceLevel
    place: str = Field(min_length=1)
    label: str = Field(min_length=1)


class PopulationPlace(JointEstimateModel):
    place: str = Field(min_length=1)
    label: str = Field(min_length=1)
    level: Literal["region", "subregion", "country", "city"]
    population: int = Field(gt=0)
    city: str | None = None
    country: str | None = None
    subregion: str | None = None
    region: str | None = None

    @model_validator(mode="after")
    def owns_hierarchy_level(self):
        named_place = getattr(self, self.level)
        if named_place is not None and named_place != self.place:
            raise ValueError(f"{self.level} must match place")
        return self


class FeatureFilter(JointEstimateModel):
    feature_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    operator: FilterOperator
    values: list[str | float] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_values(self):
        expected = 2 if self.operator == "between" else None
        if expected is not None and len(self.values) != expected:
            raise ValueError("A between filter needs exactly two values")
        if self.operator not in {"between", "in"} and len(self.values) != 1:
            raise ValueError(f"A {self.operator} filter needs exactly one value")
        if self.operator in {"gt", "gte", "lt", "lte", "between"} and any(
            not isinstance(value, (int, float)) for value in self.values
        ):
            raise ValueError(f"A {self.operator} filter needs numeric values")
        if self.operator == "between" and float(self.values[0]) > float(self.values[1]):
            raise ValueError("A between filter needs its lower value first")
        return self


class MeasuredJointData(JointEstimateModel):
    level: PlaceLevel
    place: str = Field(min_length=1)
    conditions: list[FeatureFilter] = Field(min_length=2)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_size: int = Field(gt=0)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    population: str = Field(min_length=1)
    coverage_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    provenance: Evidence
    fallback_for: list[str] = Field(default_factory=list)
    explicit_fallback: bool = False

    @model_validator(mode="after")
    def valid_measurement(self):
        if len({condition.feature_id for condition in self.conditions}) < 2:
            raise ValueError("Measured joint data needs at least two distinct features")
        if self.ci_low > self.ci_high:
            raise ValueError("Measured joint confidence interval is reversed")
        if not self.ci_low <= self.probability <= self.ci_high:
            raise ValueError("Measured joint probability must be inside its confidence interval")
        if self.provenance.source_date is None:
            raise ValueError("Measured joint data needs a source date")
        if self.level == "global" and self.fallback_for and not self.explicit_fallback:
            raise ValueError("Global joint fallback needs explicit_fallback")
        return self


class DistributionSource(JointEstimateModel):
    place: str
    level: PlaceLevel
    status: ResolutionStatus
    source: str
    version: str
    source_date: str | None
    population: str
    coverage_percent: float
    uncertainty: float
    applied_population: int
    estimated_count: int
    agent_percent: float


class InheritedValue(JointEstimateModel):
    value: str
    agent_percent: float
    estimated_count: int
    sources: list[DistributionSource]


class FeatureInheritanceView(JointEstimateModel):
    feature_id: str
    selector: PlaceSelector
    selected_population: int
    represented_population: int
    unresolved_population: int
    values: list[InheritedValue]
    sources: list[DistributionSource]
    continuous_mean: float | None = None
    continuous_standard_deviation: float | None = None


class JointSourceApplication(JointEstimateModel):
    place: str
    level: PlaceLevel
    source: str
    version: str
    source_date: str
    sample_size: int
    population: str
    ci_low: float
    ci_high: float
    coverage_percent: float
    uncertainty: float
    applied_population: int


class JoinedFilterEstimate(JointEstimateModel):
    selector: PlaceSelector
    filters: list[FeatureFilter]
    method: Literal["measured_joint", "independence_estimate", "mixed"]
    method_label: str
    probability: float
    agent_percent: float
    estimated_count: int
    selected_population: int
    represented_population: int
    unresolved_population: int
    measured_population_percent: float
    ci_low: float
    ci_high: float
    sources: list[JointSourceApplication]
    coefficient_fit_eligible: bool
    missing_requirement: str | None = None
    missing_md_entry: str | None = None


class ResolvedDistribution(JointEstimateModel):
    distribution: FeatureDistribution
    status: ResolutionStatus


LEVELS = ("city", "country", "subregion", "region")


def place_at_level(place: PopulationPlace, level: PlaceLevel) -> str | None:
    if level == place.level:
        return place.place
    if level == "global":
        return "global"
    return getattr(place, level)


def selected_population_places(
    places: list[PopulationPlace], selector: PlaceSelector
) -> list[PopulationPlace]:
    identities = [(place.level, place.place) for place in places]
    if len(set(identities)) != len(identities):
        raise ValueError("Population places must be unique by level and place")
    if selector.level == "global":
        selected = places
    else:
        selected = [
            place for place in places if place_at_level(place, selector.level) == selector.place
        ]
    if not selected:
        raise ValueError(f"No population weights found for {selector.label}")
    return selected


def distribution_status(
    distribution: FeatureDistribution, place: PopulationPlace
) -> ResolutionStatus:
    if distribution.provenance.status != "present":
        return distribution.provenance.status
    if distribution.level == place.level and distribution.place == place.place:
        return "present"
    if distribution.level == "country":
        return "inherited"
    return "imputed"


def resolve_distribution_for_place(
    registry: FeatureRegistry, feature_id: str, place: PopulationPlace
) -> ResolvedDistribution | None:
    available_levels = [
        level
        for level in LEVELS
        if place_at_level(place, level) is not None
        and LEVELS.index(level) >= LEVELS.index(place.level)
    ]
    for level in available_levels:
        place_id = place_at_level(place, level)
        match = next(
            (
                distribution
                for distribution in registry.distributions
                if distribution.feature_id == feature_id
                and distribution.level == level
                and distribution.place == place_id
            ),
            None,
        )
        if match is not None:
            return ResolvedDistribution(
                distribution=match,
                status=distribution_status(match, place),
            )
    hierarchy_places = {
        identity for level in LEVELS if (identity := place_at_level(place, level)) is not None
    }
    global_match = next(
        (
            distribution
            for distribution in registry.distributions
            if distribution.feature_id == feature_id
            and distribution.level == "global"
            and distribution.explicit_fallback
            and (
                "*" in distribution.fallback_for
                or hierarchy_places & set(distribution.fallback_for)
            )
        ),
        None,
    )
    if global_match is None:
        return None
    return ResolvedDistribution(distribution=global_match, status="imputed")


def feature_inheritance(
    registry: FeatureRegistry,
    places: list[PopulationPlace],
    selector: PlaceSelector,
    feature_id: str,
) -> FeatureInheritanceView:
    definitions = {definition.id: definition for definition in registry.definitions}
    if feature_id not in definitions:
        raise ValueError(f"Unknown feature {feature_id}")
    selected = selected_population_places(places, selector)
    selected_population = sum(place.population for place in selected)
    represented_population = 0
    value_counts: dict[str, float] = defaultdict(float)
    source_counts: dict[str, dict[tuple[str, ...], float]] = defaultdict(lambda: defaultdict(float))
    source_details: dict[tuple[str, ...], tuple[FeatureDistribution, ResolutionStatus]] = {}
    application_population: dict[tuple[str, ...], int] = defaultdict(int)
    continuous_weighted_mean = 0.0
    continuous_weighted_second_moment = 0.0
    for place in selected:
        resolved = resolve_distribution_for_place(registry, feature_id, place)
        if resolved is None:
            continue
        distribution = resolved.distribution
        represented_population += place.population
        source_key = (
            distribution.level,
            distribution.place,
            resolved.status,
            distribution.provenance.source,
            distribution.provenance.version,
            distribution.provenance.source_date or "",
        )
        source_details[source_key] = (distribution, resolved.status)
        application_population[source_key] += place.population
        if distribution.values:
            for value, probability in distribution.values.items():
                estimated = place.population * probability
                value_counts[value] += estimated
                source_counts[value][source_key] += estimated
        elif distribution.mean is not None and distribution.standard_deviation is not None:
            continuous_weighted_mean += place.population * distribution.mean
            continuous_weighted_second_moment += place.population * (
                distribution.standard_deviation**2 + distribution.mean**2
            )
    values = []
    canonical_values = definitions[feature_id].canonical_values
    ordered_values = canonical_values + sorted(set(value_counts) - set(canonical_values))
    for value in ordered_values:
        count = value_counts.get(value, 0)
        sources = []
        for source_key, source_count in sorted(
            source_counts.get(value, {}).items(), key=lambda item: (-item[1], item[0])
        ):
            distribution, status = source_details[source_key]
            sources.append(
                DistributionSource(
                    place=distribution.place,
                    level=distribution.level,
                    status=status,
                    source=distribution.provenance.source,
                    version=distribution.provenance.version,
                    source_date=distribution.provenance.source_date,
                    population=distribution.population,
                    coverage_percent=distribution.coverage_percent,
                    uncertainty=distribution.provenance.uncertainty,
                    applied_population=application_population[source_key],
                    estimated_count=round(source_count),
                    agent_percent=source_count / selected_population * 100,
                )
            )
        values.append(
            InheritedValue(
                value=value,
                agent_percent=count / selected_population * 100,
                estimated_count=round(count),
                sources=sources,
            )
        )
    continuous_mean = None
    continuous_standard_deviation = None
    if represented_population and not values:
        continuous_mean = continuous_weighted_mean / represented_population
        variance = max(
            0,
            continuous_weighted_second_moment / represented_population - continuous_mean**2,
        )
        continuous_standard_deviation = variance**0.5
    all_sources = [
        DistributionSource(
            place=distribution.place,
            level=distribution.level,
            status=status,
            source=distribution.provenance.source,
            version=distribution.provenance.version,
            source_date=distribution.provenance.source_date,
            population=distribution.population,
            coverage_percent=distribution.coverage_percent,
            uncertainty=distribution.provenance.uncertainty,
            applied_population=population,
            estimated_count=population,
            agent_percent=population / selected_population * 100,
        )
        for source_key, population in sorted(
            application_population.items(), key=lambda item: (-item[1], item[0])
        )
        for distribution, status in [source_details[source_key]]
    ]
    return FeatureInheritanceView(
        feature_id=feature_id,
        selector=selector,
        selected_population=selected_population,
        represented_population=represented_population,
        unresolved_population=selected_population - represented_population,
        values=values,
        sources=all_sources,
        continuous_mean=continuous_mean,
        continuous_standard_deviation=continuous_standard_deviation,
    )


def normalized_filter_key(filters: list[FeatureFilter]) -> tuple[str, ...]:
    def normalized_value(value: str | float) -> str:
        if isinstance(value, (int, float)):
            return f"number:{float(value):.12g}"
        return f"text:{value}"

    def filter_key(item: FeatureFilter) -> str:
        values = "|".join(normalized_value(value) for value in item.values)
        return f"{item.feature_id}|{item.operator}|{values}"

    return tuple(sorted(filter_key(item) for item in filters))


def categorical_filter_probability(
    distribution: FeatureDistribution, filters: list[FeatureFilter]
) -> float:
    def matches(value: str, feature_filter: FeatureFilter) -> bool:
        if feature_filter.operator == "eq":
            return value == str(feature_filter.values[0])
        if feature_filter.operator == "in":
            return value in {str(item) for item in feature_filter.values}
        try:
            number = float(value)
            requested = [float(item) for item in feature_filter.values]
        except ValueError:
            return False
        if feature_filter.operator == "gt":
            return number > requested[0]
        if feature_filter.operator == "gte":
            return number >= requested[0]
        if feature_filter.operator == "lt":
            return number < requested[0]
        if feature_filter.operator == "lte":
            return number <= requested[0]
        return requested[0] <= number <= requested[1]

    return sum(
        probability
        for value, probability in distribution.values.items()
        if all(matches(value, feature_filter) for feature_filter in filters)
    )


def continuous_filter_probability(
    definition: FeatureDefinition,
    distribution: FeatureDistribution,
    filters: list[FeatureFilter],
) -> float:
    lower = -inf
    upper = inf
    exact = None
    for feature_filter in filters:
        values = [float(value) for value in feature_filter.values]
        if feature_filter.operator in {"gt", "gte"}:
            lower = max(lower, values[0])
        elif feature_filter.operator in {"lt", "lte"}:
            upper = min(upper, values[0])
        elif feature_filter.operator == "between":
            lower = max(lower, values[0])
            upper = min(upper, values[1])
        elif feature_filter.operator == "eq":
            exact = values[0]
        else:
            raise ValueError("Continuous features do not support the in operator")
    if exact is not None:
        lower = max(lower, exact)
        upper = min(upper, exact)
    if lower > upper:
        return 0
    mean = distribution.mean
    deviation = distribution.standard_deviation
    if mean is None or deviation is None:
        raise ValueError(f"Continuous distribution missing moments for {definition.id}")
    if deviation == 0:
        return float(lower <= mean <= upper)
    if exact is not None:
        return 0
    if definition.value_range is not None:
        if lower <= definition.value_range.minimum:
            lower = -inf
        if upper >= definition.value_range.maximum:
            upper = inf
    normal = NormalDist(mean, deviation)
    lower_probability = 0 if lower == -inf else normal.cdf(lower)
    upper_probability = 1 if upper == inf else normal.cdf(upper)
    return max(0, min(1, upper_probability - lower_probability))


def marginal_probability_for_place(
    registry: FeatureRegistry,
    place: PopulationPlace,
    filters: list[FeatureFilter],
) -> float | None:
    definitions = {definition.id: definition for definition in registry.definitions}
    probability = 1.0
    filters_by_feature: dict[str, list[FeatureFilter]] = defaultdict(list)
    for feature_filter in filters:
        filters_by_feature[feature_filter.feature_id].append(feature_filter)
    for feature_id, feature_filters in filters_by_feature.items():
        definition = definitions.get(feature_id)
        if definition is None:
            raise ValueError(f"Unknown feature {feature_id}")
        resolved = resolve_distribution_for_place(registry, feature_id, place)
        if resolved is None:
            return None
        distribution = resolved.distribution
        if definition.kind in {"categorical", "binary"}:
            feature_probability = categorical_filter_probability(distribution, feature_filters)
        else:
            feature_probability = continuous_filter_probability(
                definition, distribution, feature_filters
            )
        probability *= feature_probability
    return probability


def joint_record_for_place(
    records: list[MeasuredJointData],
    place: PopulationPlace,
    filters: list[FeatureFilter],
) -> MeasuredJointData | None:
    requested = normalized_filter_key(filters)
    available_levels = [
        level
        for level in LEVELS
        if place_at_level(place, level) is not None
        and LEVELS.index(level) >= LEVELS.index(place.level)
    ]
    for level in available_levels:
        place_id = place_at_level(place, level)
        match = next(
            (
                record
                for record in records
                if record.level == level
                and record.place == place_id
                and normalized_filter_key(record.conditions) == requested
            ),
            None,
        )
        if match is not None:
            return match
    hierarchy_places = {
        identity for level in LEVELS if (identity := place_at_level(place, level)) is not None
    }
    return next(
        (
            record
            for record in records
            if record.level == "global"
            and record.explicit_fallback
            and normalized_filter_key(record.conditions) == requested
            and ("*" in record.fallback_for or hierarchy_places & set(record.fallback_for))
        ),
        None,
    )


def filter_text(feature_filter: FeatureFilter) -> str:
    operators = {
        "eq": "=",
        "in": "in",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "between": "between",
    }
    values = (
        " and ".join(str(value) for value in feature_filter.values)
        if feature_filter.operator == "between"
        else ", ".join(str(value) for value in feature_filter.values)
    )
    return f"{feature_filter.feature_id} {operators[feature_filter.operator]} {values}"


def missing_joint_requirement(selector: PlaceSelector, filters: list[FeatureFilter]) -> str:
    conditions = " AND ".join(filter_text(item) for item in filters)
    return (
        f"Joint distribution for {conditions} in {selector.label}, measured on the same "
        "weighted respondents, including source, version, date, sample size, survey weights, "
        "and confidence interval"
    )


def missing_joint_markdown(selector: PlaceSelector, filters: list[FeatureFilter]) -> str:
    requirement = missing_joint_requirement(selector, filters)
    return f"- [ ] {requirement}. Current result is an independence estimate only."


def estimate_joined_filters(
    registry: FeatureRegistry,
    places: list[PopulationPlace],
    selector: PlaceSelector,
    filters: list[FeatureFilter],
    measured_joint_data: list[MeasuredJointData] | None = None,
) -> JoinedFilterEstimate:
    if len(filters) < 2 or len({item.feature_id for item in filters}) < 2:
        raise ValueError("Joined estimates need filters for at least two distinct features")
    selected = selected_population_places(places, selector)
    records = measured_joint_data or []
    record_identities = [
        (record.level, record.place, normalized_filter_key(record.conditions)) for record in records
    ]
    if len(set(record_identities)) != len(record_identities):
        raise ValueError("Measured joint records must be unique by place and conditions")
    selected_population = sum(place.population for place in selected)
    represented_population = 0
    measured_population = 0
    expected_count = 0.0
    lower_count = 0.0
    upper_count = 0.0
    used_records: dict[int, int] = defaultdict(int)
    independence_used = False
    for place in selected:
        record = joint_record_for_place(records, place, filters)
        if record is not None:
            probability = record.probability
            lower = record.ci_low
            upper = record.ci_high
            measured_population += place.population
            used_records[records.index(record)] += place.population
        else:
            marginal_probability = marginal_probability_for_place(registry, place, filters)
            if marginal_probability is None:
                continue
            probability = marginal_probability
            lower = 0
            upper = 1
            independence_used = True
        represented_population += place.population
        expected_count += place.population * probability
        lower_count += place.population * lower
        upper_count += place.population * upper
    if represented_population == 0:
        raise ValueError("No resolved marginal or measured joint data for these filters")
    if measured_population == represented_population and not independence_used:
        method = "measured_joint"
        method_label = "measured joint"
    elif measured_population == 0:
        method = "independence_estimate"
        method_label = "independence estimate — not measured"
    else:
        method = "mixed"
        method_label = (
            "measured joint where available; independence estimate elsewhere — not fully measured"
        )
    probability = expected_count / represented_population
    sources = [
        JointSourceApplication(
            place=record.place,
            level=record.level,
            source=record.provenance.source,
            version=record.provenance.version,
            source_date=record.provenance.source_date or "",
            sample_size=record.sample_size,
            population=record.population,
            ci_low=record.ci_low,
            ci_high=record.ci_high,
            coverage_percent=record.coverage_percent,
            uncertainty=record.provenance.uncertainty,
            applied_population=population,
        )
        for record_index, population in sorted(
            used_records.items(), key=lambda item: (-item[1], records[item[0]].place)
        )
        for record in [records[record_index]]
    ]
    incomplete_measurement = method != "measured_joint"
    requirement = missing_joint_requirement(selector, filters) if incomplete_measurement else None
    markdown = missing_joint_markdown(selector, filters) if incomplete_measurement else None
    return JoinedFilterEstimate(
        selector=selector,
        filters=filters,
        method=method,
        method_label=method_label,
        probability=probability,
        agent_percent=probability * 100,
        estimated_count=round(expected_count),
        selected_population=selected_population,
        represented_population=represented_population,
        unresolved_population=selected_population - represented_population,
        measured_population_percent=measured_population / selected_population * 100,
        ci_low=lower_count / represented_population,
        ci_high=upper_count / represented_population,
        sources=sources,
        coefficient_fit_eligible=False,
        missing_requirement=requirement,
        missing_md_entry=markdown,
    )
