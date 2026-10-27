import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ai_settings import AISourceProvenance
from .auto_import_requirements import CanonicalFieldRequirement, canonical_requirement

PlaceLevel = Literal["region", "country", "city"]
CurrentFieldStatus = Literal["missing", "inherited", "imputed", "estimated"]
AttemptStatus = Literal[
    "draft",
    "researching",
    "awaiting_mapping_confirmation",
    "ready",
    "not_found",
    "rejected",
    "promoted",
]
EvidenceKind = Literal["measured", "estimated"]
SourceKind = Literal[
    "official_statistics",
    "census",
    "research_article",
    "representative_survey",
    "news",
    "user_url",
    "user_upload",
    "user_text",
]
SearchOutcome = Literal["no_result", "candidate", "rejected", "error"]
MappingConfidence = Literal["exact", "alias", "unknown"]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextPlace(ResearchModel):
    level: Literal["region", "country"]
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()


class PlaceFeatureTarget(ResearchModel):
    level: PlaceLevel
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    population: int = Field(ge=0)
    current_status: CurrentFieldStatus
    scope: str = Field(default="shared", min_length=1)
    as_of: date = Field(default_factory=date.today)
    country_code: str | None = None
    local_names: dict[str, str] = Field(default_factory=dict)
    dominant_languages: tuple[str, ...] = ()
    place_aliases: tuple[str, ...] = ()
    context_places: tuple[ContextPlace, ...] = ()


class UserSourceInput(ResearchModel):
    kind: Literal["url", "upload", "text"]
    name: str = Field(min_length=1)
    locator: str | None = None
    content: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def has_source(self):
        if self.kind == "url" and not self.locator:
            raise ValueError("A URL source needs a locator")
        if self.kind in {"upload", "text"} and not self.content:
            raise ValueError(f"A {self.kind} source needs content")
        return self


class SearchStep(ResearchModel):
    sequence: int = Field(ge=1)
    language: str = Field(min_length=2)
    language_name: str = Field(min_length=1)
    query: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    source_kind: SourceKind


class SearchPlan(ResearchModel):
    languages: tuple[str, ...]
    steps: tuple[SearchStep, ...]


class SourceCandidate(ResearchModel):
    candidate_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = Field(min_length=1)
    url: str | None = None
    source_kind: SourceKind
    feature: str = Field(min_length=1)
    place: str = Field(min_length=1)
    place_level: PlaceLevel
    denominator: str | None = None
    population: int | None = Field(default=None, ge=0)
    observation_date: date | None = None
    published_date: date | None = None
    time_unit: str | None = None
    unit: str | None = None
    distribution: dict[str, float] = Field(default_factory=dict)
    evidence_kind: Literal["measured", "hint"]
    credible: bool
    credibility_reason: str
    language: str = "en"
    original_excerpt: str = Field(min_length=1)
    translated_excerpt: str | None = None
    sample_size: int | None = Field(default=None, ge=1)
    source_version: str = "unknown"
    license: str = "unknown"
    ai_provenance: AISourceProvenance | None = None


class VerificationCheck(ResearchModel):
    name: Literal[
        "credibility",
        "feature",
        "place",
        "denominator",
        "population",
        "date",
        "time_basis",
        "unit",
        "distribution",
        "translation",
        "evidence_kind",
    ]
    passed: bool
    expected: str
    actual: str
    reason: str


class SourceVerification(ResearchModel):
    candidate_id: str
    accepted: bool
    direct_measurement: bool
    checks: tuple[VerificationCheck, ...]
    reasons: tuple[str, ...]


class RejectedSource(ResearchModel):
    candidate: SourceCandidate
    verification: SourceVerification


class ResearchLogEntry(ResearchModel):
    sequence: int = Field(ge=1)
    origin: Literal["user", "automatic"]
    language: str
    engine: str
    query_or_source: str
    source_kind: SourceKind
    outcome: SearchOutcome
    candidate_ids: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()


class LabelMapping(ResearchModel):
    source_label: str
    proposed_label: str | None = None
    confidence: MappingConfidence
    reason: str


class MappingPreview(ResearchModel):
    version: str
    rows: tuple[LabelMapping, ...]
    needs_confirmation: Literal[True] = True


class ConfirmedLabelMapping(ResearchModel):
    source_label: str
    target_label: str | None


class MappingConfirmation(ResearchModel):
    confirmed: bool
    mappings: tuple[ConfirmedLabelMapping, ...]


class SourceExtraction(ResearchModel):
    candidate_id: str
    title: str
    extracted_distribution: dict[str, float]
    weight: float = Field(gt=0)
    weight_basis: str


class PercentageInterval(ResearchModel):
    lower: float = Field(ge=0, le=100)
    upper: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def ordered(self):
        if self.upper < self.lower:
            raise ValueError("Uncertainty interval upper bound must be at least its lower bound")
        return self


class EstimateTrace(ResearchModel):
    method: Literal["weighted_compositional_estimate"] = "weighted_compositional_estimate"
    extractions: tuple[SourceExtraction, ...]
    calculation: tuple[str, ...]
    assumptions: tuple[str, ...]
    confidence_intervals: dict[str, PercentageInterval]
    better_data_needed: str


class AutoImportAttempt(ResearchModel):
    attempt_id: str
    target: PlaceFeatureTarget
    requirement: CanonicalFieldRequirement
    status: AttemptStatus
    result_kind: EvidenceKind | None = None
    user_sources: tuple[UserSourceInput, ...] = ()
    search_plan: SearchPlan
    search_log: tuple[ResearchLogEntry, ...] = ()
    sources: tuple[SourceCandidate, ...] = ()
    rejected_sources: tuple[RejectedSource, ...] = ()
    selected_source_ids: tuple[str, ...] = ()
    verifications: tuple[SourceVerification, ...] = ()
    mapping_preview: MappingPreview | None = None
    mapping_confirmed: bool = False
    proposed_distribution: dict[str, float] | None = None
    mapped_distribution: dict[str, float] | None = None
    estimate_trace: EstimateTrace | None = None
    languages_searched: tuple[str, ...] = ()
    failure_reason: str | None = None
    promotion_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ResearchProvider(Protocol):
    def inspect_user_source(
        self,
        source: UserSourceInput,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]: ...

    def search(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]: ...


LANGUAGE_NAMES = {
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
}
FALLBACK_COUNTRY_LANGUAGES = {
    "CN": ("zh",),
    "JP": ("ja",),
    "IN": ("hi",),
    "KR": ("ko",),
    "MX": ("es",),
    "BR": ("pt",),
    "DE": ("de",),
    "FR": ("fr",),
    "IT": ("it",),
    "RU": ("ru",),
}
FEATURE_TERMS = {
    "age_sex": {
        "en": "age and sex population distribution",
        "zh": "年龄 性别 人口 分布",
        "ja": "年齢 性別 人口 分布",
        "es": "distribución de población por edad y sexo",
        "fr": "répartition de la population par âge et sexe",
        "de": "Bevölkerung nach Alter und Geschlecht",
        "pt": "distribuição da população por idade e sexo",
    },
    "income": {
        "en": "income distribution",
        "zh": "收入 分布",
        "ja": "所得 分布",
        "es": "distribución de ingresos",
        "fr": "distribution des revenus",
        "de": "Einkommensverteilung",
        "pt": "distribuição de renda",
    },
    "education": {
        "en": "educational attainment distribution",
        "zh": "教育程度 分布",
        "ja": "教育水準 分布",
        "es": "distribución del nivel educativo",
        "fr": "répartition du niveau d'études",
        "de": "Bildungsabschluss Verteilung",
        "pt": "distribuição de escolaridade",
    },
    "ideology_economic": {
        "en": "economic ideology survey distribution",
        "zh": "经济 意识形态 调查 分布",
        "ja": "経済 イデオロギー 調査 分布",
    },
    "ideology_state": {
        "en": "authoritarian democratic values survey distribution",
        "zh": "威权 民主 价值观 调查 分布",
        "ja": "権威主義 民主主義 価値観 調査 分布",
    },
    "ideology_cultural": {
        "en": "traditional progressive values survey distribution",
        "zh": "传统 进步 价值观 调查 分布",
        "ja": "伝統 進歩 価値観 調査 分布",
    },
    "household_size": {
        "en": "household size distribution",
        "zh": "家庭 户规模 分布",
        "ja": "世帯 人員 分布",
        "es": "distribución del tamaño del hogar",
        "fr": "répartition de la taille des ménages",
        "de": "Haushaltsgröße Verteilung",
        "pt": "distribuição do tamanho do domicílio",
    },
}
SOURCE_TERMS = {
    "official_statistics": {
        "en": "official statistics",
        "zh": "官方 统计",
        "ja": "公的統計",
    },
    "research_article": {"en": "research article", "zh": "研究 论文", "ja": "研究 論文"},
    "representative_survey": {
        "en": "representative survey",
        "zh": "代表性 调查",
        "ja": "代表 調査",
    },
    "news": {"en": "local news", "zh": "当地 新闻", "ja": "地域 ニュース"},
}
LOCAL_ENGINES = {
    "zh": {
        "official_statistics": "National Bureau of Statistics of China",
        "research_article": "CNKI",
        "representative_survey": "Baidu",
        "news": "Baidu News",
    },
    "ja": {
        "official_statistics": "e-Stat / Statistics Bureau of Japan",
        "research_article": "CiNii / J-STAGE",
        "representative_survey": "Yahoo Japan",
        "news": "Yahoo Japan News",
    },
    "en": {
        "official_statistics": "Official statistics and census catalogs",
        "research_article": "Google Scholar",
        "representative_survey": "Bing",
        "news": "Bing News",
    },
}
SEARCH_SOURCE_ORDER: tuple[SourceKind, ...] = (
    "official_statistics",
    "research_article",
    "representative_survey",
    "news",
)
MAPPING_VERSION = "atlas-auto-import-labels-v1"


def _base_language(language: str) -> str:
    return language.strip().replace("_", "-").split("-", 1)[0].lower()


@lru_cache(maxsize=1)
def _country_info_languages() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[2] / "data" / "countryInfo.txt"
    if not path.exists():
        return FALLBACK_COUNTRY_LANGUAGES
    result: dict[str, tuple[str, ...]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) <= 15:
            continue
        languages = tuple(
            dict.fromkeys(
                _base_language(value)
                for value in columns[15].split(",")
                if value.strip()
            )
        )
        if languages:
            result[columns[0].upper()] = languages
    return {**FALLBACK_COUNTRY_LANGUAGES, **result}


def research_languages(target: PlaceFeatureTarget) -> tuple[str, ...]:
    supplied = tuple(_base_language(value) for value in target.dominant_languages if value)
    detected = _country_info_languages().get((target.country_code or "").upper(), ())
    local = supplied or detected
    ordered = list(dict.fromkeys(local[:3]))
    if not ordered:
        ordered.append("en")
    elif "en" not in ordered:
        ordered.append("en")
    return tuple(ordered)


def _localized_term(terms: dict[str, str], language: str) -> str:
    return terms.get(language, terms["en"])


def build_search_plan(target: PlaceFeatureTarget) -> SearchPlan:
    requirement = canonical_requirement(target.feature_id)
    languages = research_languages(target)
    steps = []
    for language in languages:
        place_name = target.local_names.get(language, target.place_label)
        feature_term = _localized_term(FEATURE_TERMS[requirement.feature_id], language)
        engines = LOCAL_ENGINES.get(language, {})
        for source_kind in SEARCH_SOURCE_ORDER:
            source_term = _localized_term(SOURCE_TERMS[source_kind], language)
            engine = engines.get(
                source_kind,
                f"{LANGUAGE_NAMES.get(language, language)} local web and statistics catalogs",
            )
            steps.append(
                SearchStep(
                    sequence=len(steps) + 1,
                    language=language,
                    language_name=LANGUAGE_NAMES.get(language, language),
                    query=f"{place_name} {feature_term} {source_term}",
                    engine=engine,
                    source_kind=source_kind,
                )
            )
    return SearchPlan(languages=languages, steps=tuple(steps))


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold().strip()
    return " ".join(re.sub(r"[^\w\u3400-\u9fff]+", " ", decomposed).split())


def _age_sex_label(label: str) -> str | None:
    normalized = _normalized(label).replace("歳", "").replace("岁", "")
    female = any(token in normalized for token in ("female", "women", "woman", "女性", "女子"))
    male = not female and any(
        token in normalized for token in ("male", "men", "man", "男性", "男子")
    )
    if not female and not male:
        return None
    sex = "female" if female else "male"
    numbers = re.findall(r"\d+", normalized)
    if len(numbers) == 1 and (
        any(token in normalized for token in ("plus", "over", "以上")) or "+" in label
    ):
        age = f"{numbers[0]}_plus"
    elif len(numbers) == 1:
        age = numbers[0]
    else:
        return None
    proposed = f"{sex}_{age}"
    return proposed if proposed in canonical_requirement("age_sex").canonical_values else None


def propose_label_mapping(
    distribution: dict[str, float], requirement: CanonicalFieldRequirement
) -> MappingPreview:
    rows = []
    canonical_by_normalized = {
        _normalized(value): value for value in requirement.canonical_values
    }
    aliases = {_normalized(source): target for source, target in requirement.label_aliases.items()}
    for source_label in distribution:
        normalized = _normalized(source_label)
        proposed = canonical_by_normalized.get(normalized)
        confidence: MappingConfidence = "exact"
        reason = "Exact canonical label"
        if proposed is None and requirement.feature_id == "age_sex":
            proposed = _age_sex_label(source_label)
            confidence = "alias" if proposed else "unknown"
            reason = "Age and sex label normalized" if proposed else "No canonical age-sex match"
        if proposed is None and normalized in aliases:
            proposed = aliases[normalized]
            confidence = "alias"
            reason = "Versioned canonical alias"
        if proposed is None and requirement.allows_source_categories and source_label.strip():
            proposed = source_label.strip()
            confidence = "alias"
            reason = "Source-defined band retained for explicit confirmation"
        if proposed is None:
            confidence = "unknown"
            reason = "Human mapping required; no label was guessed"
        rows.append(
            LabelMapping(
                source_label=source_label,
                proposed_label=proposed,
                confidence=confidence,
                reason=reason,
            )
        )
    return MappingPreview(version=MAPPING_VERSION, rows=tuple(rows))


def _matches(actual: str | None, expected: tuple[str, ...]) -> bool:
    if not actual:
        return False
    normalized = _normalized(actual)
    return any(normalized == _normalized(value) for value in expected)


def _distribution_reason(
    candidate: SourceCandidate,
    requirement: CanonicalFieldRequirement,
) -> tuple[bool, str]:
    if not candidate.distribution:
        return False, "No distribution was extracted"
    values = tuple(candidate.distribution.values())
    if any(not math.isfinite(value) for value in values):
        return False, "Distribution contains a non-finite value"
    if any(value < 0 or value > 100 for value in values):
        return False, "Distribution values must be between 0 and 100"
    total = sum(values)
    if not math.isclose(total, requirement.distribution_total, abs_tol=0.5):
        return False, (
            f"Distribution totals {total:g}; expected {requirement.distribution_total:g}"
        )
    if requirement.feature_id.startswith("ideology_"):
        bounds = [
            float(value)
            for label in candidate.distribution
            for value in re.findall(r"-?\d+(?:\.\d+)?", label)
        ]
        if not bounds or any(value < -1 or value > 1 for value in bounds):
            return False, "Ideology axis categories need numeric bounds from -1 to +1"
    return True, f"Distribution totals {total:g}"


def verify_candidate(
    candidate: SourceCandidate,
    target: PlaceFeatureTarget,
    requirement: CanonicalFieldRequirement,
) -> SourceVerification:
    feature_expected = (requirement.feature_id, requirement.name, *requirement.feature_aliases)
    place_expected = (
        target.place_id,
        target.place_label,
        *target.local_names.values(),
        *target.place_aliases,
    )
    feature_match = _matches(candidate.feature, feature_expected)
    exact_place_match = candidate.place_level == target.level and _matches(
        candidate.place, place_expected
    )
    contextual_place_match = candidate.evidence_kind == "hint" and any(
        candidate.place_level == context.level
        and _matches(
            candidate.place,
            (context.place_id, context.place_label, *context.aliases),
        )
        for context in target.context_places
    )
    place_match = exact_place_match or contextual_place_match
    denominator_match = _matches(candidate.denominator, requirement.accepted_denominators)
    population_match = candidate.population is not None and candidate.population > 0
    date_match = bool(
        candidate.observation_date
        and candidate.published_date
        and candidate.observation_date <= target.as_of
        and candidate.published_date <= target.as_of
    )
    time_basis_match = _matches(candidate.time_unit, (requirement.time_unit,))
    unit_match = _matches(candidate.unit, requirement.accepted_units)
    distribution_match, distribution_reason = _distribution_reason(candidate, requirement)
    translation_match = candidate.language == "en" or bool(candidate.translated_excerpt)
    direct_measurement = (
        candidate.evidence_kind == "measured"
        and candidate.source_kind != "news"
        and exact_place_match
    )
    evidence_match = candidate.evidence_kind == "hint" or direct_measurement
    checks = (
        VerificationCheck(
            name="credibility",
            passed=candidate.credible,
            expected="Credible source with a stated basis",
            actual=candidate.credibility_reason,
            reason=candidate.credibility_reason,
        ),
        VerificationCheck(
            name="feature",
            passed=feature_match,
            expected=requirement.name,
            actual=candidate.feature,
            reason="Feature matches" if feature_match else "Source measures a different feature",
        ),
        VerificationCheck(
            name="place",
            passed=place_match,
            expected=f"{target.level}: {target.place_label}",
            actual=f"{candidate.place_level}: {candidate.place}",
            reason=(
                "Place matches"
                if exact_place_match
                else (
                    "Broader contextual place is usable only as an estimate hint"
                    if contextual_place_match
                    else "Source is for a different place or level"
                )
            ),
        ),
        VerificationCheck(
            name="denominator",
            passed=denominator_match,
            expected=requirement.denominator,
            actual=candidate.denominator or "not stated",
            reason="Denominator matches"
            if denominator_match
            else "Denominator is missing or does not match",
        ),
        VerificationCheck(
            name="population",
            passed=population_match,
            expected="A stated positive population or sample universe",
            actual=str(candidate.population) if candidate.population is not None else "not stated",
            reason="Population is stated" if population_match else "Population is missing",
        ),
        VerificationCheck(
            name="date",
            passed=date_match,
            expected=f"Stated observation and publication dates on or before {target.as_of}",
            actual=(
                f"observed {candidate.observation_date or 'not stated'}; "
                f"published {candidate.published_date or 'not stated'}"
            ),
            reason=(
                "Observation and publication dates pass the availability cutoff"
                if date_match
                else "Observation or publication date is missing or after the availability cutoff"
            ),
        ),
        VerificationCheck(
            name="time_basis",
            passed=time_basis_match,
            expected=requirement.time_unit,
            actual=candidate.time_unit or "not stated",
            reason="Time basis matches"
            if time_basis_match
            else "Time basis is missing or incompatible",
        ),
        VerificationCheck(
            name="unit",
            passed=unit_match,
            expected=", ".join(requirement.accepted_units),
            actual=candidate.unit or "not stated",
            reason="Unit matches" if unit_match else "Unit is missing or incompatible",
        ),
        VerificationCheck(
            name="distribution",
            passed=distribution_match,
            expected=f"Values in range totaling {requirement.distribution_total:g}",
            actual=distribution_reason,
            reason=distribution_reason,
        ),
        VerificationCheck(
            name="translation",
            passed=translation_match,
            expected="Original text and an English translation for non-English evidence",
            actual="translation present" if candidate.translated_excerpt else "original text only",
            reason="Provenance is displayable in English"
            if translation_match
            else "Non-English evidence needs a translation",
        ),
        VerificationCheck(
            name="evidence_kind",
            passed=evidence_match,
            expected="Measured evidence or an explicitly labelled estimate hint",
            actual=candidate.evidence_kind,
            reason="Evidence classification accepted"
            if evidence_match
            else "News cannot establish a direct measured distribution",
        ),
    )
    reasons = tuple(check.reason for check in checks if not check.passed)
    return SourceVerification(
        candidate_id=candidate.candidate_id,
        accepted=not reasons,
        direct_measurement=not reasons and direct_measurement,
        checks=checks,
        reasons=reasons,
    )


def _wide_interval(value: float) -> PercentageInterval:
    width = 30.0
    lower = max(0.0, value - width / 2)
    upper = min(100.0, value + width / 2)
    if upper - lower < width and lower == 0:
        upper = min(100.0, width)
    if upper - lower < width and upper == 100:
        lower = max(0.0, 100 - width)
    return PercentageInterval(lower=round(lower, 6), upper=round(upper, 6))


def derive_estimate(
    candidates: list[SourceCandidate], requirement: CanonicalFieldRequirement
) -> tuple[dict[str, float], EstimateTrace, tuple[str, ...]]:
    if not candidates:
        raise ValueError("An estimate needs at least one credible hint")
    grouped: dict[tuple[str, ...], list[SourceCandidate]] = defaultdict(list)
    for candidate in candidates:
        label_key = tuple(sorted(_normalized(label) for label in candidate.distribution))
        grouped[label_key].append(candidate)
    compatible = max(
        grouped.values(), key=lambda values: (len(values), -candidates.index(values[0]))
    )
    excluded = tuple(
        candidate.candidate_id for candidate in candidates if candidate not in compatible
    )
    source_labels = list(compatible[0].distribution)
    normalized_labels = {_normalized(label): label for label in source_labels}
    totals: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    extractions = []
    for candidate in compatible:
        raw_total = sum(candidate.distribution.values())
        normalized_distribution = {
            normalized_labels[_normalized(label)]: value * 100 / raw_total
            for label, value in candidate.distribution.items()
        }
        weight = float(candidate.sample_size or 1)
        weight_basis = (
            f"reported sample size {candidate.sample_size}"
            if candidate.sample_size
            else "equal source weight because no sample size was reported"
        )
        for label, value in normalized_distribution.items():
            totals[label] += value * weight
        total_weight += weight
        extractions.append(
            SourceExtraction(
                candidate_id=candidate.candidate_id,
                title=candidate.title,
                extracted_distribution={
                    label: round(value, 6) for label, value in normalized_distribution.items()
                },
                weight=weight,
                weight_basis=weight_basis,
            )
        )
    distribution = {label: round(value / total_weight, 6) for label, value in totals.items()}
    rounding_delta = 100 - sum(distribution.values())
    first_label = next(iter(distribution))
    distribution[first_label] = round(distribution[first_label] + rounding_delta, 6)
    intervals = {label: _wide_interval(value) for label, value in distribution.items()}
    calculation = (
        "Normalize each extracted source distribution to 100 percent.",
        "Weight each source by its reported sample size; use equal source weight when absent.",
        "Average matching categories and preserve the source categories for human mapping.",
        "Assign a 30 percentage-point uncertainty interval to every estimated share.",
    )
    assumptions = (
        "The selected surveys or reports are informative for the target place.",
        "Differences in sampling frame and field date are not corrected without microdata.",
        "This estimate is descriptive only and is ineligible for coefficient fitting.",
    )
    trace = EstimateTrace(
        extractions=tuple(extractions),
        calculation=calculation,
        assumptions=assumptions,
        confidence_intervals=intervals,
        better_data_needed=requirement.better_data_needed,
    )
    return distribution, trace, excluded


def apply_confirmed_mapping(
    distribution: dict[str, float],
    preview: MappingPreview,
    confirmation: MappingConfirmation,
    requirement: CanonicalFieldRequirement,
) -> dict[str, float]:
    if not confirmation.confirmed:
        raise ValueError("Mapping must be explicitly confirmed")
    expected_labels = {row.source_label for row in preview.rows}
    supplied = {row.source_label for row in confirmation.mappings}
    if supplied != expected_labels or len(supplied) != len(confirmation.mappings):
        raise ValueError("Confirmed mappings must cover every source label exactly once")
    mapped: dict[str, float] = defaultdict(float)
    canonical = set(requirement.canonical_values)
    target_labels = [
        (row.target_label or "").strip()
        for row in confirmation.mappings
        if (row.target_label or "").strip()
    ]
    if len(target_labels) != len(set(target_labels)):
        raise ValueError("Each source category must map to a distinct canonical category")
    for row in confirmation.mappings:
        target_label = (row.target_label or "").strip()
        if not target_label:
            raise ValueError(f"Choose a canonical label for {row.source_label}")
        if canonical and target_label not in canonical:
            raise ValueError(f"{target_label} is not a canonical label for {requirement.name}")
        mapped[target_label] += distribution[row.source_label]
    total = sum(mapped.values())
    if not math.isclose(total, requirement.distribution_total, abs_tol=0.5):
        raise ValueError(
            f"Mapped distribution totals {total:g}; expected {requirement.distribution_total:g}"
        )
    return {label: round(value, 6) for label, value in mapped.items()}

