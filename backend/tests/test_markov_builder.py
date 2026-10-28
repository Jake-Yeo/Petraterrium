import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.ai_provider import AIGeneration, AIProviderError
from petraterrium.ai_settings import AISourceProvenance
from petraterrium.main import create_app
from petraterrium.markov_builder import (
    ChainConfirmationError,
    ChainDraft,
    ChainNodeDraft,
    ChainProposalRequest,
    ChainTransitionDraft,
    ProposalAudit,
    confirmed_chain_from_draft,
    create_markov_builder_router,
    deterministic_proposal,
    propose_chain,
    validate_chain_draft,
)
from petraterrium.simulation.registry_store import SimulationRegistryStore


def valid_draft() -> ChainDraft:
    return ChainDraft(
        id="evening_choice",
        name="Evening choice",
        source_text="Choose home or outside with supplied evidence",
        entry_node="decision",
        nodes=[
            ChainNodeDraft(id="decision", label="Decision", origin="manual_edit"),
            ChainNodeDraft(id="home", label="Stay home", terminal=True, origin="manual_edit"),
            ChainNodeDraft(id="outside", label="Go out", terminal=True, origin="manual_edit"),
        ],
        transitions=[
            ChainTransitionDraft(
                id="choose_home",
                from_node="decision",
                to_node="home",
                probability=0.6,
                condition="weekend",
                origin="manual_edit",
            ),
            ChainTransitionDraft(
                id="choose_outside",
                from_node="decision",
                to_node="outside",
                probability=0.4,
                condition="weekend",
                origin="manual_edit",
            ),
        ],
    )


def test_plain_language_choice_keeps_unknown_values_unresolved():
    draft = deterministic_proposal(
        ChainProposalRequest(text="An agent decides whether to stay at home or go out")
    )

    assert {node.id for node in draft.nodes} == {"decision", "stay_at_home", "go_out"}
    assert {(edge.from_node, edge.to_node) for edge in draft.transitions} == {
        ("decision", "stay_at_home"),
        ("decision", "go_out"),
    }
    assert all(edge.probability is None for edge in draft.transitions)
    assert all(edge.condition is None for edge in draft.transitions)
    result = validate_chain_draft(draft)
    assert result.can_confirm is False
    assert result.missing_probabilities == ["decision_to_go_out", "decision_to_stay_at_home"]
    assert result.missing_conditions == ["decision_to_go_out", "decision_to_stay_at_home"]
    assert result.dead_ends == ["go_out", "stay_at_home"]


def test_explicit_arrow_syntax_can_produce_a_complete_draft():
    request = ChainProposalRequest(
        text=(
            "Decision -> Stay home [terminal] | 60% if weekend; "
            "Decision -> Go out [terminal] | 40% if weekend"
        ),
        chain_id="weekend_choice",
    )

    draft = deterministic_proposal(request)
    result = validate_chain_draft(draft)

    assert result.can_confirm is True
    assert result.terminal_states == ["go_out", "stay_home"]
    assert result.outgoing_totals[0].known_total == 1
    assert result.outgoing_totals[0].sums_to_one is True


def test_model_proposal_uses_selected_source_and_drops_unsupported_probability():
    captured = {}

    class Provider:
        def generate_structured(
            self,
            user_prompt,
            response_format,
            *,
            system_prompt,
            prompt_version,
        ):
            captured.update(
                {
                    "user_prompt": user_prompt,
                    "system_prompt": system_prompt,
                    "prompt_version": prompt_version,
                }
            )
            output = response_format.model_validate(
                {
                    "name": "Friday choice",
                    "entry_label": "Decision",
                    "nodes": [
                        {
                            "label": "Decision",
                            "terminal": False,
                            "source_excerpt": "decides",
                        },
                        {
                            "label": "Home",
                            "terminal": False,
                            "source_excerpt": "stay home",
                        },
                        {
                            "label": "Outside",
                            "terminal": False,
                            "source_excerpt": "go outside",
                        },
                    ],
                    "transitions": [
                        {
                            "from_label": "Decision",
                            "to_label": "Home",
                            "probability": 0.5,
                            "condition": "Friday",
                            "source_excerpt": "On Friday an agent decides whether to stay home",
                        },
                        {
                            "from_label": "Decision",
                            "to_label": "Outside",
                            "probability": 0.5,
                            "condition": "Friday",
                            "source_excerpt": (
                                "On Friday an agent decides whether to stay home or go outside"
                            ),
                        },
                    ],
                }
            )
            return AIGeneration(
                output=output,
                provenance=AISourceProvenance(
                    source="openai_cli",
                    source_label="OpenAI CLI",
                    model="test-cli-model",
                    generated_at="2026-10-27T12:00:00Z",
                    prompt_version=prompt_version,
                    input_tokens=11,
                    output_tokens=7,
                ),
            )

    result = propose_chain(
        ChainProposalRequest(text="On Friday an agent decides whether to stay home or go outside"),
        ai_provider=Provider(),
    )

    assert result.audit.provider == "openai_cli"
    assert result.audit.model == "test-cli-model"
    assert "2026-10-27T12:00:00+00:00 via OpenAI CLI" in result.audit.message
    assert result.draft.proposal_audit == result.audit
    assert all(edge.origin == "model_proposal" for edge in result.draft.transitions)
    assert all(edge.probability is None for edge in result.draft.transitions)
    assert all(edge.condition == "Friday" for edge in result.draft.transitions)
    assert captured["prompt_version"] == "markov-chain-proposal-v1"


def test_model_proposal_requires_the_selected_source():
    with pytest.raises(AIProviderError, match="no fallback was attempted"):
        propose_chain(ChainProposalRequest(text="An agent chooses home or outside"))


def test_validation_reports_probability_total_dead_end_and_nonterminating_loop():
    draft = ChainDraft(
        id="loop",
        name="Loop",
        source_text="A to B to A with an unreachable end",
        entry_node="a",
        nodes=[
            ChainNodeDraft(id="a", label="A", origin="manual_edit"),
            ChainNodeDraft(id="b", label="B", origin="manual_edit"),
            ChainNodeDraft(id="end", label="End", terminal=True, origin="manual_edit"),
            ChainNodeDraft(id="stuck", label="Stuck", origin="manual_edit"),
        ],
        transitions=[
            ChainTransitionDraft(
                id="a_b",
                from_node="a",
                to_node="b",
                probability=0.8,
                condition="always",
                origin="manual_edit",
            ),
            ChainTransitionDraft(
                id="b_a",
                from_node="b",
                to_node="a",
                probability=1,
                condition="always",
                origin="manual_edit",
            ),
        ],
    )

    result = validate_chain_draft(draft)

    assert result.can_confirm is False
    assert result.dead_ends == ["stuck"]
    assert result.non_terminating_loops == [["a", "b"]]
    assert result.unreachable_nodes == ["end", "stuck"]
    assert any(issue.code == "outgoing_total" for issue in result.issues)


def test_out_of_range_probability_is_reported_in_the_draft_validation():
    draft = valid_draft()
    draft = draft.model_copy(
        update={
            "transitions": [
                draft.transitions[0].model_copy(update={"probability": 1.2}),
                draft.transitions[1],
            ]
        }
    )

    result = validate_chain_draft(draft)

    assert result.can_confirm is False
    assert any(issue.code == "probability_range" for issue in result.issues)


def test_confirmation_requires_validity_and_explicit_user_action():
    draft = valid_draft()

    try:
        confirmed_chain_from_draft(draft, False)
    except ValueError as error:
        assert "Explicit user confirmation" in str(error)
    else:
        raise AssertionError("Unconfirmed draft was accepted")

    confirmed = confirmed_chain_from_draft(draft, True)
    assert confirmed.entry_node == "decision"
    assert confirmed.transitions[0].probability == 0.6

    broken = draft.model_copy(
        update={
            "transitions": [
                draft.transitions[0].model_copy(update={"probability": None}),
                draft.transitions[1],
            ]
        }
    )
    try:
        confirmed_chain_from_draft(broken, True)
    except ChainConfirmationError as error:
        assert error.validation.missing_probabilities == ["choose_home"]
    else:
        raise AssertionError("Invalid draft was accepted")


def test_router_persists_only_through_confirm_endpoint():
    persisted = []
    application = FastAPI()
    application.include_router(
        create_markov_builder_router(lambda chain: persisted.append(chain) or f"dsl:{chain.id}")
    )
    client = TestClient(application)
    draft = valid_draft()

    validation = client.post("/markov-builder/validation", json=draft.model_dump(mode="json"))
    assert validation.status_code == 200
    assert validation.json()["can_confirm"] is True
    assert persisted == []

    confirmation = client.post(
        "/markov-builder/confirm",
        json={"draft": draft.model_dump(mode="json"), "user_confirmed": True},
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["persisted"] is True
    assert confirmation.json()["persistence_id"] == "dsl:evening_choice"
    assert len(persisted) == 1


def test_application_exposes_the_markov_builder_workflow(tmp_path):
    application = create_app(atlas_path=tmp_path / "atlas.sqlite3")

    with TestClient(application) as client:
        proposal = client.post(
            "/markov-builder/proposals",
            json={
                "text": (
                    "Decision -> Stay home [terminal] | 60% if weekend; "
                    "Decision -> Go out [terminal] | 40% if weekend"
                ),
                "chain_id": "weekend_choice",
                "use_llm": False,
            },
        )

    assert proposal.status_code == 200
    payload = proposal.json()
    assert payload["draft"]["id"] == "weekend_choice"
    assert payload["validation"]["can_confirm"] is True


def test_confirmed_builder_chain_stays_blocked_until_evidence_is_attached(tmp_path):
    registry = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        simulation_registry_store=registry,
    )

    with TestClient(application) as client:
        proposal = client.post(
            "/markov-builder/proposals",
            json={
                "text": (
                    "Decision -> Stay home [terminal] | 60% if weekend; "
                    "Decision -> Go out [terminal] | 40% if weekend"
                ),
                "chain_id": "weekend_choice",
                "use_llm": False,
            },
        ).json()
        confirmation = client.post(
            "/markov-builder/confirm",
            json={"draft": proposal["draft"], "user_confirmed": True},
        )

    assert confirmation.status_code == 200
    saved = registry.decision_trees()
    saved_tree = next(item for item in saved.trees if item.id == "weekend_choice")
    saved_module = next(
        item for item in saved.modules if item.id == saved_tree.root_module_id
    )
    assert saved_tree.status == "blocked"
    assert saved_module.status == "blocked"
    assert saved_module.source == (
        "User-confirmed natural-language proposal · deterministic parser · evidence pending"
    )
    assert saved_tree.proposal_audit.origin == "deterministic"
    assert saved_tree.proposal_audit.source_id == "deterministic-parser"
    assert saved_tree.proposal_audit.source_label == "Deterministic parser"
    assert saved_tree.proposal_audit.prompt_version == "markov-chain-proposal-v1"
    assert saved_module.proposal_audit == saved_tree.proposal_audit
    assert all(edge.decision_id is None for edge in saved_module.edges)
    assert all("evidence pending" in edge.label for edge in saved_module.edges)


def test_confirmed_builder_chain_persists_full_selected_ai_provenance(tmp_path):
    registry = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    audit = ProposalAudit(
        provider="openai_cli",
        model="gpt-test",
        prompt_version="markov-chain-proposal-v7",
        generated_at="2026-10-27T12:00:00Z",
        input_tokens=41,
        output_tokens=23,
        estimated_cost_usd=0.0042,
        message="Unsaved proposal generated via OpenAI CLI.",
    )
    chain = confirmed_chain_from_draft(
        valid_draft().model_copy(update={"proposal_audit": audit}),
        user_confirmed=True,
    )

    registry.save_confirmed_chain(chain)

    saved = SimulationRegistryStore(registry.path).decision_trees()
    expected = {
        "origin": "ai",
        "source_id": "openai_cli",
        "source_label": "OpenAI CLI",
        "model": "gpt-test",
        "generated_at": "2026-10-27T12:00:00Z",
        "prompt_version": "markov-chain-proposal-v7",
        "input_tokens": 41,
        "output_tokens": 23,
        "estimated_cost_usd": 0.0042,
        "message": "Unsaved proposal generated via OpenAI CLI.",
    }
    assert saved.trees[0].proposal_audit.model_dump(mode="json") == expected
    assert saved.modules[0].proposal_audit.model_dump(mode="json") == expected


def test_confirmed_manual_chain_is_labelled_without_ai_provenance(tmp_path):
    registry = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    chain = confirmed_chain_from_draft(valid_draft(), user_confirmed=True)

    registry.save_confirmed_chain(chain)

    saved = registry.decision_trees()
    assert saved.trees[0].proposal_audit.origin == "manual"
    assert saved.trees[0].proposal_audit.source_label == "Manual confirmation"
    assert saved.modules[0].proposal_audit == saved.trees[0].proposal_audit
