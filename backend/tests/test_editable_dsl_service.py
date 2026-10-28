from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.default_dsl import DefaultDslService
from petraterrium.simulation.editable_dsl_contracts import (
    ConfirmEditableDslRequest,
    EditableDslTreeEdge,
    EditableDslTreeNode,
    PreviewEditableDslRequest,
)
from petraterrium.simulation.editable_dsl_persistence import JsonEditableDslRepository
from petraterrium.simulation.editable_dsl_routes import create_editable_dsl_router
from petraterrium.simulation.editable_dsl_service import EditableDslService
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import SimulationRunConfig


def confirm_document(service, document):
    current = service.current()
    preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=current.document_hash,
            document=document,
        )
    )
    assert preview.validation.valid, preview.validation.issues
    return service.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=current.document_hash,
            preview_hash=preview.preview_hash,
            document=document,
            user_confirmed=True,
        )
    )


def test_unrelated_edit_retains_original_duration_and_probability_sources(tmp_path):
    store, _, service = installed_service(tmp_path)
    original = store.payload_snapshot()
    current = service.current()
    confirm_document(service, changed_breakfast_duration(current))
    overlay = service.registry_overlay().payload_snapshot()
    for before, after in zip(original["default_actions"], overlay["default_actions"], strict=True):
        assert after["evidence"] == before["evidence"]
        assert after["duration"]["evidence"] == before["duration"].get(
            "evidence", before["evidence"]
        )
    assert [item["source"]["reason"] for item in overlay["coefficient_registry"]["defaults"]] == [
        item["source"]["reason"] for item in original["coefficient_registry"]["defaults"]
    ]


def test_tree_formulas_and_action_coefficient_evidence_compile_to_runtime(tmp_path):
    _, _, service = installed_service(tmp_path)
    current = service.current()
    actions = list(current.document.actions)
    index = next(i for i, action in enumerate(actions) if action.id == "eat_breakfast")
    action = actions[index]
    coefficient = action.coefficients[0].model_copy(
        update={
            "value": 0.25,
            "evidence": action.coefficients[0].evidence.model_copy(
                update={
                    "status": "measured",
                    "source": "Breakfast outcome survey",
                    "source_version": "survey-2",
                    "uncertainty": 0.1,
                }
            ),
        }
    )
    actions[index] = action.model_copy(
        update={"coefficients": (coefficient, *action.coefficients[1:])}
    )
    tree = current.document.trees[0]
    edges = tuple(
        edge.model_copy(update={"formula": "0.25" if i == 0 else "0.75"})
        for i, edge in enumerate(tree.edges)
    )
    exercise_node = next(node for node in tree.nodes if node.id == "exercise")
    nodes = tuple(
        node.model_copy(update={"kind": "action", "action_id": "exercise"})
        if node == exercise_node
        else node
        for node in tree.nodes
    )
    nodes = (*nodes, EditableDslTreeNode(id="finished", label="Finished", kind="terminal"))
    edges = (
        *edges,
        EditableDslTreeEdge(
            id="finish_exercise",
            from_node="exercise",
            to_node="finished",
            probability=1.0,
            formula="1",
            condition="always",
        ),
    )
    document = current.document.model_copy(
        update={
            "actions": tuple(actions),
            "trees": (tree.model_copy(update={"edges": edges, "nodes": nodes}),),
        }
    )
    confirm_document(service, document)
    prepared = prepare_registry_run(
        service.registry_overlay(),
        SimulationRunConfig(
            population_size=10,
            seed=1,
            days=1,
            tick_interval_hours=1,
            start_date="2026-10-27",
            place_scope={"level": "global", "identifier": None},
            agent_type_mix={},
        ),
    )
    probabilities = [
        transition["rules"][0]["probability"]
        for transition in prepared.rust_request["modules"][0]["transitions"]
    ]
    assert probabilities == [0.25, 0.75, 1.0]
    incoming = prepared.rust_request["modules"][0]["transitions"][0]
    assert incoming["action_id"] == "exercise"
    breakfast = next(
        item
        for item in prepared.rust_request["meaningful_actions"]
        if item["id"] == "eat_breakfast"
    )
    assert breakfast["rules"][0]["probability"] == 0.25
    assert breakfast["rules"][0]["provenance"]["source"] == "Breakfast outcome survey"
    assert breakfast["rules"][0]["provenance"]["status"] == "measured"
    assert prepared.coefficient_evidence.measured_count > 0
    receipt = next(
        item
        for group in prepared.coefficient_evidence.by_action_place
        for item in group.coefficients
        if item.source_label == "Breakfast outcome survey"
    )
    assert receipt.evidence_state == "measured"
    assert receipt.source_version == "survey-2"
    sleep = next(
        item
        for item in prepared.rust_request["state_dynamics"]["time_execution"]["actions"]
        if item["action_id"] == "eat_breakfast"
    )
    assert sleep["duration"]["provenance"]["source"] != "Breakfast outcome survey"


def test_unsupported_formula_blocks_confirmation_instead_of_saving_inert_text(tmp_path):
    _, _, service = installed_service(tmp_path)
    current = service.current()
    action = current.document.actions[0].model_copy(update={"formula": "internet_probability(age)"})
    document = current.document.model_copy(
        update={"actions": (action, *current.document.actions[1:])}
    )
    preview = service.preview(
        PreviewEditableDslRequest(expected_active_hash=current.document_hash, document=document)
    )
    assert not preview.validation.valid
    assert any(
        "Unsupported probability expression" in issue.message for issue in preview.validation.issues
    )


def installed_service(tmp_path):
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    DefaultDslService(store).ensure()
    repository = JsonEditableDslRepository(tmp_path / "editable-dsl")
    service = EditableDslService(
        store,
        repository,
        clock=lambda: datetime(2026, 10, 27, 12, tzinfo=UTC).isoformat(),
    )
    return store, repository, service


def changed_breakfast_duration(current, median_hours=0.4):
    actions = []
    for action in current.document.actions:
        if action.id != "eat_breakfast":
            actions.append(action)
            continue
        duration = action.duration.model_copy(update={"median_hours": median_hours})
        actions.append(action.model_copy(update={"duration": duration}))
    return current.document.model_copy(update={"actions": tuple(actions)})


def test_preview_is_non_mutating_and_confirmed_revision_overlays_the_next_run(tmp_path):
    store, repository, service = installed_service(tmp_path)
    current = service.current()
    original_payload = store.payload_snapshot()
    overlay = service.registry_overlay()
    edited = changed_breakfast_duration(current)

    preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=current.document_hash,
            document=edited,
        )
    )

    assert preview.validation.valid
    assert any(item.path.endswith("actions[1].duration.median_hours") for item in preview.diff)
    assert store.payload_snapshot() == original_payload
    assert repository.history() == ()

    accepted = service.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=current.document_hash,
            preview_hash=preview.preview_hash,
            document=edited,
            user_confirmed=True,
        )
    )

    assert accepted.revision == 1
    assert accepted.parent_hash == current.document_hash
    assert accepted.document_hash != current.document_hash
    assert service.current() == accepted
    assert repository.history() == (accepted,)

    overlaid_payload = overlay.payload_snapshot()
    breakfast = next(
        item for item in overlaid_payload["default_actions"] if item["id"] == "eat_breakfast"
    )
    assert breakfast["duration"]["duration_median_hours"] == 0.4
    assert overlaid_payload["editable_dsl"]["document_hash"] == accepted.document_hash
    assert overlay.default_dsl_receipt().hash == accepted.document_hash
    assert store.payload_snapshot() == original_payload
    prepared = prepare_registry_run(
        overlay,
        SimulationRunConfig(
            population_size=10,
            seed=1,
            days=1,
            tick_interval_hours=1,
            start_date="2026-10-27",
            place_scope={"level": "global", "identifier": None},
            agent_type_mix={},
        ),
    )
    assert prepared.default_dsl_hash == accepted.document_hash
    assert overlay.payload_snapshot()["default_dsl"]["hash"] == accepted.document_hash


def test_history_is_immutable_and_stale_confirmation_is_rejected(tmp_path):
    _, repository, service = installed_service(tmp_path)
    first = service.current()
    first_document = changed_breakfast_duration(first, 0.4)
    first_preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=first.document_hash,
            document=first_document,
        )
    )
    first_revision = service.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=first.document_hash,
            preview_hash=first_preview.preview_hash,
            document=first_document,
            user_confirmed=True,
        )
    )
    second_document = changed_breakfast_duration(first_revision, 0.45)
    second_preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=first_revision.document_hash,
            document=second_document,
        )
    )

    second_revision = service.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=first_revision.document_hash,
            preview_hash=second_preview.preview_hash,
            document=second_document,
            user_confirmed=True,
        )
    )

    assert [item.revision for item in repository.history()] == [2, 1]
    assert repository.get(first_revision.document_hash) == first_revision
    assert repository.get(second_revision.document_hash) == second_revision

    try:
        service.confirm(
            ConfirmEditableDslRequest(
                expected_active_hash=first.document_hash,
                preview_hash=first_preview.preview_hash,
                document=first_document,
                user_confirmed=True,
            )
        )
    except ValueError as error:
        assert "changed since preview" in str(error)
    else:
        raise AssertionError("Stale editable DSL confirmation was accepted")

    service.clear_active_overlay()
    assert service.current().source == "installed_registry"
    assert [item.revision for item in repository.history()] == [2, 1]


def test_overlay_applies_action_state_and_graph_edits_without_mutating_base_registry(tmp_path):
    store, _, service = installed_service(tmp_path)
    current = service.current()
    base_payload = store.payload_snapshot()
    actions = []
    for action in current.document.actions:
        if action.id == "eat_breakfast":
            coefficients = (
                action.coefficients[0].model_copy(update={"value": 0.8}),
                *action.coefficients[1:],
            )
            action = action.model_copy(
                update={
                    "formula": "coefficient(runtime_rule_1)",
                    "coefficients": coefficients,
                }
            )
        actions.append(action)
    states = tuple(
        state.model_copy(update={"initial": 0.25, "decay_per_hour": 0.01})
        if state.id == "stress"
        else state
        for state in current.document.states
    )
    trees = []
    for tree in current.document.trees:
        if tree.id == "daily_activity_module":
            edges = tuple(
                edge.model_copy(
                    update={
                        "probability": 0.6 if edge.id == "choose_exercise" else 0.4,
                        "formula": "1",
                        "condition": (
                            "memory.stress < 0.5"
                            if edge.id == "choose_exercise"
                            else "memory.stress >= 0.5"
                        ),
                    }
                )
                for edge in tree.edges
            )
            tree = tree.model_copy(update={"edges": edges})
        trees.append(tree)
    document = current.document.model_copy(
        update={"actions": tuple(actions), "states": states, "trees": tuple(trees)}
    )
    preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=current.document_hash,
            document=document,
        )
    )
    assert preview.validation.valid
    accepted = service.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=current.document_hash,
            preview_hash=preview.preview_hash,
            document=document,
            user_confirmed=True,
        )
    )

    overlay = service.registry_overlay()
    payload = overlay.payload_snapshot()
    breakfast = next(item for item in payload["default_actions"] if item["id"] == "eat_breakfast")
    assert breakfast["formula"] == "coefficient(runtime_rule_1)"
    assert breakfast["runtime_rules"][0]["probability"] == 0.8
    stress_rule = next(
        item
        for item in payload["agent_states"]["runtime_rules"]
        if item["target_state_id"] == "stress"
    )
    assert stress_rule["coefficients"]["stress"] == -0.01
    assert all(
        float(agent["states"]["stress"]) == 0.25
        for agent in payload["initial_population"]["population"]["agents"]
    )
    module = next(
        item
        for item in payload["decision_trees"]["modules"]
        if item["id"] == "daily_activity_module"
    )
    assert module["edges"][0]["condition"] == "memory.stress < 0.5"
    coefficient_set = next(
        item
        for item in payload["coefficient_registry"]["defaults"]
        if item["action_id"] == "daily_activity_module"
    )
    assert coefficient_set["coefficients"] == {
        "choose_exercise": 0.6,
        "choose_recovery": 0.4,
    }
    assert payload["editable_dsl"]["document"]["trees"][0]["edges"][0]["formula"] == "1"
    assert payload["default_dsl"]["hash"] == accepted.document_hash
    assert store.payload_snapshot() == base_payload
    changed_base = store.payload_snapshot()
    changed_base["external_registry_marker"] = "latest"
    with store._lock:
        store._write(changed_base)
    assert overlay.payload_snapshot()["external_registry_marker"] == "latest"


def test_validation_reports_duration_probability_reference_and_evidence_errors(tmp_path):
    _, _, service = installed_service(tmp_path)
    current = service.current()
    first_action = current.document.actions[0]
    invalid_duration = first_action.duration.model_copy(
        update={
            "min_hours": 0.5,
            "median_hours": 0.5,
            "max_hours": 0.5,
            "evidence": first_action.duration.evidence.model_copy(
                update={"source": "", "uncertainty": 2}
            ),
        }
    )
    invalid_action = first_action.model_copy(update={"duration": invalid_duration})
    first_tree = current.document.trees[0]
    first_edge = first_tree.edges[0].model_copy(
        update={"probability": 0.2, "to_node": "missing-node"}
    )
    invalid_tree = first_tree.model_copy(update={"edges": (first_edge, *first_tree.edges[1:])})
    invalid_document = current.document.model_copy(
        update={
            "actions": (invalid_action, *current.document.actions[1:]),
            "trees": (invalid_tree, *current.document.trees[1:]),
        }
    )

    preview = service.preview(
        PreviewEditableDslRequest(
            expected_active_hash=current.document_hash,
            document=invalid_document,
        )
    )

    messages = {item.message for item in preview.validation.issues}
    assert "A fixed action duration is not executable" in messages
    assert "Evidence source and source version are required" in messages
    assert "Evidence uncertainty must be between 0 and 1" in messages
    assert "Edge endpoints must reference nodes in the same tree" in messages
    assert any("Outgoing probabilities" in message for message in messages)
    assert not preview.validation.valid

    try:
        service.confirm(
            ConfirmEditableDslRequest(
                expected_active_hash=current.document_hash,
                preview_hash=preview.preview_hash,
                document=invalid_document,
                user_confirmed=True,
            )
        )
    except ValueError as error:
        assert "validation errors" in str(error)
    else:
        raise AssertionError("Invalid editable DSL document was confirmed")


def test_router_exposes_typed_preview_confirm_and_history_without_raw_edit_route(tmp_path):
    _, _, service = installed_service(tmp_path)
    app = FastAPI()
    app.include_router(create_editable_dsl_router(service))
    client = TestClient(app)

    current_response = client.get("/simulation/editable-dsl")
    assert current_response.status_code == 200
    current = current_response.json()
    document = current["document"]
    breakfast = next(item for item in document["actions"] if item["id"] == "eat_breakfast")
    assert "sourceVersion" in breakfast["duration"]["evidence"]
    assert "source_version" not in breakfast["duration"]["evidence"]
    breakfast["duration"]["median_hours"] = 0.4

    preview_response = client.post(
        "/simulation/editable-dsl/preview",
        json={"expected_active_hash": current["document_hash"], "document": document},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["validation"]["valid"] is True

    rejected = client.post(
        "/simulation/editable-dsl/confirm",
        json={
            "expected_active_hash": current["document_hash"],
            "preview_hash": preview["preview_hash"],
            "document": document,
            "user_confirmed": False,
        },
    )
    assert rejected.status_code == 422

    confirmed = client.post(
        "/simulation/editable-dsl/confirm",
        json={
            "expected_active_hash": current["document_hash"],
            "preview_hash": preview["preview_hash"],
            "document": document,
            "user_confirmed": True,
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["revision"] == 1
    assert client.get("/simulation/editable-dsl/history").json()[0]["revision"] == 1
    assert client.post("/simulation/editable-dsl/raw", json={}).status_code == 404
