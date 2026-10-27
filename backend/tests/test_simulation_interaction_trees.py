from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from petraterrium.simulation.interaction_trees import (
    AgentRoutineEffect,
    AgentStateEffect,
    DirectedRelationship,
    InteractionParticipant,
    InteractionPlaceContext,
    InteractionProbabilityFactor,
    InteractionProbabilityFactorCase,
    InteractionTimeContext,
    InteractionTransitionEvidence,
    InteractionTreeCondition,
    InteractionTreeContext,
    InteractionTreeDefinition,
    InteractionTreeNode,
    InteractionTreeRegistry,
    InteractionTreeRequest,
    InteractionTreeTransition,
    RelationshipKindEffect,
    RelationshipStateEffect,
    create_interaction_tree_router,
)


def evidence():
    return InteractionTransitionEvidence(
        source="Observed relationship panel",
        version="2026-01",
        status="measured_joint",
        uncertainty=0.08,
        source_date="2026-01-15",
        evidence_id="relationship-panel-acceptance",
    )


def definition():
    conditions = (
        InteractionTreeCondition(
            input="relationship.state.strength",
            operator="gte",
            value=0.5,
        ),
        InteractionTreeCondition(input="co_located", operator="eq", value=True),
    )
    return InteractionTreeDefinition(
        id="ask_out",
        name="Ask someone out",
        version="1",
        entry_node="asked",
        allowed_channels=("in_person", "phone_message"),
        co_location_policy="remote_allowed",
        nodes=(
            InteractionTreeNode(id="asked", label="Actor asks target", terminal=False),
            InteractionTreeNode(id="dating", label="Target accepts", terminal=True),
            InteractionTreeNode(id="declined", label="Target declines", terminal=True),
        ),
        transitions=(
            InteractionTreeTransition(
                id="accept",
                from_node="asked",
                to_node="dating",
                outcome="accepted",
                probability=1,
                evidence=evidence(),
                conditions=conditions,
                effects=(
                    RelationshipKindEffect(relationship_type="dating"),
                    RelationshipStateEffect(
                        field="strength",
                        operation="add",
                        value=0.2,
                        minimum=0,
                        maximum=1,
                    ),
                    AgentRoutineEffect(
                        participant="actor", operation="add", routine_id="partner_time"
                    ),
                    AgentRoutineEffect(
                        participant="target", operation="add", routine_id="partner_time"
                    ),
                    AgentStateEffect(
                        participant="actor",
                        field="confidence",
                        operation="add",
                        value=0.1,
                        minimum=0,
                        maximum=1,
                    ),
                    AgentStateEffect(
                        participant="target",
                        field="confidence",
                        operation="add",
                        value=0.05,
                        minimum=0,
                        maximum=1,
                    ),
                ),
            ),
            InteractionTreeTransition(
                id="decline",
                from_node="asked",
                to_node="declined",
                outcome="declined",
                probability=0,
                evidence=evidence(),
                conditions=conditions,
            ),
        ),
    )


def request():
    return InteractionTreeRequest(
        seed=29,
        tick=48,
        tree=definition(),
        context=InteractionTreeContext(
            actor=InteractionParticipant(
                agent_id="agent-a",
                place_id="cafe-1",
                states={"confidence": 0.5},
                routines=("weekly_social",),
            ),
            target=InteractionParticipant(
                agent_id="agent-b",
                place_id="cafe-1",
                states={"confidence": 0.5},
                routines=("weekly_social",),
            ),
            relationship=DirectedRelationship(
                source_agent_id="agent-a",
                target_agent_id="agent-b",
                eligible=True,
                relationship_type="acquaintance",
                states={"strength": 0.7},
            ),
            place=InteractionPlaceContext(id="cafe-1", kind="cafe"),
            time=InteractionTimeContext(weekday=5, hour=19),
            channel="in_person",
        ),
    )


def response_definition(target_tree_id=None):
    return InteractionTreeDefinition(
        id="talk_response",
        name="Talk response",
        version="1",
        entry_node="listen",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="listen", label="Listen", terminal=False),
            InteractionTreeNode(
                id="responded",
                label="Responded",
                terminal=True,
                target_tree_id=target_tree_id,
            ),
        ),
        transitions=(
            InteractionTreeTransition(
                id="respond",
                from_node="listen",
                to_node="responded",
                outcome="responded",
                probability=1,
                evidence=evidence(),
                effects=(
                    AgentStateEffect(
                        participant="target",
                        field="confidence",
                        operation="add",
                        value=0.2,
                        minimum=0,
                        maximum=1,
                    ),
                ),
            ),
        ),
    )


def talk_definition(target_tree_id="talk_response"):
    return InteractionTreeDefinition(
        id="talk",
        name="Talk",
        version="1",
        entry_node="start",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="start", label="Start talking", terminal=False),
            InteractionTreeNode(
                id="open_response",
                label="Open response",
                terminal=True,
                target_tree_id=target_tree_id,
            ),
        ),
        transitions=(
            InteractionTreeTransition(
                id="speak",
                from_node="start",
                to_node="open_response",
                outcome="spoke",
                probability=1,
                evidence=evidence(),
                effects=(
                    AgentStateEffect(
                        participant="actor",
                        field="confidence",
                        operation="add",
                        value=0.1,
                        minimum=0,
                        maximum=1,
                    ),
                ),
            ),
        ),
    )


def rust_result():
    payload = request().model_dump(mode="json")
    actor_before = payload["context"]["actor"]
    target_before = payload["context"]["target"]
    relationship_before = payload["context"]["relationship"]
    actor_after = {**actor_before, "states": {"confidence": 0.6}}
    actor_after["routines"] = ["partner_time", "weekly_social"]
    target_after = {**target_before, "states": {"confidence": 0.55}}
    target_after["routines"] = ["partner_time", "weekly_social"]
    relationship_after = {
        **relationship_before,
        "relationship_type": "dating",
        "states": {"strength": 0.9},
    }
    return {
        "tree_id": "ask_out",
        "tree_version": "1",
        "seed": 29,
        "tick": 48,
        "outcome_node": "dating",
        "outcome": "accepted",
        "path": [
            {
                "node_id": "asked",
                "transition_id": "accept",
                "outcome": "accepted",
                "probability": 1,
                "draw": 0.4,
                "evidence": evidence().model_dump(mode="json"),
            }
        ],
        "receipt": {
            "actor_id": "agent-a",
            "target_id": "agent-b",
            "relationship_direction": "agent-a→agent-b",
            "place_id": "cafe-1",
            "channel": "in_person",
            "weekday": 5,
            "hour": 19,
        },
        "actor_before": actor_before,
        "actor_after": actor_after,
        "target_before": target_before,
        "target_after": target_after,
        "relationship_before": relationship_before,
        "relationship_after": relationship_after,
        "changes": [
            {
                "recipient": "relationship",
                "field": "kind",
                "before": "acquaintance",
                "after": "dating",
            },
            {
                "recipient": "actor",
                "field": "routine.partner_time",
                "before": False,
                "after": True,
            },
            {
                "recipient": "target",
                "field": "routine.partner_time",
                "before": False,
                "after": True,
            },
        ],
    }


def test_rejects_unknown_evidence_before_a_transition_can_drive_the_tree():
    payload = evidence().model_dump()
    payload["status"] = "unknown"

    try:
        InteractionTransitionEvidence.model_validate(payload)
    except ValidationError as error:
        assert "measured_joint" in str(error)
    else:
        raise AssertionError("Unknown evidence must not select an interaction transition")


def test_transition_factor_contract_preserves_runtime_inputs_provenance_and_effect_scales():
    factor = InteractionProbabilityFactor(
        id="pair-trust",
        label="Pair trust",
        cases=(
            InteractionProbabilityFactorCase(
                id="low",
                conditions=(
                    InteractionTreeCondition(
                        input="relationship.state.trust",
                        operator="lt",
                        value=0.5,
                    ),
                ),
                multiplier=0.5,
            ),
            InteractionProbabilityFactorCase(
                id="high",
                conditions=(
                    InteractionTreeCondition(
                        input="relationship.state.trust",
                        operator="gte",
                        value=0.5,
                    ),
                ),
                multiplier=2,
            ),
        ),
        evidence=evidence(),
    )
    transition = definition().transitions[0].model_copy(
        update={
            "probability_factors": (factor,),
            "effects": (
                AgentStateEffect(
                    participant="actor",
                    field="confidence",
                    operation="add",
                    value=0.1,
                    minimum=0,
                    maximum=1,
                    scale_by=("relationship.state.trust",),
                ),
            ),
        }
    )

    payload = transition.model_dump(mode="json")

    assert payload["probability_factors"][0]["cases"][1]["multiplier"] == 2
    assert payload["probability_factors"][0]["evidence"]["evidence_id"] == (
        "relationship-panel-acceptance"
    )
    assert payload["effects"][0]["scale_by"] == ["relationship.state.trust"]
    assert InteractionTreeCondition(
        input="actor.trait.sociability", operator="gte", value=0.5
    ).input == "actor.trait.sociability"


def test_requires_co_location_for_in_person_interaction():
    payload = request().model_dump(mode="json")
    payload["context"]["target"]["place_id"] = "cafe-2"

    try:
        InteractionTreeRequest.model_validate(payload)
    except ValidationError as error:
        assert "specific-place co-location" in str(error)
    else:
        raise AssertionError("In-person interaction must require co-location")


def test_requires_relationship_direction_from_actor_to_target():
    payload = request().model_dump(mode="json")
    payload["context"]["relationship"]["source_agent_id"] = "agent-b"
    payload["context"]["relationship"]["target_agent_id"] = "agent-a"

    try:
        InteractionTreeRequest.model_validate(payload)
    except ValidationError as error:
        assert "directed from actor to target" in str(error)
    else:
        raise AssertionError("Reversed relationship must be rejected")


def test_router_returns_atomic_changes_for_actor_target_and_relationship():
    registry = InteractionTreeRegistry((definition(),))
    received = []

    def executor(payload):
        received.append(payload)
        return {
            **rust_result(),
            "protocol_version": "1",
            "engine_version": "0.1.0",
        }

    application = FastAPI()
    application.include_router(create_interaction_tree_router(registry, executor))
    client = TestClient(application)

    response = client.post(
        "/simulation/interaction-trees/ask_out/evaluate",
        json=request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["outcome"] == "accepted"
    assert result["relationship_before"]["relationship_type"] == "acquaintance"
    assert result["relationship_after"]["relationship_type"] == "dating"
    assert {change["recipient"] for change in result["changes"]} == {
        "actor",
        "target",
        "relationship",
    }
    assert result["path"][0]["evidence"]["source"] == "Observed relationship panel"
    assert received[0]["operation"] == "run_interaction_tree"


def test_registry_resolves_talk_to_nested_response_for_rust_execution():
    registry = InteractionTreeRegistry((talk_definition(), response_definition()))

    assert registry.execution_trees("talk") == {
        "talk_response": response_definition()
    }


def test_registry_rejects_missing_references_cycles_and_depth_over_five():
    try:
        InteractionTreeRegistry((talk_definition(),))
    except ValueError as error:
        assert "references missing tree talk_response" in str(error)
    else:
        raise AssertionError("Missing interaction tree references must be rejected")

    try:
        InteractionTreeRegistry(
            (talk_definition(), response_definition(target_tree_id="talk"))
        )
    except ValueError as error:
        assert "reference cycle" in str(error)
    else:
        raise AssertionError("Interaction tree reference cycles must be rejected")

    definitions = []
    for level in range(1, 7):
        target = f"level-{level + 1}" if level < 6 else None
        definitions.append(
            InteractionTreeDefinition(
                id=f"level-{level}",
                name=f"Level {level}",
                version="1",
                entry_node="call",
                allowed_channels=("in_person",),
                co_location_policy="required",
                nodes=(
                    InteractionTreeNode(
                        id="call",
                        label="Call next",
                        terminal=True,
                        target_tree_id=target,
                    ),
                ),
                transitions=(),
            )
        )
    try:
        InteractionTreeRegistry(tuple(definitions))
    except ValueError as error:
        assert "depth exceeds 5" in str(error)
    else:
        raise AssertionError("Interaction tree reference depth must be capped at five")


def test_router_supplies_registered_nested_trees_to_rust():
    registry = InteractionTreeRegistry((talk_definition(), response_definition()))
    received = []
    nested_request = request().model_copy(update={"tree": talk_definition()})
    result = rust_result()
    result.update(
        {
            "tree_id": "talk",
            "tree_version": "1",
            "outcome_node": "open_response",
            "outcome": "responded",
            "path": [
                {
                    "tree_id": "talk",
                    "node_id": "start",
                    "transition_id": "speak",
                    "outcome": "spoke",
                    "probability": 1,
                    "draw": 0.2,
                    "evidence": evidence().model_dump(mode="json"),
                },
                {
                    "tree_id": "talk_response",
                    "node_id": "listen",
                    "transition_id": "respond",
                    "outcome": "responded",
                    "probability": 1,
                    "draw": 0.3,
                    "evidence": evidence().model_dump(mode="json"),
                },
            ],
        }
    )

    def executor(payload):
        received.append(payload)
        return result

    application = FastAPI()
    application.include_router(create_interaction_tree_router(registry, executor))
    client = TestClient(application)

    response = client.post(
        "/simulation/interaction-trees/talk/evaluate",
        json=nested_request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert [step["tree_id"] for step in response.json()["path"]] == [
        "talk",
        "talk_response",
    ]
    assert received[0]["trees"]["talk_response"]["id"] == "talk_response"
