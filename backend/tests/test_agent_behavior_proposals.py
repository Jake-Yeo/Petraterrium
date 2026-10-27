import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from petraterrium.ai_provider import AIGeneration
from petraterrium.ai_settings import AISourceProvenance
from petraterrium.main import create_app
from petraterrium.simulation.agent_behavior_proposals import (
    AgentBehaviorProposalDraft,
    AgentBehaviorProposalShape,
    DecisionEdgeInputPlan,
    DecisionTreeEdgeIntent,
    DecisionTreeIntent,
    DecisionTreeModuleIntent,
    DecisionTreeNodeIntent,
    DecisionTreeTopologyIntent,
    RoutineIntent,
    RoutineStepIntent,
    confirm_agent_behavior_proposal,
    decision_tree_drafts,
    evidence_requirements,
)
from petraterrium.simulation.agent_types import (
    AgentTypeDefinition,
    AgentTypeMember,
    AgentTypeProposalAudit,
)
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
from petraterrium.simulation.registry_store import (
    DecisionEvidenceRegistryDefinition,
    SimulationRegistryStore,
)


def audit() -> AgentTypeProposalAudit:
    return AgentTypeProposalAudit(
        provider="openai_cli",
        model="test-model",
        generated_at="2026-10-27T12:00:00Z",
        prompt_version="agent-behavior-proposal-v2",
    )


def blocked_topology() -> DecisionTreeTopologyIntent:
    return DecisionTreeTopologyIntent(
        version="proposal-1",
        trees=[
            DecisionTreeIntent(
                id="social_choice",
                version="proposal-1",
                name="Social choice",
                root_module_id="social_choice_module",
                agent_type_ids=["person"],
            )
        ],
        modules=[
            DecisionTreeModuleIntent(
                id="social_choice_module",
                version="proposal-1",
                name="Social choice",
                entry_node="decide",
                nodes=[
                    DecisionTreeNodeIntent(
                        id="decide",
                        label="Decide",
                        kind="decision",
                    ),
                    DecisionTreeNodeIntent(
                        id="stay_home",
                        label="Stay home",
                        kind="terminal",
                    ),
                ],
                edges=[
                    DecisionTreeEdgeIntent(
                        id="stay_home_edge",
                        from_node="decide",
                        to_node="stay_home",
                        label="Stay home",
                    )
                ],
            )
        ],
    )


class BehaviorProposalProvider:
    def generate_structured(self, prompt, schema, **kwargs):
        assert schema is AgentBehaviorProposalShape
        assert kwargs["prompt_version"] == "agent-behavior-proposal-v2"
        assert (
            "work, social, family, health, consumption, political, and other"
            in kwargs["system_prompt"]
        )
        assert "leave them blocked with an exact evidence requirement" in kwargs[
            "system_prompt"
        ]
        context = json.loads(prompt)
        assert "decision_evidence" in context
        person = AgentTypeDefinition(
            id="person",
            name="Person",
            routines=[
                AgentTypeMember(
                    id="workday",
                    name="Workday",
                    definition="Daily work activity awaiting a confirmed schedule",
                    source_feature_ids=["age"],
                )
            ],
        )
        return AIGeneration(
            output=AgentBehaviorProposalShape(
                types=[person],
                routines=[
                    RoutineIntent(
                        id="workday",
                        name="Workday",
                        agent_type_id="person",
                        source_feature_ids=["age"],
                        steps=[
                            RoutineStepIntent(
                                id="work",
                                name="Work",
                                activity="Work at assigned workplace",
                                decision_tree_module_id="social_choice_module",
                            )
                        ],
                    )
                ],
                decision_trees=blocked_topology(),
                decision_inputs=[
                    DecisionEdgeInputPlan(
                        tree_id="social_choice",
                        module_id="social_choice_module",
                        edge_id="stay_home_edge",
                        source_feature_ids=["age"],
                        outcome="Stay home",
                        population_scope="people represented by the person agent type",
                        place_scope="country",
                        time_scope="day of week",
                        decision_id="invented_decision",
                        evidence_edge_id="invented_edge",
                    )
                ],
            ),
            provenance=AISourceProvenance(
                source="openai_cli",
                source_label="OpenAI CLI",
                model="test-model",
                generated_at="2026-10-27T12:00:00Z",
                prompt_version="agent-behavior-proposal-v2",
            ),
        )


def test_route_keeps_schedules_and_probabilities_unknown_until_one_confirmation(
    tmp_path,
):
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_provider=BehaviorProposalProvider(),
        simulation_registry_store=store,
    )

    with TestClient(application) as client:
        proposal = client.post(
            "/simulation/agent-types/proposals",
            json={"prompt": "Create a work routine and social choice"},
        )
        assert proposal.status_code == 200
        draft = proposal.json()
        assert draft["schema_version"] == "2"
        assert draft["routine_drafts"][0]["steps"][0]["schedule"] is None
        assert draft["routine_drafts"][0]["evidence"]["status"] == "unknown"
        assert draft["decision_tree_drafts"]["trees"][0]["status"] == "blocked"
        assert draft["decision_tree_drafts"]["modules"][0]["edges"][0][
            "decision_id"
        ] is None
        assert {item["status"] for item in draft["evidence_requirements"]} == {
            "missing"
        }
        routine_requirement = next(
            item
            for item in draft["evidence_requirements"]
            if item["kind"] == "routine_schedule"
        )
        assert routine_requirement["accepted_bases"] == ["measured", "user_defined"]

        rejected = client.post(
            "/simulation/agent-types/confirm",
            json={"draft": draft, "user_confirmed": True},
        )
        assert rejected.status_code == 422
        assert "needs a confirmed schedule" in rejected.json()["detail"]
        assert store.agent_types() is None
        assert store.routines() is None
        assert store.decision_trees().trees == []

        routine = draft["routine_drafts"][0]
        routine["evidence"]["status"] = "user_defined"
        routine["steps"][0]["schedule"] = {
            "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "start_time": "09:00",
            "end_time": "17:00",
            "ends_next_day": False,
            "place_ids": ["assigned_workplace"],
            "role_ids": ["worker"],
        }
        confirmed = client.post(
            "/simulation/agent-types/confirm",
            json={"draft": draft, "user_confirmed": True},
        )

    assert confirmed.status_code == 200
    assert store.agent_types() is not None
    assert store.routines().routines[0].steps[0].schedule.start_time == "09:00"
    assert "human-confirmed" in store.routines().routines[0].evidence.note
    assert store.decision_trees().trees[0].status == "blocked"
    assert "human-confirmed" in store.decision_trees().trees[0].source
    assert "awaiting human confirmation" not in store.decision_trees().trees[0].source
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert {
        "agent_types",
        "routines",
        "decision_trees",
        "agent_behavior_proposal",
    }.issubset(payload)


def _citation(decision_id: str, factor_ids: tuple[str, ...]) -> ResearchCitation:
    return ResearchCitation(
        kind="research_paper",
        imported_source_id="imported-study-2026",
        title="Observed choices",
        source="Imported survey",
        publication_date=date(2026, 1, 1),
        population_studied="Adults in the imported sample",
        link_or_reference="registry://imported-study-2026",
        supports_decision_ids=(decision_id,),
        supports_factor_ids=factor_ids,
    )


def _evidence_registry(basis: str) -> DecisionEvidenceRegistryDefinition:
    decision_id = "choose_activity"
    factors = (
        ProbabilityFactor(
            id="age_factor",
            name="Age",
            input_kind="trait",
            input_key="age",
            feature_id="age",
        ),
        ProbabilityFactor(
            id="availability_factor",
            name="Availability",
            input_kind="context",
            input_key="choice_available",
        ),
    )
    citation = _citation(decision_id, tuple(factor.id for factor in factors))
    edges = []
    evidence = []
    for edge_id, target, probability in (
        ("go_edge", "go", 0.6),
        ("stay_edge", "stay", 0.4),
    ):
        edges.append(
            DecisionEdgeTemplate(
                id=edge_id,
                decision_id=decision_id,
                domain="social",
                from_state="decide",
                to_state=target,
                label=target.title(),
                formula=DecisionProbabilityFormula(
                    id=f"{edge_id}_formula",
                    name=f"{target.title()} probability",
                    combination="product",
                    factors=factors,
                ),
                source=citation,
            )
        )
        for factor, estimate in zip(factors, (probability, 1.0), strict=True):
            evidence.append(
                DecisionFactorEvidence(
                    id=f"{edge_id}-{factor.id}",
                    decision_id=decision_id,
                    edge_id=edge_id,
                    factor_id=factor.id,
                    place=EvidencePlace(level="global", place_id="global"),
                    predicate=EvidencePredicate(operator="any"),
                    basis=basis,
                    estimate=estimate,
                    ci_low=max(0, estimate - 0.05),
                    ci_high=min(1, estimate + 0.05),
                    sample_size=1000,
                    fittable=basis != "marginal",
                    source=citation,
                )
            )
    template = DecisionTreeTemplate(
        id=decision_id,
        name="Choose activity",
        domain="social",
        status="ready",
        entry_state="decide",
        terminal_states=("go", "stay"),
        nodes=(
            DecisionNodeTemplate(id="decide", label="Decide", kind="decision"),
            DecisionNodeTemplate(id="go", label="Go", kind="terminal"),
            DecisionNodeTemplate(id="stay", label="Stay", kind="terminal"),
        ),
        edges=tuple(edges),
    )
    return DecisionEvidenceRegistryDefinition(
        version="evidence-1",
        templates=[template],
        evidence=evidence,
    )


def _matched_draft(
    registry: DecisionEvidenceRegistryDefinition,
    feature_id: str = "age",
) -> AgentBehaviorProposalDraft:
    topology = DecisionTreeTopologyIntent(
        version="proposal-1",
        trees=[
            DecisionTreeIntent(
                id="choose_activity",
                version="proposal-1",
                name="Choose activity",
                root_module_id="choose_activity",
                agent_type_ids=["person"],
            )
        ],
        modules=[
            DecisionTreeModuleIntent(
                id="choose_activity",
                version="proposal-1",
                name="Choose activity",
                entry_node="decide",
                nodes=[
                    DecisionTreeNodeIntent(
                        id="decide",
                        label="Decide",
                        kind="decision",
                    ),
                    DecisionTreeNodeIntent(id="go", label="Go", kind="terminal"),
                    DecisionTreeNodeIntent(
                        id="stay",
                        label="Stay",
                        kind="terminal",
                    ),
                ],
                edges=[
                    DecisionTreeEdgeIntent(
                        id="go_edge",
                        from_node="decide",
                        to_node="go",
                    ),
                    DecisionTreeEdgeIntent(
                        id="stay_edge",
                        from_node="decide",
                        to_node="stay",
                    ),
                ],
            )
        ],
    )
    trees = decision_tree_drafts(topology, audit())
    plans = [
        DecisionEdgeInputPlan(
            tree_id="choose_activity",
            module_id="choose_activity",
            edge_id=edge_id,
            source_feature_ids=[feature_id],
            outcome=outcome,
            population_scope="Adults in the imported sample",
            place_scope="global",
            time_scope="Imported survey period",
            decision_id="choose_activity",
            evidence_edge_id=edge_id,
        )
        for edge_id, outcome in (("go_edge", "Go"), ("stay_edge", "Stay"))
    ]
    return AgentBehaviorProposalDraft(
        id="agent_types",
        prompt="Create an evidence-backed activity choice",
        imported_feature_ids=["age"],
        types=[AgentTypeDefinition(id="person", name="Person")],
        audit=audit(),
        revision=1,
        routine_drafts=[],
        decision_tree_drafts=trees,
        decision_inputs=plans,
        evidence_requirements=evidence_requirements([], trees, plans, registry),
    )


@pytest.mark.parametrize(
    ("basis", "feature_id", "expected_status", "expected_requirement"),
    [
        ("measured_joint", "age", "ready", "matched"),
        ("marginal", "age", "blocked", "missing"),
        ("measured_joint", "income", "blocked", "missing"),
    ],
)
def test_only_joint_or_fitted_evidence_can_make_confirmed_tree_ready(
    basis,
    feature_id,
    expected_status,
    expected_requirement,
):
    registry = _evidence_registry(basis)
    draft = _matched_draft(registry, feature_id)

    bundle = confirm_agent_behavior_proposal(draft, True, registry)

    assert bundle.decision_trees.trees[0].status == expected_status
    assert bundle.decision_trees.modules[0].status == expected_status
    assert {item.status for item in bundle.evidence_requirements} == {
        expected_requirement
    }
    if expected_status == "ready":
        assert [
            member.id for member in bundle.agent_types.types[0].decisions
        ] == ["choose_activity"]
    for edge in bundle.decision_trees.modules[0].edges:
        if expected_status == "ready":
            assert edge.decision_id == "choose_activity"
            assert edge.evidence_edge_id == edge.id
        else:
            assert edge.decision_id is None
            assert edge.evidence_edge_id is None


def test_behavior_confirmation_rejects_decision_member_without_tree():
    registry = _evidence_registry("measured_joint")
    draft = _matched_draft(registry)
    person = draft.types[0].model_copy(
        update={
            "decisions": [
                AgentTypeMember(
                    id="missing_tree",
                    name="Missing tree",
                    definition="This decision has no tree definition",
                )
            ]
        }
    )

    with pytest.raises(ValueError, match="missing decision trees"):
        confirm_agent_behavior_proposal(
            draft.model_copy(update={"types": [person]}),
            True,
            registry,
        )
