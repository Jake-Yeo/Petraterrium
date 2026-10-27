from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from .interactions import InteractionProgramDefinition
from .population_generation import attach_relationship_evidence
from .registry_store import SimulationRegistryStore


class InteractionProgramRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InteractionProgramView(InteractionProgramRouteModel):
    configured: bool
    program: InteractionProgramDefinition


class InteractionProgramValidationIssue(InteractionProgramRouteModel):
    path: str
    message: str


class InteractionProgramValidation(InteractionProgramRouteModel):
    valid: bool
    issues: tuple[InteractionProgramValidationIssue, ...]


class ConfirmInteractionProgramRequest(InteractionProgramRouteModel):
    program: InteractionProgramDefinition
    user_confirmed: Literal[True]


def _view(store: SimulationRegistryStore) -> InteractionProgramView:
    program = store.interaction_program()
    return InteractionProgramView(
        configured=program is not None,
        program=program
        or InteractionProgramDefinition(version="1", status="draft", rules=()),
    )


def _validate_tree_references(
    store: SimulationRegistryStore, program: InteractionProgramDefinition
) -> None:
    known_tree_ids = {tree.id for tree in store.interaction_trees()}
    missing = sorted(
        {
            rule.interaction_tree_id
            for rule in program.rules
            if rule.interaction_tree_id is not None
            and rule.interaction_tree_id not in known_tree_ids
        }
    )
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Interaction rules reference missing trees: {', '.join(missing)}",
        )


def validate_interaction_program(
    store: SimulationRegistryStore,
    program: InteractionProgramDefinition,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> InteractionProgramValidation:
    issues: list[InteractionProgramValidationIssue] = []
    try:
        InteractionProgramDefinition.model_validate(
            {**program.model_dump(mode="json"), "status": "confirmed"}
        )
    except ValidationError as error:
        issues.extend(
            InteractionProgramValidationIssue(
                path=".".join(str(item) for item in problem["loc"]),
                message=str(problem["msg"]),
            )
            for problem in error.errors()
        )
    known_tree_ids = {tree.id for tree in store.interaction_trees()}
    for rule_index, rule in enumerate(program.rules):
        if rule.interaction_tree_id and rule.interaction_tree_id not in known_tree_ids:
            issues.append(
                InteractionProgramValidationIssue(
                    path=f"rules.{rule_index}.interaction_tree_id",
                    message=f"Interaction tree {rule.interaction_tree_id!r} is not registered",
                )
            )
        if evidence_receipts is None:
            continue
        factors = (
            rule.base_factor,
            *rule.relationship_factors.values(),
            *rule.colocation_factors.values(),
            *rule.place_factors.values(),
            *(window.factor for window in rule.time_factors),
            *rule.context_factors,
        )
        for factor in factors:
            provenance = factor.provenance
            if provenance.status not in {"measured_joint", "fitted_model"}:
                continue
            issue = evidence_receipts.interaction_issue(
                provenance.evidence_id,
                provenance.source,
                provenance.version,
                provenance.source_date.isoformat() if provenance.source_date else None,
                {rule.id, rule.source_action, rule.interaction_type, factor.id},
            )
            if issue is not None:
                issues.append(
                    InteractionProgramValidationIssue(
                        path=f"rules.{rule_index}.factors.{factor.id}",
                        message=issue,
                    )
                )
    if evidence_receipts is not None:
        for evidence_index, relationship in enumerate(program.relationship_evidence):
            provenance = relationship.provenance
            if provenance.status not in {"measured_joint", "fitted_model"}:
                continue
            issue = evidence_receipts.interaction_issue(
                provenance.evidence_id,
                provenance.source,
                provenance.version,
                provenance.source_date.isoformat() if provenance.source_date else None,
                {relationship.kind, f"relationship:{relationship.kind}"},
            )
            if issue is not None:
                issues.append(
                    InteractionProgramValidationIssue(
                        path=f"relationship_evidence.{evidence_index}",
                        message=issue,
                    )
                )
    return InteractionProgramValidation(valid=not issues, issues=tuple(issues))


def create_interaction_program_router(
    store: SimulationRegistryStore,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/simulation/interaction-program",
        tags=["Interaction program"],
    )

    @router.get("", response_model=InteractionProgramView)
    def get_program() -> InteractionProgramView:
        return _view(store)

    @router.post("/validate", response_model=InteractionProgramValidation)
    def validate_program(
        program: InteractionProgramDefinition,
    ) -> InteractionProgramValidation:
        return validate_interaction_program(store, program, evidence_receipts)

    @router.post("/confirm", response_model=InteractionProgramView)
    def confirm_program(
        request: ConfirmInteractionProgramRequest,
    ) -> InteractionProgramView:
        if request.program.status != "confirmed":
            raise HTTPException(
                status_code=422,
                detail="A confirmed interaction program must have confirmed status",
            )
        validation = validate_interaction_program(
            store, request.program, evidence_receipts
        )
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail=[item.model_dump(mode="json") for item in validation.issues],
            )
        _validate_tree_references(store, request.program)
        materialization = store.initial_population()
        if materialization is not None:
            try:
                materialization = attach_relationship_evidence(
                    materialization,
                    request.program.relationship_evidence,
                )
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
        store.save_interaction_program(request.program)
        if materialization is not None:
            store.save_initial_population(materialization)
        return _view(store)

    return router
