import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.agent_types import AgentTypeDefinition, AgentTypeMember
from petraterrium.simulation.decision_evidence import (
    AgentDecisionContext,
    AgentPlace,
    DecisionEdgeTemplate,
    DecisionFactorEvidence,
    DecisionNodeTemplate,
    DecisionProbabilityFormula,
    DecisionTreeTemplate,
    EvidencePlace,
    EvidencePredicate,
    NoSourceAttachment,
    ProbabilityFactor,
    ResearchCitation,
)
from petraterrium.simulation.decision_evidence_routes import (
    create_decision_evidence_router,
)
from petraterrium.simulation.interaction_trees import (
    InteractionTransitionEvidence,
    InteractionTreeDefinition,
    InteractionTreeNode,
    InteractionTreeTransition,
)
from petraterrium.simulation.registry_store import (
    DecisionEvidenceRegistryDefinition,
    SimulationRegistryStore,
)
from petraterrium.simulation.routines import (
    RoutineDefinition,
    RoutineEvidence,
    RoutineRegistryDefinition,
    RoutineSchedule,
    RoutineStep,
)
from petraterrium.simulation.routines_routes import create_routine_router
from petraterrium.simulation.tree_modules import (
    DecisionTreeModule,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
)


def _routine_registry(module_id: str) -> RoutineRegistryDefinition:
    person = AgentTypeDefinition(
        id="person",
        name="Person",
        routines=[
            AgentTypeMember(
                id="evening",
                name="Evening",
                definition="User-confirmed evening schedule",
            )
        ],
    )
    return RoutineRegistryDefinition(
        agent_types=[person],
        routines=[
            RoutineDefinition(
                id="evening",
                name="Evening",
                agent_type_id="person",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed schedule without measured provenance",
                ),
                steps=[
                    RoutineStep(
                        id="choose_evening",
                        name="Choose evening activity",
                        activity="choose an evening activity",
                        schedule=RoutineSchedule(
                            days=["friday"],
                            start_time="18:00",
                            end_time="22:00",
                            place_ids=["current_place"],
                            role_ids=["person"],
                        ),
                        decision_tree_module_id=module_id,
                    )
                ],
            )
        ],
    )


def _decision_tree_registry(module_id: str) -> DecisionTreeRegistryDefinition:
    return DecisionTreeRegistryDefinition(
        version="1",
        trees=[],
        modules=[
            DecisionTreeModule(
                id=module_id,
                version="1",
                name="Evening choice",
                entry_node="done",
                nodes=[DecisionTreeNode(id="done", label="Done", kind="terminal")],
                source="User-confirmed module",
                status="draft",
            )
        ],
    )


def _decision_source(factor_ids: tuple[str, ...]) -> ResearchCitation:
    return ResearchCitation(
        kind="research_paper",
        imported_source_id="fixture-time-use-study",
        title="Fixture time use study",
        source="Fixture journal",
        publication_date=date(2025, 1, 1),
        population_studied="Adults in Canada",
        link_or_reference="fixture://time-use-study",
        supports_decision_ids=("go_out",),
        supports_factor_ids=factor_ids,
    )


def _decision_template(
    source: ResearchCitation | NoSourceAttachment,
    status: str,
) -> DecisionTreeTemplate:
    factors = (
        ProbabilityFactor(
            id="age_factor",
            name="Age",
            input_kind="trait",
            input_key="age",
            feature_id="age",
        ),
        ProbabilityFactor(
            id="weekday_factor",
            name="Weekday",
            input_kind="time",
            input_key="weekday",
        ),
    )
    edge = DecisionEdgeTemplate(
        id="leave_home",
        decision_id="go_out",
        domain="social",
        from_state="decide",
        to_state="outside",
        label="Go out",
        formula=DecisionProbabilityFormula(
            id="go_out_probability",
            name="Go out probability",
            combination="product",
            factors=factors,
        ),
        source=source,
    )
    return DecisionTreeTemplate.model_validate(
        {
            "id": "go_out",
            "name": "Go out",
            "domain": "social",
            "status": status,
            "entry_state": "decide",
            "terminal_states": ("outside",),
            "nodes": (
                DecisionNodeTemplate(id="decide", label="Decide", kind="decision"),
                DecisionNodeTemplate(id="outside", label="Outside", kind="terminal"),
            ),
            "edges": (edge,),
        }
    )


def _factor_evidence(
    factor_id: str,
    value: int | str,
    estimate: float,
    place: EvidencePlace,
    source: ResearchCitation,
) -> DecisionFactorEvidence:
    return DecisionFactorEvidence(
        id=f"{place.place_id}-{factor_id}",
        decision_id="go_out",
        edge_id="leave_home",
        factor_id=factor_id,
        place=place,
        predicate=EvidencePredicate(operator="exact", value=value),
        basis="measured_joint",
        estimate=estimate,
        ci_low=max(0, estimate - 0.1),
        ci_high=min(1, estimate + 0.1),
        sample_size=500,
        fittable=True,
        source=source,
    )


def _interaction_tree(version: str) -> InteractionTreeDefinition:
    evidence = InteractionTransitionEvidence(
        source="Observed interaction fixture",
        version=version,
        status="measured_joint",
        uncertainty=0.1,
    )
    return InteractionTreeDefinition(
        id="greet",
        name="Greeting",
        version=version,
        entry_node="start",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="start", label="Start", terminal=False),
            InteractionTreeNode(id="done", label="Done", terminal=True),
        ),
        transitions=(
            InteractionTreeTransition(
                id="finish",
                from_node="start",
                to_node="done",
                outcome="greeted",
                probability=1,
                evidence=evidence,
            ),
        ),
    )


def test_routine_confirmation_uses_current_decision_modules(tmp_path) -> None:
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    store.save_decision_trees(_decision_tree_registry("evening_choice"))
    application = FastAPI()
    application.include_router(create_routine_router(store))
    registry = _routine_registry("evening_choice")

    with TestClient(application) as client:
        before = client.get("/simulation/routines/status")
        invalid = client.post(
            "/simulation/routines/validate",
            json=_routine_registry("missing_choice").model_dump(mode="json"),
        )
        confirmed = client.post(
            "/simulation/routines/confirm",
            json={
                "registry": registry.model_dump(mode="json"),
                "user_confirmed": True,
            },
        )
        detail = client.get("/simulation/routines/agent-types/person")
        store.save_decision_trees(DecisionTreeRegistryDefinition(version="2", trees=[], modules=[]))
        stale = client.get("/simulation/routines/agent-types/person")

    assert before.json() == {
        "configured": False,
        "agent_type_count": 0,
        "routine_count": 0,
        "valid": None,
        "issue_count": 0,
    }
    assert invalid.json()["valid"] is False
    assert invalid.json()["issues"][0]["code"] == "unknown_decision_tree_module"
    assert confirmed.status_code == 200
    assert confirmed.json()["status"]["configured"] is True
    assert detail.json()["routines"][0]["routine"]["id"] == "evening"
    assert stale.status_code == 409
    assert stale.json()["detail"]["issues"][0]["code"] == "unknown_decision_tree_module"


def test_decision_registry_confirms_then_resolves_most_specific_evidence(tmp_path) -> None:
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = FastAPI()
    application.include_router(create_decision_evidence_router(store))
    pending = DecisionEvidenceRegistryDefinition(
        version="1",
        templates=[
            _decision_template(
                NoSourceAttachment(reason="No source has been attached"),
                "awaiting_evidence",
            )
        ],
        evidence=[],
    )
    context = AgentDecisionContext(
        agent_id="agent-1",
        place=AgentPlace(region_id="northern-america", country_id="CA"),
        traits={"age": 30},
        time={"weekday": "friday"},
    )

    with TestClient(application) as client:
        pending_response = client.post(
            "/simulation/decision-evidence/confirm",
            json={
                "registry": pending.model_dump(mode="json"),
                "user_confirmed": True,
            },
        )
        unknown = client.post(
            "/simulation/decision-evidence/go_out/edges/leave_home/evaluate",
            json=context.model_dump(mode="json"),
        )

    assert pending_response.status_code == 200
    assert unknown.json()["status"] == "unknown"
    assert unknown.json()["probability"] is None
    assert unknown.json()["ci_low"] == 0
    assert unknown.json()["ci_high"] == 1

    factor_ids = ("age_factor", "weekday_factor")
    source = _decision_source(factor_ids)
    global_place = EvidencePlace(level="global", place_id="global")
    canada_place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="northern-america",
        country_id="CA",
    )
    rows = [
        _factor_evidence("age_factor", 30, 0.2, global_place, source),
        _factor_evidence("weekday_factor", "friday", 0.2, global_place, source),
        _factor_evidence("age_factor", 30, 0.5, canada_place, source),
        _factor_evidence("weekday_factor", "friday", 0.6, canada_place, source),
    ]
    measured = DecisionEvidenceRegistryDefinition(
        version="2",
        templates=[_decision_template(source, "ready")],
        evidence=rows,
    )

    with TestClient(application) as client:
        confirmed = client.post(
            "/simulation/decision-evidence/confirm",
            json={
                "registry": measured.model_dump(mode="json"),
                "user_confirmed": True,
            },
        )
        catalog = client.get("/simulation/decision-evidence/catalog")
        detail = client.get("/simulation/decision-evidence/go_out")
        evaluated = client.post(
            "/simulation/decision-evidence/go_out/edges/leave_home/evaluate",
            json=context.model_dump(mode="json"),
        )

    assert confirmed.status_code == 200
    assert catalog.json()[0]["evidence_count"] == 4
    assert len(detail.json()["evidence"]) == 4
    assert evaluated.json()["status"] == "measured"
    assert evaluated.json()["probability"] == pytest.approx(0.3)
    assert {item["resolved_level"] for item in evaluated.json()["factors"]} == {"country"}


def test_invalid_decision_references_are_not_persisted(tmp_path) -> None:
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = FastAPI()
    application.include_router(create_decision_evidence_router(store))
    source = _decision_source(("age_factor", "weekday_factor", "missing_factor"))
    invalid = DecisionEvidenceRegistryDefinition(
        version="1",
        templates=[_decision_template(source, "ready")],
        evidence=[
            _factor_evidence(
                "missing_factor",
                30,
                0.5,
                EvidencePlace(level="global", place_id="global"),
                source,
            )
        ],
    )

    with TestClient(application) as client:
        validation = client.post(
            "/simulation/decision-evidence/validate",
            json=invalid.model_dump(mode="json"),
        )
        confirmation = client.post(
            "/simulation/decision-evidence/confirm",
            json={
                "registry": invalid.model_dump(mode="json"),
                "user_confirmed": True,
            },
        )
        status = client.get("/simulation/decision-evidence/status")

    assert validation.json()["issues"][0]["code"] == "unknown_evidence_factor"
    assert confirmation.status_code == 422
    assert status.json()["configured"] is False


def test_interaction_tree_versions_replace_by_id_and_preserve_other_registry_data(
    tmp_path,
) -> None:
    path = tmp_path / "simulation-registry.json"
    path.write_text(json.dumps({"existing": {"kept": True}}), encoding="utf-8")
    store = SimulationRegistryStore(path)

    store.save_interaction_tree(_interaction_tree("1"))
    store.save_interaction_tree(_interaction_tree("2"))

    definitions = store.interaction_trees()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [(item.id, item.version) for item in definitions] == [("greet", "2")]
    assert payload["existing"] == {"kept": True}
    assert payload["interaction_trees"][0]["version"] == "2"
