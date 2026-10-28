import csv
import io
import ipaddress
import json
import os
import re
import socket
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..ai_settings import AISourceProvenance
from ..llm_gateway import AIProviderError
from .auto_import_requirements import CanonicalFieldRequirement
from .auto_import_research import (
    PlaceFeatureTarget,
    ResearchLogEntry,
    SearchStep,
    SourceCandidate,
    UserSourceInput,
)

MAX_RESEARCH_BYTES = 2_000_000
MAX_PDF_RESEARCH_BYTES = 25_000_000
MAX_PAGE_TEXT = 40_000
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[SourceCandidate]


class _EstimateCategoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: str = Field(min_length=1)
    percentage: float = Field(ge=0, le=100)
    confidence_lower: float = Field(ge=0, le=100)
    confidence_upper: float = Field(ge=0, le=100)


class _EstimateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: tuple[_EstimateCategoryRecord, ...] = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    source_ids_used: tuple[str, ...]

    @model_validator(mode="after")
    def has_unique_categories(self):
        category_ids = [category.category_id for category in self.categories]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("Estimate category IDs must be unique")
        return self

    def distribution_maps(
        self,
    ) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
        distribution = {
            category.category_id: category.percentage for category in self.categories
        }
        confidence_intervals = {
            category.category_id: (
                category.confidence_lower,
                category.confidence_upper,
            )
            for category in self.categories
        }
        return distribution, confidence_intervals


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_endtag(self, tag: str):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._anchor_text).strip()))
            self._href = None
            self._anchor_text = []

    def handle_data(self, data: str):
        value = " ".join(data.split())
        if value:
            self.text.append(value)
            if self._href:
                self._anchor_text.append(value)


class _TableCellParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag: str):
        if tag in {"td", "th"} and self._cell is not None:
            value = " ".join(" ".join(self._cell).split())
            if value:
                self.cells.append(value)
            self._cell = None

    def handle_data(self, data: str):
        if self._cell is not None:
            self._cell.append(data)


class PublicResearchProvider:
    def __init__(self, fixture_path: str | Path | None = None, ai_provider=None):
        self.fixture_path = (
            Path(fixture_path or os.getenv("PETRATERRIUM_RESEARCH_FIXTURE", ""))
            if fixture_path or os.getenv("PETRATERRIUM_RESEARCH_FIXTURE")
            else None
        )
        self.ai_provider = ai_provider
        self.client = httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "Petraterrium data atlas research/0.2"},
        )

    def inspect_user_source(
        self,
        source: UserSourceInput,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]:
        if source.kind == "url":
            content, content_type = self._download(source.locator or "")
            return self._extract(
                content,
                source.locator,
                content_type,
                target,
                requirement,
                "user_url",
                source.language,
            )
        return self._extract(
            source.content or "",
            source.locator or source.name,
            "text/plain",
            target,
            requirement,
            "user_upload" if source.kind == "upload" else "user_text",
            source.language,
        )

    def search(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]:
        fixture = self._fixture_candidates(step, target)
        if fixture is not None:
            return fixture
        search_url = _search_url(step.engine, step.query)
        body, content_type = self._download(search_url)
        links = _result_links(body, content_type, search_url)
        candidates = []
        for link in links[:3]:
            try:
                content, page_type = self._download(link)
                candidates.extend(
                    self._extract(
                        content,
                        link,
                        page_type,
                        target,
                        requirement,
                        step.source_kind,
                        step.language,
                    )
                )
            except (httpx.HTTPError, ValueError, OSError):
                continue
        return candidates

    def synthesize_estimate(
        self,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
        search_log: tuple[ResearchLogEntry, ...],
        candidates: tuple[SourceCandidate, ...],
    ) -> SourceCandidate:
        if self.ai_provider is None:
            raise AIProviderError(
                "ai_provider_unavailable",
                "No AI source is configured for research synthesis.",
            )
        payload = json.dumps(
            {
                "target": target.model_dump(mode="json"),
                "requirement": requirement.model_dump(mode="json"),
                "search_log": [entry.model_dump(mode="json") for entry in search_log],
                "candidate_evidence": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "title": candidate.title,
                        "url": candidate.url,
                        "source_kind": candidate.source_kind,
                        "place": candidate.place,
                        "language": candidate.language,
                        "distribution": candidate.distribution,
                        "excerpt": candidate.original_excerpt,
                        "translation": candidate.translated_excerpt,
                        "credibility_reason": candidate.credibility_reason,
                    }
                    for candidate in candidates
                ],
            },
            ensure_ascii=False,
        )
        try:
            generated = self.ai_provider.generate_structured(
                payload,
                _EstimateDraft,
                system_prompt=(
                    "Produce a transparent place-specific estimated distribution after the app's "
                    "ordered research attempts. Use accepted or partial evidence when present, "
                    "then related country or regional evidence, and finally a "
                    "maximum-uncertainty prior. Use only canonical category IDs when the "
                    "requirement supplies them. Return one category record per distribution "
                    "category, with its percentage and confidence bounds. Percentages must be "
                    "finite values from 0 to 100 and sum to exactly 100. Explain every crosswalk, "
                    "assumption, and source contribution. Never describe an estimate as measured. "
                    "Every confidence interval must be at least 30 percentage points wide."
                ),
                prompt_version="atlas-research-synthesis-v1",
            )
        except AIProviderError as error:
            if requirement.feature_id == "specialization":
                return _specialization_crosswalk_estimate(
                    target,
                    requirement,
                    candidates,
                    str(error),
                )
            raise
        draft = generated.output
        distribution, confidence_intervals = draft.distribution_maps()
        return SourceCandidate(
            title=f"Petraterrium research synthesis for {target.place_label}",
            source_kind="expert_commentary",
            feature=requirement.feature_id,
            place=target.place_label,
            place_level=target.level,
            denominator=requirement.denominator,
            population=max(1, target.population),
            observation_date=target.as_of,
            published_date=target.as_of,
            time_unit=requirement.time_unit,
            unit=requirement.accepted_units[0],
            distribution=distribution,
            evidence_kind="hint",
            credible=True,
            credibility_reason=draft.reasoning,
            language="en",
            original_excerpt=draft.reasoning,
            source_version="atlas-research-synthesis-v1",
            license=(
                "Project-generated estimate; upstream source rights remain with publishers"
            ),
            estimate_reasoning=draft.reasoning,
            estimate_assumptions=draft.assumptions,
            estimate_confidence_intervals=confidence_intervals,
            estimate_source_ids=tuple(
                source_id
                for source_id in draft.source_ids_used
                if any(candidate.candidate_id == source_id for candidate in candidates)
            ),
            ai_provenance=generated.provenance,
        )

    def _fixture_candidates(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
    ) -> list[SourceCandidate] | None:
        if self.fixture_path is None:
            return None
        records = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        candidates = []
        matched = False
        for record in records.get("searches", []):
            match = record.get("match", {})
            if any(
                match.get(key) not in (None, value)
                for key, value in (
                    ("place_id", target.place_id),
                    ("feature_id", target.feature_id),
                    ("language", step.language),
                    ("engine", step.engine),
                    ("source_kind", step.source_kind),
                )
            ):
                continue
            matched = True
            candidates.extend(
                SourceCandidate.model_validate(candidate)
                for candidate in record.get("candidates", [])
            )
        return candidates if matched else []

    def _download(self, url: str) -> tuple[str, str]:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Research URLs must use HTTP or HTTPS")
            _require_public_host(parsed.hostname)
            request_headers = {}
            if (urlparse(current_url).hostname or "").casefold() == "sdmx.oecd.org":
                request_headers["Accept"] = "text/csv"
            with self.client.stream("GET", current_url, headers=request_headers) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Research redirect has no destination")
                    if redirect_count == MAX_REDIRECTS:
                        raise ValueError("Research source exceeds the redirect limit")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "text/plain")
                size_limit = (
                    MAX_PDF_RESEARCH_BYTES
                    if _media_type(content_type) == "application/pdf"
                    else MAX_RESEARCH_BYTES
                )
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > size_limit:
                        raise ValueError("Research source exceeds the configured size limit")
                encoding = response.encoding or "utf-8"
            return _decode_research_content(bytes(content), content_type, encoding), content_type
        raise ValueError("Research source exceeds the redirect limit")

    def _extract(
        self,
        content: str,
        locator: str | None,
        content_type: str,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
        source_kind: str,
        language: str | None,
    ) -> list[SourceCandidate]:
        source_specific = _source_specific_candidates(
            content,
            locator,
            content_type,
            target,
            requirement,
            source_kind,
            language,
        )
        if source_specific is not None:
            return source_specific
        structured = _structured_candidates(content, content_type)
        if structured:
            return [
                _attribute_candidate(candidate, locator, source_kind, language)
                for candidate in structured
            ]
        text = _visible_text(content, content_type)[:MAX_PAGE_TEXT]
        if not text:
            return []
        if self.ai_provider is None:
            raise AIProviderError(
                "ai_provider_unavailable",
                "No AI source is configured for research extraction. Choose OpenAI CLI or "
                "OpenAI API in AI Settings; no fallback was attempted.",
            )
        payload = json.dumps(
            {
                "target": target.model_dump(mode="json"),
                "requirement": requirement.model_dump(mode="json"),
                "source_url": locator,
                "source_kind": source_kind,
                "expected_language": language,
                "source_text": text,
            },
            ensure_ascii=False,
        )
        prompt = (
            "Extract only explicitly stated distributions and metadata from the supplied "
            "source. Return no candidate when feature, place, denominator, observation date, "
            "publication date, time basis, units, and "
            "category values are not stated. Preserve a short original-language excerpt and "
            "translate it to English when needed. Classify news and indirect survey figures "
            "as hints. A complete official national percentage table may omit an absolute "
            "population while retaining its declared national denominator. Never calculate, "
            "infer, complete, or guess a missing value."
        )
        generated = self.ai_provider.generate_structured(
            payload,
            _CandidateEnvelope,
            system_prompt=prompt,
            prompt_version="atlas-source-extraction-v1",
        )
        result = generated.output
        return [
            _attribute_candidate(
                candidate.model_dump(mode="json"),
                locator,
                source_kind,
                language,
                generated.provenance,
            )
            for candidate in result.candidates
        ]


def _media_type(content_type: str) -> str:
    return content_type.partition(";")[0].strip().casefold()


def _decode_research_content(content: bytes, content_type: str, encoding: str) -> str:
    if _media_type(content_type) != "application/pdf":
        return content.decode(encoding, errors="replace")
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        raise ValueError("Research PDF could not be read") from exc


def _require_public_host(hostname: str) -> None:
    addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    for address in addresses:
        value = ipaddress.ip_address(address)
        if not value.is_global:
            raise ValueError("Research URLs cannot target local or private network addresses")


def _attribute_candidate(
    value: dict,
    locator: str | None,
    source_kind: str,
    expected_language: str | None,
    ai_provenance: AISourceProvenance | None = None,
) -> SourceCandidate:
    candidate = SourceCandidate.model_validate(value)
    supplied_language = value.get("language")
    language = supplied_language or expected_language or candidate.language or "unknown"
    user_source = source_kind in {"user_url", "user_upload", "user_text"}
    if source_kind == "user_url":
        url = locator
    elif user_source:
        url = None
    else:
        url = locator
    trusted = _trusted_source_metadata(url)
    updates = {
        "url": url,
        "source_kind": trusted.get("source_kind", source_kind),
        "language": language,
        "ai_provenance": ai_provenance,
    }
    if candidate.license.strip().casefold() in {"", "unknown", "not stated"}:
        updates["license"] = trusted.get("license", candidate.license)
    if candidate.source_version.strip().casefold() in {"", "unknown", "not stated"}:
        updates["source_version"] = trusted.get(
            "source_version", candidate.source_version
        )
    return SourceCandidate.model_validate(
        candidate.model_copy(update=updates).model_dump(mode="python")
    )


def _trusted_source_metadata(url: str | None) -> dict[str, str]:
    hostname = (urlparse(url).hostname or "").casefold() if url else ""
    if hostname == "uis.unesco.org" or hostname.endswith(".uis.unesco.org"):
        return {
            "source_kind": "official_statistics",
            "license": "CC BY-SA 4.0",
            "source_version": "UNESCO UIS Data Browser",
        }
    if hostname == "oecd.org" or hostname.endswith(".oecd.org"):
        return {
            "source_kind": "official_statistics",
            "license": "OECD Terms and Conditions",
            "source_version": "OECD Data Explorer",
        }
    if hostname == "moe.gov.cn" or hostname.endswith(".moe.gov.cn"):
        return {
            "source_kind": "official_statistics",
            "license": "not stated",
            "source_version": "China Ministry of Education national statistics",
        }
    if hostname == "nuc.edu.ng" or hostname.endswith(".nuc.edu.ng"):
        return {
            "source_kind": "official_statistics",
            "license": "not stated",
            "source_version": "Nigerian University System Statistical Digest 2019",
        }
    if hostname == "hec.gov.pk" or hostname.endswith(".hec.gov.pk"):
        return {
            "source_kind": "official_statistics",
            "license": "not stated",
            "source_version": "HEC Higher Education Data Repository Annual Report 2022-23",
        }
    return {}


UIS_FIELD_CODES = {
    "FOSGP.5T8.FUK": "00",
    "FOSGP.5T8.F110": "01",
    "FOSGP.5T8.F200": "02",
    "FOSGP.5T8.F300": "03",
    "FOSGP.5T8.F400": "04",
    "FOSGP.5T8.F500": "05",
    "FOSGP.5T8.F600": "06",
    "FOSGP.5T8.F700": "07",
    "FOSGP.5T8.F800": "08",
    "FOSGP.5T8.F900": "09",
    "FOSGP.5T8.F1000": "10",
}

CHINA_MOE_DISCIPLINES = {
    "哲学": "Philosophy",
    "经济学": "Economics",
    "法学": "Law",
    "教育学": "Education",
    "文学": "Literature",
    "历史学": "History",
    "理学": "Science",
    "工学": "Engineering",
    "农学": "Agriculture",
    "医学": "Medicine",
    "管理学": "Management",
    "艺术学": "Art",
}

NIGERIA_NUC_DISCIPLINES = {
    "Administration and Management": r"Administration\s+and\s+Management",
    "Sciences": r"Sciences",
    "Social Sciences": r"Social\s+Sciences",
    "Education": r"Education",
    "Engineering and Technology": r"Engineering\s+and\s+Technology",
    "Arts": r"Arts",
    "Agriculture": r"Agriculture",
    "Basic Medical and Health Sciences": r"Basic\s+Medical\s+and\s+Health\s+Sciences",
    "Computing": r"Computing",
    "Law": r"Law",
    "Environmental Sciences": r"Environmental\s+Sciences",
    "Medicine": r"Medicine",
    "Pharmacy": r"Pharmacy",
    "Veterinary Medicine": r"Veterinary\s+Medicine",
}

PAKISTAN_HEC_DISCIPLINE_ORDER = (
    "01",
    "09",
    "08",
    "07",
    "06",
    "05",
    "04",
    "03",
    "02",
    "00",
    "10",
    None,
)

SPECIALIZATION_CROSSWALK = {
    "philosophy": "02",
    "economics": "03",
    "law": "04",
    "education": "01",
    "literature": "02",
    "history": "02",
    "science": "05",
    "sciences": "05",
    "social sciences": "03",
    "engineering": "07",
    "engineering and technology": "07",
    "agriculture": "08",
    "medicine": "09",
    "management": "04",
    "administration and management": "04",
    "art": "02",
    "arts": "02",
    "basic medical and health sciences": "09",
    "computing": "06",
    "environmental sciences": "05",
    "pharmacy": "09",
    "veterinary medicine": "08",
}


def _specialization_crosswalk_estimate(
    target: PlaceFeatureTarget,
    requirement: CanonicalFieldRequirement,
    candidates: tuple[SourceCandidate, ...],
    synthesis_error: str,
) -> SourceCandidate:
    sources = tuple(
        candidate
        for candidate in candidates
        if candidate.feature == requirement.feature_id
        and candidate.credible
        and candidate.distribution
    )
    values = {label: 0.0 for label in requirement.canonical_values}
    aliases = {
        _normalized_crosswalk_label(label): target_label
        for label, target_label in requirement.label_aliases.items()
    }
    mapped_labels: list[str] = []
    unmapped_labels: list[str] = []
    unmapped_total = 0.0
    for source in sources:
        for label, value in source.distribution.items():
            normalized_label = _normalized_crosswalk_label(label)
            target_label = None
            if label in values:
                target_label = label
            elif normalized_label in aliases:
                target_label = aliases[normalized_label]
            elif normalized_label in SPECIALIZATION_CROSSWALK:
                target_label = SPECIALIZATION_CROSSWALK[normalized_label]
            if target_label in values:
                values[target_label] += value
                mapped_labels.append(label)
            else:
                unmapped_total += value
                unmapped_labels.append(label)
    assumptions = [
        "Broad source disciplines were crosswalked to ISCED-F 2013 broad fields.",
        "The distribution is descriptive population evidence and does not imply a "
        "behavioral coefficient.",
    ]
    if unmapped_total:
        allocation = unmapped_total / len(values)
        values = {label: value + allocation for label, value in values.items()}
        assumptions.append(
            "Unmapped source share was spread evenly across all ISCED-F broad fields "
            "with maximum uncertainty."
        )
    if not mapped_labels:
        values = {label: 1.0 for label in values}
        assumptions.append(
            "No source category had a versioned crosswalk, so the draft uses a "
            "maximum-uncertainty uniform prior."
        )
    distribution = _normalized_percentage_distribution(values)
    intervals = {
        label: _wide_percentage_interval(value)
        for label, value in distribution.items()
    }
    source_ids = tuple(dict.fromkeys(source.candidate_id for source in sources))
    latest_observation = max(
        (source.observation_date for source in sources if source.observation_date),
        default=target.as_of,
    )
    latest_publication = max(
        (source.published_date for source in sources if source.published_date),
        default=target.as_of,
    )
    population = max(
        (source.sample_size or source.population or 0 for source in sources),
        default=target.population,
    )
    mapped_summary = ", ".join(dict.fromkeys(mapped_labels)) or "none"
    unmapped_summary = ", ".join(dict.fromkeys(unmapped_labels)) or "none"
    reasoning = (
        f"Configured synthesis was unavailable ({synthesis_error}). The in-app research "
        f"pipeline applied its versioned ISCED-F crosswalk to source categories. "
        f"Mapped categories: {mapped_summary}. Unmapped categories: {unmapped_summary}."
    )
    return SourceCandidate(
        title=f"Petraterrium ISCED-F crosswalk estimate for {target.place_label}",
        source_kind="expert_commentary",
        feature=requirement.feature_id,
        place=target.place_label,
        place_level=target.level,
        denominator=requirement.denominator,
        population=max(1, population),
        observation_date=latest_observation,
        published_date=latest_publication,
        time_unit=requirement.time_unit,
        unit=requirement.accepted_units[0],
        distribution=distribution,
        evidence_kind="hint",
        credible=True,
        credibility_reason=reasoning,
        language=sources[0].language if sources else "en",
        original_excerpt=reasoning,
        translated_excerpt=(
            reasoning if sources and sources[0].language != "en" else None
        ),
        source_version="atlas-specialization-crosswalk-v1",
        license=(
            "Project-generated estimate; upstream source rights remain with publishers"
        ),
        estimate_reasoning=reasoning,
        estimate_assumptions=tuple(assumptions),
        estimate_confidence_intervals=intervals,
        estimate_source_ids=source_ids,
    )


def _normalized_crosswalk_label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _wide_percentage_interval(value: float) -> tuple[float, float]:
    if value <= 17.5:
        return 0.0, 35.0
    if value >= 82.5:
        return 65.0, 100.0
    return round(value - 17.5, 9), round(value + 17.5, 9)


def _normalized_percentage_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        raise ValueError("A percentage distribution needs a positive total")
    normalized = {
        label: round(value * 100 / total, 9) for label, value in values.items()
    }
    first_label = next(iter(normalized))
    normalized[first_label] += 100 - sum(normalized.values())
    return normalized


def _source_specific_candidates(
    content: str,
    locator: str | None,
    content_type: str,
    target: PlaceFeatureTarget,
    requirement: CanonicalFieldRequirement,
    source_kind: str,
    language: str | None,
) -> list[SourceCandidate] | None:
    if requirement.feature_id != "specialization":
        return None
    hostname = (urlparse(locator).hostname or "").casefold() if locator else ""
    if hostname == "api.uis.unesco.org":
        values = _uis_specialization_candidate(content, target)
    elif hostname == "sdmx.oecd.org":
        values = _oecd_specialization_candidate(content, target)
    elif (
        target.country_code == "CN"
        and (hostname == "moe.gov.cn" or hostname.endswith(".moe.gov.cn"))
    ):
        values = _china_moe_specialization_candidate(content, locator, target)
    elif (
        target.country_code == "NG"
        and (hostname == "nuc.edu.ng" or hostname.endswith(".nuc.edu.ng"))
    ):
        values = _nigeria_nuc_specialization_candidate(content, locator, target)
    elif (
        target.country_code == "PK"
        and (hostname == "hec.gov.pk" or hostname.endswith(".hec.gov.pk"))
    ):
        values = _pakistan_hec_specialization_candidate(content, target)
    else:
        return None
    if values is None:
        return []
    return [
        _attribute_candidate(
            values,
            locator,
            source_kind,
            language,
        )
    ]


def _uis_specialization_candidate(
    content: str,
    target: PlaceFeatureTarget,
) -> dict | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    records = [
        record
        for record in payload.get("records", [])
        if record.get("indicatorId") in UIS_FIELD_CODES
        and isinstance(record.get("value"), (int, float))
    ]
    if not records:
        return None
    distribution = _normalized_percentage_distribution(
        {
            UIS_FIELD_CODES[record["indicatorId"]]: float(record["value"])
            for record in records
        }
    )
    years = {int(record["year"]) for record in records}
    if len(years) != 1:
        return None
    metadata = payload.get("indicatorMetadata", [])
    updated = next(
        (
            item.get("lastDataUpdate")
            for item in metadata
            if item.get("lastDataUpdate")
        ),
        None,
    )
    try:
        published_date = datetime.strptime(updated, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        published_date = date.today()
    year = years.pop()
    footnotes = tuple(
        dict.fromkeys(
            footnote.get("value", "")
            for record in records
            for footnote in record.get("footnotes", [])
            if footnote.get("value")
        )
    )
    release = next(
        (
            item.get("lastDataUpdateDescription")
            for item in metadata
            if item.get("lastDataUpdateDescription")
        ),
        "UIS indicator release",
    )
    return {
        "title": f"UNESCO UIS tertiary graduates by field · {target.place_label}",
        "source_kind": "official_statistics",
        "feature": "specialization",
        "place": target.place_label,
        "place_level": target.level,
        "denominator": "tertiary graduates",
        "population": None,
        "observation_date": date(year, 12, 31).isoformat(),
        "published_date": published_date.isoformat(),
        "time_unit": "graduation year",
        "unit": "percent",
        "distribution": distribution,
        "evidence_kind": "measured",
        "credible": True,
        "credibility_reason": (
            "National administrative percentage distribution published by UNESCO UIS"
        ),
        "language": "en",
        "original_excerpt": "; ".join(footnotes) or "UNESCO UIS national submission",
        "source_version": str(release),
        "license": "CC BY-SA 4.0",
    }


def _oecd_specialization_candidate(
    content: str,
    target: PlaceFeatureTarget,
) -> dict | None:
    rows = list(csv.DictReader(io.StringIO(content)))
    relevant = [
        row
        for row in rows
        if row.get("EDUCATION_FIELD", "") in {f"F{code:02d}" for code in range(11)}
        and row.get("OBS_VALUE")
    ]
    if not relevant:
        return None
    years = {int(row["TIME_PERIOD"]) for row in relevant}
    if len(years) != 1:
        return None
    values = {
        row["EDUCATION_FIELD"][1:]: float(row["OBS_VALUE"])
        for row in relevant
    }
    unit = relevant[0].get("UNIT_MEASURE")
    population = None
    if unit != "PT_ST":
        population = round(sum(values.values()))
        total = sum(values.values())
        if total <= 0:
            return None
        values = _normalized_percentage_distribution(values)
    else:
        values = _normalized_percentage_distribution(values)
    year = years.pop()
    return {
        "title": f"OECD UOE tertiary graduates by field · {target.place_label}",
        "source_kind": "official_statistics",
        "feature": "specialization",
        "place": target.place_label,
        "place_level": target.level,
        "denominator": "tertiary graduates",
        "population": population,
        "observation_date": date(year, 12, 31).isoformat(),
        "published_date": date.today().isoformat(),
        "time_unit": "graduation year",
        "unit": "percent",
        "distribution": values,
        "evidence_kind": "measured",
        "credible": True,
        "credibility_reason": (
            "National UOE graduate records published by the OECD Data Explorer"
        ),
        "language": "en",
        "original_excerpt": (
            f"{len(relevant)} ISCED-F broad-field rows for {year}; "
            f"source unit {unit or 'not stated'}"
        ),
        "sample_size": population,
        "source_version": f"OECD UOE {year}",
        "license": "OECD Terms and Conditions",
    }


def _china_moe_specialization_candidate(
    content: str,
    locator: str | None,
    target: PlaceFeatureTarget,
) -> dict | None:
    parser = _TableCellParser()
    parser.feed(content)
    cells = parser.cells
    if not any("毕业生数" in cell and "Graduates" in cell for cell in cells):
        return None
    values: dict[str, float] = {}
    for index, cell in enumerate(cells[:-1]):
        discipline = next(
            (label for prefix, label in CHINA_MOE_DISCIPLINES.items() if cell.startswith(prefix)),
            None,
        )
        if discipline is None:
            continue
        try:
            values[discipline] = float(cells[index + 1].replace(",", ""))
        except ValueError:
            return None
    if len(values) != len(CHINA_MOE_DISCIPLINES):
        return None
    total = round(sum(values.values()))
    if total <= 0:
        return None
    observation_match = re.search(r"/(20\d{2})/quanguo/", locator or "")
    published_match = re.search(r"/t(20\d{6})_", locator or "")
    if observation_match is None or published_match is None:
        return None
    observation_year = int(observation_match.group(1))
    published_date = datetime.strptime(published_match.group(1), "%Y%m%d").date()
    return {
        "title": f"China higher education graduates by discipline · {target.place_label}",
        "source_kind": "official_statistics",
        "feature": "specialization",
        "place": target.place_label,
        "place_level": target.level,
        "denominator": "tertiary graduates",
        "population": total,
        "observation_date": date(observation_year, 12, 31).isoformat(),
        "published_date": published_date.isoformat(),
        "time_unit": "graduation year",
        "unit": "percent",
        "distribution": _normalized_percentage_distribution(values),
        "evidence_kind": "hint",
        "credible": True,
        "credibility_reason": (
            "Official national graduate counts require a transparent discipline-to-ISCED-F "
            "crosswalk before use"
        ),
        "language": "zh",
        "original_excerpt": (
            f"教育部全国普通本科分学科毕业生数，{observation_year}年，总计{total}人"
        ),
        "translated_excerpt": (
            f"Ministry of Education national undergraduate graduates by discipline, "
            f"{observation_year}; {total} graduates"
        ),
        "sample_size": total,
        "source_version": f"China MOE national higher education statistics {observation_year}",
        "license": "not stated",
    }


def _nigeria_nuc_specialization_candidate(
    content: str,
    locator: str | None,
    target: PlaceFeatureTarget,
) -> dict | None:
    start_match = re.search(
        r"Table\s+3\.5\.5:\s+Total\s+Enrolment\s+by\s+Discipline",
        content,
        re.IGNORECASE,
    )
    if start_match is None:
        return None
    end_match = re.search(
        r"(?m)^\s*3\.6\s+Undergraduate\s+New\s+Entrants",
        content[start_match.start() :],
        re.IGNORECASE,
    )
    if end_match is None:
        return None
    table = content[
        start_match.start() : start_match.start() + end_match.start()
    ]
    matched_labels = []
    for label, pattern in NIGERIA_NUC_DISCIPLINES.items():
        match = re.search(rf"(?m)^\s*{pattern}\s+", table, re.IGNORECASE)
        if match is None:
            return None
        matched_labels.append((match.start(), match.end(), label))
    matched_labels.sort()
    values: dict[str, float] = {}
    for index, (_start, end, label) in enumerate(matched_labels):
        next_start = (
            matched_labels[index + 1][0]
            if index + 1 < len(matched_labels)
            else table.casefold().rfind("grand total")
        )
        numbers = re.findall(r"\d[\d,]*", table[end:next_start])
        if not numbers:
            return None
        values[label] = float(numbers[-1].replace(",", ""))
    total = round(sum(values.values()))
    if total <= 0:
        return None
    publication_match = re.search(r"/uploads/(20\d{2})/(\d{2})/", locator or "")
    if publication_match is None:
        return None
    published_date = date(
        int(publication_match.group(1)),
        int(publication_match.group(2)),
        1,
    )
    return {
        "title": f"Nigerian university enrolment by discipline · {target.place_label}",
        "source_kind": "official_statistics",
        "feature": "specialization",
        "place": target.place_label,
        "place_level": target.level,
        "denominator": "tertiary students",
        "population": total,
        "observation_date": date(2019, 12, 31).isoformat(),
        "published_date": published_date.isoformat(),
        "time_unit": "academic year",
        "unit": "percent",
        "distribution": _normalized_percentage_distribution(values),
        "evidence_kind": "hint",
        "credible": True,
        "credibility_reason": (
            "Official national university enrolment counts require a transparent "
            "discipline-to-ISCED-F crosswalk before use"
        ),
        "language": "en",
        "original_excerpt": (
            f"NUC Table 3.5.5, total enrolment by discipline, {total} students"
        ),
        "sample_size": total,
        "source_version": "Nigerian University System Statistical Digest 2019",
        "license": "not stated",
    }


def _pakistan_hec_specialization_candidate(
    content: str,
    target: PlaceFeatureTarget,
) -> dict | None:
    start_match = re.search(
        r"The\s+graph\s+represents\s+the\s+distribution\s+of\s+male\s+and\s+"
        r"female\s+students.*?academic\s+fields\.",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if start_match is None:
        return None
    end_match = re.search(
        r"Gender\s*-?\s*wise\s+Enrollment\s+in\s+Major\s+Disciplines\s*"
        r"\(2020\s*-\s*21\)",
        content[start_match.end() :],
        re.IGNORECASE,
    )
    if end_match is None:
        return None
    chart = content[
        start_match.end() : start_match.end() + end_match.start()
    ]
    counts = [
        int(value.replace(",", ""))
        for value in re.findall(r"\b\d[\d,]*\b", chart)[:24]
    ]
    if len(counts) != 24:
        return None
    female_counts = counts[:12]
    male_counts = counts[12:]
    values = {f"{code:02d}": 0.0 for code in range(11)}
    for code, female, male in zip(
        PAKISTAN_HEC_DISCIPLINE_ORDER,
        female_counts,
        male_counts,
        strict=True,
    ):
        if code is not None:
            values[code] = float(female + male)
    categorized_total = round(sum(values.values()))
    excluded_other = female_counts[-1] + male_counts[-1]
    if categorized_total <= 0 or excluded_other <= 0:
        return None
    return {
        "title": f"Pakistan tertiary enrolment by ISCED-F field · {target.place_label}",
        "source_kind": "official_statistics",
        "feature": "specialization",
        "place": target.place_label,
        "place_level": target.level,
        "denominator": "tertiary students",
        "population": categorized_total,
        "observation_date": date(2021, 6, 30).isoformat(),
        "published_date": date(2023, 7, 19).isoformat(),
        "time_unit": "academic year",
        "unit": "percent",
        "distribution": _normalized_percentage_distribution(values),
        "evidence_kind": "measured",
        "credible": True,
        "credibility_reason": (
            "Official national HEC enrolment counts use the ISCED-F broad-field labels; "
            f"{excluded_other} students labelled Other were excluded before normalization"
        ),
        "language": "en",
        "original_excerpt": (
            "HEC gender-wise enrolment in major disciplines, academic year 2020-21; "
            f"{categorized_total} categorized students and {excluded_other} labelled Other"
        ),
        "sample_size": categorized_total,
        "source_version": "HEC HEDR Annual Report 2022-23",
        "license": "not stated",
    }


def _search_url(engine: str, query: str) -> str:
    encoded = quote_plus(query)
    if engine.startswith("Bing") or engine in {
        "Official statistics and census catalogs",
        "Bing News",
    }:
        return f"https://www.bing.com/search?format=rss&q={encoded}"
    if engine == "National Bureau of Statistics of China":
        return f"https://www.stats.gov.cn/search/s?qt={encoded}"
    if engine == "CNKI":
        return f"https://kns.cnki.net/kns8s/defaultresult/index?kw={encoded}"
    if engine in {"Baidu", "Baidu News"}:
        return f"https://www.baidu.com/s?wd={encoded}"
    if engine == "e-Stat / Statistics Bureau of Japan":
        return f"https://www.e-stat.go.jp/stat-search?page=1&query={encoded}"
    if engine == "CiNii / J-STAGE":
        return f"https://cir.nii.ac.jp/all?q={encoded}"
    if engine in {"Yahoo Japan", "Yahoo Japan News"}:
        return f"https://search.yahoo.co.jp/search?p={encoded}"
    if engine == "KOSIS":
        return f"https://kosis.kr/search/search.do?query={encoded}"
    if engine == "Naver":
        return f"https://search.naver.com/search.naver?query={encoded}"
    if engine == "Naver News":
        return f"https://search.naver.com/search.naver?where=news&query={encoded}"
    if engine == "Google Scholar":
        return f"https://scholar.google.com/scholar?q={encoded}"
    if engine == "Rosstat":
        return f"https://rosstat.gov.ru/search?q={encoded}"
    if engine in {"Yandex", "Yandex News"}:
        return f"https://yandex.com/search/?text={encoded}"
    if engine == "eLIBRARY.RU":
        return f"https://elibrary.ru/query_results.asp?querybox={encoded}"
    if engine == "IBGE":
        return f"https://www.ibge.gov.br/busca.html?searchword={encoded}"
    if engine == "SciELO Brasil":
        return f"https://search.scielo.org/?q={encoded}&lang=pt"
    if engine in {"Google Brasil", "Google Notícias Brasil"}:
        return f"https://www.google.com/search?q={encoded}&gl=br&hl=pt-BR"
    if engine == "INEGI and local official catalogs":
        return f"https://www.inegi.org.mx/app/buscador/default.html?q={encoded}"
    if engine == "Redalyc / SciELO":
        return f"https://www.redalyc.org/busquedaArticuloFiltros.oa?q={encoded}"
    if engine in {"Google México", "Google Noticias México"}:
        return f"https://www.google.com/search?q={encoded}&gl=mx&hl=es-MX"
    if engine == "MoSPI India":
        return f"https://www.google.co.in/search?q=site%3Amospi.gov.in+{encoded}"
    if engine == "Census of India":
        return f"https://www.google.co.in/search?q=site%3Acensusindia.gov.in+{encoded}"
    if engine in {"Google India", "Google News India", "Google Scholar India"}:
        return f"https://www.google.co.in/search?q={encoded}&hl=hi"
    if engine == "BPS Statistics Indonesia":
        return f"https://www.google.co.id/search?q=site%3Abps.go.id+{encoded}&hl=id"
    if engine == "GARUDA Indonesia":
        return f"https://garuda.kemdikbud.go.id/documents?q={encoded}"
    if engine in {"Google Indonesia", "Google Berita Indonesia"}:
        return f"https://www.google.co.id/search?q={encoded}&hl=id"
    if engine == "Bangladesh Bureau of Statistics":
        return f"https://www.google.com/search?q=site%3Abbs.gov.bd+{encoded}&hl=bn"
    if engine == "BanglaJOL":
        return f"https://www.banglajol.info/index.php/index/search/search?query={encoded}"
    if engine in {"Google Bangladesh", "Google News Bangladesh"}:
        return f"https://www.google.com/search?q={encoded}&gl=bd&hl=bn"
    if engine == "Pakistan Bureau of Statistics":
        return f"https://www.google.com/search?q=site%3Apbs.gov.pk+{encoded}&gl=pk&hl=ur"
    if engine == "HEC Pakistan Research Repository":
        return f"https://www.google.com/search?q=site%3Aeprints.hec.gov.pk+{encoded}&gl=pk"
    if engine in {"Google Pakistan", "Google News Pakistan"}:
        return f"https://www.google.com/search?q={encoded}&gl=pk&hl=ur"
    return f"https://www.bing.com/search?format=rss&q={encoded}"


def _result_links(content: str, content_type: str, base_url: str) -> list[str]:
    links = []
    if "xml" in content_type or content.lstrip().startswith("<?xml"):
        try:
            root = ElementTree.fromstring(content)
            links.extend(
                element.text.strip() for element in root.findall(".//item/link") if element.text
            )
        except ElementTree.ParseError:
            pass
    parser = _PageParser()
    parser.feed(content)
    for href, _ in parser.links:
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        redirected = query.get("url", query.get("u", []))
        if redirected:
            candidate = unquote(redirected[0])
        if urlparse(candidate).scheme in {"http", "https"}:
            links.append(candidate)
    base_without_fragment = urlparse(base_url)._replace(fragment="").geturl()
    return list(
        dict.fromkeys(
            link
            for link in links
            if urlparse(link)._replace(fragment="").geturl() != base_without_fragment
        )
    )


def _visible_text(content: str, content_type: str) -> str:
    if "html" not in content_type and "<html" not in content[:500].casefold():
        return content
    parser = _PageParser()
    parser.feed(content)
    return "\n".join(parser.text)


def _structured_candidates(content: str, content_type: str) -> list[dict]:
    text = _visible_text(content, content_type).strip()
    for candidate_text in (content.strip(), text):
        if not candidate_text:
            continue
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "candidates" in parsed:
            return list(parsed["candidates"])
        if isinstance(parsed, dict) and "distribution" in parsed:
            return [parsed]
        if isinstance(parsed, list) and all(isinstance(value, dict) for value in parsed):
            return parsed
    if "csv" in content_type or "," in text.partition("\n")[0]:
        rows = list(csv.DictReader(io.StringIO(text)))
        if rows and {"category", "value"}.issubset(rows[0]):
            metadata = {
                key: value for key, value in rows[0].items() if key not in {"category", "value"}
            }
            metadata["distribution"] = {row["category"]: float(row["value"]) for row in rows}
            return [metadata]
    return []
