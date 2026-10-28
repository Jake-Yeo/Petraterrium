import json

import pytest

from petraterrium.simulation.default_dsl import DefaultActionDefinition
from petraterrium.simulation.editable_dsl_contracts import EditableDslDocument
from petraterrium.simulation.editable_dsl_semantics import (
    probability_value,
    runtime_conditions,
    validate_transition_profiles,
)
from petraterrium.simulation.run_warnings import RunCoefficientReceipt, evidence_summary
from petraterrium.simulation.runtime_state_compiler import _meaningful_actions
from tests.test_default_pipeline_runs import _action


def document_with_threshold(value=0.4):
    return EditableDslDocument.model_validate(
        {
            "schema_version": "2",
            "version": "test",
            "tick_hours": 1,
            "actions": [],
            "states": [
                {
                    "id": "stress",
                    "name": "Stress",
                    "min": 0,
                    "max": 1,
                    "initial": 0,
                    "decay_per_hour": 0,
                    "recovery_per_hour": 0,
                    "thresholds": [{"id": "high", "label": "High stress", "value": value}],
                }
            ],
            "trees": [
                {
                    "id": "choice",
                    "name": "Choice",
                    "entry_node": "entry",
                    "nodes": [
                        {"id": "entry", "label": "Entry", "kind": "entry"},
                        {"id": "rest", "label": "Rest", "kind": "terminal"},
                        {"id": "work", "label": "Work", "kind": "terminal"},
                    ],
                    "edges": [
                        {
                            "id": "rest",
                            "from_node": "entry",
                            "to_node": "rest",
                            "probability": 0.5,
                            "formula": "1",
                            "condition": "memory.stress >= threshold(stress, high)",
                        },
                        {
                            "id": "work",
                            "from_node": "entry",
                            "to_node": "work",
                            "probability": 0.5,
                            "formula": "1",
                            "condition": "memory.stress < threshold(stress, high)",
                        },
                    ],
                }
            ],
        }
    )


def test_threshold_edits_change_compiled_numeric_conditions():
    before = runtime_conditions(
        "memory.stress >= threshold(stress, high)", document_with_threshold()
    )
    after = runtime_conditions(
        "memory.stress >= threshold(stress, high)", document_with_threshold(0.8)
    )
    assert before == [{"input": "memory.stress", "operator": "gte", "value": 0.4}]
    assert after == [{"input": "memory.stress", "operator": "gte", "value": 0.8}]


def test_place_time_and_coefficient_expressions_are_executable_primitives():
    document = document_with_threshold()
    assert probability_value("clamp(coefficient(rate) * 2, 0, 1)", {"rate": 0.2}) == 0.4
    assert runtime_conditions("place.kind == 'bar' and context.weekday == 4", document) == [
        {"input": "place.kind", "operator": "eq", "value": 0.0, "categorical_value": "bar"},
        {"input": "context.weekday", "operator": "eq", "value": 4.0},
    ]


def test_conditional_tree_requires_explicit_complete_probabilities():
    document = document_with_threshold()
    validate_transition_profiles(document.trees[0], document)
    edge = document.trees[0].edges[0].model_copy(update={"formula": "0.5"})
    tree = document.trees[0].model_copy(update={"edges": (edge, document.trees[0].edges[1])})
    with pytest.raises(ValueError, match="Executable outgoing probabilities"):
        validate_transition_profiles(tree, document)


@pytest.mark.parametrize("expression", ["agent.age * 0.1", "fetch('source')", "1 / 0", "2"])
def test_unsupported_or_invalid_formulas_are_rejected(expression):
    with pytest.raises(ValueError):
        probability_value(expression, {})


def test_measured_coefficients_remain_distinct_in_backward_compatible_run_summary():
    receipt = RunCoefficientReceipt.model_validate(
        {
            "action_id": "social",
            "edge_id": "go_out",
            "place": {
                "level": "country",
                "place_id": "CA",
                "region_id": "NORTH_AMERICA",
                "country_id": "CA",
            },
            "evidence_state": "measured",
            "value": 0.2,
            "interval": {"low": 0.1, "high": 0.3},
            "coefficient_set_id": "survey",
            "default_coefficient_set_id": "prior",
            "default_value": 0.1,
            "source_label": "Country survey",
            "source_version": "2026",
        }
    )
    summary, warnings = evidence_summary([receipt])
    assert summary.measured_count == 1
    assert summary.default_estimated_count == summary.fitted_count == 0
    assert summary.by_action_place[0].measured_count == 1
    assert warnings == []


def test_native_runtime_rule_retains_measured_provenance_after_editor_cache_is_removed():
    action = _action("social")
    action["runtime_rules"] = [
        {
            "conditions": [],
            "probability": 0.2,
            "evidence": {
                "status": "default_estimated",
                "explicit_default_reason": "Confirmed survey mapping",
                "uncertainty_low": 0.1,
                "uncertainty_high": 0.3,
                "source_ids": [],
                "editable_provenance": {
                    "status": "measured",
                    "source": "Country survey",
                    "sourceVersion": "2026",
                    "sourceDate": "2026-01-01",
                    "uncertainty": 0.1,
                },
            },
        }
    ]
    native = DefaultActionDefinition.model_validate_json(json.dumps(action))
    compiled = _meaningful_actions([native], {}, "later-cache-version", {})
    provenance = compiled[0]["rules"][0]["provenance"]
    assert provenance["status"] == "measured"
    assert provenance["source"] == "Country survey"
    assert provenance["version"] == "2026"
