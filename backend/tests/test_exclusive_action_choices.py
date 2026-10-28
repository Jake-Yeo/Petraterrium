from __future__ import annotations

import json

import pytest

from petraterrium.simulation.default_dsl import (
    DefaultActionDefinition,
    _validate_exclusive_action_choices,
)
from petraterrium.simulation.runtime_state_compiler import _meaningful_actions


def action(
    action_id: str,
    probability: float,
    *,
    threshold: float = 0.5,
    group: str | None = "midday_meal",
) -> DefaultActionDefinition:
    return DefaultActionDefinition.model_validate_json(
        json.dumps(
            {
            "id": action_id,
            "name": action_id.replace("_", " ").title(),
            "description": f"Fixture {action_id}",
            "duration": {
                "minimum_minutes": 1,
                "typical_minutes": 5,
                "maximum_minutes": 10,
                "shape": "triangular",
            },
            "formula": f"P({action_id})",
            "conditions": ["midday"],
            "place_requirements": ["current_place"],
            "time_requirements": ["midday"],
            "state_inputs": ["stress"],
            "outcomes": [],
            "evidence": {
                "status": "default_estimated",
                "explicit_default_reason": "Fixture default",
                "uncertainty_low": 0,
                "uncertainty_high": 1,
                "source_ids": [],
            },
            "exclusive_choice_group": group,
            "runtime_rules": [
                {
                    "conditions": [
                        {
                            "input": "context.hour",
                            "operator": "eq",
                            "value": 12,
                        },
                        {
                            "input": "memory.stress",
                            "operator": "lt",
                            "value": threshold,
                        },
                    ],
                    "probability": probability,
                }
            ],
            }
        )
    )


def test_exclusive_choice_probabilities_compile_as_one_group() -> None:
    actions = [action("eat_lunch", 0.8), action("skip_lunch", 0.2)]

    _validate_exclusive_action_choices(actions)
    compiled = _meaningful_actions(actions, {}, "fixture-v1")

    assert [item["exclusive_choice_group"] for item in compiled] == [
        "midday_meal",
        "midday_meal",
    ]


def test_exclusive_choice_rejects_probabilities_that_do_not_sum_to_one() -> None:
    with pytest.raises(ValueError, match="expected 1"):
        _validate_exclusive_action_choices(
            [action("eat_lunch", 0.8), action("skip_lunch", 0.1)]
        )


def test_exclusive_choice_rejects_misaligned_eligibility_rules() -> None:
    with pytest.raises(ValueError, match="matching condition partitions"):
        _validate_exclusive_action_choices(
            [
                action("eat_lunch", 0.8),
                action("skip_lunch", 0.2, threshold=0.7),
            ]
        )


def test_independent_actions_remain_ungrouped() -> None:
    actions = [action("exercise", 0.5, group=None)]

    _validate_exclusive_action_choices(actions)
    compiled = _meaningful_actions(actions, {}, "fixture-v1")

    assert compiled[0]["exclusive_choice_group"] is None
