from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .dsl import DSLConfig, OutputSpec, PopulationReference, SliderSpec, TickConfig

CONTRACT_VERSION = "2"
CountryCode = str
RunStatus = Literal["queued", "running", "done", "failed"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


class Parameters(Contract):
    transmission: float = Field(default=0.38, ge=0, le=3, allow_inf_nan=False)
    progression: float = Field(default=0.2, ge=0, le=3, allow_inf_nan=False)
    recovery: float = Field(default=0.09, ge=0, le=3, allow_inf_nan=False)
    mixing: float = Field(default=0.04, ge=0, le=1, allow_inf_nan=False)
    initial_infected: int = Field(default=40, ge=1, le=10000, strict=True)


class RunConfig(Contract):
    scenario: str = Field(default="pandemic", min_length=1)
    countries: list[CountryCode] = Field(default_factory=list, max_length=300)
    start_day: int = Field(default=0, ge=0, le=10000, strict=True)
    end_day: int = Field(default=160, ge=1, le=10730, strict=True)
    seed: int = Field(default=42, ge=0, le=4294967295, strict=True)
    parameters: Parameters = Field(default_factory=Parameters)
    dsl: DSLConfig | None = None
    population: PopulationReference | None = None
    tick: TickConfig | None = None
    outputs: OutputSpec | None = None
    evidence_table_version: str = Field(default="FAKE-evidence-v1", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def places_from_population(cls, value):
        if not isinstance(value, dict) or value.get("countries"):
            return value
        population = value.get("population") or (value.get("dsl") or {}).get("population")
        if isinstance(population, dict) and population.get("places"):
            return {**value, "countries": population["places"]}
        return value

    @field_validator("countries")
    @classmethod
    def canonical_countries(cls, value: list[CountryCode]) -> list[CountryCode]:
        if not value:
            raise ValueError("Select at least one place")
        if len(set(value)) != len(value):
            raise ValueError("Select each place only once")
        return sorted(value)

    @model_validator(mode="after")
    def valid_window(self) -> "RunConfig":
        if not 1 <= self.end_day - self.start_day <= 730:
            raise ValueError("End day must be 1 to 730 days after start day")
        if self.dsl and self.scenario != self.dsl.id:
            raise ValueError("Run scenario must match the DSL id")
        if self.dsl is None and self.scenario != "pandemic":
            raise ValueError("A new scenario requires a complete DSL config")
        return self


class PlaceSnapshot(Contract):
    country: CountryCode
    latitude: float | None = None
    longitude: float | None = None
    susceptible: int = Field(default=0, ge=0)
    exposed: int = Field(default=0, ge=0)
    infected: int = Field(default=0, ge=0)
    recovered: int = Field(default=0, ge=0)
    states: dict[str, dict[str, int]] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class DailySnapshot(Contract):
    run_id: str = Field(min_length=1)
    day: int = Field(ge=0)
    places: list[PlaceSnapshot] = Field(min_length=1, max_length=300)
    seed: int = Field(ge=0)
    engine_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    config_hash: str = ""
    tick: int = Field(default=0, ge=0)
    elapsed_hours: float = Field(default=0, ge=0, allow_inf_nan=False)


class Totals(Contract):
    population: int = Field(ge=0)
    susceptible: int = Field(default=0, ge=0)
    exposed: int = Field(default=0, ge=0)
    infected: int = Field(default=0, ge=0)
    recovered: int = Field(default=0, ge=0)


class MetricPeak(Contract):
    day: int = Field(ge=0)
    value: float = Field(ge=0, allow_inf_nan=False)


class Metrics(Contract):
    totals: Totals
    peak_day: int
    peak_infected: int = Field(ge=0)
    days_recorded: int = Field(ge=1)
    state_totals: dict[str, dict[str, int]] = Field(default_factory=dict)
    metric_peaks: dict[str, MetricPeak] = Field(default_factory=dict)
    stories_generated: int = Field(default=0, ge=0)


class RunError(Contract):
    code: str
    message: str


class MissingFallback(Contract):
    field: str
    status: Literal[
        "inherited",
        "imputed",
        "missing",
        "unknown",
        "label_only",
        "literature_estimate",
    ]
    fallback: str
    impact: str


class EnsembleUpdate(Contract):
    run_id: str
    completed: int = Field(ge=1)
    total: int = Field(ge=1)
    seeds: list[int]
    quantiles: dict[str, dict[str, float]]
    evidence_table_version: str


class StoryRecord(Contract):
    story_id: str
    event_id: str
    place: str
    day: int = Field(ge=0)
    headline: str
    body: str
    metrics: dict[str, float]
    template: bool
    arc_id: str


class StoryList(Contract):
    stories: list[StoryRecord]


class AgentPoint(Contract):
    agent_id: str
    place: str
    latitude: float
    longitude: float
    state: str
    color: str
    log_tier: Literal["spotlight", "sampled", "mass"]


class AgentPointList(Contract):
    agents: list[AgentPoint]
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    representative: bool = True


class AgentTimelineEntry(Contract):
    tick: int = Field(ge=0)
    day: int = Field(ge=0)
    action: str
    chain_id: str | None = None
    causes: dict[str, float] = Field(default_factory=dict)
    state_after: dict[str, str] = Field(default_factory=dict)


class AgentRelationship(Contract):
    target_id: str
    kind: str
    weight: float = Field(ge=-1, le=1)


class AgentDetail(Contract):
    agent_id: str
    run_id: str
    place: str
    role: str
    synthetic: Literal[True] = True
    log_tier: Literal["spotlight", "sampled", "mass"]
    log_scope: str
    traits: dict[str, Any]
    states: dict[str, str]
    behaviour: dict[str, float]
    relationships: list[AgentRelationship]
    timeline: list[AgentTimelineEntry]
    media: list[str]


class StoryDetail(Contract):
    story: StoryRecord
    place_metrics: dict[str, float]
    agents: list[AgentPoint]
    arc: list[StoryRecord]


class PlaceDetail(Contract):
    place_id: str
    run_id: str
    status: str
    metrics: dict[str, float]
    events: list[str]
    arc: list[str]


class DSLRender(Contract):
    plain_language: str
    sliders: list[SliderSpec]


class BacktestComparison(Contract):
    metric: str
    simulated: list[float]
    observed: list[float]
    mean_absolute_error: float = Field(ge=0)
    outcome: Literal["hit", "miss"]
    cutoff_date: str
    provenance: str


class RunSummary(Contract):
    run_id: str
    config_hash: str
    config: RunConfig
    status: RunStatus
    created_at: str
    last_sequence: int = Field(ge=0)
    outputs: OutputSpec
    evidence_table_version: str
    population_version: str
    missing_fallbacks: list[MissingFallback] = Field(default_factory=list)
    metrics: Metrics | None = None
    error: RunError | None = None


class RunDetail(RunSummary):
    snapshots: list[DailySnapshot]
    ensemble_updates: list[EnsembleUpdate] = Field(default_factory=list)
    stories: list[StoryRecord] = Field(default_factory=list)
    backtests: list[BacktestComparison] = Field(default_factory=list)


class RunCreated(RunDetail):
    cached: bool


class RunList(Contract):
    runs: list[RunSummary]


class RunComplete(Contract):
    run_id: str
    status: Literal["done"] = "done"
    metrics: Metrics


class RunFailed(Contract):
    run_id: str
    status: Literal["failed"] = "failed"
    error: RunError


class Country(Contract):
    country: CountryCode
    name: str
    population: int = Field(gt=0)
    latitude: float
    longitude: float
    fake: Literal[True] = True


class Catalog(Contract):
    countries: list[Country]
    engine_version: str
    data_version: str
    contract_version: str = CONTRACT_VERSION
    notice: str
