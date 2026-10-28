from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TextDslModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextDslDiagnostic(TextDslModel):
    code: str
    line: int = Field(ge=1)
    column: int = Field(default=1, ge=1)
    message: str


class TextDslValidation(TextDslModel):
    valid: bool
    program_id: str | None = None
    version: str | None = None
    tick_hours: float | None = None
    adult_population: int | None = None
    entities: tuple[str, ...] = ()
    policies: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    role_distributions: tuple[str, ...] = ()
    spotlights: tuple[str, ...] = ()
    archetypes: tuple[str, ...] = ()
    composition_archetypes: tuple[dict[str, str], ...] = ()
    weighted_populations: tuple[str, ...] = ()
    aggregate_functions: tuple[dict[str, Any], ...] = ()
    compositions: tuple[dict[str, Any], ...] = ()
    composition_populations: tuple[str, ...] = ()
    neighbourhoods: tuple[str, ...] = ()
    neighbourhood_populations: tuple[str, ...] = ()
    diagnostics: tuple[TextDslDiagnostic, ...] = ()
    graph: dict[str, Any] | None = None


class TextDslDocument(TextDslModel):
    code: str
    source_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    saved_at: str | None = None
    validation: TextDslValidation


class ValidateTextDslRequest(TextDslModel):
    code: str = Field(min_length=1)


class SaveTextDslRequest(TextDslModel):
    code: str = Field(min_length=1)
    expected_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class TextDslRunRequest(TextDslModel):
    seed: int = Field(default=1, ge=0)
    days: int = Field(default=30, ge=1, le=365)
    sample_budget: int | None = Field(default=None, ge=1, le=10_000)
    role_parameters: dict[str, dict[str, float]] = Field(default_factory=dict)
    baseline_run_id: str | None = None
    population_id: str | None = None
    composition_id: str | None = None
    composition_population_id: str | None = None
    neighbourhood_id: str | None = None
    neighbourhood_population_id: str | None = None


TextDslReportValue = float | str | dict[str, float]


class TextDslReportColumn(TextDslModel):
    id: str
    label: str
    format: str
    metric: Any
    line: int


class TextDslReportRow(TextDslModel):
    group_id: str
    values: dict[str, TextDslReportValue]


class TextDslReportSnapshot(TextDslModel):
    tick: int
    rows: tuple[TextDslReportRow, ...]


class TextDslReport(TextDslModel):
    id: str
    title: str
    group_by: str
    display: str
    record: str
    columns: tuple[TextDslReportColumn, ...]
    snapshots: tuple[TextDslReportSnapshot, ...]


class TextDslReportDelta(TextDslModel):
    report_id: str
    group_id: str
    values: dict[str, TextDslReportValue]


class TextDslRunResult(TextDslModel):
    run_id: str
    source_hash: str
    seed: int
    days: int
    ticks: int
    adult_population: int
    total_agents: int
    generated_children: int
    sample_budget: int | None = None
    population_allocations: tuple[dict[str, Any], ...] = ()
    population_id: str | None = None
    results_title: str
    results_subtitle: str
    reports: tuple[TextDslReport, ...]
    comparison: tuple[TextDslReportDelta, ...] = ()
    engine_version: str
    created_at: str
    raw_result: dict[str, Any] | None = Field(default=None, exclude=True)


class TextDslRunSummary(TextDslModel):
    run_id: str
    source_hash: str
    seed: int
    days: int
    ticks: int
    total_agents: int
    sample_budget: int | None = None
    population_id: str | None = None
    created_at: str


class AggregateEvaluationRequest(TextDslModel):
    function_id: str
    seed: int = Field(default=1, ge=0)
    days: int = Field(default=30, ge=1, le=365)
    evaluated_at_day: int = Field(default=0, ge=0)
    inputs: dict[str, float] = Field(default_factory=dict)
    branch_inputs: dict[str, dict[str, float]] = Field(default_factory=dict)
    input_schedule: tuple[dict[str, Any], ...] = ()
    events: tuple[str, ...] = ()
    force_relearn: bool = False


class AggregateEvaluationResult(TextDslModel):
    function_id: str
    cache_hit: bool
    invalidation_reason: str | None = None
    agent_ticks: int
    inputs_hash: str
    valid_from: int
    valid_until: int
    dsl_source_hash: str
    cache_version: int
    time_series: tuple[dict[str, Any], ...]
    reports: tuple[TextDslReport, ...]
    elapsed_seconds: float
    cache_tree: dict[str, Any] | None = None
    feedback_iterations: int = 0
    feedback_change_percent: float = 0.0


class AggregateCacheVersion(TextDslModel):
    function_id: str
    version: int
    dsl_source_hash: str
    valid_from: int
    valid_until: int
    inputs_hash: str
    learning_agent_ticks: int
