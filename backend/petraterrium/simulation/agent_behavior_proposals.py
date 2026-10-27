from .agent_behavior_contracts import (
    AgentBehaviorProposalDraft,
    AgentBehaviorProposalShape,
    BehaviorEvidenceRequirement,
    ConfirmAgentBehaviorProposalRequest,
    ConfirmedAgentBehaviorBundle,
    DecisionEdgeInputPlan,
    DecisionTreeEdgeIntent,
    DecisionTreeIntent,
    DecisionTreeModuleIntent,
    DecisionTreeNodeIntent,
    DecisionTreeTopologyIntent,
    EvidenceRequirementStatus,
    RoutineIntent,
    RoutineProposalDraft,
    RoutineStepIntent,
    RoutineStepProposal,
)
from .agent_types import (
    AgentTypeDefinition,
    AgentTypeMember,
    AgentTypeProposalAudit,
    confirm_agent_type_proposal,
)
from .decision_evidence import DecisionFactorEvidence, DecisionTreeTemplate
from .registry_store import DecisionEvidenceRegistryDefinition
from .routines import (
    RoutineDefinition,
    RoutineEvidence,
    RoutineRegistryDefinition,
    RoutineStep,
    validate_routines,
)
from .tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeModuleRegistry,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
)

__all__ = [
    "AgentBehaviorProposalDraft",
    "AgentBehaviorProposalShape",
    "BehaviorEvidenceRequirement",
    "ConfirmAgentBehaviorProposalRequest",
    "ConfirmedAgentBehaviorBundle",
    "DecisionEdgeInputPlan",
    "DecisionTreeEdgeIntent",
    "DecisionTreeIntent",
    "DecisionTreeModuleIntent",
    "DecisionTreeNodeIntent",
    "DecisionTreeTopologyIntent",
    "RoutineIntent",
    "RoutineProposalDraft",
    "RoutineStepIntent",
    "RoutineStepProposal",
    "confirm_agent_behavior_proposal",
    "decision_tree_drafts",
    "evidence_requirements",
    "proposal_feature_ids",
    "routine_proposals",
    "sanitized_decision_inputs",
]

def proposal_source(audit: AgentTypeProposalAudit) -> str:
    provider = {
        "openai_cli": "OpenAI CLI",
        "openai_api": "OpenAI API",
        "deterministic": "Deterministic parser",
        "manual": "Manual entry",
    }[audit.provider]
    return (
        f"{provider} proposal · model {audit.model} · prompt {audit.prompt_version} · "
        f"generated {audit.generated_at} · awaiting human confirmation"
    )


def confirmed_proposal_source(audit: AgentTypeProposalAudit) -> str:
    return proposal_source(audit).replace(
        "awaiting human confirmation",
        "human-confirmed",
    )


def routine_proposals(intents: list[RoutineIntent]) -> list[RoutineProposalDraft]:
    return [
        RoutineProposalDraft(
            id=intent.id,
            name=intent.name,
            agent_type_id=intent.agent_type_id,
            description=intent.description,
            source_feature_ids=intent.source_feature_ids,
            evidence=RoutineEvidence(
                status="unknown",
                note=(
                    "No schedule was inferred. A human must attach measured schedule provenance "
                    "or enter and confirm a user-defined schedule."
                ),
            ),
            steps=[
                RoutineStepProposal(
                    id=step.id,
                    name=step.name,
                    activity=step.activity,
                    decision_tree_module_id=step.decision_tree_module_id,
                )
                for step in intent.steps
            ],
        )
        for intent in intents
    ]


def decision_tree_drafts(
    topology: DecisionTreeTopologyIntent,
    audit: AgentTypeProposalAudit,
) -> DecisionTreeRegistryDefinition:
    source = proposal_source(audit)
    return DecisionTreeRegistryDefinition(
        version=topology.version,
        trees=[
            DecisionTreeDefinition(
                id=tree.id,
                version=tree.version,
                name=tree.name,
                description=tree.description,
                root_module_id=tree.root_module_id,
                agent_type_ids=tree.agent_type_ids,
                place_ids=tree.place_ids,
                source=source,
                status="blocked",
            )
            for tree in topology.trees
        ],
        modules=[
            DecisionTreeModule(
                id=module.id,
                version=module.version,
                name=module.name,
                description=module.description,
                entry_node=module.entry_node,
                nodes=[
                    DecisionTreeNode(
                        id=node.id,
                        label=node.label,
                        kind=node.kind,
                        description=node.description,
                        target_module_id=node.target_module_id,
                    )
                    for node in module.nodes
                ],
                edges=[
                    DecisionTreeEdge(
                        id=edge.id,
                        from_node=edge.from_node,
                        to_node=edge.to_node,
                        label=edge.label,
                        condition=edge.condition,
                    )
                    for edge in module.edges
                ],
                source=source,
                status="blocked",
            )
            for module in topology.modules
        ],
    )


def _plan_key(plan: DecisionEdgeInputPlan) -> tuple[str, str, str]:
    return plan.tree_id, plan.module_id, plan.edge_id


def _template_edge(
    plan: DecisionEdgeInputPlan,
    templates: dict[str, DecisionTreeTemplate],
):
    if plan.decision_id is None or plan.evidence_edge_id is None:
        return None
    template = templates.get(plan.decision_id)
    if template is None:
        return None
    return next(
        (edge for edge in template.edges if edge.id == plan.evidence_edge_id),
        None,
    )


def sanitized_decision_inputs(
    plans: list[DecisionEdgeInputPlan],
    registry: DecisionEvidenceRegistryDefinition | None,
) -> list[DecisionEdgeInputPlan]:
    templates = {item.id: item for item in registry.templates} if registry else {}
    return [
        plan
        if _template_edge(plan, templates) is not None
        else plan.model_copy(update={"decision_id": None, "evidence_edge_id": None})
        for plan in plans
    ]


def _qualifying_evidence(
    template_edge,
    evidence_rows: list[DecisionFactorEvidence],
) -> list[DecisionFactorEvidence]:
    if template_edge is None:
        return []
    factor_ids = {factor.id for factor in template_edge.formula.factors}
    rows = [
        row
        for row in evidence_rows
        if row.decision_id == template_edge.decision_id
        and row.edge_id == template_edge.id
        and row.factor_id in factor_ids
        and row.basis in {"measured_joint", "fitted_model"}
        and row.fittable
    ]
    covered = {row.factor_id for row in rows}
    return rows if factor_ids.issubset(covered) else []


def _qualifying_plan_evidence(
    plan: DecisionEdgeInputPlan,
    templates: dict[str, DecisionTreeTemplate],
    evidence_rows: list[DecisionFactorEvidence],
) -> list[DecisionFactorEvidence]:
    template_edge = _template_edge(plan, templates)
    if (
        template_edge is None
        or plan.decision_id != plan.tree_id
        or plan.evidence_edge_id != plan.edge_id
    ):
        return []
    expected_features = {
        factor.feature_id
        for factor in template_edge.formula.factors
        if factor.feature_id is not None
    }
    if set(plan.source_feature_ids) != expected_features:
        return []
    return _qualifying_evidence(template_edge, evidence_rows)


def _tree_matches_template(
    tree: DecisionTreeDefinition,
    module: DecisionTreeModule,
    template: DecisionTreeTemplate,
) -> bool:
    if tree.id != template.id or tree.root_module_id != module.id:
        return False
    if any(node.kind == "module_reference" for node in module.nodes):
        return False
    template_nodes = {node.id for node in template.nodes}
    module_nodes = {node.id for node in module.nodes}
    if template.entry_state != module.entry_node or template_nodes != module_nodes:
        return False
    template_edges = {
        edge.id: (edge.from_state, edge.to_state) for edge in template.edges
    }
    module_edges = {edge.id: (edge.from_node, edge.to_node) for edge in module.edges}
    if template_edges != module_edges:
        return False
    terminal_nodes = {node.id for node in module.nodes if node.kind == "terminal"}
    return terminal_nodes == set(template.terminal_states)


def _tree_module_ids(
    tree: DecisionTreeDefinition,
    modules: dict[str, DecisionTreeModule],
) -> set[str]:
    found: set[str] = set()
    pending = [tree.root_module_id]
    while pending:
        module_id = pending.pop()
        if module_id in found:
            continue
        found.add(module_id)
        module = modules.get(module_id)
        if module is None:
            continue
        pending.extend(
            node.target_module_id
            for node in module.nodes
            if node.target_module_id is not None
        )
    return found


def _tree_edge_keys(
    trees: DecisionTreeRegistryDefinition,
) -> set[tuple[str, str, str]]:
    modules = {module.id: module for module in trees.modules}
    return {
        (tree.id, module_id, edge.id)
        for tree in trees.trees
        for module_id in _tree_module_ids(tree, modules)
        if (module := modules.get(module_id)) is not None
        for edge in module.edges
    }


def evidence_requirements(
    routines: list[RoutineProposalDraft],
    trees: DecisionTreeRegistryDefinition,
    plans: list[DecisionEdgeInputPlan],
    registry: DecisionEvidenceRegistryDefinition | None,
) -> list[BehaviorEvidenceRequirement]:
    templates = {item.id: item for item in registry.templates} if registry else {}
    evidence_rows = registry.evidence if registry else []
    requirements: list[BehaviorEvidenceRequirement] = []
    for routine in routines:
        for step in routine.steps:
            matched = step.schedule is not None and routine.evidence.status in {
                "measured",
                "user_defined",
            }
            requirements.append(
                BehaviorEvidenceRequirement(
                    id=f"routine-{routine.id}-{step.id}",
                    kind="routine_schedule",
                    status="matched" if matched else "missing",
                    target_id=f"{routine.id}.{step.id}",
                    source_feature_ids=routine.source_feature_ids,
                    outcome=step.activity,
                    population_scope=f"agent type {routine.agent_type_id}",
                    place_scope="global",
                    time_scope="weekly schedule",
                    accepted_bases=["measured", "user_defined"],
                    required_fields=[
                        "days",
                        "start_time",
                        "end_time",
                        "place_ids",
                        "role_ids",
                        "source_title_or_human_confirmation",
                        "source_date_if_measured",
                    ],
                    matched_evidence_ids=[],
                    message=(
                        "Schedule supplied with measured provenance or explicit human definition"
                        if matched
                        else (
                            "Need days, start and end time, place ids, role ids, and either "
                            "measured source provenance or explicit human definition"
                        )
                    ),
                )
            )
    edge_keys = _tree_edge_keys(trees)
    for plan in plans:
        matches = _qualifying_plan_evidence(plan, templates, evidence_rows)
        status: EvidenceRequirementStatus = "matched" if matches else "missing"
        requirements.append(
            BehaviorEvidenceRequirement(
                id=f"decision-{plan.tree_id}-{plan.module_id}-{plan.edge_id}",
                kind="decision_probability",
                status=status,
                target_id=f"{plan.tree_id}.{plan.module_id}.{plan.edge_id}",
                source_feature_ids=plan.source_feature_ids,
                outcome=plan.outcome,
                population_scope=plan.population_scope,
                place_scope=plan.place_scope,
                time_scope=plan.time_scope,
                accepted_bases=["measured_joint", "fitted_model"],
                required_fields=[
                    "trait_and_outcome_joint_rows",
                    "place",
                    "time_period",
                    "sample_size",
                    "survey_weights",
                    "estimate",
                    "confidence_interval",
                    "source",
                    "source_date",
                    "held_out_sample_if_fitted",
                ],
                matched_evidence_ids=sorted(row.id for row in matches),
                message=(
                    "Matched measured joint or held-out fitted evidence for every factor"
                    if matches
                    else (
                        "Need measured joint trait-to-outcome rows or a held-out fitted model "
                        "covering every factor at the named population, place, and time scope"
                    )
                ),
            )
        )
    planned_keys = {_plan_key(plan) for plan in plans}
    for tree_id, module_id, edge_id in sorted(edge_keys - planned_keys):
        requirements.append(
            BehaviorEvidenceRequirement(
                id=f"decision-{tree_id}-{module_id}-{edge_id}",
                kind="decision_probability",
                status="missing",
                target_id=f"{tree_id}.{module_id}.{edge_id}",
                source_feature_ids=[],
                outcome="Outcome link not specified",
                population_scope="Population not specified",
                place_scope="global",
                time_scope="Time scope not specified",
                accepted_bases=["measured_joint", "fitted_model"],
                required_fields=[
                    "source_feature_ids",
                    "outcome",
                    "population_scope",
                    "place_scope",
                    "time_scope",
                    "trait_and_outcome_joint_rows",
                    "sample_size",
                    "confidence_interval",
                    "source",
                    "source_date",
                ],
                matched_evidence_ids=[],
                message="Need an exact evidence plan and measured or held-out fitted data",
            )
        )
    return sorted(requirements, key=lambda item: item.id)


def _validated_plan_targets(
    trees: DecisionTreeRegistryDefinition,
    plans: list[DecisionEdgeInputPlan],
) -> None:
    valid_keys = _tree_edge_keys(trees)
    keys = [_plan_key(plan) for plan in plans]
    if len(set(keys)) != len(keys):
        raise ValueError("Decision input plans must be unique by tree, module, and edge")
    unknown = sorted(set(keys) - valid_keys)
    if unknown:
        paths = ", ".join(".".join(key) for key in unknown)
        raise ValueError(f"Decision input plans reference unknown root edges: {paths}")


def _finalized_tree_registry(
    draft: AgentBehaviorProposalDraft,
    registry: DecisionEvidenceRegistryDefinition | None,
) -> DecisionTreeRegistryDefinition:
    _validated_plan_targets(draft.decision_tree_drafts, draft.decision_inputs)
    templates = {item.id: item for item in registry.templates} if registry else {}
    evidence_rows = registry.evidence if registry else []
    plans = {_plan_key(plan): plan for plan in draft.decision_inputs}
    modules_by_id = {module.id: module for module in draft.decision_tree_drafts.modules}
    ready_tree_ids: set[str] = set()
    ready_module_ids: set[str] = set()
    finalized_modules: dict[str, DecisionTreeModule] = {}
    confirmed_source = confirmed_proposal_source(draft.audit)
    for tree in draft.decision_tree_drafts.trees:
        module = modules_by_id.get(tree.root_module_id)
        template = templates.get(tree.id)
        ready = bool(
            module is not None
            and template is not None
            and template.status == "ready"
            and _tree_matches_template(tree, module, template)
        )
        edges: list[DecisionTreeEdge] = []
        if module is not None:
            for edge in module.edges:
                plan = plans.get((tree.id, module.id, edge.id))
                qualifying = (
                    _qualifying_plan_evidence(plan, templates, evidence_rows)
                    if plan
                    else []
                )
                linked = bool(
                    ready
                    and plan is not None
                    and plan.decision_id == tree.id
                    and plan.evidence_edge_id == edge.id
                    and qualifying
                )
                if not linked:
                    ready = False
                edges.append(
                    edge.model_copy(
                        update={
                            "decision_id": plan.decision_id if linked else None,
                            "evidence_edge_id": plan.evidence_edge_id if linked else None,
                        }
                    )
                )
            finalized_modules[module.id] = module.model_copy(update={"edges": edges})
        if ready and module is not None:
            ready_tree_ids.add(tree.id)
            ready_module_ids.add(module.id)
    modules = [
        finalized_modules.get(module.id, module).model_copy(
            update={
                "source": confirmed_source,
                "status": "ready" if module.id in ready_module_ids else "blocked",
            }
        )
        for module in draft.decision_tree_drafts.modules
    ]
    trees = [
        tree.model_copy(
            update={
                "source": confirmed_source,
                "status": "ready" if tree.id in ready_tree_ids else "blocked",
            }
        )
        for tree in draft.decision_tree_drafts.trees
    ]
    return DecisionTreeRegistryDefinition(
        version=draft.decision_tree_drafts.version,
        trees=trees,
        modules=modules,
    )


def _materialized_routines(
    draft: AgentBehaviorProposalDraft,
) -> RoutineRegistryDefinition:
    definitions: list[RoutineDefinition] = []
    incomplete: list[str] = []
    for routine in draft.routine_drafts:
        if routine.evidence.status not in {"measured", "user_defined"}:
            incomplete.append(
                f"{routine.id} needs measured provenance or explicit user-defined confirmation"
            )
        steps: list[RoutineStep] = []
        for step in routine.steps:
            if step.schedule is None:
                incomplete.append(f"{routine.id}.{step.id} needs a confirmed schedule")
                continue
            steps.append(
                RoutineStep(
                    id=step.id,
                    name=step.name,
                    activity=step.activity,
                    schedule=step.schedule,
                    decision_tree_module_id=step.decision_tree_module_id,
                )
            )
        if len(steps) == len(routine.steps):
            evidence = routine.evidence
            if evidence.status == "user_defined":
                evidence = RoutineEvidence(
                    status="user_defined",
                    note=(
                        "Human-confirmed schedule; proposal provenance: "
                        f"{confirmed_proposal_source(draft.audit)}"
                    ),
                )
            definitions.append(
                RoutineDefinition(
                    id=routine.id,
                    name=routine.name,
                    agent_type_id=routine.agent_type_id,
                    description=routine.description,
                    evidence=evidence,
                    steps=steps,
                )
            )
    if incomplete:
        raise ValueError("; ".join(incomplete))
    registry = RoutineRegistryDefinition(
        agent_types=draft.types,
        routines=definitions,
    )
    validation = validate_routines(
        registry,
        {module.id for module in draft.decision_tree_drafts.modules},
    )
    if not validation.valid:
        raise ValueError("; ".join(issue.message for issue in validation.issues))
    return registry


def proposal_feature_ids(draft: AgentBehaviorProposalDraft) -> set[str]:
    member_ids = {
        feature_id
        for agent_type in draft.types
        for member in [*agent_type.traits, *agent_type.routines, *agent_type.decisions]
        for feature_id in member.source_feature_ids
    }
    routine_ids = {
        feature_id
        for routine in draft.routine_drafts
        for feature_id in routine.source_feature_ids
    }
    decision_ids = {
        feature_id
        for plan in draft.decision_inputs
        for feature_id in plan.source_feature_ids
    }
    return member_ids | routine_ids | decision_ids


def _types_with_decision_tree_links(
    draft: AgentBehaviorProposalDraft,
    decision_trees: DecisionTreeRegistryDefinition,
) -> list[AgentTypeDefinition]:
    tree_ids = {tree.id for tree in decision_trees.trees}
    missing = sorted(
        {
            member.id
            for agent_type in draft.types
            for member in agent_type.decisions
            if member.id not in tree_ids
        }
    )
    if missing:
        raise ValueError(
            "Agent type decision members reference missing decision trees: "
            + ", ".join(missing)
        )
    feature_ids_by_tree = {
        tree.id: sorted(
            {
                feature_id
                for plan in draft.decision_inputs
                if plan.tree_id == tree.id
                for feature_id in plan.source_feature_ids
            }
        )
        for tree in decision_trees.trees
    }
    ready_by_type: dict[str, list[DecisionTreeDefinition]] = {}
    for tree in decision_trees.trees:
        if tree.status != "ready":
            continue
        for agent_type_id in tree.agent_type_ids:
            ready_by_type.setdefault(agent_type_id, []).append(tree)
    linked: list[AgentTypeDefinition] = []
    for agent_type in draft.types:
        decisions = list(agent_type.decisions)
        existing = {member.id for member in decisions}
        for tree in sorted(ready_by_type.get(agent_type.id, []), key=lambda item: item.id):
            if tree.id in existing:
                continue
            decisions.append(
                AgentTypeMember(
                    id=tree.id,
                    name=tree.name,
                    definition=tree.description or f"{tree.name} decision tree",
                    description=tree.description or None,
                    source_feature_ids=feature_ids_by_tree[tree.id],
                )
            )
        linked.append(agent_type.model_copy(update={"decisions": decisions}))
    return linked


def confirm_agent_behavior_proposal(
    draft: AgentBehaviorProposalDraft,
    user_confirmed: bool,
    evidence_registry: DecisionEvidenceRegistryDefinition | None,
) -> ConfirmedAgentBehaviorBundle:
    if not user_confirmed:
        raise ValueError(
            "Explicit user confirmation is required before saving agent behavior"
        )
    tree_validation = DecisionTreeModuleRegistry(draft.decision_tree_drafts).validation
    if not tree_validation.valid:
        raise ValueError("; ".join(issue.message for issue in tree_validation.issues))
    known_type_ids = {agent_type.id for agent_type in draft.types}
    unknown_tree_types = sorted(
        {
            agent_type_id
            for tree in draft.decision_tree_drafts.trees
            for agent_type_id in tree.agent_type_ids
            if agent_type_id not in known_type_ids
        }
    )
    if unknown_tree_types:
        raise ValueError(
            "Decision trees reference unknown agent types: "
            f"{', '.join(unknown_tree_types)}"
        )
    decision_trees = _finalized_tree_registry(draft, evidence_registry)
    linked_draft = draft.model_copy(
        update={"types": _types_with_decision_tree_links(draft, decision_trees)}
    )
    confirmed_types = confirm_agent_type_proposal(linked_draft, True)
    routines = _materialized_routines(linked_draft)
    requirements = evidence_requirements(
        draft.routine_drafts,
        decision_trees,
        draft.decision_inputs,
        evidence_registry,
    )
    return ConfirmedAgentBehaviorBundle(
        agent_types=confirmed_types,
        routines=routines,
        decision_trees=decision_trees,
        evidence_requirements=requirements,
        audit=draft.audit,
        revision=draft.revision,
    )
