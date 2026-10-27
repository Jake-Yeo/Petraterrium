from math import sqrt

from pydantic import BaseModel, ConfigDict

from ..dsl import ChoiceCondition, ChoiceEvidence, Evidence


class ChoiceResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: ChoiceEvidence
    status: str
    resolved_level: str
    region_override: bool


def choice_from_counts(
    identity: str,
    action_id: str,
    conditioning_id: str,
    numerator: int,
    sample_size: int,
    population: str,
    denominator: str,
    source: str,
    source_date: str,
    time_unit: str,
    conditioning: ChoiceCondition | None = None,
) -> ChoiceEvidence:
    if sample_size <= 0 or numerator < 0 or numerator > sample_size:
        raise ValueError("Choice counts require 0 <= numerator <= sample size")
    value = numerator / sample_size
    error = 1.96 * sqrt(value * (1 - value) / sample_size)
    return ChoiceEvidence(
        id=identity,
        action_id=action_id,
        conditioning_id=conditioning_id,
        conditioning=conditioning or ChoiceCondition(),
        definition=f"Observed {action_id} within the stated diary denominator",
        value=value,
        ci_low=max(0, value - error),
        ci_high=min(1, value + error),
        source_type="time_use_diary",
        tier=2,
        sample_size=sample_size,
        source_date=source_date,
        population=population,
        denominator=denominator,
        time_unit=time_unit,
        source_time_unit=time_unit,
        tier_flag="measured",
        provenance=Evidence(
            source=source,
            version=source_date,
            status="present",
            uncertainty=min(1, error * 2),
            source_date=source_date,
        ),
    )


def unknown_choice(
    action_id: str,
    conditioning_id: str,
    place: str,
    time_unit: str,
) -> ChoiceEvidence:
    requirement = f"Needs a representative time-use or behaviour survey for {place}"
    return ChoiceEvidence(
        id=f"unknown-{action_id}-{conditioning_id}",
        action_id=action_id,
        conditioning_id=conditioning_id,
        conditioning=ChoiceCondition(place=place),
        definition=f"Unknown probability of {action_id} for {conditioning_id}",
        value=None,
        ci_low=0,
        ci_high=1,
        source_type="unknown",
        tier=5,
        sample_size=None,
        source_date=None,
        population=place,
        denominator="Defined population with no measured denominator",
        time_unit=time_unit,
        source_time_unit=time_unit,
        tier_flag="unknown",
        provenance=Evidence(
            source="No qualifying choice evidence",
            version="missing",
            status="missing",
            uncertainty=1,
        ),
        missing_requirement=requirement,
    )


def resolve_choice_evidence(
    rows: list[ChoiceEvidence],
    action_id: str,
    conditioning_id: str,
    city: str,
    country: str,
    region: str,
    time_unit: str,
    subregion: str | None = None,
) -> ChoiceResolution:
    places = [("city", city, "present", False), ("country", country, "inherited", False)]
    if subregion:
        places.append(("subregion", subregion, "imputed", True))
    places.append(("region", region, "imputed", True))
    for level, place, status, region_override in places:
        match = next(
            (
                row
                for row in rows
                if row.action_id == action_id
                and row.conditioning_id == conditioning_id
                and row.conditioning.place == place
                and row.time_unit == time_unit
            ),
            None,
        )
        if match is not None:
            return ChoiceResolution(
                evidence=match,
                status=status if match.tier_flag == "measured" else match.tier_flag,
                resolved_level=level,
                region_override=region_override,
            )
    return ChoiceResolution(
        evidence=unknown_choice(action_id, conditioning_id, country, time_unit),
        status="unknown",
        resolved_level="unknown",
        region_override=False,
    )


def demo_choice_evidence() -> list[ChoiceEvidence]:
    return [
        ChoiceEvidence(
            id="local-socializing-hint",
            action_id="talk",
            conditioning_id="friday-evening",
            conditioning=ChoiceCondition(
                context={"day": "friday", "time": "after_20_00"},
                place="Northport",
            ),
            definition="Leave home after 20:00 for leisure on Friday",
            value=None,
            ci_low=0,
            ci_high=1,
            source_type="news",
            tier=5,
            sample_size=None,
            source_date="2026-01-10",
            population="Northport adults",
            denominator="No representative denominator",
            time_unit="friday",
            source_time_unit="friday",
            tier_flag="hint_only",
            provenance=Evidence(
                source="FAKE local-news demo fixture",
                version="FAKE-choice-v1",
                status="hint_only",
                uncertainty=1,
                source_date="2026-01-10",
            ),
            missing_requirement="Needs a representative Friday time-use survey for this action",
        )
    ]
