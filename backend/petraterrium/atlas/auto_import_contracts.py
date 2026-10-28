from typing import Any, Literal

from pydantic import Field

from ..ai_settings import AISourceProvenance
from ..contracts import Contract


class AutoImportCanonicalValue(Contract):
    id: str
    label: str


class AutoImportDistributionRequirement(Contract):
    values: list[AutoImportCanonicalValue]
    denominator: str
    time_unit: str
    unit: str
    range: str | None
    total: str | None


class AutoImportTargetView(Contract):
    place_id: str
    place_label: str
    level: Literal["region", "country", "city"]
    country_code: str | None
    geonameid: int | None
    population: int = Field(ge=0)
    field_id: str
    field_label: str
    current_status: Literal["present", "inherited", "imputed", "estimated", "missing"]
    as_of: str
    required_distribution: AutoImportDistributionRequirement


class AutoImportQueueItemView(AutoImportTargetView):
    item_id: str
    missing_impact: int = Field(ge=0)
    priority: Literal["primary", "lower"]
    place_item_count: int = Field(ge=1)


class AutoImportQueuePageView(Contract):
    items: list[AutoImportQueueItemView]
    filtered_count: int = Field(ge=0)
    filtered_population: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    primary_count: int = Field(ge=0)
    primary_population: int = Field(ge=0)
    lower_priority_count: int = Field(ge=0)
    lower_priority_population: int = Field(ge=0)


class AutoImportMappingOption(Contract):
    id: str
    label: str


class AutoImportMappingColumn(Contract):
    column: str
    target: str | None
    ambiguous: bool
    samples: list[str]
    options: list[AutoImportMappingOption]


class AutoImportVerificationCheck(Contract):
    id: str
    label: str
    status: Literal["passed", "failed", "unknown"]
    detail: str


class AutoImportResearchSource(Contract):
    source_id: str
    title: str
    publisher: str
    url: str | None
    source_date: str | None
    published_date: str | None
    version: str | None
    licence: str | None
    language: str
    original_excerpt: str | None
    translated_excerpt: str | None
    accepted: bool
    rejection_reason: str | None
    ai_provenance: AISourceProvenance | None


class AutoImportSearchEntry(Contract):
    engine: str
    language: str
    query: str
    searched_at: str | None
    result_count: int = Field(ge=0)
    outcome: str
    rejection_reasons: list[str]


class AutoImportEstimateInput(Contract):
    label: str
    value: str
    source_id: str | None


class AutoImportEstimateTraceView(Contract):
    method: str
    calculation: str
    assumptions: list[str]
    inputs: list[AutoImportEstimateInput]
    confidence_interval: str
    source_ids_used: list[str]
    limitations: list[str]


class AutoImportDistributionChange(Contract):
    source_label: str
    target_label: str
    before: float
    after: float


class AutoImportAttemptView(Contract):
    attempt_id: str
    target: AutoImportTargetView
    stage: Literal["collecting", "mapping", "verifying", "review", "ready", "failed", "promoted"]
    mappings: list[AutoImportMappingColumn]
    verification: list[AutoImportVerificationCheck]
    sources: list[AutoImportResearchSource]
    search_log: list[AutoImportSearchEntry]
    evidence_kind: Literal["measured", "estimated"] | None
    estimate_trace: AutoImportEstimateTraceView | None
    candidate_values: dict[str, float | str | None]
    distribution_changes: list[AutoImportDistributionChange]
    draft_status: Literal["editable_draft", "confirmed", "promoted"]
    usable_in_demo: bool
    can_promote: bool
    error: str | None
    promoted_at: str | None
    promotion_id: str | None


class AutoImportBatchSummary(Contract):
    total: int = Field(ge=0)
    completed: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    ready: int = Field(ge=0)
    measured: int = Field(ge=0)
    estimated: int = Field(ge=0)
    failed: int = Field(ge=0)
    retryable_failed: int = Field(ge=0)
    promoted: int = Field(ge=0)


class AutoImportBatchItemView(Contract):
    item_id: str
    attempt_id: str | None
    target: AutoImportTargetView
    status: Literal["queued", "running", "ready", "failed", "promoted"]
    evidence_kind: Literal["measured", "estimated"] | None
    mappings: list[AutoImportMappingColumn]
    mapping_confirmed: bool
    can_promote: bool
    error: str | None


class AutoImportBatchView(Contract):
    batch_id: str
    status: Literal["queued", "running", "review", "partial", "complete", "failed"]
    summary: AutoImportBatchSummary
    items: list[AutoImportBatchItemView]
    created_at: str
    updated_at: str


class AutoImportEvidenceView(Contract):
    attempts: list[AutoImportAttemptView]


class AutoImportMappingEdit(Contract):
    column: str
    target: str | None = None


class AutoImportMappingReview(Contract):
    mappings: list[AutoImportMappingEdit]
    reviewed: bool
    distribution: dict[str, float] | None = None


class AutoImportPromotionRequest(Contract):
    redistribution_confirmed: bool


class AutoImportRerunRequest(Contract):
    source_tiers: list[
        Literal[
            "official_statistics",
            "census",
            "representative_survey",
            "research_article",
            "government_report",
            "university_report",
            "news",
            "online_opinion",
            "expert_commentary",
        ]
    ] = Field(default_factory=list)


class AutoImportExplicitSelection(Contract):
    mode: Literal["explicit"]
    item_ids: list[str]


class AutoImportAllFilteredSelection(Contract):
    mode: Literal["all_filtered"]
    query: dict[str, Any]
    excluded_item_ids: list[str] = Field(default_factory=list)


class AutoImportBatchRequest(Contract):
    scope: str
    as_of: str
    concurrency: int = Field(ge=1, le=32)
    selection: AutoImportExplicitSelection | AutoImportAllFilteredSelection


class AutoImportBatchPromotionRequest(Contract):
    mode: Literal["all_eligible", "selected"]
    item_ids: list[str] = Field(default_factory=list)
    mapping_confirmed: bool
    redistribution_confirmed: bool
