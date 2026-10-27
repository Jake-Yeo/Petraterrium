from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from petraterrium.simulation.interaction_program_routes import (
    create_interaction_program_router,
)
from petraterrium.simulation.interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    TimeFactorWindow,
)
from petraterrium.simulation.registry_store import SimulationRegistryStore


def factor(identity: str, status: str = "measured_joint") -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=identity,
        value=0.5,
        provenance=InteractionFactorProvenance(
            source="Imported interaction evidence",
            version="2026-10-27",
            source_date="2026-10-27",
            evidence_id=identity,
            licence="Test fixture",
            status=status,
            uncertainty=0.1,
        ),
    )


def relationship_evidence(kind: str = "family") -> RelationshipKindEvidence:
    return RelationshipKindEvidence(
        kind=kind,
        weight=0.9,
        trust=0.8,
        similarity=0.7,
        provenance=InteractionFactorProvenance(
            source="Imported relationship panel",
            version="2026-10-27",
            source_date="2026-10-27",
            evidence_id=f"{kind}-panel",
            licence="Test fixture",
            status="measured_joint",
            uncertainty=0.1,
        ),
    )


def rule() -> InteractionRule:
    return InteractionRule(
        id="family-talk",
        source_action="family-dinner",
        interaction_type="talk",
        channel="in_person",
        max_targets_per_initiator=1,
        allowed_relationships=("family",),
        allowed_place_kinds=("home",),
        base_factor=factor("base"),
        relationship_factors={"family": factor("family")},
        colocation_factors={"same_specific_place": factor("colocated")},
        place_factors={"home": factor("home")},
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=17,
                end_hour=22,
                factor=factor("evening"),
            ),
        ),
    )


def test_confirmed_program_rejects_unknown_probability_factors():
    payload = rule().model_dump(mode="json")
    payload["base_factor"] = factor("base", "unknown").model_dump(mode="json")
    try:
        InteractionProgramDefinition(
            version="1",
            status="confirmed",
            rules=(InteractionRule.model_validate(payload),),
        )
    except ValidationError as error:
        assert "non-executable factors: base" in str(error)
    else:
        raise AssertionError("Expected unknown interaction evidence to block confirmation")


def test_draft_validation_reports_blocked_evidence_without_writing(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    application = FastAPI()
    application.include_router(create_interaction_program_router(store), prefix="/api")
    client = TestClient(application)
    payload = rule().model_dump(mode="json")
    payload["base_factor"] = factor("base", "unknown").model_dump(mode="json")
    draft = InteractionProgramDefinition(
        version="draft-v1",
        status="draft",
        relationship_evidence=(relationship_evidence(),),
        rules=(InteractionRule.model_validate(payload),),
    )

    response = client.post(
        "/api/simulation/interaction-program/validate",
        json=draft.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "non-executable factors: base" in response.json()["issues"][0]["message"]
    assert store.interaction_program() is None


def test_approved_estimate_requires_explicit_user_approval():
    payload = factor("approved", "approved_estimate").model_dump(mode="json")
    unapproved = InteractionFactor.model_validate(payload)
    assert unapproved.provenance.executable is False

    payload["provenance"]["user_approved"] = True
    approved = InteractionFactor.model_validate(payload)
    assert approved.provenance.executable is True


def test_confirmed_program_persists_and_reloads(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    application = FastAPI()
    application.include_router(create_interaction_program_router(store), prefix="/api")
    client = TestClient(application)
    program = InteractionProgramDefinition(
        version="evidence-v1",
        status="confirmed",
        relationship_evidence=(relationship_evidence(),),
        rules=(rule(),),
    )

    response = client.post(
        "/api/simulation/interaction-program/confirm",
        json={"program": program.model_dump(mode="json"), "user_confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["program"]["rules"][0]["id"] == "family-talk"
    assert SimulationRegistryStore(store.path).interaction_program() == program


def test_tree_backed_rule_requires_registered_tree(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    application = FastAPI()
    application.include_router(create_interaction_program_router(store), prefix="/api")
    client = TestClient(application)
    payload = rule().model_dump(mode="json")
    payload["interaction_tree_id"] = "talk-tree"
    program = InteractionProgramDefinition(
        version="evidence-v1",
        status="confirmed",
        relationship_evidence=(relationship_evidence(),),
        rules=(InteractionRule.model_validate(payload),),
    )

    response = client.post(
        "/api/simulation/interaction-program/confirm",
        json={"program": program.model_dump(mode="json"), "user_confirmed": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "path": "rules.0.interaction_tree_id",
            "message": "Interaction tree 'talk-tree' is not registered",
        }
    ]
