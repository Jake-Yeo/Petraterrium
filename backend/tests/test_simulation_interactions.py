from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from petraterrium.simulation.interactions import (
    InteractionAgentColumns,
    InteractionCatalog,
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionPlace,
    InteractionQuery,
    InteractionRelationship,
    InteractionRequest,
    InteractionRule,
    InteractionRunRegistry,
    RelationshipProfile,
    TimeFactorWindow,
    create_interaction_router,
)


def provenance(status="measured_joint"):
    return InteractionFactorProvenance(
        source="Imported time-use panel",
        version="2025-v2",
        source_date="2025-09-17",
        evidence_id="time-use-panel-2025",
        licence="Test fixture",
        status=status,
        uncertainty=0.04,
    )


def factor(identity, value=1.0, status="measured_joint"):
    return InteractionFactor(
        id=identity,
        label=identity.replace("_", " "),
        value=value,
        provenance=provenance(status),
    )


def rule():
    return InteractionRule(
        id="family-talk",
        source_action="talk",
        interaction_type="talk",
        channel="in_person",
        max_targets_per_initiator=1,
        allowed_relationships=("family", "stranger"),
        allowed_place_kinds=("home",),
        base_factor=factor("base"),
        relationship_factors={
            "family": factor("family"),
            "stranger": factor("stranger", 0.05),
        },
        colocation_factors={"same_specific_place": factor("co_location")},
        place_factors={"home": factor("home")},
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=17,
                end_hour=23,
                factor=factor("evening"),
            ),
        ),
        unrelated_relationship=RelationshipProfile(
            kind="stranger", weight=0.1, trust=0.2, similarity=0.3
        ),
    )


def request():
    return InteractionRequest(
        seed=4,
        tick=1,
        hour=19,
        weekday=2,
        agents=InteractionAgentColumns(
            agent_ids=("parent", "child"),
            place=(0, 0),
            actions=(("talk",), ()),
            states={"mood": (0.0, 0.0)},
        ),
        places=(InteractionPlace(id="home-1", kind="home", allows_in_person=True),),
        relationships=(
            InteractionRelationship(
                source_index=0,
                target_index=1,
                kind="family",
                weight=0.9,
                trust=0.8,
                similarity=0.7,
            ),
        ),
        rules=(rule(),),
    )


def rust_event(tick=3, initiator="parent", target="child", relationship="family"):
    return {
        "tick": tick,
        "hour": 19.0,
        "weekday": 4,
        "rule_id": "family-talk",
        "interaction_type": "talk",
        "channel": "in_person",
        "initiator_index": 0,
        "initiator_id": initiator,
        "target_index": 1,
        "target_id": target,
        "place_index": 0,
        "place_id": "home-1",
        "relationship_type": relationship,
        "relationship_weight": 0.9,
        "trust": 0.8,
        "similarity": 0.7,
        "probability": 0.54,
        "factors": [
            {"kind": "base", "factor": factor("base", 0.9).model_dump(mode="json")},
            {
                "kind": "relationship",
                "factor": factor("family", 0.6).model_dump(mode="json"),
            },
        ],
        "state_deltas": [
            {
                "agent_id": target,
                "state": "mood",
                "before": 0.1,
                "delta": 0.2,
                "after": 0.3,
            }
        ],
        "relationship_deltas": [
            {
                "source_agent_id": initiator,
                "target_agent_id": target,
                "field": "trust",
                "before": 0.8,
                "delta": 0.05,
                "after": 0.85,
            }
        ],
    }


def test_request_keeps_explicit_evidence_and_columnar_state_for_rust():
    payload = request().rust_payload()
    assert payload["agents"]["agent_ids"] == ["parent", "child"]
    assert payload["rules"][0]["relationship_factors"]["family"]["value"] == 1
    assert payload["rules"][0]["relationship_factors"]["stranger"]["value"] == 0.05
    assert (
        payload["rules"][0]["colocation_factors"]["same_specific_place"]["provenance"]["source"]
        == "Imported time-use panel"
    )


def test_in_person_rule_cannot_exist_without_colocation_evidence():
    payload = rule().model_dump()
    payload["colocation_factors"] = {"different_specific_place": factor("apart")}
    try:
        InteractionRule.model_validate(payload)
    except ValidationError as error:
        assert "same-specific-place factor" in str(error)
    else:
        raise AssertionError("Expected in-person rule validation to fail")


def test_catalog_filters_both_directions_and_reports_agent_breakdowns():
    output = {
        "events": [
            rust_event(),
            rust_event(4, initiator="friend", target="parent", relationship="friend"),
        ]
    }
    catalog = InteractionCatalog.from_rust_output(
        output,
        {"parent": "Mara", "child": "Noah", "friend": "Avery"},
    )
    page = catalog.query(InteractionQuery(agent_id="parent"))
    assert page.total == 2
    assert page.breakdown.by_relationship == {"friend": 1, "family": 1}
    assert page.breakdown.by_counterparty == {"Avery": 1, "Noah": 1}
    received = catalog.query(InteractionQuery(agent_id="parent", direction="target"))
    assert received.total == 1
    assert received.items[0].initiator_name == "Avery"
    detail = catalog.detail(page.items[-1].event_id)
    assert detail.initiator_name == "Mara"
    assert detail.target_name == "Noah"
    assert detail.effect_count == 2
    assert detail.factors[1].factor.provenance.source == "Imported time-use panel"


def test_catalog_preserves_interaction_tree_path_and_outcome():
    event = rust_event()
    event["interaction_tree"] = {
        "tree_id": "talk-tree",
        "tree_version": "v2",
        "outcome_node": "agree",
        "outcome": "increase_trust",
        "path": [
            {
                "node_id": "topic",
                "transition_id": "topic-to-agree",
                "outcome": "increase_trust",
                "probability": 0.6,
                "draw": 0.2,
                "evidence": {
                    "source": "Imported conversation study",
                    "version": "2025-v1",
                    "status": "measured_joint",
                    "uncertainty": 0.08,
                    "source_date": "2025-03-01",
                    "evidence_id": "talk-joint-1",
                },
            }
        ],
    }

    detail = (
        InteractionCatalog.from_rust_output({"events": [event]}).query(InteractionQuery()).items[0]
    )
    full = InteractionCatalog.from_rust_output({"events": [event]}).detail(detail.event_id)

    assert full.interaction_tree is not None
    assert full.interaction_tree.outcome == "increase_trust"
    assert full.interaction_tree.path[0].evidence.evidence_id == "talk-joint-1"


def test_router_exposes_run_scoped_interactions_and_exact_detail():
    registry = InteractionRunRegistry()
    catalog = registry.record(
        "run-1",
        {"events": [rust_event()]},
        {"parent": "Mara", "child": "Noah"},
    )
    application = FastAPI()
    application.include_router(create_interaction_router(registry), prefix="/api")
    client = TestClient(application)
    response = client.get("/api/simulation/runs/run-1/interactions?agent_id=parent")
    assert response.status_code == 200
    assert response.json()["items"][0]["initiator_name"] == "Mara"
    event_id = catalog.query(InteractionQuery()).items[0].event_id
    detail = client.get(f"/api/simulation/runs/run-1/interactions/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["state_deltas"][0]["agent_id"] == "child"
    assert client.get("/api/simulation/runs/missing/interactions").status_code == 404


def test_registry_accumulates_chunks_idempotently():
    registry = InteractionRunRegistry()
    names = {"parent": "Mara", "child": "Noah"}
    first = rust_event(tick=3)
    second = rust_event(tick=4)

    registry.record("run-1", {"events": [first]}, names)
    registry.record("run-1", {"events": [second]}, names)
    registry.record("run-1", {"events": [first]}, names)

    page = registry.catalog("run-1").query(InteractionQuery())
    assert page.total == 2
    assert [event.tick for event in page.items] == [4, 3]
