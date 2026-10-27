import json
from collections import Counter
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from .decision_evidence import (
    AgentDecisionContext,
    DecisionFactorEvidence,
    DecisionTreeTemplate,
    EvaluatedDecisionProbability,
    NoSourceAttachment,
    evaluate_decision_edge,
)
from .registry_store import (
    DecisionEvidenceRegistryDefinition,
    SimulationRegistryStore,
)


class DecisionEvidenceRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionEvidenceValidationIssue(DecisionEvidenceRouteModel):
    code: str
    path: str
    message: str


class DecisionEvidenceValidation(DecisionEvidenceRouteModel):
    valid: bool
    issues: list[DecisionEvidenceValidationIssue]


class DecisionEvidenceCatalogItem(DecisionEvidenceRouteModel):
    id: str
    name: str
    domain: str
    status: str
    edge_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class DecisionEvidenceRegistryStatus(DecisionEvidenceRouteModel):
    configured: bool
    version: str | None = None
    template_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    valid: bool | None = None
    issue_count: int = Field(default=0, ge=0)


class DecisionEvidenceRegistryView(DecisionEvidenceRouteModel):
    status: DecisionEvidenceRegistryStatus
    registry: DecisionEvidenceRegistryDefinition | None
    validation: DecisionEvidenceValidation | None
    catalog: list[DecisionEvidenceCatalogItem]


class DecisionEvidenceDetail(DecisionEvidenceRouteModel):
    template: DecisionTreeTemplate
    evidence: list[DecisionFactorEvidence]


class ConfirmDecisionEvidenceRegistryRequest(DecisionEvidenceRouteModel):
    registry: dict[str, Any]
    user_confirmed: Literal[True]


def _issue(code: str, path: str, message: str) -> DecisionEvidenceValidationIssue:
    return DecisionEvidenceValidationIssue(code=code, path=path, message=message)


def _parse_registry(payload: dict[str, Any]) -> DecisionEvidenceRegistryDefinition:
    try:
        return DecisionEvidenceRegistryDefinition.model_validate_json(json.dumps(payload))
    except ValidationError as error:
        detail = [
            {
                "type": item["type"],
                "loc": ["body", *item["loc"]],
                "msg": item["msg"],
            }
            for item in error.errors()
        ]
        raise HTTPException(422, detail) from error


def validate_decision_evidence_registry(
    registry: DecisionEvidenceRegistryDefinition,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> DecisionEvidenceValidation:
    issues: list[DecisionEvidenceValidationIssue] = []
    template_counts = Counter(template.id for template in registry.templates)
    evidence_counts = Counter(row.id for row in registry.evidence)
    for template_id, count in sorted(template_counts.items()):
        if count > 1:
            issues.append(
                _issue(
                    "duplicate_template_id",
                    f"templates.{template_id}",
                    f"Decision template id {template_id!r} appears {count} times",
                )
            )
    for evidence_id, count in sorted(evidence_counts.items()):
        if count > 1:
            issues.append(
                _issue(
                    "duplicate_evidence_id",
                    f"evidence.{evidence_id}",
                    f"Decision evidence id {evidence_id!r} appears {count} times",
                )
            )
    templates = {template.id: template for template in registry.templates}
    for template_index, template in enumerate(registry.templates):
        edge_counts = Counter(edge.id for edge in template.edges)
        for edge_id, count in sorted(edge_counts.items()):
            if count > 1:
                issues.append(
                    _issue(
                        "duplicate_edge_id",
                        f"templates.{template_index}.edges.{edge_id}",
                        f"Decision edge id {edge_id!r} appears {count} times",
                    )
                )
        if template.status == "ready":
            for edge_index, edge in enumerate(template.edges):
                if isinstance(edge.source, NoSourceAttachment):
                    issues.append(
                        _issue(
                            "ready_edge_without_source",
                            f"templates.{template_index}.edges.{edge_index}.source",
                            (
                                f"Ready decision {template.id!r} has an edge without "
                                "attached research evidence"
                            ),
                        )
                    )
                elif evidence_receipts is not None:
                    source_issue = evidence_receipts.decision_source_issue(
                        edge.source.imported_source_id,
                        edge.source.source,
                        edge.source.publication_date,
                        edge.decision_id,
                    )
                    if source_issue is not None:
                        issues.append(
                            _issue(
                                "untrusted_source_receipt",
                                f"templates.{template_index}.edges.{edge_index}.source",
                                source_issue,
                            )
                        )
    for evidence_index, row in enumerate(registry.evidence):
        path = f"evidence.{evidence_index}"
        template = templates.get(row.decision_id)
        if template is None:
            issues.append(
                _issue(
                    "unknown_evidence_decision",
                    f"{path}.decision_id",
                    f"Evidence {row.id!r} references unknown decision {row.decision_id!r}",
                )
            )
            continue
        edge = next((item for item in template.edges if item.id == row.edge_id), None)
        if edge is None:
            issues.append(
                _issue(
                    "unknown_evidence_edge",
                    f"{path}.edge_id",
                    (
                        f"Evidence {row.id!r} references unknown edge {row.edge_id!r} "
                        f"in decision {row.decision_id!r}"
                    ),
                )
            )
            continue
        factor_ids = {factor.id for factor in edge.formula.factors}
        if row.factor_id not in factor_ids:
            issues.append(
                _issue(
                    "unknown_evidence_factor",
                    f"{path}.factor_id",
                    (
                        f"Evidence {row.id!r} references unknown factor {row.factor_id!r} "
                        f"on edge {row.edge_id!r}"
                    ),
                )
            )
            continue
        if evidence_receipts is not None:
            factor = next(item for item in edge.formula.factors if item.id == row.factor_id)
            source_issue = evidence_receipts.decision_source_issue(
                row.source.imported_source_id,
                row.source.source,
                row.source.publication_date,
                row.decision_id,
            )
            if source_issue is not None:
                issues.append(
                    _issue(
                        "untrusted_source_receipt",
                        f"{path}.source",
                        source_issue,
                    )
                )
                continue
            factor_issue = evidence_receipts.decision_factor_issue(
                row.source.imported_source_id,
                row.decision_id,
                factor.input_key,
                row.basis,
                row.place.level,
                row.place.country_id,
                row.predicate.operator,
                row.predicate.value,
                row.predicate.values,
                row.predicate.lower,
                row.predicate.upper,
                row.estimate,
                row.sample_size,
            )
            if factor_issue is not None:
                issues.append(
                    _issue(
                        "evidence_receipt_mismatch",
                        path,
                        factor_issue,
                    )
                )
    return DecisionEvidenceValidation(valid=not issues, issues=issues)


def _catalog(
    registry: DecisionEvidenceRegistryDefinition,
) -> list[DecisionEvidenceCatalogItem]:
    evidence_counts = Counter(row.decision_id for row in registry.evidence)
    return [
        DecisionEvidenceCatalogItem(
            id=template.id,
            name=template.name,
            domain=template.domain,
            status=template.status,
            edge_count=len(template.edges),
            evidence_count=evidence_counts[template.id],
        )
        for template in sorted(registry.templates, key=lambda item: (item.name.casefold(), item.id))
    ]


def _view(
    store: SimulationRegistryStore,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> DecisionEvidenceRegistryView:
    registry = store.decision_evidence()
    if registry is None:
        return DecisionEvidenceRegistryView(
            status=DecisionEvidenceRegistryStatus(configured=False),
            registry=None,
            validation=None,
            catalog=[],
        )
    validation = validate_decision_evidence_registry(registry, evidence_receipts)
    return DecisionEvidenceRegistryView(
        status=DecisionEvidenceRegistryStatus(
            configured=True,
            version=registry.version,
            template_count=len(registry.templates),
            evidence_count=len(registry.evidence),
            valid=validation.valid,
            issue_count=len(validation.issues),
        ),
        registry=registry,
        validation=validation,
        catalog=_catalog(registry),
    )


def create_decision_evidence_router(
    store: SimulationRegistryStore,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/simulation/decision-evidence",
        tags=["Simulation decision evidence"],
    )

    @router.get("", response_model=DecisionEvidenceRegistryView)
    def get_registry() -> DecisionEvidenceRegistryView:
        return _view(store, evidence_receipts)

    @router.get("/status", response_model=DecisionEvidenceRegistryStatus)
    def get_status() -> DecisionEvidenceRegistryStatus:
        return _view(store, evidence_receipts).status

    @router.get("/catalog", response_model=list[DecisionEvidenceCatalogItem])
    def get_catalog() -> list[DecisionEvidenceCatalogItem]:
        return _view(store, evidence_receipts).catalog

    @router.post("/validate", response_model=DecisionEvidenceValidation)
    def validate_registry(
        registry: dict[str, Any],
    ) -> DecisionEvidenceValidation:
        return validate_decision_evidence_registry(
            _parse_registry(registry), evidence_receipts
        )

    @router.post("/confirm", response_model=DecisionEvidenceRegistryView)
    def confirm_registry(
        request: ConfirmDecisionEvidenceRegistryRequest,
    ) -> DecisionEvidenceRegistryView:
        registry = _parse_registry(request.registry)
        validation = validate_decision_evidence_registry(registry, evidence_receipts)
        if not validation.valid:
            raise HTTPException(422, validation.model_dump(mode="json"))
        store.save_decision_evidence(registry)
        return _view(store, evidence_receipts)

    @router.get("/{decision_id}", response_model=DecisionEvidenceDetail)
    def get_decision(decision_id: str) -> DecisionEvidenceDetail:
        registry = store.decision_evidence()
        if registry is None:
            raise HTTPException(404, "Decision evidence registry is not configured")
        template = next(
            (item for item in registry.templates if item.id == decision_id),
            None,
        )
        if template is None:
            raise HTTPException(404, "Decision template was not found")
        return DecisionEvidenceDetail(
            template=template,
            evidence=[row for row in registry.evidence if row.decision_id == decision_id],
        )

    @router.post(
        "/{decision_id}/edges/{edge_id}/evaluate",
        response_model=EvaluatedDecisionProbability,
    )
    def evaluate_edge(
        decision_id: str,
        edge_id: str,
        context: AgentDecisionContext,
    ) -> EvaluatedDecisionProbability:
        registry = store.decision_evidence()
        if registry is None:
            raise HTTPException(404, "Decision evidence registry is not configured")
        validation = validate_decision_evidence_registry(registry, evidence_receipts)
        if not validation.valid:
            raise HTTPException(409, validation.model_dump(mode="json"))
        template = next(
            (item for item in registry.templates if item.id == decision_id),
            None,
        )
        if template is None:
            raise HTTPException(404, "Decision template was not found")
        edge = next((item for item in template.edges if item.id == edge_id), None)
        if edge is None:
            raise HTTPException(404, "Decision edge was not found")
        return evaluate_decision_edge(edge, context, registry.evidence)

    return router
