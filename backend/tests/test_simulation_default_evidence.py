import json
import time
from datetime import date

import pytest

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from petraterrium.population import AgentRecord
from petraterrium.rust_core import RustCoreClient
from petraterrium.simulation.coefficient_evidence import (
    ActionCoefficientRegistry,
    CoefficientCitation,
    CoefficientInterval,
    CoefficientPlace,
    DefaultActionCoefficients,
    DefaultDslEvidenceIdentity,
    ShippedDefaultReason,
    resolve_action_coefficients,
    validate_coefficient_registry,
)
from petraterrium.simulation.coefficient_promotions import (
    FittedModelProvenance,
    HeldOutValidationReceipt,
    VerifiedFittedAction,
    promote_verified_fit,
)
from petraterrium.simulation.default_dsl import DefaultDslService
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_persistence import SimulationRunRecorder
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import (
    SimulationPlaceScope,
    SimulationRunConfig,
    SimulationRunService,
)
from petraterrium.simulation.runtime_decision_compiler import compile_runtime_decisions
from petraterrium.simulation.tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
)

DEFAULT_IDENTITY = DefaultDslEvidenceIdentity(
    version="foundation-v1",
    hash="sha256:" + "a" * 64,
    source="shipped",
)


def default_reason() -> ShippedDefaultReason:
    return ShippedDefaultReason(
        reason="Initial behavior prior used until linked outcome data is promoted.",
        default_dsl_version=DEFAULT_IDENTITY.version,
        default_dsl_hash=DEFAULT_IDENTITY.hash,
    )


def place(country: str) -> CoefficientPlace:
    return CoefficientPlace(
        level="country",
        place_id=country,
        region_id="Northern America",
        country_id=country,
    )


def distribution(
    identity: str,
    action_id: str,
    country: str,
    leave: float,
) -> DefaultActionCoefficients:
    return DefaultActionCoefficients(
        id=identity,
        action_id=action_id,
        place=place(country),
        coefficients={"stay": 1 - leave, "leave": leave},
        intervals={
            "stay": CoefficientInterval(low=0, high=1),
            "leave": CoefficientInterval(low=0, high=1),
        },
        source=default_reason(),
    )


def registry() -> ActionCoefficientRegistry:
    return ActionCoefficientRegistry(
        version="foundation-evidence-v1",
        defaults=[
            distribution("daily-ca", "daily-choice", "CA", 0.6),
            distribution("daily-us", "daily-choice", "US", 0.5),
            distribution("meal-ca", "meal-choice", "CA", 0.8),
        ],
        fitted=[],
        promotions=[],
    )


def agent(country: str = "CA") -> AgentRecord:
    return AgentRecord(
        agent_id=f"agent-{country.casefold()}",
        place=country,
        latitude=49,
        longitude=-123,
        role="person",
        log_tier="mass",
        traits={
            "agent_type": "person",
            "agent_types": ["person"],
            "country_id": country,
            "country": country,
            "region": "Northern America",
        },
        states={},
        behaviour={},
        behaviour_provenance={},
        relationships=[],
        weight=1,
    )


def tree_registry() -> DecisionTreeRegistryDefinition:
    return DecisionTreeRegistryDefinition(
        version="foundation-tree-v1",
        trees=[
            DecisionTreeDefinition(
                id="daily-tree",
                version="v1",
                name="Daily choice",
                root_module_id="daily-choice",
                agent_type_ids=["person"],
                place_ids=[],
                source="Default DSL foundation",
                status="ready",
            )
        ],
        modules=[
            DecisionTreeModule(
                id="daily-choice",
                version="v1",
                name="Daily choice",
                entry_node="choose",
                nodes=[
                    DecisionTreeNode(id="choose", label="Choose", kind="decision"),
                    DecisionTreeNode(id="stay", label="Stay", kind="terminal"),
                    DecisionTreeNode(id="leave", label="Leave", kind="terminal"),
                ],
                edges=[
                    DecisionTreeEdge(id="stay", from_node="choose", to_node="stay"),
                    DecisionTreeEdge(id="leave", from_node="choose", to_node="leave"),
                ],
                source="Default DSL foundation",
                status="ready",
            )
        ],
    )


def wait_for_terminal(service: SimulationRunService, run_id: str):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        view = service.get(run_id)
        if view.status in {"completed", "cancelled", "failed"}:
            return view
        time.sleep(0.02)
    raise AssertionError("Simulation run did not finish")


def test_zero_fitted_models_complete_1000_agents_30_days_with_durable_warning(tmp_path):
    registry_store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(registry_store).ensure()
    path = tmp_path / "runs.sqlite3"
    service = SimulationRunService(
        lambda config: prepare_registry_run(registry_store, config),
        RustCoreClient(),
        persistence=SimulationRunRecorder(path),
    )
    config = SimulationRunConfig(
        population_size=1000,
        seed=1,
        days=30,
        tick_interval_hours=24,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="global"),
        agent_type_mix={},
    )

    launched = service.launch(config)
    assert launched.global_demo_summary is not None
    assert launched.global_demo_summary.total_agents == 1_000
    assert len(launched.global_demo_summary.country_agent_counts) == 12
    assert len(launched.global_demo_summary.region_agent_counts) == 8
    specialization = launched.global_demo_summary.fields["specialization"]
    assert specialization.estimated == ["China", "Nigeria"]
    assert "Canada" in specialization.own_country_inherited
    china = next(
        item for item in specialization.place_evidence if item.country_code == "CN"
    )
    assert china.status == "estimated"
    assert china.source_place == "CN"
    assert china.source_version is not None
    canada = next(
        item for item in specialization.place_evidence if item.country_code == "CA"
    )
    assert canada.status == "own_country_inherited"
    assert canada.source_place == "CA"
    assert canada.source == "OECD UOE tertiary graduates by field · Canada"
    assert canada.source_version == "OECD UOE 2023"
    assert launched.global_demo_summary.comparisons
    global_comparison = next(
        item
        for item in launched.global_demo_summary.comparisons
        if item.level == "global"
    )
    assert global_comparison.agent_count == 1_000
    assert any(
        item.field == "specialization"
        and item.status == "estimated"
        and "China" in item.places
        for item in launched.global_demo_summary.deviations
    )
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed", completed.error
    assert completed.global_demo_summary == launched.global_demo_summary
    assert completed.default_dsl_version == "base-1.0.0"
    assert completed.default_dsl_hash is not None
    assert completed.result is not None
    assert completed.result.default_dsl_version == completed.default_dsl_version
    assert completed.result.default_dsl_hash == completed.default_dsl_hash
    coefficients = [
        coefficient
        for group in completed.evidence_summary.by_action_place
        for coefficient in group.coefficients
    ]
    assert completed.evidence_summary.default_estimated_count == len(coefficients)
    assert coefficients
    assert all(
        coefficient.evidence_state == "default_estimated"
        for coefficient in coefficients
    )
    assert completed.evidence_summary.fitted_count == 0
    assert {warning.action_id for warning in completed.evidence_warnings} == {
        "bad_work",
        "daily_activity_module",
        "eat_breakfast",
        "eat_dinner",
        "eat_lunch",
        "exercise",
        "personal_care",
        "skip_lunch",
        "sleep",
        "social_activity",
        "work_or_study",
    }
    assert all(
        coefficient.default_reason
        for group in completed.evidence_summary.by_action_place
        for coefficient in group.coefficients
    )
    service.shutdown()

    restored = SimulationRunService(
        lambda config: prepare_registry_run(registry_store, config),
        RustCoreClient(),
        persistence=SimulationRunRecorder(path),
    )
    reopened = restored.get(launched.run_id)
    assert reopened.global_demo_summary == completed.global_demo_summary
    assert reopened.default_dsl_version == completed.default_dsl_version
    assert reopened.default_dsl_hash == completed.default_dsl_hash
    assert reopened.evidence_summary == completed.evidence_summary
    assert reopened.evidence_warnings == completed.evidence_warnings
    restored.shutdown()


def test_invented_or_unsupported_default_citation_is_blocked_and_named(tmp_path):
    citation = CoefficientCitation(
        imported_source_id="invented-study",
        title="Invented behavior study",
        source="Imaginary Journal",
        publication_date=date(2026, 1, 1),
        population_studied="Adults in Canada",
        link_or_reference="https://invalid.example/invented",
        supports_action_ids=("daily-choice",),
    )
    item = distribution("daily-ca", "daily-choice", "CA", 0.6).model_copy(
        update={"source": citation}
    )
    evidence = ActionCoefficientRegistry(
        version="bad-v1",
        defaults=[item],
        fitted=[],
        promotions=[],
    )

    validation = validate_coefficient_registry(
        evidence,
        DEFAULT_IDENTITY,
        AtlasEvidenceReceiptRegistry(AtlasStore(tmp_path / "atlas.sqlite3")),
    )

    assert validation.executable is False
    assert validation.issues[0].evidence_state == "blocked"
    assert validation.issues[0].action_id == "daily-choice"
    assert validation.issues[0].coefficient_set_id == "daily-ca"
    assert "not an explicitly promoted shared behaviour import" in validation.issues[0].message


def test_fitted_promotion_records_diff_and_overrides_only_matching_action_place():
    base = registry()
    fitted = VerifiedFittedAction(
        action_id="daily-choice",
        place=place("CA"),
        coefficients={"stay": 0.2, "leave": 0.8},
        intervals={
            "stay": CoefficientInterval(low=0.1, high=0.3),
            "leave": CoefficientInterval(low=0.7, high=0.9),
        },
        provenance=FittedModelProvenance(
            imported_source_id="canada-time-use-v2",
            source="Statistics Canada Time Use Survey",
            source_version="2026-v2",
            source_date="2026-07-01",
            published_date="2026-08-01",
            model_id=42,
            model_input_traits={"age": 30},
        ),
        held_out=HeldOutValidationReceipt(
            metric="log_loss",
            held_out_rows=200,
            fitted_score=0.42,
            default_score=0.51,
        ),
    )

    promoted, diff = promote_verified_fit(base, fitted, user_confirmed=True)

    changes = [
        (change.edge_id, change.default_value, change.fitted_value) for change in diff.changes
    ]
    assert changes == [
        ("leave", 0.6, 0.8),
        ("stay", 0.4, 0.2),
    ]
    assert diff.held_out.held_out_rows == 200
    assert diff.provenance.model_id == 42
    assert (
        resolve_action_coefficients(promoted, "daily-choice", place("CA")).evidence_state
        == "fitted"
    )
    assert resolve_action_coefficients(promoted, "daily-choice", place("CA")).coefficients == {
        "stay": 0.2,
        "leave": 0.8,
    }
    assert resolve_action_coefficients(promoted, "daily-choice", place("US")).coefficients == {
        "stay": 0.5,
        "leave": 0.5,
    }
    assert (
        resolve_action_coefficients(promoted, "meal-choice", place("CA")).evidence_state
        == "default_estimated"
    )

    compilation = compile_runtime_decisions(
        tree_registry(),
        None,
        [agent("CA")],
        date(2026, 10, 27),
        coefficient_registry=promoted,
        default_dsl_identity=DEFAULT_IDENTITY,
    )
    transitions = {
        transition["id"]: transition
        for module in compilation.modules
        for transition in module["transitions"]
    }
    assert transitions["leave"]["rules"][0]["probability"] == 0.8
    assert transitions["stay"]["rules"][0]["probability"] == 0.2
    assert all(
        transition["rules"][0]["provenance"]["status"] == "fitted"
        for transition in transitions.values()
    )
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in compilation.coefficient_receipts]
    )
    assert "canada-time-use-v2" in serialized
    receipts = {item.edge_id: item for item in compilation.coefficient_receipts}
    assert receipts["leave"].default_value == 0.6
    assert receipts["leave"].fitted_delta == pytest.approx(0.2)
    assert receipts["leave"].promotion_id == diff.promotion_id
    assert receipts["leave"].default_coefficient_set_id == "daily-ca"


def test_reason_only_default_must_match_verified_shipped_dsl_identity():
    invalid_identity = DefaultDslEvidenceIdentity(
        version="foundation-v2",
        hash="sha256:" + "b" * 64,
        source="shipped",
    )

    validation = validate_coefficient_registry(registry(), invalid_identity, None)

    assert validation.executable is False
    assert {issue.code for issue in validation.issues} == {"untrusted_default_reason"}


def test_population_marginal_cannot_be_constructed_as_fitted_provenance():
    with pytest.raises(ValueError, match="linked trait/context/outcome"):
        FittedModelProvenance(
            imported_source_id="population-marginal",
            source="Population census",
            source_version="2026",
            source_date="2026-01-01",
            published_date="2026-02-01",
            model_id=2,
            model_input_traits={},
            evidence_kind="population_marginal",
        )
