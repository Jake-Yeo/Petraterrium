import pytest
from pydantic import ValidationError

from petraterrium.simulation.agent_types import (
    AgentTypeDefinition,
    AgentTypeMember,
    AgentTypeOverride,
    AgentTypeProposalAudit,
    AgentTypeProposalDraft,
    AgentTypeResolutionError,
    ConfirmAgentTypeProposalRequest,
    confirm_agent_type_proposal,
    resolve_agent_types,
    validate_agent_types,
)


def member(identity: str, definition: str) -> AgentTypeMember:
    return AgentTypeMember(
        id=identity,
        name=identity.replace("_", " ").title(),
        definition=definition,
    )


def family_type() -> AgentTypeDefinition:
    return AgentTypeDefinition(
        id="family_man",
        name="FamilyMan",
        traits=[member("family_role", "parent_or_partner")],
        routines=[member("family_dinner", "weekday evening at home")],
        decisions=[member("family_evening", "family_evening_tree")],
    )


def business_type() -> AgentTypeDefinition:
    return AgentTypeDefinition(
        id="business_agent",
        name="BusinessAgent",
        parent_ids=["family_man"],
        traits=[member("employment_role", "business_owner")],
        routines=[member("pub_meeting", "Friday evening at a pub")],
        decisions=[member("business_meeting", "pub_business_meeting_tree")],
    )


def worker_type() -> AgentTypeDefinition:
    return AgentTypeDefinition(
        id="worker_agent",
        name="WorkerAgent",
        parent_ids=["family_man"],
        traits=[member("employment_role", "employee")],
        routines=[member("work_shift", "weekday daytime at work")],
        decisions=[member("family_dinner_choice", "family_dinner_tree")],
    )


def test_business_and_worker_inherit_family_capabilities_with_named_sources():
    resolved = resolve_agent_types([family_type(), business_type(), worker_type()])

    business = resolved.by_id("business_agent")
    worker = resolved.by_id("worker_agent")

    assert {(item.member.id, item.source_type_id) for item in business.routines} == {
        ("family_dinner", "family_man"),
        ("pub_meeting", "business_agent"),
    }
    assert {(item.member.id, item.source_type_id) for item in business.decisions} == {
        ("business_meeting", "business_agent"),
        ("family_evening", "family_man"),
    }
    assert {(item.member.id, item.source_type_id) for item in worker.routines} == {
        ("family_dinner", "family_man"),
        ("work_shift", "worker_agent"),
    }
    assert any(item.inherited for item in business.routines)
    assert any(item.inherited for item in worker.decisions)


def test_child_definition_wins_and_records_the_parent_it_overrides():
    parent = AgentTypeDefinition(
        id="person",
        name="Person",
        routines=[member("evening", "stay home")],
    )
    child = AgentTypeDefinition(
        id="night_worker",
        name="Night Worker",
        parent_ids=["person"],
        routines=[member("evening", "work night shift")],
    )

    resolved = resolve_agent_types([parent, child]).by_id("night_worker")

    assert resolved.routines[0].member.definition == "work night shift"
    assert resolved.routines[0].source_type_id == "night_worker"
    assert resolved.routines[0].overridden_source_type_ids == ["person"]


def test_parallel_parent_conflict_requires_an_explicit_override():
    office = AgentTypeDefinition(
        id="office_worker",
        name="Office Worker",
        routines=[member("lunch", "eat at office")],
    )
    remote = AgentTypeDefinition(
        id="remote_worker",
        name="Remote Worker",
        routines=[member("lunch", "eat at home")],
    )
    hybrid = AgentTypeDefinition(
        id="hybrid_worker",
        name="Hybrid Worker",
        parent_ids=["office_worker", "remote_worker"],
    )

    result = validate_agent_types([office, remote, hybrid])

    assert result.valid is False
    assert result.conflicts[0].type_id == "hybrid_worker"
    assert result.conflicts[0].member_id == "lunch"
    assert result.conflicts[0].source_type_ids == ["office_worker", "remote_worker"]
    assert any(issue.code == "ambiguous_inherited_member" for issue in result.issues)
    with pytest.raises(AgentTypeResolutionError, match="explicit override"):
        resolve_agent_types([office, remote, hybrid])


def test_explicit_override_selects_one_parallel_parent():
    office = AgentTypeDefinition(
        id="office_worker",
        name="Office Worker",
        routines=[member("lunch", "eat at office")],
    )
    remote = AgentTypeDefinition(
        id="remote_worker",
        name="Remote Worker",
        routines=[member("lunch", "eat at home")],
    )
    hybrid = AgentTypeDefinition(
        id="hybrid_worker",
        name="Hybrid Worker",
        parent_ids=["office_worker", "remote_worker"],
        overrides=[
            AgentTypeOverride(
                member_kind="routine",
                member_id="lunch",
                source_type_id="remote_worker",
            )
        ],
    )

    resolved = resolve_agent_types([office, remote, hybrid]).by_id("hybrid_worker")

    assert resolved.routines[0].member.definition == "eat at home"
    assert resolved.routines[0].source_type_id == "remote_worker"
    assert resolved.routines[0].overridden_source_type_ids == ["office_worker"]
    assert resolved.routines[0].explicit_override is True


def test_more_specific_parent_wins_before_an_override_is_needed():
    person = AgentTypeDefinition(
        id="person",
        name="Person",
        traits=[member("pace", "ordinary")],
    )
    athlete = AgentTypeDefinition(
        id="athlete",
        name="Athlete",
        parent_ids=["person"],
        traits=[member("pace", "fast")],
    )
    student_athlete = AgentTypeDefinition(
        id="student_athlete",
        name="Student Athlete",
        parent_ids=["person", "athlete"],
    )

    resolved = resolve_agent_types([person, athlete, student_athlete]).by_id(
        "student_athlete"
    )

    assert resolved.traits[0].source_type_id == "athlete"
    assert resolved.traits[0].member.definition == "fast"
    assert resolved.traits[0].explicit_override is True
    assert resolved.traits[0].overridden_source_type_ids == ["person"]


def test_unknown_parent_cycles_duplicates_and_bad_overrides_are_invalid():
    unknown = AgentTypeDefinition(id="child", name="Child", parent_ids=["missing"])
    assert any(
        issue.code == "unknown_parent" for issue in validate_agent_types([unknown]).issues
    )

    first = AgentTypeDefinition(id="first", name="First", parent_ids=["second"])
    second = AgentTypeDefinition(id="second", name="Second", parent_ids=["first"])
    assert any(
        issue.code == "inheritance_cycle"
        for issue in validate_agent_types([first, second]).issues
    )

    duplicate = AgentTypeDefinition(id="first", name="Duplicate")
    assert any(
        issue.code == "duplicate_type_id"
        for issue in validate_agent_types([first, duplicate]).issues
    )

    bad_override = AgentTypeDefinition(
        id="bad",
        name="Bad",
        overrides=[
            AgentTypeOverride(
                member_kind="trait",
                member_id="missing",
                source_type_id="stranger",
            )
        ],
    )
    assert any(
        issue.code == "invalid_override_source"
        for issue in validate_agent_types([bad_override]).issues
    )


def test_member_ids_are_unique_within_a_type_and_inputs_are_strict():
    with pytest.raises(ValidationError, match="unique"):
        AgentTypeDefinition(
            id="duplicate_members",
            name="Duplicate members",
            traits=[member("role", "one"), member("role", "two")],
        )
    with pytest.raises(ValidationError):
        AgentTypeDefinition.model_validate(
            {"id": "person", "name": "Person", "unexpected": True}
        )


def test_proposal_requires_human_confirmation_and_valid_inheritance():
    draft = AgentTypeProposalDraft(
        id="work_and_family",
        prompt="Create business and worker types with their shared family behavior",
        imported_feature_ids=["occupation", "household_composition"],
        types=[family_type(), business_type(), worker_type()],
        audit=AgentTypeProposalAudit(
            provider="openai_cli",
            model="gpt-5",
            generated_at="2026-10-27T12:00:00Z",
            prompt_version="agent-types-v1",
        ),
    )

    with pytest.raises(ValueError, match="confirmation"):
        confirm_agent_type_proposal(draft, user_confirmed=False)
    with pytest.raises(ValidationError):
        ConfirmAgentTypeProposalRequest.model_validate(
            {"draft": draft.model_dump(), "user_confirmed": False}
        )

    confirmed = confirm_agent_type_proposal(draft, user_confirmed=True)

    assert confirmed.id == "work_and_family"
    assert confirmed.confirmed is True
    assert confirmed.audit.provider == "openai_cli"
    assert confirmed.resolved.by_id("business_agent").parent_ids == ["family_man"]

    invalid = draft.model_copy(
        update={
            "types": [
                AgentTypeDefinition(
                    id="orphan", name="Orphan", parent_ids=["missing_parent"]
                )
            ]
        }
    )
    with pytest.raises(AgentTypeResolutionError, match="Unknown parent"):
        confirm_agent_type_proposal(invalid, user_confirmed=True)
