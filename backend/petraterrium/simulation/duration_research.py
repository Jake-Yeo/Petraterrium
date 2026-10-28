import csv
import io
import math
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .default_pipeline_contracts import (
    DefaultPipelineSource,
    DurationCandidate,
    DurationChosenResult,
    DurationDistribution,
    DurationInterval,
    DurationResearchOutput,
    DurationResearchRequest,
    DurationSearchLogEntry,
    DurationUncertainty,
)


@dataclass(frozen=True)
class FetchedDurationResource:
    url: str
    content: bytes
    content_type: str
    retrieved_at: datetime
    last_modified: str


class DurationSourceClient(Protocol):
    def fetch(self, url: str) -> FetchedDurationResource: ...


class DurationActivityMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    code_prefixes: tuple[str, ...] = Field(min_length=1)
    start_hour_min: int | None = Field(default=None, ge=0, le=23)
    start_hour_max: int | None = Field(default=None, ge=1, le=24)
    aggregation: str = Field(pattern=r"^(episode|respondent_day)$")
    evidence_kind: str = Field(pattern=r"^(measured|estimated)$")
    description: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_time_window(self):
        if (self.start_hour_min is None) != (self.start_hour_max is None):
            raise ValueError("Duration activity mapping time windows need both bounds")
        if (
            self.start_hour_min is not None
            and self.start_hour_max is not None
            and self.start_hour_min >= self.start_hour_max
        ):
            raise ValueError("Duration activity mapping time-window bounds must be ordered")
        return self


class DurationActivityMappingCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = Field(pattern=r"^1$")
    version: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    mappings: tuple[DurationActivityMapping, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_actions(self):
        action_ids = [mapping.action_id for mapping in self.mappings]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("Duration activity mappings must have unique action ids")
        return self


def default_duration_mapping_path() -> Path:
    return (
        Path(__file__).with_name("defaults")
        / "research"
        / "atus-2025-action-mappings.json"
    )


class HttpxDurationSourceClient:
    def __init__(self, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Petraterrium duration research pipeline/1.0"},
        )

    def fetch(self, url: str) -> FetchedDurationResource:
        with self.client.stream("GET", url) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 25_000_000:
                    raise ValueError("Duration research source exceeds 25 MB")
        return FetchedDurationResource(
            url=str(response.url),
            content=bytes(content),
            content_type=response.headers.get("content-type", "application/octet-stream"),
            retrieved_at=self.clock(),
            last_modified=response.headers.get("last-modified", "not stated"),
        )


@dataclass(frozen=True)
class _Episode:
    case_id: str
    duration_minutes: float
    code: str
    start_hour: int
    weight: float


class AtusDurationResearchPipeline:
    pipeline_version = "default-duration-research-v1"

    def __init__(
        self,
        client: DurationSourceClient | None = None,
        year: int = 2025,
        clock: Callable[[], datetime] | None = None,
        mapping_path: str | Path | None = None,
    ):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.client = client or HttpxDurationSourceClient(self.clock)
        self.year = year
        selected_mapping_path = Path(mapping_path or default_duration_mapping_path())
        self.mapping_catalog = DurationActivityMappingCatalog.model_validate_json(
            selected_mapping_path.read_text(encoding="utf-8")
        )
        self.mapping_by_action = {
            mapping.action_id: mapping for mapping in self.mapping_catalog.mappings
        }

    @staticmethod
    def catalog_url(year: int) -> str:
        return f"https://www.bls.gov/tus/data/datafiles-{year}.htm"

    @staticmethod
    def activity_url(year: int) -> str:
        return f"https://www.bls.gov/tus/datafiles/atusact-{year}.zip"

    @staticmethod
    def respondent_url(year: int) -> str:
        return f"https://www.bls.gov/tus/datafiles/atusresp-{year}.zip"

    @staticmethod
    def hetus_url() -> str:
        return (
            "https://ec.europa.eu/eurostat/en/web/microdata/collections-research/"
            "harmonised-european-time-use-surveys"
        )

    def research(self, actions: list[dict] | tuple[dict, ...]) -> DurationResearchOutput:
        if not actions:
            raise ValueError("Duration research needs at least one action")
        action_ids = tuple(action["id"] for action in actions)
        requests = tuple(
            DurationResearchRequest(
                action_id=action["id"],
                action_label=action["name"],
                target_place_id="GLOBAL",
                target_place_label="Global default",
                target_language="en",
                requested_source_tiers=(
                    "official_statistics",
                    "representative_survey",
                    "research_article",
                    "government_report",
                    "news",
                    "online_opinion",
                ),
            )
            for action in actions
        )
        resources: dict[str, FetchedDurationResource] = {}
        errors: dict[str, str] = {}
        urls = (
            self.catalog_url(self.year),
            self.activity_url(self.year),
            self.respondent_url(self.year),
            self.hetus_url(),
        )
        for url in urls:
            try:
                resources[url] = self.client.fetch(url)
            except Exception as error:
                errors[url] = str(error)
        candidates = self._candidates(actions, resources, errors)
        chosen = tuple(self._global_choice(candidate) for candidate in candidates)
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        logs = self._search_log(action_ids, candidate_ids, resources, errors)
        return DurationResearchOutput(
            requests=requests,
            search_log=logs,
            candidates=candidates,
            chosen_results=chosen,
        )

    def _candidates(
        self,
        actions: list[dict] | tuple[dict, ...],
        resources: dict[str, FetchedDurationResource],
        errors: dict[str, str],
    ) -> tuple[DurationCandidate, ...]:
        activity = resources.get(self.activity_url(self.year))
        respondent = resources.get(self.respondent_url(self.year))
        if activity is None or respondent is None:
            return tuple(self._prior_candidate(action, errors) for action in actions)
        episodes = _atus_episodes(activity.content, respondent.content)
        source = self._atus_source(activity, respondent)
        candidates = []
        for action in actions:
            mapping = self.mapping_by_action.get(action["id"])
            if mapping is None:
                candidates.append(
                    self._prior_candidate(
                        action,
                        {
                            **errors,
                            "mapping": (
                                f"No action mapping exists in {self.mapping_catalog.version}"
                            ),
                        },
                    )
                )
                continue
            action_episodes = tuple(
                episode for episode in episodes if _matches_mapping(mapping, episode)
            )
            if not action_episodes:
                candidates.append(self._prior_candidate(action, errors))
                continue
            candidates.append(
                _candidate_from_episodes(
                    action,
                    action_episodes,
                    source,
                    activity_mapping=mapping,
                    mapping_version=self.mapping_catalog.version,
                )
            )
        return tuple(candidates)

    def _atus_source(
        self,
        activity: FetchedDurationResource,
        respondent: FetchedDurationResource,
    ) -> DefaultPipelineSource:
        source_date = activity.last_modified
        if source_date == "not stated":
            source_date = respondent.last_modified
        return DefaultPipelineSource(
            source_id=f"atus-{self.year}-activity-microdata",
            title=f"American Time Use Survey {self.year} Activity and Respondent files",
            publisher="U.S. Bureau of Labor Statistics",
            url=self.catalog_url(self.year),
            source_kind="official_statistics",
            source_date=source_date,
            source_version=str(self.year),
            licence="U.S. government public data; BLS terms apply",
            population="U.S. civilian noninstitutional population age 15 and over",
            place_id="US",
            place_label="United States",
            language="en",
            engine="BLS official data catalog",
            retrieved_at=max(activity.retrieved_at, respondent.retrieved_at),
        )

    def _prior_candidate(self, action: dict, errors: dict[str, str]) -> DurationCandidate:
        duration = action["duration"]
        if "duration_min_hours" in duration:
            minimum_hours = float(duration["duration_min_hours"])
            median_hours = float(duration["duration_median_hours"])
            maximum_hours = float(duration["duration_max_hours"])
        else:
            minimum_hours = float(duration["minimum_minutes"]) / 60.0
            median_hours = float(duration["typical_minutes"]) / 60.0
            maximum_hours = float(duration["maximum_minutes"]) / 60.0
        distribution = DurationDistribution(
            minimum_hours=minimum_hours,
            median_hours=median_hours,
            maximum_hours=maximum_hours,
            shape=duration["shape"],
        )
        error_text = "; ".join(sorted(set(errors.values()))) or "No mapped episode remained"
        source = DefaultPipelineSource(
            source_id="petraterrium-duration-prior-v1",
            title="Petraterrium explicit duration prior",
            publisher="Petraterrium",
            url="petraterrium:duration-prior-v1",
            source_kind="project_estimate",
            source_date=self.clock().date().isoformat(),
            source_version="1",
            licence="Project data",
            population="Global structural demo",
            place_id="GLOBAL",
            place_label="Global default",
            language="en",
            engine="Petraterrium deterministic estimator",
            retrieved_at=self.clock(),
        )
        return DurationCandidate(
            candidate_id=f"duration-prior-{action['id']}",
            action_id=action["id"],
            evidence_kind="estimated",
            duration=distribution,
            source_provenance=(source,),
            sample_size=1,
            effective_sample_size=1.0,
            denominator="One explicit structural prior for an action occurrence",
            mapping="No verified official episode mapping was available in this run",
            reasoning=(
                "The pipeline preserved the prior range as an estimated draft after all "
                f"configured official-source attempts failed: {error_text}"
            ),
            assumptions=(
                "The prior is usable only as an estimated demo value.",
                "Its uncertainty spans the full retained range.",
            ),
            uncertainty=_full_range_uncertainty(distribution, "No source sample was available"),
        )

    def _global_choice(self, candidate: DurationCandidate) -> DurationChosenResult:
        measured = candidate.duration
        minimum_minutes = max(1, math.floor(measured.minimum_hours * 60 * 0.75))
        median_minutes = max(minimum_minutes, round(measured.median_hours * 60))
        maximum_minutes = max(
            median_minutes + 1,
            min(1440, math.ceil(measured.maximum_hours * 60 * 1.25)),
        )
        duration = DurationDistribution(
            minimum_hours=minimum_minutes / 60.0,
            median_hours=median_minutes / 60.0,
            maximum_hours=maximum_minutes / 60.0,
            shape=measured.shape,
        )
        source_place = candidate.source_provenance[0].place_label
        return DurationChosenResult(
            action_id=candidate.action_id,
            evidence_kind="estimated",
            duration=duration,
            candidate_ids=(candidate.candidate_id,),
            source_provenance=candidate.source_provenance,
            target_place_id="GLOBAL",
            target_place_label="Global default",
            reasoning=(
                f"The pipeline used the {source_place} occurrence distribution as related "
                "official evidence, widened its fitted bounds for a global default, and kept "
                "the result estimated because one country's diary sample is not a global "
                "measurement."
            ),
            assumptions=(
                *candidate.assumptions,
                "The lower fitted bound is widened by 25 percent.",
                "The upper fitted bound is widened by 25 percent and capped at 24 hours.",
                "The triangular shape is an approximation from three weighted quantiles.",
            ),
            uncertainty=_full_range_uncertainty(
                duration,
                "Cross-country and within-country subgroup variation is not identified",
            ),
        )

    def _search_log(
        self,
        action_ids: tuple[str, ...],
        candidate_ids: tuple[str, ...],
        resources: dict[str, FetchedDurationResource],
        errors: dict[str, str],
    ) -> tuple[DurationSearchLogEntry, ...]:
        now = self.clock()
        records = []
        source_specs = (
            (
                self.catalog_url(self.year),
                "US",
                "United States",
                "BLS official data catalog",
                "official_statistics",
                "ATUS catalog and documentation located",
            ),
            (
                self.activity_url(self.year),
                "US",
                "United States",
                "BLS official data catalog",
                "official_statistics",
                "ATUS activity episodes downloaded",
            ),
            (
                self.respondent_url(self.year),
                "US",
                "United States",
                "BLS official data catalog",
                "official_statistics",
                "ATUS final respondent weights downloaded",
            ),
        )
        for sequence, (url, place_id, place_label, engine, kind, success) in enumerate(
            source_specs,
            start=1,
        ):
            resource = resources.get(url)
            records.append(
                DurationSearchLogEntry(
                    sequence=sequence,
                    action_ids=action_ids,
                    place_id=place_id,
                    place_label=place_label,
                    language="en",
                    engine=engine,
                    source_kind=kind,
                    query_or_source=url,
                    searched_at=resource.retrieved_at if resource else now,
                    outcome="candidate" if resource else "error",
                    candidate_ids=candidate_ids if resource and sequence == 2 else (),
                    detail=success if resource else errors.get(url, "Source unavailable"),
                )
            )
        hetus_url = self.hetus_url()
        hetus = resources.get(hetus_url)
        records.append(
            DurationSearchLogEntry(
                sequence=4,
                action_ids=action_ids,
                place_id="EUROPE",
                place_label="Europe",
                language="en",
                engine="Eurostat official data catalog",
                source_kind="official_statistics",
                query_or_source=hetus_url,
                searched_at=hetus.retrieved_at if hetus else now,
                outcome="unavailable" if hetus else "error",
                detail=(
                    "HETUS scientific-use microdata require approved research-entity access, "
                    "so they were logged but not used in the executable cached result."
                    if hetus
                    else errors.get(hetus_url, "Source unavailable")
                ),
            )
        )
        return tuple(records)


def _atus_episodes(activity_zip: bytes, respondent_zip: bytes) -> tuple[_Episode, ...]:
    weights = {
        row["TUCASEID"]: float(row["TUFINLWGT"])
        for row in _zip_rows(respondent_zip)
        if float(row.get("TUFINLWGT", 0) or 0) > 0
    }
    episodes = []
    for row in _zip_rows(activity_zip):
        weight = weights.get(row.get("TUCASEID", ""))
        duration = float(row.get("TUACTDUR24", 0) or 0)
        code = str(row.get("TRCODE", "")).zfill(6)
        if weight is None or duration <= 0 or not code:
            continue
        start_text = row.get("TUSTARTTIM", "00:00:00")
        try:
            start_hour = int(start_text.split(":", 1)[0]) % 24
        except (TypeError, ValueError):
            start_hour = 0
        episodes.append(
            _Episode(
                case_id=row["TUCASEID"],
                duration_minutes=duration,
                code=code,
                start_hour=start_hour,
                weight=weight,
            )
        )
    if not episodes:
        raise ValueError("ATUS files contained no weighted activity episodes")
    return tuple(episodes)


def _zip_rows(content: bytes) -> Iterable[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.casefold().endswith((".dat", ".csv"))
        ]
        if not names:
            raise ValueError("Time-use archive contains no CSV data file")
        with archive.open(names[0]) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
                yield from csv.DictReader(text)


def _matches_mapping(mapping: DurationActivityMapping, episode: _Episode) -> bool:
    if not episode.code.startswith(mapping.code_prefixes):
        return False
    if mapping.start_hour_min is None or mapping.start_hour_max is None:
        return True
    return mapping.start_hour_min <= episode.start_hour < mapping.start_hour_max


def _candidate_from_episodes(
    action: dict,
    episodes: tuple[_Episode, ...],
    source: DefaultPipelineSource,
    activity_mapping: DurationActivityMapping,
    mapping_version: str,
) -> DurationCandidate:
    aggregate_daily = activity_mapping.aggregation == "respondent_day"
    if aggregate_daily:
        daily: dict[str, tuple[float, float]] = {}
        for episode in episodes:
            duration, _weight = daily.get(episode.case_id, (0.0, episode.weight))
            daily[episode.case_id] = (duration + episode.duration_minutes, episode.weight)
        values = tuple(daily.values())
        denominator = "ATUS respondent diary-day total for the mapped activity"
    else:
        values = tuple((episode.duration_minutes, episode.weight) for episode in episodes)
        denominator = "ATUS activity occurrences among respondents reporting the mapped activity"
    quantiles = {
        probability: _weighted_quantile(values, probability)
        for probability in (0.025, 0.05, 0.1, 0.4, 0.5, 0.6, 0.9, 0.95, 0.975)
    }
    minimum = quantiles[0.05]
    median = quantiles[0.5]
    maximum = quantiles[0.95]
    if minimum == maximum:
        minimum = min(value for value, _weight in values)
        maximum = max(value for value, _weight in values)
    if minimum == maximum:
        maximum = minimum + 1
    distribution = DurationDistribution(
        minimum_hours=minimum / 60.0,
        median_hours=median / 60.0,
        maximum_hours=maximum / 60.0,
        shape="triangular",
    )
    weights = [weight for _value, weight in values]
    effective_n = sum(weights) ** 2 / sum(weight**2 for weight in weights)
    proxy = activity_mapping.evidence_kind == "estimated"
    assumptions = (
        "Each diary episode is weighted by the respondent final survey weight TUFINLWGT.",
        "The fitted minimum and maximum are the weighted 5th and 95th percentiles.",
        "The fitted median is the weighted 50th percentile.",
        "The triangular shape approximates the three fitted quantiles.",
        *activity_mapping.assumptions,
        f"The action crosswalk is versioned as {mapping_version}.",
    )
    if proxy:
        assumptions = (
            *assumptions,
            "The mapped diary activity is related to the action but does not directly measure it.",
        )
    if aggregate_daily:
        assumptions = (
            *assumptions,
            "Multiple mapped episodes for one respondent are summed across the diary day.",
        )
    return DurationCandidate(
        candidate_id=f"atus-{source.source_version}-{action['id']}",
        action_id=action["id"],
        evidence_kind="estimated" if proxy else "measured",
        duration=distribution,
        source_provenance=(source,),
        sample_size=len(values),
        effective_sample_size=effective_n,
        denominator=denominator,
        mapping=f"{mapping_version}: {activity_mapping.description}",
        reasoning=(
            "Weighted occurrence-duration quantiles were calculated from the official ATUS "
            "Activity file joined to final respondent weights."
            if not proxy
            else "Weighted ATUS occurrence durations supply a related-activity estimate; the "
            "source does not directly identify this action outcome."
        ),
        assumptions=assumptions,
        uncertainty=DurationUncertainty(
            minimum=DurationInterval(
                lower_hours=quantiles[0.025] / 60.0,
                upper_hours=quantiles[0.1] / 60.0,
            ),
            median=DurationInterval(
                lower_hours=quantiles[0.4] / 60.0,
                upper_hours=quantiles[0.6] / 60.0,
            ),
            maximum=DurationInterval(
                lower_hours=quantiles[0.9] / 60.0,
                upper_hours=quantiles[0.975] / 60.0,
            ),
            method="weighted quantile sensitivity bands",
            coverage="2.5/10, 40/60, and 90/97.5 percentile brackets",
            limitations=(
                "These are empirical sensitivity bands rather than replicate-weight "
                "confidence intervals.",
                "ATUS covers the United States and people age 15 or older.",
            ),
        ),
    )


def _weighted_quantile(values: tuple[tuple[float, float], ...], probability: float) -> float:
    ordered = sorted(values)
    total = sum(weight for _value, weight in ordered)
    threshold = probability * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _full_range_uncertainty(
    distribution: DurationDistribution,
    limitation: str,
) -> DurationUncertainty:
    interval = DurationInterval(
        lower_hours=distribution.minimum_hours,
        upper_hours=distribution.maximum_hours,
    )
    return DurationUncertainty(
        minimum=interval,
        median=interval,
        maximum=interval,
        method="wide bounded estimate",
        coverage="Full selected duration range",
        limitations=(limitation,),
    )

