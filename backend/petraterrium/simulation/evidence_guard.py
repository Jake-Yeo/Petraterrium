from __future__ import annotations

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from .coefficient_evidence import (
    load_coefficient_registry,
    load_default_dsl_identity,
    validate_coefficient_registry,
)
from .decision_evidence_routes import validate_decision_evidence_registry
from .interaction_program_routes import validate_interaction_program
from .interaction_trees import InteractionTreeRegistry
from .registry_store import SimulationRegistryStore


def require_trusted_simulation_evidence(
    store: SimulationRegistryStore,
    evidence_receipts: AtlasEvidenceReceiptRegistry,
    interaction_trees: InteractionTreeRegistry,
) -> None:
    coefficient_registry = load_coefficient_registry(store)
    if coefficient_registry is not None:
        coefficient_validation = validate_coefficient_registry(
            coefficient_registry,
            load_default_dsl_identity(store),
            evidence_receipts,
        )
        if not coefficient_validation.executable:
            detail = "; ".join(
                f"{issue.action_id}/{issue.coefficient_set_id}: {issue.message}"
                for issue in coefficient_validation.issues
            )
            raise ValueError(f"Coefficient evidence is blocked: {detail}")
    decision_evidence = store.decision_evidence()
    if decision_evidence is not None:
        validation = validate_decision_evidence_registry(
            decision_evidence,
            evidence_receipts,
        )
        if not validation.valid:
            detail = "; ".join(
                f"{issue.code}:{issue.path}:{issue.message}" for issue in validation.issues
            )
            raise ValueError(f"Decision evidence registry is not executable: {detail}")
    interaction_program = store.interaction_program()
    if interaction_program is None:
        return
    program_validation = validate_interaction_program(
        store,
        interaction_program,
        evidence_receipts,
    )
    if not program_validation.valid:
        detail = "; ".join(f"{issue.path}:{issue.message}" for issue in program_validation.issues)
        raise ValueError(f"Interaction program is not executable: {detail}")
    tree_ids = sorted(
        {
            rule.interaction_tree_id
            for rule in interaction_program.rules
            if rule.interaction_tree_id is not None
        }
    )
    for tree_id in tree_ids:
        interaction_trees.execution_trees(tree_id)
