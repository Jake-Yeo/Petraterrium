from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.main import create_app
from petraterrium.markov_builder import (
    ChainConfirmationError,
    ChainDraft,
    ChainNodeDraft,
    ChainProposalRequest,
    ChainTransitionDraft,
    confirmed_chain_from_draft,
    create_markov_builder_router,
    deterministic_proposal,
    propose_chain,
    validate_chain_draft,
)


def valid_draft() -> ChainDraft:
    return ChainDraft(
        id="evening_choice",
        name="Evening choice",
        source_text="Choose home or outside with supplied evidence",
        entry_node="decision",
        nodes=[
            ChainNodeDraft(
                id="decision", label="Decision", origin="manual_edit"
            ),
            ChainNodeDraft(
                id="home", label="Stay home", terminal=True, origin="manual_edit"
            ),
            ChainNodeDraft(
                id="outside", label="Go out", terminal=True, origin="manual_edit"
            ),
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


def test_model_proposal_uses_gateway_and_drops_unsupported_probability():
    captured = {}

    class Usage:
        input_tokens = 11
        output_tokens = 7

    class Responses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            output = kwargs["text_format"].model_validate(
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
            return type("Response", (), {"output_parsed": output, "usage": Usage()})()

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = Responses()

    result = propose_chain(
        ChainProposalRequest(
            text="On Friday an agent decides whether to stay home or go outside"
        ),
        client_factory=Client,
    )

    assert result.audit.provider == "openai"
    assert all(edge.origin == "model_proposal" for edge in result.draft.transitions)
    assert all(edge.probability is None for edge in result.draft.transitions)
    assert all(edge.condition == "Friday" for edge in result.draft.transitions)
    assert captured["store"] is False
    assert captured["model"]


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
        create_markov_builder_router(
            lambda chain: persisted.append(chain) or f"dsl:{chain.id}"
        )
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
