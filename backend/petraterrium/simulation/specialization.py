from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..atlas.auto_import_research import AutoImportAttempt, SourceCandidate

ISCED_F_LABELS = {
    "00": "Generic programmes and qualifications",
    "01": "Education",
    "02": "Arts and humanities",
    "03": "Social sciences, journalism and information",
    "04": "Business, administration and law",
    "05": "Natural sciences, mathematics and statistics",
    "06": "Information and communication technologies",
    "07": "Engineering, manufacturing and construction",
    "08": "Agriculture, forestry, fisheries and veterinary",
    "09": "Health and welfare",
    "10": "Services",
}
SPECIALIZATION_COUNTRY_CODES = (
    "IN",
    "CN",
    "US",
    "ID",
    "PK",
    "NG",
    "BR",
    "BD",
    "RU",
    "MX",
    "CA",
    "AU",
)


class SpecializationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class SpecializationSourceAttempt(SpecializationModel):
    original_title: str = Field(min_length=1)
    english_title: str = Field(min_length=1)
    url: str | None = Field(default=None, pattern=r"^https?://")
    publication_date: str | None = None
    language: str = Field(min_length=2)
    source_type: str = Field(min_length=1)
    place: str = Field(min_length=1)
    represented_population: str = Field(min_length=1)
    discovery_method: str = Field(min_length=1)
    query: str = Field(min_length=1)
    result_used: bool
    notes: str = Field(min_length=1)


class CountrySpecializationDistribution(SpecializationModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    country_name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    evidence_status: Literal["measured", "estimated"]
    source_evidence_status: Literal["measured", "estimated"]
    draft_status: Literal["editable_draft", "confirmed", "promoted"]
    pipeline_attempt_id: str = Field(min_length=1)
    population_basis: str = Field(min_length=1)
    reference_year: int = Field(ge=1900, le=2100)
    licence: str = Field(min_length=1)
    coverage_percent: float = Field(gt=0, le=100)
    isced_f_distribution: dict[str, float]
    uncertainty: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)
    mapping_notes: str = Field(min_length=1)
    sources_tried: tuple[SpecializationSourceAttempt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_distribution(self):
        expected = set(ISCED_F_LABELS)
        actual = set(self.isced_f_distribution)
        if actual != expected:
            raise ValueError(
                "ISCED-F distribution keys differ: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        if any(value < 0 or value > 100 for value in self.isced_f_distribution.values()):
            raise ValueError("ISCED-F distribution percentages must be between 0 and 100")
        total = sum(self.isced_f_distribution.values())
        if abs(total - 100) > 1e-6:
            raise ValueError(f"ISCED-F distribution sums to {total}, expected 100")
        if not any(source.result_used for source in self.sources_tried):
            raise ValueError("Specialization distribution requires at least one used source")
        return self

    @property
    def primary_sources(self) -> tuple[SpecializationSourceAttempt, ...]:
        return tuple(source for source in self.sources_tried if source.result_used)


class SpecializationCatalog(SpecializationModel):
    schema_version: Literal["1"] = "1"
    version: str = Field(min_length=1)
    mapping: Literal["ISCED-F 2013 broad fields"] = "ISCED-F 2013 broad fields"
    labels: dict[str, str]
    countries: tuple[CountrySpecializationDistribution, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_catalog(self):
        if self.labels != ISCED_F_LABELS:
            raise ValueError("Specialization catalog labels must match ISCED-F 2013")
        country_codes = [country.country_code for country in self.countries]
        if len(country_codes) != len(set(country_codes)):
            raise ValueError("Specialization catalog country codes must be unique")
        return self

    def country(self, country_code: str) -> CountrySpecializationDistribution:
        normalized = country_code.upper()
        for country in self.countries:
            if country.country_code == normalized:
                return country
        raise ValueError(f"No specialization distribution for {normalized}")


def default_specialization_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sources" / "specialization"


def _source_attempt(
    candidate: SourceCandidate,
    selected_source_ids: set[str],
) -> SpecializationSourceAttempt:
    return SpecializationSourceAttempt(
        original_title=candidate.title,
        english_title=candidate.title,
        url=candidate.url,
        publication_date=(
            candidate.published_date.isoformat() if candidate.published_date else None
        ),
        language=candidate.language,
        source_type=f"{candidate.source_kind} · {candidate.evidence_kind}",
        place=candidate.place,
        represented_population=(
            str(candidate.population)
            if candidate.population is not None
            else candidate.denominator or "Declared source denominator"
        ),
        discovery_method="In-app source inspection and validation",
        query=candidate.url or candidate.title,
        result_used=candidate.candidate_id in selected_source_ids,
        notes=(
            candidate.estimate_reasoning
            or candidate.credibility_reason
        ),
    )


def _search_attempts(attempt: AutoImportAttempt) -> tuple[SpecializationSourceAttempt, ...]:
    return tuple(
        SpecializationSourceAttempt(
            original_title=f"{entry.engine} search",
            english_title=f"{entry.engine} search",
            language=entry.language,
            source_type=entry.source_kind,
            place=attempt.target.place_label,
            represented_population=attempt.requirement.denominator,
            discovery_method=entry.engine,
            query=entry.query_or_source,
            result_used=False,
            notes=(
                f"{entry.outcome}; {len(entry.candidate_ids)} candidate(s)"
                + (
                    "; " + "; ".join(entry.rejection_reasons)
                    if entry.rejection_reasons
                    else ""
                )
            ),
        )
        for entry in attempt.search_log
    )


def _candidate_sources(attempt: AutoImportAttempt) -> tuple[SourceCandidate, ...]:
    return tuple(
        {
            candidate.candidate_id: candidate
            for candidate in (
                *attempt.sources,
                *(item.candidate for item in attempt.rejected_sources),
            )
        }.values()
    )


def _catalog_country(attempt: AutoImportAttempt) -> CountrySpecializationDistribution:
    if attempt.target.level != "country" or attempt.target.feature_id != "specialization":
        raise ValueError("Specialization pipeline receipt must target one country")
    if attempt.result_kind not in {"measured", "estimated"}:
        raise ValueError("Specialization pipeline receipt has no executable result")
    distribution = attempt.mapped_distribution or attempt.proposed_distribution
    if distribution is None:
        raise ValueError("Specialization pipeline receipt has no distribution")
    distribution_total = sum(distribution.values())
    if distribution_total <= 0:
        raise ValueError("Specialization pipeline receipt has a non-positive distribution")
    normalized_distribution = {
        key: round(float(value) * 100 / distribution_total, 9)
        for key, value in distribution.items()
    }
    first_label = next(iter(normalized_distribution))
    normalized_distribution[first_label] += 100 - sum(
        normalized_distribution.values()
    )
    candidates = _candidate_sources(attempt)
    selected = set(attempt.selected_source_ids)
    if attempt.estimate_trace:
        selected.update(attempt.estimate_trace.source_ids_used)
    selected.update(
        source_id
        for candidate in candidates
        if candidate.candidate_id in attempt.selected_source_ids
        for source_id in candidate.estimate_source_ids
    )
    source_attempts = tuple(
        _source_attempt(candidate, selected) for candidate in candidates
    )
    sources_tried = (*source_attempts, *_search_attempts(attempt))
    if not any(source.result_used for source in sources_tried):
        raise ValueError("Specialization receipt does not identify its used source")
    selected_candidates = [
        candidate for candidate in candidates if candidate.candidate_id in selected
    ]
    reference_years = [
        candidate.observation_date.year
        for candidate in selected_candidates
        if candidate.observation_date
    ]
    licences = sorted(
        {
            candidate.license
            for candidate in selected_candidates
            if candidate.license.strip()
        }
    )
    versions = sorted(
        {
            candidate.source_version
            for candidate in selected_candidates
            if candidate.source_version.strip()
        }
    )
    trace = attempt.estimate_trace
    if trace:
        interval_widths = [
            interval.upper - interval.lower
            for interval in trace.confidence_intervals.values()
        ]
        uncertainty = max(interval_widths, default=100) / 100
        reasoning = " ".join((*trace.calculation, *trace.assumptions))
    else:
        uncertainty = 0.05 if attempt.mapping_confirmed else 0.3
        reasoning = (
            "The in-app pipeline extracted and validated a complete national official "
            "distribution. The mapping remains an editable draft."
        )
    draft_status: Literal["editable_draft", "confirmed", "promoted"] = (
        "promoted"
        if attempt.status == "promoted"
        else "confirmed"
        if attempt.mapping_confirmed
        else "editable_draft"
    )
    executable_status: Literal["measured", "estimated"] = (
        "measured"
        if attempt.result_kind == "measured" and draft_status != "editable_draft"
        else "estimated"
    )
    source_population = next(
        (
            candidate.population
            for candidate in selected_candidates
            if candidate.population is not None
        ),
        None,
    )
    return CountrySpecializationDistribution(
        country_code=(attempt.target.country_code or attempt.target.place_id).upper(),
        country_name=attempt.target.place_label,
        version="|".join(versions) or f"pipeline-attempt-{attempt.attempt_id}",
        evidence_status=executable_status,
        source_evidence_status=attempt.result_kind,
        draft_status=draft_status,
        pipeline_attempt_id=attempt.attempt_id,
        population_basis=(
            f"{attempt.requirement.denominator}; N={source_population:,}"
            if source_population is not None
            else attempt.requirement.denominator
        ),
        reference_year=max(reference_years, default=attempt.target.as_of.year),
        licence=" · ".join(licences) or "Project-generated estimate",
        coverage_percent=100,
        isced_f_distribution=normalized_distribution,
        uncertainty=min(1, max(0, uncertainty)),
        reasoning=reasoning,
        mapping_notes=(
            f"{attempt.requirement.value_specification}; "
            f"mapping {attempt.mapping_preview.version if attempt.mapping_preview else 'pending'}"
        ),
        sources_tried=sources_tried,
    )


@lru_cache(maxsize=4)
def _load_specialization_catalog(directory: str) -> SpecializationCatalog:
    root = Path(directory)
    receipt_directory = root / "pipeline"
    countries = [
        _catalog_country(
            AutoImportAttempt.model_validate_json(path.read_text(encoding="utf-8"))
        )
        for path in sorted(receipt_directory.glob("*.json"))
    ]
    actual = {country.country_code for country in countries}
    expected = set(SPECIALIZATION_COUNTRY_CODES)
    if actual != expected:
        raise ValueError(
            "Specialization country coverage differs: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    versions = "|".join(
        f"{country.country_code}:{country.version}"
        for country in sorted(countries, key=lambda item: item.country_code)
    )
    return SpecializationCatalog(
        version=f"global-demo-specialization-v1|{versions}",
        labels=ISCED_F_LABELS,
        countries=tuple(sorted(countries, key=lambda item: item.country_code)),
    )


def load_specialization_catalog(
    directory: Path | None = None,
) -> SpecializationCatalog:
    return _load_specialization_catalog(
        str((directory or default_specialization_directory()).resolve())
    )


def sample_specialization(
    country: CountrySpecializationDistribution,
    rng: np.random.Generator,
) -> tuple[str, str]:
    codes = sorted(ISCED_F_LABELS)
    probabilities = np.asarray(
        [country.isced_f_distribution[code] for code in codes],
        dtype=np.float64,
    )
    probabilities /= probabilities.sum()
    code = str(rng.choice(codes, p=probabilities))
    return code, ISCED_F_LABELS[code]
