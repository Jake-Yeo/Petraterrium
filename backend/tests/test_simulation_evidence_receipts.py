import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from petraterrium.simulation.decision_evidence import (
    DecisionEdgeTemplate,
    DecisionFactorEvidence,
    DecisionNodeTemplate,
    DecisionProbabilityFormula,
    DecisionTreeTemplate,
    EvidencePlace,
    EvidencePredicate,
    ProbabilityFactor,
    ResearchCitation,
)
from petraterrium.simulation.decision_evidence_routes import (
    create_decision_evidence_router,
)
from petraterrium.simulation.evidence_guard import require_trusted_simulation_evidence
from petraterrium.simulation.interaction_program_routes import (
    create_interaction_program_router,
)
from petraterrium.simulation.interaction_trees import (
    InteractionTransitionEvidence,
    InteractionTreeDefinition,
    InteractionTreeNode,
    InteractionTreeRegistry,
    InteractionTreeTransition,
)
from petraterrium.simulation.interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    TimeFactorWindow,
)
from petraterrium.simulation.registry_store import (
    DecisionEvidenceRegistryDefinition,
    SimulationRegistryStore,
)


def _seed_behaviour_import(
    store: AtlasStore,
    identity: str = "trusted-go-out",
    scope: str = "shared",
) -> None:
    prepared = [
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"age": 30, "weekday": "friday"},
            "outcome": 1,
            "weight": 1,
        },
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"age": 30, "weekday": "friday"},
            "outcome": 0,
            "weight": 1,
        },
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"age": 31, "weekday": "monday"},
            "outcome": 1,
            "weight": 1,
        },
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"age": 31, "weekday": "monday"},
            "outcome": 0,
            "weight": 1,
        },
    ]
    metadata = {
        "run_id": scope,
        "kind": "behaviour",
        "source": "Canadian Time Use Panel",
        "source_date": "2025-01-01",
        "published_date": "2025-02-01",
        "version": "ctup-2025-v1",
        "uploader": "fixture",
        "unit": "percent",
        "redistribution_allowed": False,
        "processing_notes": [],
    }
    with store.connection() as connection:
        connection.execute(
            """INSERT INTO imports(
            import_id,source,source_date,published_date,version,scope,uploader,kind,filename,
            row_count,status,metadata_json,rows_json,mapping_json,audit_json,validation_json,
            validated_json,promoted_from,redistribution_allowed,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity,
                metadata["source"],
                metadata["source_date"],
                metadata["published_date"],
                metadata["version"],
                metadata["run_id"],
                metadata["uploader"],
                metadata["kind"],
                "behaviour.json",
                len(prepared),
                "committed",
                json.dumps(metadata),
                json.dumps(prepared),
                "[]",
                "{}",
                json.dumps({"valid": True}),
                json.dumps(prepared),
                None,
                0,
                "2025-02-01T00:00:00+00:00",
            ),
        )


def _source(identity: str) -> ResearchCitation:
    return ResearchCitation(
        kind="research_paper",
        imported_source_id=identity,
        title="Canadian time-use evidence",
        source="Canadian Time Use Panel",
        publication_date=date(2025, 2, 1),
        population_studied="Adults in Canada",
        link_or_reference="https://example.test/ctup",
        supports_decision_ids=("go_out",),
        supports_factor_ids=("age_factor", "weekday_factor"),
    )


def _registry(identity: str) -> DecisionEvidenceRegistryDefinition:
    citation = _source(identity)
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
        source=citation,
    )
    template = DecisionTreeTemplate(
        id="go_out",
        name="Go out",
        domain="social",
        status="ready",
        entry_state="decide",
        terminal_states=("outside",),
        nodes=(
            DecisionNodeTemplate(id="decide", label="Decide", kind="decision"),
            DecisionNodeTemplate(id="outside", label="Outside", kind="terminal"),
        ),
        edges=(edge,),
    )
    place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="northern-america",
        country_id="CA",
    )
    evidence = [
        DecisionFactorEvidence(
            id=f"ca-{factor.id}",
            decision_id="go_out",
            edge_id="leave_home",
            factor_id=factor.id,
            place=place,
            predicate=EvidencePredicate(
                operator="exact",
                value=30 if factor.id == "age_factor" else "friday",
            ),
            basis="measured_joint",
            estimate=0.5,
            ci_low=0.3,
            ci_high=0.7,
            sample_size=2,
            fittable=True,
            source=citation,
        )
        for factor in factors
    ]
    return DecisionEvidenceRegistryDefinition(
        version="1",
        templates=[template],
        evidence=evidence,
    )


def test_decision_confirmation_requires_a_committed_matching_behaviour_receipt(
    tmp_path,
) -> None:
    atlas = AtlasStore(tmp_path / "atlas.sqlite3")
    receipts = AtlasEvidenceReceiptRegistry(atlas)
    store = SimulationRegistryStore(tmp_path / "simulation.json")
    application = FastAPI()
    application.include_router(create_decision_evidence_router(store, receipts))
    client = TestClient(application)

    invented = client.post(
        "/simulation/decision-evidence/confirm",
        json={
            "registry": _registry("invented-study").model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert invented.status_code == 422
    assert invented.json()["detail"]["issues"][0]["code"] == "untrusted_source_receipt"
    assert store.decision_evidence() is None

    _seed_behaviour_import(atlas, "run-only-go-out", "run-a")
    run_only = client.post(
        "/simulation/decision-evidence/confirm",
        json={
            "registry": _registry("run-only-go-out").model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert run_only.status_code == 422
    assert "explicitly promoted shared" in str(run_only.json()["detail"])

    _seed_behaviour_import(atlas)
    trusted = client.post(
        "/simulation/decision-evidence/confirm",
        json={
            "registry": _registry("trusted-go-out").model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert trusted.status_code == 200
    assert trusted.json()["status"]["valid"] is True


def _interaction_tree(evidence_id: str) -> InteractionTreeDefinition:
    return InteractionTreeDefinition(
        id="go_out",
        name="Go out interaction",
        version="1",
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
                outcome="done",
                probability=1,
                evidence=InteractionTransitionEvidence(
                    source="Canadian Time Use Panel",
                    version="ctup-2025-v1",
                    status="measured_joint",
                    uncertainty=0.2,
                    source_date="2025-01-01",
                    evidence_id=evidence_id,
                ),
            ),
        ),
    )


def test_interaction_tree_registry_rejects_self_declared_measured_evidence(
    tmp_path,
) -> None:
    atlas = AtlasStore(tmp_path / "atlas.sqlite3")
    receipts = AtlasEvidenceReceiptRegistry(atlas)
    registry = InteractionTreeRegistry(evidence_receipts=receipts)

    try:
        registry.save(_interaction_tree("invented-study"))
    except ValueError as error:
        assert "explicitly promoted shared behaviour import" in str(error)
    else:
        raise AssertionError("Invented measured evidence must not be registered")

    _seed_behaviour_import(atlas)
    assert registry.save(_interaction_tree("trusted-go-out")).id == "go_out"


def _interaction_factor(identity: str, evidence_id: str) -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=identity,
        value=0.5,
        provenance=InteractionFactorProvenance(
            source="Canadian Time Use Panel",
            version="ctup-2025-v1",
            source_date="2025-01-01",
            evidence_id=evidence_id,
            licence="Fixture licence",
            status="measured_joint",
            uncertainty=0.2,
        ),
    )


def _interaction_program(evidence_id: str) -> InteractionProgramDefinition:
    provenance = _interaction_factor("relationship", evidence_id).provenance
    return InteractionProgramDefinition(
        version="1",
        status="confirmed",
        relationship_evidence=(
            RelationshipKindEvidence(
                kind="go_out",
                weight=0.5,
                trust=0.5,
                similarity=0.5,
                provenance=provenance,
            ),
        ),
        rules=(
            InteractionRule(
                id="go-out-interaction",
                source_action="go_out",
                interaction_type="go_out",
                channel="in_person",
                max_targets_per_initiator=1,
                allowed_relationships=("go_out",),
                allowed_place_kinds=("venue",),
                base_factor=_interaction_factor("base", evidence_id),
                relationship_factors={
                    "go_out": _interaction_factor("relationship", evidence_id)
                },
                colocation_factors={
                    "same_specific_place": _interaction_factor("colocated", evidence_id)
                },
                place_factors={"venue": _interaction_factor("venue", evidence_id)},
                time_factors=(
                    TimeFactorWindow(
                        weekdays=(0, 1, 2, 3, 4, 5, 6),
                        start_hour=0,
                        end_hour=24,
                        factor=_interaction_factor("time", evidence_id),
                    ),
                ),
            ),
        ),
    )


def test_interaction_program_confirmation_checks_every_measured_receipt(
    tmp_path,
) -> None:
    atlas = AtlasStore(tmp_path / "atlas.sqlite3")
    receipts = AtlasEvidenceReceiptRegistry(atlas)
    store = SimulationRegistryStore(tmp_path / "simulation.json")
    application = FastAPI()
    application.include_router(create_interaction_program_router(store, receipts))
    client = TestClient(application)

    rejected = client.post(
        "/simulation/interaction-program/confirm",
        json={
            "program": _interaction_program("invented-study").model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert rejected.status_code == 422
    assert all(
        "explicitly promoted shared behaviour import" in issue["message"]
        for issue in rejected.json()["detail"]
    )

    _seed_behaviour_import(atlas)
    confirmed = client.post(
        "/simulation/interaction-program/confirm",
        json={
            "program": _interaction_program("trusted-go-out").model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["configured"] is True


def test_run_guard_revalidates_persisted_evidence_against_atlas_receipts(
    tmp_path,
) -> None:
    atlas = AtlasStore(tmp_path / "atlas.sqlite3")
    receipts = AtlasEvidenceReceiptRegistry(atlas)
    store = SimulationRegistryStore(tmp_path / "simulation.json")
    store.save_decision_evidence(_registry("invented-study"))
    trees = InteractionTreeRegistry(evidence_receipts=receipts)

    with pytest.raises(ValueError, match="untrusted_source_receipt"):
        require_trusted_simulation_evidence(store, receipts, trees)

    _seed_behaviour_import(atlas)
    store.save_decision_evidence(_registry("trusted-go-out"))

    require_trusted_simulation_evidence(store, receipts, trees)
