import pytest
from pydantic import ValidationError

from petraterrium.atlas.ideology_axes import (
    IDEOLOGY_AXIS_IDS,
    IdeologyAxisFit,
    IdeologyAxisFitSet,
    IdeologySurveyItemMapping,
    LegacyIdeologyObservation,
    canonical_ideology_axes,
    ideology_rule_condition,
    require_ideology_axis,
)
from petraterrium.dsl import Evidence


def evidence(source: str = "Test survey") -> Evidence:
    return Evidence(
        source=source,
        version="2026.1",
        source_date="2026-01-31",
        status="present",
        uncertainty=0.2,
    )


def mapping(axis_id: str, variable: str) -> IdeologySurveyItemMapping:
    return IdeologySurveyItemMapping(
        axis_id=axis_id,
        survey_id="survey-1",
        variable=variable,
        question=f"Question for {variable}",
        negative_anchor="Negative pole",
        positive_anchor="Positive pole",
        response_min=1,
        response_max=10,
        provenance=evidence(),
    )


def fit(axis_id: str, variable: str) -> IdeologyAxisFit:
    item = mapping(axis_id, variable)
    return IdeologyAxisFit(
        axis_id=axis_id,
        items=[item],
        coefficients={item.identity: 0.5},
        intercept=0.1,
        sample_size=500,
        provenance=evidence("Weighted survey fit"),
    )


def test_canonical_ideology_axes_are_independent_continuous_features():
    axes = canonical_ideology_axes()

    assert tuple(axis.definition.id for axis in axes) == IDEOLOGY_AXIS_IDS
    assert "ideology" not in IDEOLOGY_AXIS_IDS
    assert all(axis.definition.kind == "continuous" for axis in axes)
    assert all(axis.definition.value_range.minimum == -1 for axis in axes)
    assert all(axis.definition.value_range.maximum == 1 for axis in axes)
    assert axes[0].negative_pole == "Planned economy"
    assert axes[0].positive_pole == "Free market"
    assert axes[1].negative_pole == "Authoritarian"
    assert axes[1].positive_pole == "Democratic or anarchist self-rule"
    assert "anti-authoritarian" in axes[1].description
    assert "not identical" in axes[1].description
    assert axes[2].negative_pole == "Traditional or conservative"
    assert axes[2].positive_pole == "Progressive or modern"
    assert len({axis.description for axis in axes}) == 3


def test_legacy_ideology_is_non_predictive_and_has_no_axis_values():
    observation = LegacyIdeologyObservation(
        value={"left": 0.4, "right": 0.6},
        provenance=evidence("Legacy ideology import"),
    )

    assert observation.feature_id == "ideology"
    assert observation.status == "legacy_only"
    assert observation.predictive is False
    assert observation.axis_values is None

    with pytest.raises(ValidationError):
        LegacyIdeologyObservation(
            value=0.25,
            provenance=evidence(),
            predictive=True,
        )

    with pytest.raises(ValidationError):
        LegacyIdeologyObservation(
            value=0.25,
            provenance=evidence(),
            axis_values={"ideology_economic": 0.25},
        )


def test_legacy_ideology_cannot_be_used_as_a_predictor_or_auto_split():
    with pytest.raises(ValueError, match="legacy-only"):
        require_ideology_axis("ideology")

    assert require_ideology_axis("ideology_economic") == "ideology_economic"


def test_each_axis_fit_uses_only_its_own_survey_items_and_coefficients():
    economic_item = mapping("ideology_economic", "private_ownership")

    with pytest.raises(ValidationError, match="own survey items"):
        IdeologyAxisFit(
            axis_id="ideology_state",
            items=[economic_item],
            coefficients={economic_item.identity: 0.5},
            intercept=0,
            sample_size=500,
            provenance=evidence(),
        )

    with pytest.raises(ValidationError, match="exactly match"):
        IdeologyAxisFit(
            axis_id="ideology_economic",
            items=[economic_item],
            coefficients={"survey-1:other": 0.5},
            intercept=0,
            sample_size=500,
            provenance=evidence(),
        )


def test_axis_fit_set_requires_three_separate_fits_without_reused_items():
    complete = IdeologyAxisFitSet(
        fits=[
            fit("ideology_economic", "private_ownership"),
            fit("ideology_state", "strong_leader"),
            fit("ideology_cultural", "tradition_change"),
        ]
    )

    assert {item.axis_id for item in complete.fits} == set(IDEOLOGY_AXIS_IDS)

    with pytest.raises(ValidationError, match="one separate fit"):
        IdeologyAxisFitSet(
            fits=[
                fit("ideology_economic", "private_ownership"),
                fit("ideology_state", "strong_leader"),
            ]
        )

    with pytest.raises(ValidationError, match="cannot be reused"):
        IdeologyAxisFitSet(
            fits=[
                fit("ideology_economic", "shared_item"),
                fit("ideology_state", "shared_item"),
                fit("ideology_cultural", "tradition_change"),
            ]
        )


def test_each_axis_id_is_compatible_with_dsl_rule_conditions():
    conditions = [ideology_rule_condition(axis_id, "gte", 0.25) for axis_id in IDEOLOGY_AXIS_IDS]

    assert [condition.attribute for condition in conditions] == list(IDEOLOGY_AXIS_IDS)
    assert all(condition.operator == "gte" for condition in conditions)
    assert all(condition.value == 0.25 for condition in conditions)

    with pytest.raises(ValueError, match="between -1 and 1"):
        ideology_rule_condition("ideology_economic", "gte", 1.1)
