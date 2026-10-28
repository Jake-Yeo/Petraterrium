from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DefaultPipelineModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class DurationDistribution(DefaultPipelineModel):
    minimum_hours: float = Field(ge=0)
    median_hours: float = Field(ge=0)
    maximum_hours: float = Field(ge=0)
    shape: Literal["triangular", "uniform", "lognormal"]

    @model_validator(mode="after")
    def ordered(self):
        if not self.minimum_hours <= self.median_hours <= self.maximum_hours:
            raise ValueError("Duration distribution bounds must be ordered")
        if self.minimum_hours == self.maximum_hours:
            raise ValueError("Duration distribution cannot be a fixed duration")
        return self


class DurationInterval(DefaultPipelineModel):
    lower_hours: float = Field(ge=0)
    upper_hours: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.lower_hours > self.upper_hours:
            raise ValueError("Duration uncertainty bounds must be ordered")
        return self


class DurationUncertainty(DefaultPipelineModel):
    minimum: DurationInterval
    median: DurationInterval
    maximum: DurationInterval
    method: str = Field(min_length=1)
    coverage: str = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)


class DefaultPipelineSource(DefaultPipelineModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: str = Field(min_length=1)
    source_kind: Literal[
        "official_statistics",
        "representative_survey",
        "research_article",
        "government_report",
        "news",
        "online_opinion",
        "project_estimate",
    ]
    source_date: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    licence: str = Field(min_length=1)
    population: str = Field(min_length=1)
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    language: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    retrieved_at: datetime


class DurationResearchRequest(DefaultPipelineModel):
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    action_label: str = Field(min_length=1)
    target_place_id: str = Field(min_length=1)
    target_place_label: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    requested_source_tiers: tuple[str, ...] = Field(min_length=1)


class DurationSearchLogEntry(DefaultPipelineModel):
    sequence: int = Field(ge=1)
    action_ids: tuple[str, ...] = Field(min_length=1)
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    language: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    query_or_source: str = Field(min_length=1)
    searched_at: datetime
    outcome: Literal["candidate", "unavailable", "rejected", "error"]
    candidate_ids: tuple[str, ...] = ()
    detail: str = Field(min_length=1)


class DurationCandidate(DefaultPipelineModel):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    evidence_kind: Literal["measured", "estimated"]
    duration: DurationDistribution
    source_provenance: tuple[DefaultPipelineSource, ...] = Field(min_length=1)
    sample_size: int = Field(ge=1)
    effective_sample_size: float = Field(gt=0)
    denominator: str = Field(min_length=1)
    units: Literal["hours per occurrence"] = "hours per occurrence"
    mapping: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    uncertainty: DurationUncertainty


class DurationChosenResult(DefaultPipelineModel):
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    evidence_kind: Literal["measured", "estimated"]
    duration: DurationDistribution
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    source_provenance: tuple[DefaultPipelineSource, ...] = Field(min_length=1)
    target_place_id: str = Field(min_length=1)
    target_place_label: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    uncertainty: DurationUncertainty


class DurationResearchOutput(DefaultPipelineModel):
    requests: tuple[DurationResearchRequest, ...] = Field(min_length=1)
    search_log: tuple[DurationSearchLogEntry, ...] = Field(min_length=1)
    candidates: tuple[DurationCandidate, ...] = Field(min_length=1)
    chosen_results: tuple[DurationChosenResult, ...] = Field(min_length=1)


class DefaultStateSnapshotReference(DefaultPipelineModel):
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(pattern=r"^snapshots/[0-9a-f]{64}\.json\.gz$")
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    section_hashes: dict[str, str] = Field(min_length=1)
    section_counts: dict[str, int] = Field(min_length=1)
    compressed_bytes: int = Field(ge=1)


class DefaultPipelineRun(DefaultPipelineModel):
    schema_version: Literal["1"] = "1"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    version: int = Field(ge=1)
    previous_run_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    pipeline_version: str = Field(min_length=1)
    created_at: datetime
    completed_at: datetime
    requests: tuple[DurationResearchRequest, ...] = Field(min_length=1)
    search_log: tuple[DurationSearchLogEntry, ...] = Field(min_length=1)
    candidates: tuple[DurationCandidate, ...] = Field(min_length=1)
    chosen_results: tuple[DurationChosenResult, ...] = Field(min_length=1)
    snapshot: DefaultStateSnapshotReference
    run_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_action_results(self):
        action_ids = [result.action_id for result in self.chosen_results]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("Default pipeline chosen action results must be unique")
        return self


class DefaultPipelineRunSummary(DefaultPipelineModel):
    run_id: str
    version: int
    previous_run_id: str | None
    created_at: datetime
    completed_at: datetime
    action_count: int = Field(ge=1)
    measured_count: int = Field(ge=0)
    estimated_count: int = Field(ge=0)
    active: bool
    run_hash: str
    snapshot_id: str


class DefaultPipelineRunList(DefaultPipelineModel):
    active_run_id: str | None
    runs: tuple[DefaultPipelineRunSummary, ...]


class DefaultPipelineDurationChange(DefaultPipelineModel):
    action_id: str
    before: DurationDistribution | None
    after: DurationDistribution | None
    before_evidence_kind: Literal["measured", "estimated"] | None
    after_evidence_kind: Literal["measured", "estimated"] | None
    before_source_ids: tuple[str, ...]
    after_source_ids: tuple[str, ...]
    reason: str


class DefaultPipelineResearchChange(DefaultPipelineModel):
    added: tuple[str, ...]
    removed: tuple[str, ...]


class DefaultPipelineRunDiff(DefaultPipelineModel):
    from_run_id: str
    to_run_id: str
    researched_data: DefaultPipelineResearchChange
    chosen_data: tuple[DefaultPipelineDurationChange, ...]
    changed_snapshot_sections: tuple[str, ...]


class ActivateDefaultPipelineRunRequest(DefaultPipelineModel):
    expected_run_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    user_confirmed: Literal[True]


class RestoreDefaultPipelineRunRequest(DefaultPipelineModel):
    run_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    expected_run_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    user_confirmed: Literal[True]


class DefaultPipelineActivation(DefaultPipelineModel):
    run_id: str
    version: int
    active: Literal[True] = True
    activated_at: datetime
    run_hash: str


class DefaultStateRestoreReceipt(DefaultPipelineModel):
    run_id: str
    version: int
    snapshot_id: str
    restored_at: datetime
    restored_sections: tuple[str, ...]
    section_hashes: dict[str, str]
    run_hash: str

