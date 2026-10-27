import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..atlas.database import AtlasStore
from ..atlas.feature_catalog import FeatureCatalogStore
from ..atlas.features import canonical_feature_registry
from ..llm_gateway import AIProviderError
from .agent_behavior_proposals import (
    AgentBehaviorProposalDraft,
    AgentBehaviorProposalShape,
    ConfirmAgentBehaviorProposalRequest,
    DecisionTreeTopologyIntent,
    confirm_agent_behavior_proposal,
    decision_tree_drafts,
    evidence_requirements,
    proposal_feature_ids,
    routine_proposals,
    sanitized_decision_inputs,
)
from .agent_types import (
    AgentTypeDefinition,
    AgentTypeProposalAudit,
    ConfirmAgentTypeProposalRequest,
    ConfirmedAgentTypeRegistry,
    ResolvedAgentTypeRegistry,
    confirm_agent_type_proposal,
)
from .registry_store import SimulationRegistryStore

PROMPT_VERSION = "agent-behavior-proposal-v2"


class AgentTypeRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentTypeProposalRequest(AgentTypeRouteModel):
    prompt: str = Field(min_length=1, max_length=12_000)


class AgentTypeProposalShape(AgentTypeRouteModel):
    types: list[AgentTypeDefinition] = Field(min_length=1)


class AgentTypeRegistryView(AgentTypeRouteModel):
    configured: bool
    confirmed: ConfirmedAgentTypeRegistry | None
    resolved: ResolvedAgentTypeRegistry


def _feature_context(atlas_store: AtlasStore | None = None) -> tuple[set[str], str]:
    registry = canonical_feature_registry()
    if atlas_store is not None:
        registry = FeatureCatalogStore(atlas_store).enriched_registry(registry)
    features = registry.definitions
    identities = {feature.id for feature in features}
    distributions_by_feature = {
        feature_id: sorted(
            [item for item in registry.distributions if item.feature_id == feature_id],
            key=lambda item: (
                item.method != "measured",
                -item.coverage_percent,
                item.level,
                item.place,
            ),
        )
        for feature_id in identities
    }
    context = json.dumps(
        [
            {
                "id": feature.id,
                "name": feature.name,
                "description": feature.description,
                "kind": feature.kind,
                "predictive": feature.predictive,
                "distribution_count": len(distributions_by_feature[feature.id]),
                "imported_distributions": [
                    {
                        "level": distribution.level,
                        "place": distribution.place,
                        "population": distribution.population,
                        "coverage_percent": distribution.coverage_percent,
                        "values": distribution.values,
                        "mean": distribution.mean,
                        "standard_deviation": distribution.standard_deviation,
                        "method": distribution.method,
                        "source": distribution.provenance.source,
                        "source_version": distribution.provenance.version,
                        "evidence_status": distribution.provenance.status,
                    }
                    for distribution in distributions_by_feature[feature.id][:3]
                ],
            }
            for feature in features
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return identities, context


def _source_feature_ids(types: list[AgentTypeDefinition]) -> set[str]:
    return {
        feature_id
        for agent_type in types
        for member in [*agent_type.traits, *agent_type.routines, *agent_type.decisions]
        for feature_id in member.source_feature_ids
    }


def _require_known_features(
    types: list[AgentTypeDefinition], atlas_store: AtlasStore | None = None
) -> None:
    known, _ = _feature_context(atlas_store)
    unknown = sorted(_source_feature_ids(types) - known)
    if unknown:
        raise HTTPException(
            422,
            f"Unknown registry feature references: {', '.join(unknown)}",
        )


def _decision_evidence_context(store: SimulationRegistryStore) -> str:
    registry = store.decision_evidence()
    if registry is None:
        return json.dumps({"version": None, "templates": [], "evidence": []})
    return json.dumps(
        {
            "version": registry.version,
            "templates": [
                {
                    "id": template.id,
                    "name": template.name,
                    "domain": template.domain,
                    "status": template.status,
                    "entry_state": template.entry_state,
                    "terminal_states": template.terminal_states,
                    "nodes": [node.model_dump(mode="json") for node in template.nodes],
                    "edges": [
                        {
                            "id": edge.id,
                            "from_state": edge.from_state,
                            "to_state": edge.to_state,
                            "factor_feature_ids": [
                                factor.feature_id
                                for factor in edge.formula.factors
                                if factor.feature_id is not None
                            ],
                        }
                        for edge in template.edges
                    ],
                }
                for template in registry.templates
            ],
            "evidence": [
                {
                    "id": row.id,
                    "decision_id": row.decision_id,
                    "edge_id": row.edge_id,
                    "factor_id": row.factor_id,
                    "basis": row.basis,
                    "place": row.place.model_dump(mode="json"),
                    "fittable": row.fittable,
                    "source_id": row.source.imported_source_id,
                    "source_date": row.source.publication_date.isoformat(),
                }
                for row in registry.evidence
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def create_agent_type_router(
    store: SimulationRegistryStore,
    ai_provider,
    atlas_store: AtlasStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/simulation/agent-types", tags=["Simulation agent types"])

    @router.get("", response_model=AgentTypeRegistryView)
    def get_agent_types() -> AgentTypeRegistryView:
        confirmed = store.agent_types()
        return AgentTypeRegistryView(
            configured=confirmed is not None,
            confirmed=confirmed,
            resolved=store.resolved_agent_types(),
        )

    @router.post("/proposals", response_model=AgentBehaviorProposalDraft)
    def propose_agent_types(request: AgentTypeProposalRequest) -> AgentBehaviorProposalDraft:
        feature_ids, feature_context = _feature_context(atlas_store)
        decision_evidence_context = _decision_evidence_context(store)
        system_prompt = (
            "Propose one editable global agent behavior bundle containing an agent-type "
            "inheritance graph, typed routine intents, modular decision-tree topology, and one "
            "exact input plan for every root decision edge. Agent types may have multiple "
            "parents. Use registry feature ids only when the supplied registry shows them. "
            "Reference decision evidence ids only when they appear in the supplied decision "
            "evidence registry. Cover supported decisions across work, social, family, health, "
            "consumption, political, and other imported-data domains with separate focused "
            "modules. Omit unsupported decisions or leave them blocked with an exact evidence "
            "requirement. Routine intents name activities and optional decision "
            "modules but never contain schedules. Never invent a time, day, place, probability, "
            "coefficient, citation, source, country ranking, or observation. Unknown evidence "
            "references remain empty. Conflicts between inherited members remain explicit "
            "overrides for human review. Return a proposal only."
        )
        payload = json.dumps(
            {
                "request": request.prompt,
                "registry_features": json.loads(feature_context),
                "decision_evidence": json.loads(decision_evidence_context),
            },
            ensure_ascii=False,
        )
        try:
            generated = ai_provider.generate_structured(
                payload,
                AgentBehaviorProposalShape,
                system_prompt=system_prompt,
                prompt_version=PROMPT_VERSION,
            )
        except AIProviderError as error:
            raise HTTPException(502, str(error)) from error
        output = generated.output
        if isinstance(output, AgentTypeProposalShape):
            output = AgentBehaviorProposalShape(
                types=output.types,
                decision_trees=DecisionTreeTopologyIntent(
                    version="1",
                    trees=[],
                    modules=[],
                ),
            )
        types = output.types
        current = store.agent_types()
        provenance = generated.provenance
        audit = AgentTypeProposalAudit(
            provider=provenance.source,
            model=provenance.model,
            generated_at=provenance.generated_at.isoformat(),
            prompt_version=provenance.prompt_version,
        )
        routines = routine_proposals(output.routines)
        tree_drafts = decision_tree_drafts(output.decision_trees, audit)
        inputs = sanitized_decision_inputs(
            output.decision_inputs,
            store.decision_evidence(),
        )
        requirements = evidence_requirements(
            routines,
            tree_drafts,
            inputs,
            store.decision_evidence(),
        )
        draft = AgentBehaviorProposalDraft(
            id="agent_types",
            prompt=request.prompt,
            imported_feature_ids=[],
            types=types,
            audit=audit,
            revision=(current.revision + 1) if current else 1,
            routine_drafts=routines,
            decision_tree_drafts=tree_drafts,
            decision_inputs=inputs,
            evidence_requirements=requirements,
        )
        unknown = sorted(proposal_feature_ids(draft) - feature_ids)
        if unknown:
            raise HTTPException(
                502,
                f"AI proposal referenced unknown registry features: {', '.join(unknown)}",
            )
        referenced = sorted(proposal_feature_ids(draft) & feature_ids)
        return draft.model_copy(update={"imported_feature_ids": referenced})

    @router.post("/confirm", response_model=ConfirmedAgentTypeRegistry)
    def confirm_agent_types(
        request: ConfirmAgentBehaviorProposalRequest | ConfirmAgentTypeProposalRequest,
    ) -> ConfirmedAgentTypeRegistry:
        if isinstance(request, ConfirmAgentBehaviorProposalRequest):
            known_features, _ = _feature_context(atlas_store)
            unknown = sorted(proposal_feature_ids(request.draft) - known_features)
            if unknown:
                raise HTTPException(
                    422,
                    f"Unknown registry feature references: {', '.join(unknown)}",
                )
            try:
                bundle = confirm_agent_behavior_proposal(
                    request.draft,
                    request.user_confirmed,
                    store.decision_evidence(),
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            store.save_behavior_proposal(
                bundle.agent_types,
                bundle.routines,
                bundle.decision_trees,
                bundle,
            )
            return bundle.agent_types
        _require_known_features(request.draft.types, atlas_store)
        try:
            confirmed = confirm_agent_type_proposal(
                request.draft,
                request.user_confirmed,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return store.save_agent_types(confirmed)

    return router

