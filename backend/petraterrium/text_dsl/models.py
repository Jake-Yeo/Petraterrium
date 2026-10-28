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
    archetypes: tuple[str, ...] = ()
    weighted_populations: tuple[str, ...] = ()
    diagnostics: tuple[TextDslDiagnostic, ...] = ()


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
    baseline_run_id: str | None = None
    population_id: str | None = None


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
    population_id: str | None = None
    created_at: str
