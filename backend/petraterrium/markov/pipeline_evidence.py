import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Scalar = str | float | int | bool
TimeUnit = Literal["event", "hour", "day", "friday", "week", "year"]
SourceKind = Literal[
    "official_statistics",
    "census",
    "representative_survey",
    "research_article",
    "government_report",
    "university_report",
    "news",
    "online_opinion",
    "expert_commentary",
    "user_url",
    "user_upload",
    "user_text",
]


class PipelineEvidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class PipelineEstimateSource(PipelineEvidenceModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    title: str = Field(min_length=1)
    url: str | None = None
    source_kind: SourceKind
    observation_date: str | None = None
    published_date: str | None = None
    retrieved_date: str | None = None
    language: str = Field(min_length=2)
    excerpt: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    license: str = Field(min_length=1)
    supports_joint_outcome: bool = False

    @model_validator(mode="after")
    def valid_dates(self):
        for value in (self.observation_date, self.published_date, self.retrieved_date):
            if value is not None:
                date.fromisoformat(value)
        return self


class PipelineResearchLog(PipelineEvidenceModel):
    sequence: int = Field(ge=1)
    origin: Literal["user", "automatic"]
    language: str = Field(min_length=2)
    engine: str = Field(min_length=1)
    query_or_source: str = Field(min_length=1)
    source_kind: SourceKind
    outcome: Literal["no_result", "candidate", "rejected", "error"]
    source_ids: tuple[str, ...] = ()


class PipelineTransitionEstimate(PipelineEvidenceModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    kind: Literal["pipeline_estimate"] = "pipeline_estimate"
    review_state: Literal["draft"] = "draft"
    pipeline_attempt_id: str = Field(min_length=1)
    outcome_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    conditioning_id: str = Field(min_length=1)
    place: str = Field(min_length=1)
    time_unit: TimeUnit
    predictor_values: dict[str, Scalar] = Field(default_factory=dict)
    condition_values: dict[str, Scalar] = Field(default_factory=dict)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    population: str = Field(min_length=1)
    sample_size: int | None = Field(default=None, gt=0)
    reasoning: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    method: Literal["source_synthesis", "joint_outcome_synthesis"]
    sources: tuple[PipelineEstimateSource, ...] = Field(min_length=1)
    selected_source_ids: tuple[str, ...] = Field(min_length=1)
    search_log: tuple[PipelineResearchLog, ...] = Field(min_length=1)
    pipeline_provider: str = Field(min_length=1)
    pipeline_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def auditable_draft(self):
        if not self.ci_low <= self.probability <= self.ci_high:
            raise ValueError("Estimated probability must be inside its confidence interval")
        if self.ci_high - self.ci_low < 0.3 - 1e-12:
            raise ValueError("Pipeline estimates require a confidence interval at least 0.3 wide")
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Pipeline estimate source ids must be unique")
        selected = set(self.selected_source_ids)
        if not selected.issubset(source_ids):
            raise ValueError("Every selected source id must identify a recorded source")
        logged_sources = {
            source_id
            for entry in self.search_log
            if entry.outcome == "candidate"
            for source_id in entry.source_ids
        }
        if not selected.issubset(logged_sources):
            raise ValueError("Every selected source must appear in a candidate search log entry")
        sequences = [entry.sequence for entry in self.search_log]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("Pipeline research log sequences must be contiguous and ordered")
        selected_sources = [source for source in self.sources if source.id in selected]
        if not any(
            source.observation_date or source.published_date or source.retrieved_date
            for source in selected_sources
        ):
            raise ValueError("Pipeline estimates require a dated selected source")
        text = " ".join((self.reasoning, *self.assumptions)).casefold()
        if re.search(r"independence product|marginal product|p\s*\(.+\)\s*[x×*]\s*p\s*\(", text):
            raise ValueError("Independence products cannot become transition evidence")
        joint_sources = [source for source in selected_sources if source.supports_joint_outcome]
        if self.method == "joint_outcome_synthesis" and not joint_sources:
            raise ValueError("Joint outcome synthesis requires a selected joint outcome source")
        if self.predictor_values and (
            self.method != "joint_outcome_synthesis" or not joint_sources
        ):
            raise ValueError(
                "Predictor-conditioned estimates require selected joint outcome evidence"
            )
        if any(key.casefold() == "mbti" for key in self.predictor_values) and not joint_sources:
            raise ValueError("MBTI estimates require population-specific joint outcome evidence")
        return self

    @property
    def uncertainty(self) -> float:
        return max(0.5, self.ci_high - self.ci_low)

    @property
    def source_date(self) -> str:
        dates = [
            value
            for source in self.sources
            if source.id in self.selected_source_ids
            for value in (
                source.observation_date,
                source.published_date,
                source.retrieved_date,
            )
            if value is not None
        ]
        return max(dates)

    @property
    def source_summary(self) -> str:
        selected = set(self.selected_source_ids)
        return "; ".join(source.title for source in self.sources if source.id in selected)
