import json
from copy import deepcopy
from pathlib import Path

from petraterrium.contracts import ActionLogEntry, DecisionGraphFilter
from petraterrium.decision_graph import run_decision_graph, static_decision_graph
from petraterrium.dsl import DSLConfig, validate_dsl

SMOKE_PATH = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"


def smoke_config():
    return json.loads(SMOKE_PATH.read_text())


def log(
    agent: str,
    action: str,
    previous: str | None,
    step: int,
    state: str,
    tick: int,
):
    return ActionLogEntry(
        chain_id="sharing",
        agent_id=agent,
        tick=tick,
        action_id=action,
        target_agent_id="agent-c" if action == "repost" else None,
        place="Northport",
        cause="FAKE deterministic action fixture",
        state_before={"signal": state},
        state_after={"signal": state},
        previous_action_id=previous,
        chain_step_index=step,
        segment="spotlight",
        role="citizen",
    )


def test_static_graph_contains_every_dsl_action_and_no_invented_nodes():
    dsl = DSLConfig.model_validate(smoke_config())
    graph = static_decision_graph(dsl)
    assert {node.action_id for node in graph.nodes} == {action.id for action in dsl.actions}
    assert {edge.target for edge in graph.edges} <= {action.id for action in dsl.actions}
    assert {edge.source for edge in graph.edges} <= {action.id for action in dsl.actions}
    assert all(edge.terminates for edge in graph.edges)
    talk = next(node for node in graph.nodes if node.action_id == "talk")
    assert talk.opportunity == "social_contact"
    assert talk.loser_outcome == "deferred"
    assert talk.reschedulable is True
    assert any(item.kind == "dead_end" for item in graph.diagnostics)


def test_run_graph_edge_frequency_matches_action_log_and_spotlight_path_order():
    dsl = DSLConfig.model_validate(smoke_config())
    logs = [
        log("agent-a", "scroll", None, 0, "aware", 1),
        log("agent-a", "repost", "scroll", 1, "aware", 1),
        log("agent-b", "scroll", None, 0, "aware", 1),
        log("agent-b", "ignore", "scroll", 1, "aware", 1),
        log("agent-c", "scroll", None, 0, "unaware", 2),
        log("agent-c", "ignore", "scroll", 1, "unaware", 2),
    ]
    graph = run_decision_graph(dsl, logs, run_id="run-1", agent_id="agent-a")
    edges = {(edge.source, edge.target): edge for edge in graph.edges}
    assert edges[("scroll", "repost")].observed_count == 1
    assert edges[("scroll", "repost")].observed_frequency == 1 / 3
    assert edges[("scroll", "ignore")].observed_count == 2
    assert edges[("scroll", "ignore")].observed_frequency == 2 / 3
    assert [step.action_id for step in graph.path] == ["scroll", "repost"]
    assert [step.chain_step_index for step in graph.path] == [0, 1]


def test_state_filter_changes_observed_outgoing_edges():
    dsl = DSLConfig.model_validate(smoke_config())
    logs = [
        log("agent-a", "scroll", None, 0, "aware", 1),
        log("agent-a", "repost", "scroll", 1, "aware", 1),
        log("agent-b", "scroll", None, 0, "unaware", 1),
        log("agent-b", "ignore", "scroll", 1, "unaware", 1),
    ]
    aware = run_decision_graph(
        dsl,
        logs,
        run_id="run-1",
        filters=DecisionGraphFilter(state="aware"),
    )
    unaware = run_decision_graph(
        dsl,
        logs,
        run_id="run-1",
        filters=DecisionGraphFilter(state="unaware"),
    )
    assert {(edge.source, edge.target) for edge in aware.edges if edge.observed_count} == {
        ("scroll", "repost")
    }
    assert {(edge.source, edge.target) for edge in unaware.edges if edge.observed_count} == {
        ("scroll", "ignore")
    }


def test_graph_flags_orphans_dead_ends_nonterminating_loops_and_overlong_logs():
    payload = smoke_config()
    payload["actions"].append(
        {
            **deepcopy(payload["actions"][0]),
            "id": "unreachable_action",
            "probability": {**payload["actions"][0]["probability"], "base": 0},
            "meaningful": True,
        }
    )
    payload["chains"].append(
        {
            "id": "unbounded-loop",
            "trigger": "repost",
            "branches": [{"action": "repost", "probability": 1, "delay_ticks": 0}],
            "max_length": None,
            "continue_probability": 1,
        }
    )
    dsl = DSLConfig.model_validate(payload)
    graph = static_decision_graph(dsl)
    kinds = {(item.kind, item.subject) for item in graph.diagnostics}
    assert ("orphan", "unreachable_action") in kinds
    assert ("dead_end", "unreachable_action") in kinds
    assert ("nonterminating_loop", "unbounded-loop") in kinds
    assert "termination bound" in " ".join(
        item.message for item in validate_dsl(payload).errors
    ).lower()

    logs = [
        log("agent-a", "scroll", None, 0, "aware", 1),
        log("agent-a", "repost", "scroll", 2, "aware", 1),
    ]
    run_graph = run_decision_graph(dsl, logs, run_id="run-1")
    assert any(
        item.kind == "chain_length" and item.subject == "sharing"
        for item in run_graph.diagnostics
    )
