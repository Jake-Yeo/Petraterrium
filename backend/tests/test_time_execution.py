from copy import deepcopy

import pytest
from pydantic import ValidationError

from petraterrium.dsl import DurationDistribution
from petraterrium.dsl.models import ActionDefinition
from petraterrium.dsl.validator import validate_dsl
from tests.test_framework import evidence, framework_dsl


def duration(
    minimum: float = 0.1,
    median: float = 0.25,
    maximum: float = 0.5,
) -> DurationDistribution:
    return DurationDistribution(
        duration_min_hours=minimum,
        duration_median_hours=median,
        duration_max_hours=maximum,
        shape="triangular",
        shape_parameters={},
        provenance=evidence("FAKE time-use diary fixture"),
    )


def test_duration_distribution_requires_an_ordered_non_fixed_range_with_evidence():
    fitted = duration()

    assert fitted.duration_min_hours == 0.1
    assert fitted.duration_median_hours == 0.25
    assert fitted.duration_max_hours == 0.5
    assert fitted.provenance.source == "FAKE time-use diary fixture"

    with pytest.raises(ValidationError, match="exceed"):
        duration(0.5, 0.5, 0.5)
    with pytest.raises(ValidationError, match="ordered"):
        duration(0.5, 0.25, 0.1)


def test_action_contract_uses_a_duration_distribution_instead_of_a_fixed_duration():
    source = framework_dsl().actions[0]
    action = ActionDefinition(
        **source.model_dump(
            exclude={
                "category",
                "duration",
                "duration_minutes",
                "emergency_interruptions",
                "interruption_outcome",
                "passive",
                "protected",
            }
        ),
        category="sleep",
        duration=duration(),
        passive=False,
        protected=True,
        interruption_outcome="defer",
        emergency_interruptions=["work"],
    )

    assert action.duration.duration_median_hours == 0.25
    assert action.runtime_interruptibility == "protected"
    assert action.runtime_interruption_outcome == "defer"
    legacy = ActionDefinition.model_validate(source.model_dump())
    assert legacy.canonical_duration_median_hours == 1


def test_dsl_validation_reports_tick_duration_consistency_and_accepts_long_actions():
    payload = framework_dsl().model_dump()
    for action in payload["actions"]:
        action.pop("duration_minutes")
        action["duration"] = duration(0.1, 0.5, 8).model_dump(mode="json")
    payload["tick"]["tick_hours"] = 1

    validation = validate_dsl(payload)

    assert validation.valid
    assert any("spans multiple ticks" in item.message for item in validation.warnings)

    inconsistent = deepcopy(payload)
    inconsistent["tick"]["tick_hours"] = 25
    validation = validate_dsl(inconsistent)
    assert validation.valid
    assert any("24-hour accounting" in item.message for item in validation.warnings)
