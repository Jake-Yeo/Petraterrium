from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from ..contracts import Contract
from ..dsl import ChoiceEvidence, FeatureRegistry

MarginalName = Literal[
    "age_sex",
    "income",
    "education",
    "ideology_economic",
    "ideology_state",
    "ideology_cultural",
    "household_size",
]
FieldStatus = Literal["present", "inherited", "imputed", "estimated", "missing"]
MarginalValue = dict[str, float] | float


class Provenance(Contract):
    import_id: str
    source: str
    source_date: str
    published_date: str
    version: str
    scope: str
    uploader: str


class MarginalField(Contract):
    field: MarginalName
    status: FieldStatus
    value: MarginalValue | None = None
    unit: str | None = None
    provenance: Provenance | None = None
    research_trace: dict[str, Any] | None = None
    suggested_source: str
    source_url: str


class LegacyMarginalField(Contract):
    field: Literal["ideology"] = "ideology"
    status: Literal["legacy_only"] = "legacy_only"
    value: MarginalValue
    unit: str
    provenance: Provenance
    predictive: Literal[False] = False


class BehaviourModel(Contract):
    country_code: str
    behaviour: str
    fitted: bool
    label_only: bool
    provenance: Provenance
    heldout_loss: float | None = None
    baseline_loss: float | None = None
    training_rows: int = 0
    heldout_rows: int = 0
    traits: list[str] = []


class AtlasCity(Contract):
    geonameid: int
    name: str
    asciiname: str
    country_code: str
    country_name: str
    admin1: str
    admin2: str
    latitude: float
    longitude: float
    population: int
    population_status: Literal["present", "missing"]
    timezone: str
    simulation_tier: Literal["simulated", "disaggregated"]
    simulation_ready: bool = False
    tier_reason: str
    coverage_percent: float
    inherited_coverage_percent: float
    resolved_coverage_percent: float
    status: FieldStatus
    coverage_state: Literal["full", "partial", "none"]
    fields: list[MarginalField]
    behaviour: list[BehaviourModel]
    density_per_km2: float | None = None
    density_provenance: Provenance | None = None


class CityDetail(Contract):
    city: AtlasCity
    missing_fields: list[MarginalName]
    direct_observation_gaps: list[MarginalName]
    history: list[Provenance]
    legacy_fields: list[LegacyMarginalField] = []
    revision: int
    simulation_note: str


class CoverageCounts(Contract):
    full: int
    partial: int
    none: int


class FieldCoverage(Contract):
    field: MarginalName
    present: int
    inherited: int
    imputed: int
    estimated: int
    missing: int
    direct_percent: float
    direct_plus_inherited_percent: float
    direct_population_percent: float
    direct_plus_inherited_population_percent: float
    imputed_population_percent: float
    estimated_population_percent: float


class AtlasSummary(Contract):
    total_cities: int
    total_population: int
    cities_without_population: int
    direct: CoverageCounts
    direct_plus_inherited: CoverageCounts
    fields: list[FieldCoverage]
    simulated_cities: int
    disaggregated_cities: int
    countries_with_fitted_behaviour: int
    revision: int
    scope: str
    as_of: str


class DataGap(Contract):
    geonameid: int
    city: str
    country_code: str
    population: int
    field: MarginalName
    status: FieldStatus
    suggested_source: str


class Backbone(Contract):
    loaded: bool = False
    source: str = "GeoNames cities500"
    source_url: str = "https://download.geonames.org/export/dump/cities500.zip"
    license: str = "CC BY 4.0"
    version: str = "not-loaded"
    downloaded_at: str | None = None
    source_date: str | None = None
    original_rows: int = 0
    retained_rows: int = 0
    excluded_rows: int = 0
    duplicate_rows: int = 0
    tier_policy: str = "Top three cities per country with at least 1,000,000 people"
    selection_policy: str = (
        "Full cities500, including its administrative-seat exceptions below 500;"
        " excludes PPLX, PPLQ, PPLW and PPLH"
    )


class AtlasCountry(Contract):
    country_code: str
    name: str
    cities: int


class AtlasScope(Contract):
    run_id: str
    label: str
    run_available: bool


class AtlasScopes(Contract):
    scopes: list[AtlasScope]


class AtlasOverview(Contract):
    summary: AtlasSummary
    cities: list[AtlasCity]
    filtered_count: int
    page: int
    page_size: int
    countries: list[AtlasCountry]
    gaps: list[DataGap]
    backbone: Backbone


class ImportMetadata(Contract):
    run_id: str = Field(min_length=1)
    kind: Literal["marginals", "behaviour", "population"] = "marginals"
    source: str = Field(min_length=1, max_length=200)
    source_date: date
    published_date: date
    version: str = Field(min_length=1, max_length=100)
    uploader: str = Field(default="local-user", min_length=1, max_length=100)
    source_id: str | None = None
    country_code: str | None = None
    unit: str = "percent"
    redistribution_allowed: bool = False
    processing_notes: list[str] = []

    @model_validator(mode="after")
    def no_future_data(self) -> "ImportMetadata":
        if self.source_date > date.today() or self.published_date > date.today():
            raise ValueError("Source and publication dates must not be in the future")
        if self.run_id == "shared":
            raise ValueError("Uploads belong to a run; promote a committed version explicitly")
        return self


class ColumnMapping(Contract):
    column: str
    target: str | None
    ambiguous: bool = False
    reason: str = ""


class MappingProposal(Contract):
    mappings: list[ColumnMapping]


class MappingAudit(Contract):
    provider: str
    model: str
    prompt_version: str
    estimated_cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    message: str


class ImportPreview(Contract):
    import_id: str
    filename: str
    metadata: ImportMetadata
    row_count: int
    sample_rows: list[dict[str, str | float | int | bool | None]]
    mappings: list[ColumnMapping]
    mapping_audit: MappingAudit
    status: Literal["awaiting_confirmation"] = "awaiting_confirmation"


class MappingConfirmation(Contract):
    mappings: list[ColumnMapping]
    confirmed: bool


class ValidationIssue(Contract):
    row: int
    field: str
    message: str


class ValidationReport(Contract):
    import_id: str
    valid: bool
    total_rows: int
    observations: int
    issues: list[ValidationIssue]
    missingness: dict[str, int]
    mapping_hash: str


class ImportCommit(Contract):
    mapping_hash: str
    confirmed: bool


class ImportVersion(Contract):
    import_id: str
    source: str
    source_date: str
    published_date: str
    version: str
    scope: str
    uploader: str
    kind: str
    filename: str
    rows: int
    status: str
    live_fields: int
    promoted_from: str | None = None
    redistribution_allowed: bool
    models: list[BehaviourModel] = []


class ImportHistory(Contract):
    versions: list[ImportVersion]


class Promotion(Contract):
    confirmed: bool
    redistribution_confirmed: bool


class AtlasSource(Contract):
    source_id: str
    name: str
    url: str
    access: Literal["public", "registration", "licensed"]
    license: str
    fields: list[str]
    adapter: str
    instructions: str
    download_hosts: list[str]


class RegistrySource(Contract):
    source_id: str
    source: str
    scope_order: int
    level: Literal["region", "country", "city"]
    access_status: Literal[
        "imported", "imported_aggregate", "unavailable", "available_remote"
    ]
    source_url: str
    version: str
    source_date: str
    license: str
    mapping: dict[str, Any]
    coverage: dict[str, Any]
    restriction_reason: str
    fallback: str
    required_action: str
    files: list[dict[str, Any]]


class SourceCatalog(Contract):
    sources: list[AtlasSource]
    llm_available: bool
    registry_sources: list[RegistrySource] = Field(default_factory=list)


class SourceFetch(Contract):
    url: str
    metadata: ImportMetadata
    access_confirmed: bool = False


class FeatureResolutionRecord(Contract):
    feature_id: str
    city: str
    country: str
    region: str
    status: str
    resolved_level: str
    source: str | None = None
    version: str | None = None
    source_date: str | None = None
    population: str | None = None
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    region_override: bool
    missing_requirement: str


class UniversalFeatureOverview(Contract):
    registry: FeatureRegistry
    resolutions: list[FeatureResolutionRecord]


class ChoiceEvidenceCatalog(Contract):
    rows: list[ChoiceEvidence]


class HierarchyRow(Contract):
    row_id: str
    level: Literal["global", "region", "subregion", "country", "city"]
    parent_id: str | None = None
    label: str
    country_code: str | None = None
    population: int = Field(ge=0)
    city_count: int = Field(ge=0)
    statuses: dict[str, FieldStatus]
    coverage_by_field: dict[str, float]
    region_override: bool = False
    weight_source: str
    children_paged: bool = False


class HierarchyOverview(Contract):
    rows: list[HierarchyRow]
    scope: str
    as_of: str
    resolution_order: list[str]
    mapping_version: str
