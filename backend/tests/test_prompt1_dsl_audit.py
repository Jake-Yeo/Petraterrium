from pathlib import Path

from petraterrium.simulation.prompt1_dsl_audit import (
    audit_prompt1_dsl,
    audit_prompt1_dsl_document,
)

ROOT = Path(__file__).resolve().parents[2]


def agent(identity, country):
    return {
        "agent_id": identity,
        "place": country,
        "role": "person",
        "traits": {
            "agent_type": "person",
            "agent_types": ["person"],
            "country_id": country,
        },
    }


def complete_action(cash_flow=None):
    return {
        "id": "social_activity",
        "category": "social",
        "formula": "P(social_activity) = configured probability",
        "conditions": [],
        "duration": {
            "duration_min_hours": 0.25,
            "duration_median_hours": 1,
            "duration_max_hours": 3,
            "shape": "triangular",
            "shape_parameters": {},
        },
        "priority": 50,
        "passive": False,
        "interruptibility": "interruptible",
        "interruption_outcome": "defer",
        "emergency_interruptions": [],
        "place_requirements": ["home"],
        "time_requirements": ["evening"],
        "state_inputs": ["loneliness"],
        "outcomes": [
            {
                "state_id": "loneliness",
                "operation": "subtract",
                "value": 0.1,
            }
        ],
        "cash_flow": cash_flow or {},
    }


def finance_rules():
    return {
        "rules": [
            {
                "target": f"finance.{ledger}",
                "formula": f"finance.{ledger}[t+1] = weighted DSL inputs",
                "terms": [],
            }
            for ledger in ("money", "income", "expenses", "savings", "debt")
        ]
    }


def valid_manifest():
    return {
        "content": {
            "initial_population": {
                "population": {"agents": [agent("ca-1", "CA"), agent("in-1", "IN")]}
            },
            "decision_trees": {
                "trees": [
                    {
                        "id": "daily_activity",
                        "status": "ready",
                        "agent_type_ids": ["person"],
                        "place_ids": [],
                    }
                ]
            },
            "default_actions": [complete_action()],
            "agent_states": {
                "definitions": [
                    {
                        "id": "loneliness",
                        "recovery": {
                            "formula": "loneliness[t+1] = loneliness[t] + configured recovery"
                        },
                    }
                ]
            },
            "finance_rules": finance_rules(),
            "interaction_program": {
                "status": "confirmed",
                "rules": [{"id": "social-contact", "source_action": "social_activity"}],
            },
            "routines": {"routines": []},
        }
    }


def test_audit_accepts_content_complete_dsl_and_generic_runtime():
    report = audit_prompt1_dsl_document(valid_manifest(), {})

    assert report.compliant
    assert report.finding_ids == ()
    assert report.render() == "Prompt 1 DSL audit passed"


def test_audit_catches_scope_content_and_runtime_shortcuts():
    manifest = valid_manifest()
    content = manifest["content"]
    content["decision_trees"]["trees"][0]["place_ids"] = ["CA"]
    content["default_actions"] = [complete_action({"other_expenses": 20.0})]
    content["agent_states"]["definitions"] = [{"id": "loneliness"}]
    content.pop("finance_rules")
    content.pop("interaction_program")
    runtime_sources = {
        "runtime_decision_compiler.py": (
            'BASELINE_PROGRAM_VERSION = "v1"\n'
            "def _baseline_module():\n"
            '    return "remain-active-without-confirmed-decision-program", "social_activity"\n'
        ),
        "runtime_state_compiler.py": 'formula = f"{target}[t+1] + event_delta"\n',
        "state_finance.rs": (
            "let income = flows.wages;\n"
            "let expenses = flows.housing;\n"
            "next.money[agent_index] = Some(0.0);\n"
        ),
    }

    report = audit_prompt1_dsl_document(manifest, runtime_sources)

    assert set(report.finding_ids) == {
        "decision_tree_population_uncovered",
        "finance_ledger_formula_missing",
        "global_cash_flow_constant",
        "interaction_program_missing",
        "runtime_action_identifier_hardcoded",
        "runtime_hardcoded_finance_formula",
        "runtime_synthesized_baseline_action",
        "runtime_synthesized_state_formula",
        "state_formula_missing",
    }
    assert "IN=1" in report.render()
    assert "target-plus-weighted-inputs" in report.render()


def test_audit_rejects_interaction_rule_with_unobservable_source_action():
    manifest = valid_manifest()
    manifest["content"]["interaction_program"]["rules"][0]["source_action"] = (
        "free text that no event emits"
    )

    report = audit_prompt1_dsl_document(manifest, {})

    assert report.finding_ids == ("interaction_source_action_unknown",)


def test_shipped_prompt1_content_has_no_engine_owned_rules():
    report = audit_prompt1_dsl(ROOT)

    assert report.compliant, report.render()
