from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from math import isfinite
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .locations import LocationPlace
from .runtime_geography import RuntimeAgentGeography, resolve_runtime_agent_geographies

AggregateValueSource = Literal["trait", "state", "memory", "runtime_trait", "profile"]
AggregateEventSource = Literal[
    "events",
    "routine_actions",
    "transition_outcomes",
    "interactions",
]
PredicateOperator = Literal[
    "truthy",
    "equals",
    "greater_than_or_equal",
    "less_than",
    "in",
    "contains_any",
    "all",
    "any",
    "not",
]
PlaceLevel = Literal["city", "country", "region", "global"]


class AggregateStatisticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AggregateValueReference(AggregateStatisticsModel):
    source: AggregateValueSource
    field: str = Field(min_length=1)


class ActionAggregateContribution(AggregateStatisticsModel):
    action_id: str = Field(min_length=1)
    statistic_id: str = Field(min_length=1)
    event_source: AggregateEventSource
    label_field: str = Field(min_length=1)
    agent_index_field: str | None = Field(default=None, min_length=1)
    agent_indices_field: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def one_agent_reference(self):
        if (self.agent_index_field is None) == (self.agent_indices_field is None):
            raise ValueError(
                "An action aggregate contribution needs one agent index field"
            )
        return self


class FinanceMetricDefinition(AggregateStatisticsModel):
    id: Literal["income", "expenses", "savings", "debt"]
    values: tuple[AggregateValueReference, ...] = Field(min_length=1)
    units: tuple[AggregateValueReference, ...] = Field(min_length=1)
    evidence_statuses: tuple[AggregateValueReference, ...] = Field(min_length=1)
    source_ids: tuple[AggregateValueReference, ...] = Field(min_length=1)
    basis: str = Field(min_length=1)


class FinanceAggregateDefinition(AggregateStatisticsModel):
    metrics: tuple[FinanceMetricDefinition, ...] = Field(min_length=4)

    @model_validator(mode="after")
    def complete_finance_metrics(self):
        ids = [metric.id for metric in self.metrics]
        required = {"income", "expenses", "savings", "debt"}
        if set(ids) != required or len(ids) != len(required):
            raise ValueError(
                "Finance aggregates require one income, expenses, savings, and debt metric"
            )
        return self


class PredicateDefinition(AggregateStatisticsModel):
    values: tuple[AggregateValueReference, ...] = ()
    operator: PredicateOperator
    expected: Any = None
    operands: tuple[PredicateDefinition, ...] = ()

    @model_validator(mode="after")
    def expected_matches_operator(self):
        if self.operator in {"all", "any", "not"}:
            required_operands = 1 if self.operator == "not" else 2
            if len(self.operands) < required_operands:
                raise ValueError(
                    f"A {self.operator} predicate requires at least {required_operands} operand(s)"
                )
            if self.values or self.expected is not None:
                raise ValueError(
                    f"A {self.operator} predicate accepts nested operands only"
                )
            return self
        if not self.values or self.operands:
            raise ValueError(f"A {self.operator} predicate requires values and no operands")
        if self.operator == "truthy" and self.expected is not None:
            raise ValueError("A truthy predicate does not accept an expected value")
        if self.operator != "truthy" and self.expected is None:
            raise ValueError(f"A {self.operator} predicate requires an expected value")
        return self


class HistogramBucket(AggregateStatisticsModel):
    label: str = Field(min_length=1)
    minimum: float | None = None
    maximum_exclusive: float | None = None

    @model_validator(mode="after")
    def increasing_bounds(self):
        if (
            self.minimum is not None
            and self.maximum_exclusive is not None
            and self.minimum >= self.maximum_exclusive
        ):
            raise ValueError("Histogram bucket minimum must be below its maximum")
        return self


class EmploymentAggregateDefinition(AggregateStatisticsModel):
    employed: PredicateDefinition
    labour_force: PredicateDefinition
    student: PredicateDefinition
    caregiver: PredicateDefinition
    retired: PredicateDefinition
    worker: PredicateDefinition
    age: tuple[AggregateValueReference, ...] = Field(min_length=1)
    sex: tuple[AggregateValueReference, ...] = Field(min_length=1)
    age_groups: tuple[HistogramBucket, ...] = Field(min_length=1)


class HistogramAggregateDefinition(AggregateStatisticsModel):
    id: str = Field(min_length=1)
    values: tuple[AggregateValueReference, ...] = Field(min_length=1)
    buckets: tuple[HistogramBucket, ...] = ()


class TimelineSubject(AggregateStatisticsModel):
    agent_id: str = Field(min_length=1)
    role: Literal["spotlight", "leader", "influencer"]
    start_tick: int = Field(default=1, ge=1)


class AggregateStatisticsProgram(AggregateStatisticsModel):
    schema_version: Literal[1] = 1
    version: str = Field(min_length=1)
    action_contributions: tuple[ActionAggregateContribution, ...] = ()
    finance: FinanceAggregateDefinition | None = None
    employment: EmploymentAggregateDefinition | None = None
    histograms: tuple[HistogramAggregateDefinition, ...] = ()
    timeline_subjects: tuple[TimelineSubject, ...] = ()

    @model_validator(mode="after")
    def unique_definitions(self):
        contribution_keys = [
            (item.event_source, item.action_id, item.statistic_id)
            for item in self.action_contributions
        ]
        if len(contribution_keys) != len(set(contribution_keys)):
            raise ValueError("Aggregate action contribution definitions must be unique")
        histogram_ids = [item.id for item in self.histograms]
        if len(histogram_ids) != len(set(histogram_ids)):
            raise ValueError("Aggregate histogram IDs must be unique")
        subject_ids = [item.agent_id for item in self.timeline_subjects]
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("Timeline subject agent IDs must be unique")
        return self


class FinanceStatistic(AggregateStatisticsModel):
    total: float | None
    mean: float | None
    median: float | None
    unit: str
    unit_counts: dict[str, int]
    comparable: bool
    basis: str
    evidence_status: Literal["measured", "estimated"]
    source_ids: list[str]
    observations: int = Field(ge=0)


class EmploymentCell(AggregateStatisticsModel):
    agent_count: int = Field(ge=0)
    employed: int = Field(ge=0)
    unemployed: int = Field(ge=0)
    labour_force: int = Field(ge=0)
    unemployment_rate: float = Field(ge=0, le=1)
    student_share: float = Field(ge=0, le=1)
    caregiver_share: float = Field(ge=0, le=1)
    retired_share: float = Field(ge=0, le=1)
    worker_share: float = Field(ge=0, le=1)


class EmploymentStatistic(EmploymentCell):
    by_age_group_and_sex: dict[str, EmploymentCell]


class HistogramStatistic(AggregateStatisticsModel):
    counts: dict[str, int]
    mean: float | None = None


class RunAggregateRecord(AggregateStatisticsModel):
    run_id: str = Field(min_length=1)
    program_version: str = Field(min_length=1)
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    place_level: PlaceLevel
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    parent_place_id: str | None = None
    population: float = Field(ge=0)
    agent_count: int = Field(ge=0)
    agent_type_counts: dict[str, int]
    agent_type_shares: dict[str, float]
    action_counts: dict[str, int]
    action_rates_per_1000: dict[str, float]
    finances: dict[str, FinanceStatistic]
    employment: EmploymentStatistic | None = None
    histograms: dict[str, HistogramStatistic]


class RunAggregatePage(AggregateStatisticsModel):
    items: list[RunAggregateRecord]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)


class _AggregateValueReader:
    def __init__(
        self,
        profiles: Sequence[Mapping[str, Any]],
        output: Mapping[str, Any],
    ):
        self.profiles = profiles
        agents = output.get("agents")
        if not isinstance(agents, Mapping):
            raise ValueError("Aggregate statistics require Rust agent columns")
        self.memory = self._column_mapping(agents.get("memory", {}), "memory")
        self.runtime_traits = self._column_mapping(
            agents.get("traits", {}), "runtime traits"
        )

    @staticmethod
    def _column_mapping(value: Any, label: str) -> Mapping[str, Sequence[Any]]:
        if not isinstance(value, Mapping):
            raise ValueError(f"Aggregate {label} must be a column mapping")
        for field, values in value.items():
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise ValueError(f"Aggregate {label} field {field} must be a column")
        return value

    def first(self, references: Sequence[AggregateValueReference], index: int) -> Any:
        for reference in references:
            value = self.read(reference, index)
            if value is not None and value != "":
                return value
        return None

    def read(self, reference: AggregateValueReference, index: int) -> Any:
        profile = self.profiles[index]
        if reference.source == "trait":
            return self._mapping_value(profile.get("traits"), reference.field)
        if reference.source == "state":
            return self._mapping_value(profile.get("states"), reference.field)
        if reference.source == "memory":
            return self._column_value(self.memory, reference.field, index)
        if reference.source == "runtime_trait":
            return self._column_value(self.runtime_traits, reference.field, index)
        return self._path_value(profile, reference.field)

    @staticmethod
    def _mapping_value(value: Any, field: str) -> Any:
        return value.get(field) if isinstance(value, Mapping) else None

    @staticmethod
    def _column_value(columns: Mapping[str, Sequence[Any]], field: str, index: int) -> Any:
        values = columns.get(field)
        if values is None:
            return None
        if index >= len(values):
            raise ValueError(f"Aggregate runtime field {field} does not cover agent {index}")
        return values[index]

    @staticmethod
    def _path_value(value: Mapping[str, Any], path: str) -> Any:
        current: Any = value
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return None
            current = current[part]
        return current


class _PlaceGroup:
    def __init__(
        self,
        level: PlaceLevel,
        identifier: str,
        label: str,
        parent_identifier: str | None = None,
    ):
        self.level = level
        self.identifier = identifier
        self.label = label
        self.parent_identifier = parent_identifier
        self.indices: list[int] = []


def collect_daily_aggregate_statistics(
    *,
    run_id: str,
    program: AggregateStatisticsProgram,
    agent_ids: Sequence[str],
    profiles: Sequence[Mapping[str, Any]],
    output: Mapping[str, Any],
    day: int,
    current_date: date,
    tick: int,
    location_places: Sequence[LocationPlace] = (),
    initial_location_ids: Sequence[str] = (),
    runtime_place_location_ids: Sequence[str] = (),
) -> list[RunAggregateRecord]:
    if len(profiles) != len(agent_ids):
        raise ValueError("Aggregate profiles must match the prepared agent population")
    for index, (agent_id, profile) in enumerate(zip(agent_ids, profiles, strict=True)):
        profile_id = str(profile.get("agent_id", agent_id))
        if profile_id != agent_id:
            raise ValueError(
                f"Aggregate profile {index} identifies {profile_id} instead of {agent_id}"
            )
    reader = _AggregateValueReader(profiles, output)
    geographies = resolve_runtime_agent_geographies(
        profiles=profiles,
        output=output,
        location_places=location_places,
        initial_location_ids=initial_location_ids,
        runtime_place_location_ids=runtime_place_location_ids,
    )
    groups = _place_groups(geographies)
    action_counts_by_agent = _action_counts(program, output, len(agent_ids))
    records = [
        _aggregate_group(
            run_id=run_id,
            program=program,
            profiles=profiles,
            geographies=geographies,
            reader=reader,
            group=group,
            action_counts_by_agent=action_counts_by_agent,
            day=day,
            current_date=current_date,
            tick=tick,
        )
        for group in groups
    ]
    level_order = {"region": 0, "country": 1, "city": 2, "global": 3}
    return sorted(records, key=lambda item: (level_order[item.place_level], item.place_id))


def timeline_agent_ids(
    program: AggregateStatisticsProgram | None,
    profiles: Sequence[Mapping[str, Any]],
) -> set[str]:
    if program is not None:
        return {subject.agent_id for subject in program.timeline_subjects}
    if profiles:
        return set()
    return set()


def timeline_start_ticks(
    program: AggregateStatisticsProgram | None,
) -> dict[str, int]:
    if program is None:
        return {}
    return {subject.agent_id: subject.start_tick for subject in program.timeline_subjects}


def _place_groups(geographies: Sequence[RuntimeAgentGeography]) -> list[_PlaceGroup]:
    countries: dict[str, _PlaceGroup] = {}
    regions: dict[str, _PlaceGroup] = {}
    cities: dict[str, _PlaceGroup] = {}
    global_group = _PlaceGroup("global", "global", "Global")
    for index, geography in enumerate(geographies):
        country_id = geography.country_id
        country_label = geography.country_label
        region_id = geography.region_id or ""
        city_id = geography.city_id or ""
        city_label = geography.city_label or city_id
        if country_id:
            country = countries.setdefault(
                country_id,
                _PlaceGroup(
                    "country",
                    country_id,
                    country_label or country_id,
                    region_id or None,
                ),
            )
            country.indices.append(index)
        if region_id:
            region = regions.setdefault(
                region_id,
                _PlaceGroup("region", region_id, region_id),
            )
            region.indices.append(index)
        if city_id:
            city = cities.setdefault(
                city_id,
                _PlaceGroup(
                    "city",
                    city_id,
                    city_label or city_id,
                    country_id or None,
                ),
            )
            city.indices.append(index)
        global_group.indices.append(index)
    return [
        *(countries[key] for key in sorted(countries)),
        *(regions[key] for key in sorted(regions)),
        *(cities[key] for key in sorted(cities)),
        global_group,
    ]


def _action_counts(
    program: AggregateStatisticsProgram,
    output: Mapping[str, Any],
    population: int,
) -> list[Counter[str]]:
    counts = [Counter() for _ in range(population)]
    for definition in program.action_contributions:
        raw_events = output.get(definition.event_source, [])
        if not isinstance(raw_events, list) or any(
            not isinstance(item, Mapping) for item in raw_events
        ):
            raise ValueError(
                f"Aggregate action source {definition.event_source} must contain objects"
            )
        for item in raw_events:
            if str(item.get(definition.label_field, "")) != definition.action_id:
                continue
            if definition.agent_index_field is not None:
                indices = [item.get(definition.agent_index_field)]
            else:
                indices = item.get(str(definition.agent_indices_field), [])
                if not isinstance(indices, list):
                    raise ValueError(
                        f"Aggregate action {definition.action_id} agent indices must be a list"
                    )
            for raw_index in indices:
                if (
                    not isinstance(raw_index, int)
                    or isinstance(raw_index, bool)
                    or not 0 <= raw_index < population
                ):
                    raise ValueError(
                        f"Aggregate action {definition.action_id} references agent {raw_index}"
                    )
                counts[raw_index][definition.statistic_id] += 1
    return counts


def _aggregate_group(
    *,
    run_id: str,
    program: AggregateStatisticsProgram,
    profiles: Sequence[Mapping[str, Any]],
    geographies: Sequence[RuntimeAgentGeography],
    reader: _AggregateValueReader,
    group: _PlaceGroup,
    action_counts_by_agent: Sequence[Counter[str]],
    day: int,
    current_date: date,
    tick: int,
) -> RunAggregateRecord:
    action_counts: Counter[str] = Counter()
    agent_types: Counter[str] = Counter()
    population = 0.0
    latitudes: list[float] = []
    longitudes: list[float] = []
    for index in group.indices:
        action_counts.update(action_counts_by_agent[index])
        profile = profiles[index]
        traits = profile.get("traits")
        traits = traits if isinstance(traits, Mapping) else {}
        agent_type = str(
            traits.get("agent_type") or profile.get("role") or "unspecified"
        ).strip()
        agent_types[agent_type or "unspecified"] += 1
        population += _finite_number(traits.get("representative_population_weight"), 1.0)
        geography = geographies[index]
        latitude = geography.latitude
        longitude = geography.longitude
        if latitude is not None and longitude is not None:
            latitudes.append(latitude)
            longitudes.append(longitude)
    for contribution in program.action_contributions:
        action_counts.setdefault(contribution.statistic_id, 0)
    agent_count = len(group.indices)
    return RunAggregateRecord(
        run_id=run_id,
        program_version=program.version,
        day=day,
        date=current_date,
        tick=tick,
        place_level=group.level,
        place_id=group.identifier,
        place_label=group.label,
        latitude=sum(latitudes) / len(latitudes) if latitudes else None,
        longitude=sum(longitudes) / len(longitudes) if longitudes else None,
        parent_place_id=group.parent_identifier,
        population=population,
        agent_count=agent_count,
        agent_type_counts=dict(sorted(agent_types.items())),
        agent_type_shares={
            key: count / agent_count for key, count in sorted(agent_types.items())
        }
        if agent_count
        else {},
        action_counts=dict(sorted(action_counts.items())),
        action_rates_per_1000={
            key: count / agent_count * 1_000
            for key, count in sorted(action_counts.items())
        }
        if agent_count
        else {},
        finances=_finance_statistics(program.finance, reader, group.indices),
        employment=_employment_statistics(program.employment, reader, group.indices),
        histograms=_histogram_statistics(program.histograms, reader, group.indices),
    )


def _finance_statistics(
    definition: FinanceAggregateDefinition | None,
    reader: _AggregateValueReader,
    indices: Sequence[int],
) -> dict[str, FinanceStatistic]:
    if definition is None:
        return {}
    result = {}
    for metric in definition.metrics:
        values: list[float] = []
        units: Counter[str] = Counter()
        statuses: list[str] = []
        sources: set[str] = set()
        for index in indices:
            numeric = _optional_number(reader.first(metric.values, index))
            if numeric is None:
                continue
            values.append(numeric)
            unit = str(reader.first(metric.units, index) or "unspecified").strip()
            units[unit or "unspecified"] += 1
            status = str(reader.first(metric.evidence_statuses, index) or "estimated")
            statuses.append(status)
            source = str(reader.first(metric.source_ids, index) or "").strip()
            if source:
                sources.add(source)
        comparable = len(units) <= 1
        result[metric.id] = FinanceStatistic(
            total=sum(values) if values and comparable else None,
            mean=sum(values) / len(values) if values and comparable else None,
            median=float(median(values)) if values and comparable else None,
            unit=next(iter(units)) if len(units) == 1 else "mixed",
            unit_counts=dict(sorted(units.items())),
            comparable=comparable,
            basis=metric.basis,
            evidence_status=(
                "measured"
                if statuses and all(_measured_status(status) for status in statuses)
                else "estimated"
            ),
            source_ids=sorted(sources),
            observations=len(values),
        )
    return result


def _employment_statistics(
    definition: EmploymentAggregateDefinition | None,
    reader: _AggregateValueReader,
    indices: Sequence[int],
) -> EmploymentStatistic | None:
    if definition is None:
        return None
    observations = {}
    for index in indices:
        employed = _predicate(definition.employed, reader, index)
        observations[index] = {
            "employed": employed,
            "labour_force": employed
            or _predicate(definition.labour_force, reader, index),
            "student": _predicate(definition.student, reader, index),
            "caregiver": _predicate(definition.caregiver, reader, index),
            "retired": _predicate(definition.retired, reader, index),
            "worker": _predicate(definition.worker, reader, index),
        }
    grouped: dict[str, list[int]] = defaultdict(list)
    for index in indices:
        age = _optional_number(reader.first(definition.age, index))
        age_group = _bucket_label(age, definition.age_groups) if age is not None else None
        sex = str(reader.first(definition.sex, index) or "unspecified").strip()
        grouped[f"{age_group or 'outside configured ages'} · {sex or 'unspecified'}"].append(
            index
        )
    overall = _employment_cell(indices, observations)
    return EmploymentStatistic(
        **overall.model_dump(),
        by_age_group_and_sex={
            key: _employment_cell(values, observations)
            for key, values in sorted(grouped.items())
        },
    )


def _employment_cell(
    indices: Sequence[int],
    observations: Mapping[int, Mapping[str, bool]],
) -> EmploymentCell:
    count = len(indices)
    employed = sum(observations[index]["employed"] for index in indices)
    labour_force = sum(observations[index]["labour_force"] for index in indices)
    unemployed = sum(
        observations[index]["labour_force"] and not observations[index]["employed"]
        for index in indices
    )
    return EmploymentCell(
        agent_count=count,
        employed=employed,
        unemployed=unemployed,
        labour_force=labour_force,
        unemployment_rate=unemployed / labour_force if labour_force else 0,
        student_share=sum(observations[index]["student"] for index in indices) / count
        if count
        else 0,
        caregiver_share=sum(observations[index]["caregiver"] for index in indices) / count
        if count
        else 0,
        retired_share=sum(observations[index]["retired"] for index in indices) / count
        if count
        else 0,
        worker_share=sum(observations[index]["worker"] for index in indices) / count
        if count
        else 0,
    )


def _histogram_statistics(
    definitions: Sequence[HistogramAggregateDefinition],
    reader: _AggregateValueReader,
    indices: Sequence[int],
) -> dict[str, HistogramStatistic]:
    result = {}
    for definition in definitions:
        counts: Counter[str] = Counter(
            {bucket.label: 0 for bucket in definition.buckets}
        )
        numeric_values: list[float] = []
        for index in indices:
            raw = reader.first(definition.values, index)
            if raw is None:
                continue
            numeric = _optional_number(raw)
            if definition.buckets:
                if numeric is None:
                    continue
                label = _bucket_label(numeric, definition.buckets)
                if label is not None:
                    counts[label] += 1
                    numeric_values.append(numeric)
            else:
                counts[str(raw)] += 1
                if numeric is not None:
                    numeric_values.append(numeric)
        result[definition.id] = HistogramStatistic(
            counts=dict(sorted(counts.items())),
            mean=(sum(numeric_values) / len(numeric_values) if numeric_values else None),
        )
    return result


def _predicate(
    definition: PredicateDefinition,
    reader: _AggregateValueReader,
    index: int,
) -> bool:
    if definition.operator == "all":
        return all(_predicate(item, reader, index) for item in definition.operands)
    if definition.operator == "any":
        return any(_predicate(item, reader, index) for item in definition.operands)
    if definition.operator == "not":
        return not _predicate(definition.operands[0], reader, index)
    value = reader.first(definition.values, index)
    if definition.operator == "truthy":
        return _truthy(value)
    if definition.operator == "equals":
        return value == definition.expected or str(value) == str(definition.expected)
    if definition.operator == "greater_than_or_equal":
        number = _optional_number(value)
        expected = _optional_number(definition.expected)
        return number is not None and expected is not None and number >= expected
    if definition.operator == "less_than":
        number = _optional_number(value)
        expected = _optional_number(definition.expected)
        return number is not None and expected is not None and number < expected
    expected_values = (
        definition.expected
        if isinstance(definition.expected, (list, tuple, set))
        else [definition.expected]
    )
    normalized = {str(item) for item in expected_values}
    if definition.operator == "in":
        return str(value) in normalized
    actual_values = value if isinstance(value, (list, tuple, set)) else [value]
    return bool({str(item) for item in actual_values}.intersection(normalized))


def _bucket_label(
    value: float | None,
    buckets: Sequence[HistogramBucket],
) -> str | None:
    if value is None:
        return None
    for bucket in buckets:
        if bucket.minimum is not None and value < bucket.minimum:
            continue
        if bucket.maximum_exclusive is not None and value >= bucket.maximum_exclusive:
            continue
        return bucket.label
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"", "0", "false", "no", "none", "null"}:
            return False
        if normalized in {"1", "true", "yes"}:
            return True
    return bool(value)


def _optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _finite_number(value: Any, default: float) -> float:
    number = _optional_number(value)
    return number if number is not None and number >= 0 else default


def _measured_status(value: str) -> bool:
    return value.strip().casefold() in {
        "measured",
        "present",
        "measured_joint",
        "fitted_model",
    }
