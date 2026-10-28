import hashlib
import json
import math
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .default_pipeline_contracts import (
    DefaultPipelineRun,
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
from .default_pipeline_persistence import canonical_json_bytes


class GlobalDurationCatalogModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class GlobalDurationActionCrosswalk(GlobalDurationCatalogModel):
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    activity_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    occurrences_per_day: int = Field(ge=1)
    description: str = Field(min_length=1)


class GlobalDurationObservation(GlobalDurationCatalogModel):
    observation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    activity_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    reported_value: float = Field(gt=0)
    reported_unit: Literal[
        "hours_per_day",
        "minutes_per_day",
        "hours_per_week",
        "minutes_per_week",
    ]
    normalization_days: int = Field(default=1, ge=1, le=7)
    denominator: str = Field(min_length=1)
    mapping_strength: Literal["direct", "broad_proxy"]
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    detail: str = Field(min_length=1)

    @property
    def hours_per_day(self) -> float:
        value = self.reported_value
        if self.reported_unit.startswith("minutes"):
            value /= 60
        if self.reported_unit.endswith("week"):
            value /= self.normalization_days
        return value


class GlobalDurationSearchAttempt(GlobalDurationCatalogModel):
    source_kind: Literal[
        "official_statistics",
        "representative_survey",
        "research_article",
        "government_report",
        "news",
        "online_opinion",
    ]
    language: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    query_or_source: str = Field(min_length=1)
    outcome: Literal["candidate", "unavailable", "rejected", "error"]
    detail: str = Field(min_length=1)


class GlobalDurationPlace(GlobalDurationCatalogModel):
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    level: Literal["country", "region"]
    region_id: str | None = None
    population: int = Field(ge=1)
    reported_sample_size: int | None = Field(default=None, ge=1)
    languages: tuple[str, ...] = Field(min_length=1)
    member_place_ids: tuple[str, ...] = ()
    sources: tuple[DefaultPipelineSource, ...] = Field(min_length=1)
    observations: tuple[GlobalDurationObservation, ...] = ()
    search_attempts: tuple[GlobalDurationSearchAttempt, ...] = Field(min_length=6)

    @model_validator(mode="after")
    def validate_place(self):
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"Duration sources for {self.place_id} must be unique")
        if any(item.source_id not in source_ids for item in self.observations):
            raise ValueError(f"Duration observations for {self.place_id} need local sources")
        attempted = {item.source_kind for item in self.search_attempts}
        required = {
            "official_statistics",
            "representative_survey",
            "research_article",
            "government_report",
            "news",
            "online_opinion",
        }
        if attempted != required:
            raise ValueError(f"Duration search tiers for {self.place_id} are incomplete")
        if self.search_attempts[0].language != self.languages[0]:
            raise ValueError(f"Duration search for {self.place_id} must begin locally")
        if self.level == "country" and (self.region_id is None or self.member_place_ids):
            raise ValueError(f"Country duration place {self.place_id} has invalid hierarchy")
        if self.level == "region" and (self.region_id is not None or not self.member_place_ids):
            raise ValueError(f"Region duration place {self.place_id} has invalid hierarchy")
        return self


class GlobalDurationSourceCatalog(GlobalDurationCatalogModel):
    schema_version: Literal["1"]
    version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    researched_at: datetime
    population_source: DefaultPipelineSource
    reference_pipeline_run: str = Field(min_length=1)
    requested_source_tiers: tuple[str, ...] = Field(min_length=6)
    action_crosswalk: tuple[GlobalDurationActionCrosswalk, ...] = Field(min_length=1)
    places: tuple[GlobalDurationPlace, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self):
        action_ids = [item.action_id for item in self.action_crosswalk]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Global duration action crosswalk ids must be unique")
        place_ids = [item.place_id for item in self.places]
        if len(place_ids) != len(set(place_ids)):
            raise ValueError("Global duration place ids must be unique")
        countries = {item.place_id for item in self.places if item.level == "country"}
        for region in (item for item in self.places if item.level == "region"):
            missing = set(region.member_place_ids) - countries
            if missing:
                raise ValueError(
                    f"Global duration region {region.place_id} has unknown members "
                    f"{sorted(missing)}"
                )
        return self


def global_duration_catalog_path() -> Path:
    return (
        Path(__file__).with_name("defaults") / "research" / "global-duration-source-catalog-v1.json"
    )


def global_duration_receipt_path() -> Path:
    return (
        Path(__file__).with_name("defaults")
        / "research"
        / "global-duration-pipeline-receipt-v1.json"
    )


class GlobalDurationResearchPipeline:
    def __init__(self, catalog_path: str | Path | None = None, additional_action_researcher=None):
        from .duration_research import AtusDurationResearchPipeline

        self.additional_action_researcher = (
            additional_action_researcher or AtusDurationResearchPipeline()
        )
        self.catalog_path = Path(catalog_path or global_duration_catalog_path())
        self.catalog = GlobalDurationSourceCatalog.model_validate_json(
            self.catalog_path.read_text(encoding="utf-8")
        )
        self.pipeline_version = self.catalog.pipeline_version
        reference_path = self.catalog_path.parent / self.catalog.reference_pipeline_run
        self.reference_run = DefaultPipelineRun.model_validate_json(
            reference_path.resolve().read_text(encoding="utf-8")
        )
        self.crosswalk_by_action = {item.action_id: item for item in self.catalog.action_crosswalk}
        self.place_by_id = {item.place_id: item for item in self.catalog.places}
        self.reference_by_action = {item.action_id: item for item in self.reference_run.candidates}

    def research(self, actions: list[dict] | tuple[dict, ...]) -> DurationResearchOutput:
        action_by_id = {action["id"]: action for action in actions}
        additional_actions = [
            action for action in actions if action["id"] not in self.crosswalk_by_action
        ]
        action_by_id = {
            key: value for key, value in action_by_id.items() if key in self.crosswalk_by_action
        }
        additional = (
            self.additional_action_researcher.research(additional_actions)
            if additional_actions
            else None
        )
        if not action_by_id:
            if additional is None:
                raise ValueError("Duration research requires at least one confirmed action")
            return additional
        countries = tuple(item for item in self.catalog.places if item.level == "country")
        regions = tuple(item for item in self.catalog.places if item.level == "region")
        country_candidates = {
            (place.place_id, action_id): self._country_candidate(place, action_id)
            for place in countries
            for action_id in action_by_id
        }
        region_candidates = {
            (place.place_id, action_id): self._region_candidate(
                place,
                action_id,
                country_candidates,
            )
            for place in regions
            for action_id in action_by_id
        }
        all_candidates = {**country_candidates, **region_candidates}
        requests = tuple(
            DurationResearchRequest(
                action_id=action_id,
                action_label=action_by_id[action_id]["name"],
                target_place_id=place.place_id,
                target_place_label=place.place_label,
                target_language=place.languages[0],
                requested_source_tiers=self.catalog.requested_source_tiers,
            )
            for place in self.catalog.places
            for action_id in action_by_id
        )
        search_log = self._search_log(tuple(action_by_id), all_candidates)
        chosen = tuple(
            self._global_result(action_id, countries, country_candidates)
            for action_id in action_by_id
        )
        additional_logs = (
            tuple(
                entry.model_copy(update={"sequence": len(search_log) + index + 1})
                for index, entry in enumerate(additional.search_log)
            )
            if additional
            else ()
        )
        return DurationResearchOutput(
            requests=(*requests, *(additional.requests if additional else ())),
            search_log=(*search_log, *additional_logs),
            candidates=(*all_candidates.values(), *(additional.candidates if additional else ())),
            chosen_results=(*chosen, *(additional.chosen_results if additional else ())),
        )

    def cached_receipt(self, actions: list[dict] | tuple[dict, ...]) -> dict:
        output = self.research(actions)
        candidates = {item.candidate_id: item for item in output.candidates}
        index = []
        for place in self.catalog.places:
            for action_id in self.crosswalk_by_action:
                candidate_id = self._candidate_id(place.place_id, action_id)
                candidate = candidates[candidate_id]
                observation = self._observation_for_action(place, action_id)
                index.append(
                    {
                        "place_id": place.place_id,
                        "place_label": place.place_label,
                        "level": place.level,
                        "region_id": place.region_id,
                        "population": place.population,
                        "action_id": action_id,
                        "candidate_id": candidate_id,
                        "evidence_kind": candidate.evidence_kind,
                        "source_ids": [source.source_id for source in candidate.source_provenance],
                        "observation_id": (
                            observation.observation_id if observation is not None else None
                        ),
                        "resolution": self._resolution(place, action_id),
                    }
                )
        payload = {
            "schema_version": "1",
            "catalog_version": self.catalog.version,
            "pipeline_version": self.pipeline_version,
            "researched_at": self.catalog.researched_at.isoformat().replace("+00:00", "Z"),
            "input": {
                "action_ids": list(self.crosswalk_by_action),
                "country_ids": [
                    item.place_id for item in self.catalog.places if item.level == "country"
                ],
                "region_ids": [
                    item.place_id for item in self.catalog.places if item.level == "region"
                ],
                "requested_source_tiers": list(self.catalog.requested_source_tiers),
                "reference_pipeline_run_id": self.reference_run.run_id,
                "reference_pipeline_run_hash": self.reference_run.run_hash,
            },
            "output": output.model_dump(mode="json"),
            "place_action_index": index,
        }
        receipt_id = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        return {"receipt_id": receipt_id, **payload}

    def write_cached_receipt(
        self,
        actions: list[dict] | tuple[dict, ...],
        destination: str | Path | None = None,
    ) -> Path:
        path = Path(destination or global_duration_receipt_path())
        path.write_text(
            json.dumps(self.cached_receipt(actions), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def _country_candidate(self, place: GlobalDurationPlace, action_id: str) -> DurationCandidate:
        reference = self.reference_by_action[action_id]
        if place.place_id == "US":
            uncertainty = reference.uncertainty
            if reference.evidence_kind == "estimated":
                uncertainty = _country_uncertainty(
                    reference.duration,
                    False,
                    (
                        "The ATUS activity is a proxy for this action rather than a direct "
                        "outcome-specific duration measure.",
                        "Subgroup, weekday, season, and simultaneous-activity differences "
                        "remain unresolved.",
                    ),
                )
            return reference.model_copy(
                update={
                    "candidate_id": self._candidate_id(place.place_id, action_id),
                    "mapping": (
                        f"{self.catalog.version}: US occurrence quantiles retained from "
                        f"{self.reference_run.run_id}; {reference.mapping}"
                    ),
                    "reasoning": (
                        "The app pipeline reused its cached weighted ATUS occurrence fit for "
                        "the United States without cross-country substitution."
                    ),
                    "uncertainty": uncertainty,
                }
            )
        observation = self._observation_for_action(place, action_id)
        scale, mapping, direct = self._country_scale(place, action_id, observation)
        duration = _scaled_duration(reference.duration, scale)
        sources = _unique_sources(
            (*place.sources, *reference.source_provenance, self.catalog.population_source)
        )
        sample_size = place.reported_sample_size or 1
        resolution = self._resolution(place, action_id)
        reason = (
            f"The app pipeline converted {observation.observation_id} into a local "
            "occurrence estimate and transferred only the ATUS quantile shape."
            if observation is not None
            else "The local official search did not publish a compatible action total; the "
            "app pipeline retained the ATUS occurrence shape as an estimated draft and "
            "widened uncertainty for the country-specific result."
        )
        limitations = [
            "The local source publishes activity totals rather than occurrence-level quantiles.",
            "The ATUS quantile ratios transfer distribution shape and do not make "
            "this a U.S. measurement.",
            "Subgroup, weekday, season, and simultaneous-activity differences remain unresolved.",
        ]
        if place.place_id == "ID":
            limitations.append(
                "Indonesia's BPS national 2026 time-use release was not available at research time."
            )
        if place.place_id == "NG":
            limitations.append(
                "Nigeria's 2024 survey covers four selected states rather than the whole country."
            )
        return DurationCandidate(
            candidate_id=self._candidate_id(place.place_id, action_id),
            action_id=action_id,
            evidence_kind="estimated",
            duration=duration,
            source_provenance=sources,
            sample_size=sample_size,
            effective_sample_size=float(sample_size),
            denominator=(
                observation.denominator
                if observation is not None
                else "One deterministic country estimate after a complete source-tier search"
            ),
            mapping=mapping,
            reasoning=f"{reason} Resolution: {resolution}.",
            assumptions=(
                "The local statistic controls level when a compatible observation exists.",
                "Minimum-to-median and maximum-to-median ratios come from the cached "
                "ATUS pipeline result.",
                "All non-U.S. results remain estimated even when their input total is official.",
                "No country's value is presented as measured for another country.",
            ),
            uncertainty=_country_uncertainty(duration, direct, tuple(limitations)),
        )

    def _region_candidate(
        self,
        place: GlobalDurationPlace,
        action_id: str,
        countries: dict[tuple[str, str], DurationCandidate],
    ) -> DurationCandidate:
        members = tuple(
            (self.place_by_id[member_id], countries[(member_id, action_id)])
            for member_id in place.member_place_ids
        )
        duration = _weighted_duration(
            tuple((candidate.duration, member.population) for member, candidate in members)
        )
        sources = _unique_sources(
            (
                *place.sources,
                *(
                    source
                    for _member, candidate in members
                    for source in candidate.source_provenance
                ),
                self.catalog.population_source,
            )
        )
        weights = tuple(member.population for member, _candidate in members)
        effective_n = sum(weights) ** 2 / sum(weight**2 for weight in weights)
        return DurationCandidate(
            candidate_id=self._candidate_id(place.place_id, action_id),
            action_id=action_id,
            evidence_kind="estimated",
            duration=duration,
            source_provenance=sources,
            sample_size=len(members),
            effective_sample_size=effective_n,
            denominator=(
                f"{len(members)} represented demo-country estimates weighted by "
                "UN WPP 2024 population"
            ),
            mapping=(
                f"{self.catalog.version}: population-weighted {place.place_label} estimate "
                f"from {', '.join(member.place_id for member, _candidate in members)}"
            ),
            reasoning=(
                f"The app pipeline aggregated the represented {place.place_label} country "
                "estimates by UN WPP population and retained the regional official source as "
                "methodological provenance."
            ),
            assumptions=(
                "Only global-demo countries represented in the region contribute numeric values.",
                "The regional result is an estimate rather than a measurement of "
                "every regional country.",
                "Country evidence labels and provenance remain attached to the aggregate.",
            ),
            uncertainty=_aggregate_uncertainty(
                duration,
                (
                    "Between-country heterogeneity outside the represented demo countries "
                    "is not identified.",
                    "Country inputs include estimated occurrence distributions.",
                ),
            ),
        )

    def _global_result(
        self,
        action_id: str,
        countries: tuple[GlobalDurationPlace, ...],
        candidates: dict[tuple[str, str], DurationCandidate],
    ) -> DurationChosenResult:
        selected = tuple((place, candidates[(place.place_id, action_id)]) for place in countries)
        duration = _weighted_duration(
            tuple((candidate.duration, place.population) for place, candidate in selected)
        )
        sources = _unique_sources(
            (
                *(
                    source
                    for _place, candidate in selected
                    for source in candidate.source_provenance
                ),
                self.catalog.population_source,
            )
        )
        return DurationChosenResult(
            action_id=action_id,
            evidence_kind="estimated",
            duration=duration,
            candidate_ids=tuple(candidate.candidate_id for _place, candidate in selected),
            source_provenance=sources,
            target_place_id="GLOBAL",
            target_place_label="Global 12-country demo population",
            reasoning=(
                "The app pipeline population-weighted all twelve country-specific candidates "
                "with UN WPP 2024 populations. The global default remains estimated because "
                "source instruments and action mappings differ across countries."
            ),
            assumptions=(
                "Every represented country contributes its own result before global aggregation.",
                "Official daily or weekly totals are converted to occurrence estimates "
                "where necessary.",
                "Regional and global aggregation never changes an estimated country "
                "result into measured evidence.",
                "The twelve demo countries approximate the global demo and do not cover "
                "every country worldwide.",
            ),
            uncertainty=_aggregate_uncertainty(
                duration,
                (
                    "Cross-country survey years, instruments, populations, and activity "
                    "coding differ.",
                    "The estimate does not identify within-country subgroup or day-type variation.",
                ),
            ),
        )

    def _country_scale(
        self,
        place: GlobalDurationPlace,
        action_id: str,
        observation: GlobalDurationObservation | None,
    ) -> tuple[float, str, bool]:
        crosswalk = self.crosswalk_by_action[action_id]
        reference = self.reference_by_action[action_id].duration
        if observation is not None and observation.activity_id == crosswalk.activity_id:
            local_median = observation.hours_per_day / crosswalk.occurrences_per_day
            scale = _bounded_scale(local_median / reference.median_hours, 0.35, 2.5)
            return (
                scale,
                f"{self.catalog.version}: {observation.observation_id}; {crosswalk.description}",
                observation.mapping_strength == "direct",
            )
        if observation is not None:
            reference_total = self._reference_activity_hours(observation.activity_id)
            scale = _bounded_scale(observation.hours_per_day / reference_total, 0.5, 1.5)
            return (
                scale,
                f"{self.catalog.version}: broad proxy {observation.observation_id}; "
                f"{crosswalk.description}",
                False,
            )
        ratios = []
        for item in place.observations:
            reference_total = self._reference_activity_hours(item.activity_id)
            ratios.append(item.hours_per_day / reference_total)
        scale = _bounded_scale(_median(ratios) if ratios else 1.0, 0.75, 1.25)
        return (
            scale,
            f"{self.catalog.version}: locally searched estimated fallback; {crosswalk.description}",
            False,
        )

    def _reference_activity_hours(self, activity_id: str) -> float:
        medians = {
            action_id: candidate.duration.median_hours
            for action_id, candidate in self.reference_by_action.items()
        }
        values = {
            "sleep": medians["sleep"],
            "personal_care": medians["personal_care"],
            "meals": sum(
                medians[action_id] for action_id in ("eat_breakfast", "eat_lunch", "eat_dinner")
            ),
            "exercise": medians["exercise"],
            "social": medians["social_activity"],
            "work_or_study": medians["work_or_study"],
        }
        values["self_care"] = values["sleep"] + values["personal_care"] + values["meals"]
        values["necessary"] = values["self_care"]
        values["leisure"] = values["exercise"] + values["social"]
        values["contracted"] = values["work_or_study"]
        values["unpaid_work"] = medians["personal_care"] + medians["work_or_study"]
        if activity_id not in values:
            raise ValueError(f"No reference duration mapping exists for {activity_id}")
        return values[activity_id]

    def _observation_for_action(
        self,
        place: GlobalDurationPlace,
        action_id: str,
    ) -> GlobalDurationObservation | None:
        target = self.crosswalk_by_action[action_id].activity_id
        direct = next(
            (item for item in place.observations if item.activity_id == target),
            None,
        )
        if direct is not None:
            return direct
        fallback_ids = {
            "sleep": ("self_care", "necessary"),
            "personal_care": ("self_care", "necessary"),
            "meals": ("self_care", "necessary"),
            "exercise": ("leisure",),
            "social": ("leisure",),
            "work_or_study": ("contracted",),
        }[target]
        return next(
            (
                item
                for fallback in fallback_ids
                for item in place.observations
                if item.activity_id == fallback
            ),
            None,
        )

    def _resolution(self, place: GlobalDurationPlace, action_id: str) -> str:
        if place.level == "region":
            return "regional_population_weighted_estimate"
        if place.place_id == "US":
            return "country_occurrence_fit"
        observation = self._observation_for_action(place, action_id)
        if observation is None:
            return "country_estimate_after_local_search"
        target = self.crosswalk_by_action[action_id].activity_id
        if observation.activity_id == target and observation.mapping_strength == "direct":
            return "country_total_to_occurrence_estimate"
        return "country_broad_proxy_estimate"

    def _search_log(
        self,
        action_ids: tuple[str, ...],
        candidates: dict[tuple[str, str], DurationCandidate],
    ) -> tuple[DurationSearchLogEntry, ...]:
        records = []
        sequence = 1
        for place in self.catalog.places:
            candidate_ids = tuple(
                candidates[(place.place_id, action_id)].candidate_id for action_id in action_ids
            )
            for attempt in place.search_attempts:
                records.append(
                    DurationSearchLogEntry(
                        sequence=sequence,
                        action_ids=action_ids,
                        place_id=place.place_id,
                        place_label=place.place_label,
                        language=attempt.language,
                        engine=attempt.engine,
                        source_kind=attempt.source_kind,
                        query_or_source=attempt.query_or_source,
                        searched_at=self.catalog.researched_at,
                        outcome=attempt.outcome,
                        candidate_ids=(candidate_ids if attempt.outcome == "candidate" else ()),
                        detail=attempt.detail,
                    )
                )
                sequence += 1
        return tuple(records)

    def _candidate_id(self, place_id: str, action_id: str) -> str:
        normalized = "".join(
            character if character.isalnum() else "-" for character in place_id.casefold()
        ).strip("-")
        return f"global-duration-v1-{normalized}-{action_id}"


def _scaled_duration(source: DurationDistribution, scale: float) -> DurationDistribution:
    minimum = max(1 / 60, source.minimum_hours * scale)
    median = max(minimum, source.median_hours * scale)
    maximum = min(24.0, max(median + 1 / 60, source.maximum_hours * scale))
    return DurationDistribution(
        minimum_hours=round(minimum, 6),
        median_hours=round(median, 6),
        maximum_hours=round(maximum, 6),
        shape=source.shape,
    )


def _weighted_duration(
    items: tuple[tuple[DurationDistribution, int], ...],
) -> DurationDistribution:
    total = sum(weight for _duration, weight in items)

    def weighted(attribute: str) -> float:
        return sum(getattr(duration, attribute) * weight for duration, weight in items) / total

    minimum = weighted("minimum_hours")
    median = max(minimum, weighted("median_hours"))
    maximum = max(median + 1 / 60, weighted("maximum_hours"))
    return DurationDistribution(
        minimum_hours=round(minimum, 6),
        median_hours=round(median, 6),
        maximum_hours=round(min(24.0, maximum), 6),
        shape="triangular",
    )


def _country_uncertainty(
    duration: DurationDistribution,
    direct: bool,
    limitations: tuple[str, ...],
) -> DurationUncertainty:
    lower_factor = 0.5 if direct else 0.25
    upper_factor = 1.5 if direct else 2.0
    return DurationUncertainty(
        minimum=DurationInterval(
            lower_hours=max(0, duration.minimum_hours * lower_factor),
            upper_hours=min(duration.median_hours, duration.minimum_hours * upper_factor),
        ),
        median=DurationInterval(
            lower_hours=duration.median_hours * lower_factor,
            upper_hours=min(24, duration.median_hours * upper_factor),
        ),
        maximum=DurationInterval(
            lower_hours=max(duration.median_hours, duration.maximum_hours * lower_factor),
            upper_hours=min(24, duration.maximum_hours * upper_factor),
        ),
        method="local aggregate plus ATUS quantile-shape transfer sensitivity",
        coverage="wide transformation range; not a confidence interval",
        limitations=limitations,
    )


def _aggregate_uncertainty(
    duration: DurationDistribution,
    limitations: tuple[str, ...],
) -> DurationUncertainty:
    return DurationUncertainty(
        minimum=DurationInterval(
            lower_hours=max(0, duration.minimum_hours * 0.25),
            upper_hours=min(duration.median_hours, duration.minimum_hours * 2),
        ),
        median=DurationInterval(
            lower_hours=duration.median_hours * 0.5,
            upper_hours=min(24, duration.median_hours * 1.5),
        ),
        maximum=DurationInterval(
            lower_hours=max(duration.median_hours, duration.maximum_hours * 0.5),
            upper_hours=min(24, duration.maximum_hours * 2),
        ),
        method="population-weighted source and mapping sensitivity",
        coverage="wide aggregation range; not a confidence interval",
        limitations=limitations,
    )


def _unique_sources(sources: Iterable[DefaultPipelineSource]) -> tuple[DefaultPipelineSource, ...]:
    result = {}
    for source in sources:
        result[source.source_id] = source
    return tuple(result.values())


def _bounded_scale(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value) or value <= 0:
        return 1.0
    return min(maximum, max(minimum, value))


def _median(values: list[float]) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
