import pytest
from pydantic import ValidationError

from petraterrium.simulation.agent_types import (
    AgentTypeDefinition,
    AgentTypeMember,
    AgentTypeOverride,
)
from petraterrium.simulation.routines import (
    RoutineDefinition,
    RoutineEvidence,
    RoutineRegistryDefinition,
    RoutineResolutionError,
    RoutineSchedule,
    RoutineStep,
    illustrative_routine_registry,
    resolve_routines,
    validate_routines,
)


def routine_member(identity: str, definition: str) -> AgentTypeMember:
    return AgentTypeMember(
        id=identity,
        name=identity.replace("_", " ").title(),
        definition=definition,
    )


def schedule(
    *,
    days: list[str] | None = None,
    start_time: str = "18:00",
    end_time: str = "20:00",
    places: list[str] | None = None,
    roles: list[str] | None = None,
) -> RoutineSchedule:
    return RoutineSchedule(
        days=days or ["friday"],
        start_time=start_time,
        end_time=end_time,
        place_ids=places or ["home"],
        role_ids=roles or ["household_member"],
    )


def routine(
    owner: str,
    identity: str,
    *,
    activity: str,
    decision_module_id: str | None = None,
) -> RoutineDefinition:
    return RoutineDefinition(
        id=identity,
        name=identity.replace("_", " ").title(),
        agent_type_id=owner,
        description=f"{activity} schedule",
        evidence=RoutineEvidence(
            status="illustrative",
            note="Test fixture only; not measured schedule evidence.",
        ),
        steps=[
            RoutineStep(
                id=activity.replace(" ", "_"),
                name=activity.title(),
                activity=activity,
                schedule=schedule(),
                decision_tree_module_id=decision_module_id,
            )
        ],
    )


def test_illustrative_examples_resolve_different_typed_routines_without_claiming_measurement():
    registry = illustrative_routine_registry()

    validation = validate_routines(
        registry,
        known_decision_tree_module_ids={
            "family_dinner_choice",
            "pub_business_meeting",
            "work_shift_choice",
        },
    )
    resolved = resolve_routines(
        registry,
        known_decision_tree_module_ids={
            "family_dinner_choice",
            "pub_business_meeting",
            "work_shift_choice",
        },
    )

    assert validation.valid is True
    business = resolved.by_agent_type_id("business_agent")
    worker = resolved.by_agent_type_id("worker_agent")
    assert {item.routine.id for item in business.routines} == {
        "business_pub_meeting",
        "family_dinner",
    }
    assert {item.routine.id for item in worker.routines} == {
        "family_dinner",
        "worker_shift",
    }

    pub = next(
        item for item in business.routines if item.routine.id == "business_pub_meeting"
    )
    assert pub.inherited is False
    assert pub.routine.evidence.status == "illustrative"
    assert pub.routine.evidence.source_title is None
    assert pub.routine.steps[0].schedule.days == ["friday"]
    assert pub.routine.steps[0].schedule.place_ids == ["pub"]
    assert pub.routine.steps[0].schedule.role_ids == ["business_agent"]
    assert pub.routine.steps[0].decision_tree_module_id == "pub_business_meeting"

    dinner = next(
        item for item in worker.routines if item.routine.id == "family_dinner"
    )
    assert dinner.inherited is True
    assert dinner.source_type_id == "family_man"
    assert dinner.routine.steps[0].decision_tree_module_id == "family_dinner_choice"


def test_direct_child_routine_overrides_parallel_parent_definitions_and_keeps_sources():
    home = AgentTypeDefinition(
        id="home_member",
        name="Home Member",
        routines=[routine_member("evening", "home evening")],
    )
    worker = AgentTypeDefinition(
        id="worker",
        name="Worker",
        routines=[routine_member("evening", "work evening")],
    )
    night_worker = AgentTypeDefinition(
        id="night_worker",
        name="Night Worker",
        parent_ids=["home_member", "worker"],
        routines=[routine_member("evening", "night shift")],
    )
    registry = RoutineRegistryDefinition(
        agent_types=[home, worker, night_worker],
        routines=[
            routine("home_member", "evening", activity="stay home"),
            routine("worker", "evening", activity="finish work"),
            routine("night_worker", "evening", activity="night shift"),
        ],
    )

    resolved = resolve_routines(registry).by_agent_type_id("night_worker")

    assert len(resolved.routines) == 1
    result = resolved.routines[0]
    assert result.source_type_id == "night_worker"
    assert result.explicit_override is True
    assert result.overridden_source_type_ids == ["home_member", "worker"]
    assert result.routine.steps[0].activity == "night shift"


def test_parallel_parent_conflict_requires_an_explicit_source_override():
    home = AgentTypeDefinition(
        id="home_member",
        name="Home Member",
        routines=[routine_member("evening", "home evening")],
    )
    worker = AgentTypeDefinition(
        id="worker",
        name="Worker",
        routines=[routine_member("evening", "work evening")],
    )
    hybrid = AgentTypeDefinition(
        id="hybrid",
        name="Hybrid",
        parent_ids=["home_member", "worker"],
    )
    routines = [
        routine("home_member", "evening", activity="stay home"),
        routine("worker", "evening", activity="finish work"),
    ]
    ambiguous = RoutineRegistryDefinition(
        agent_types=[home, worker, hybrid],
        routines=routines,
    )

    validation = validate_routines(ambiguous)

    assert validation.valid is False
    assert any(issue.code == "ambiguous_inherited_member" for issue in validation.issues)
    with pytest.raises(RoutineResolutionError, match="explicit override"):
        resolve_routines(ambiguous)

    selected = hybrid.model_copy(
        update={
            "overrides": [
                AgentTypeOverride(
                    member_kind="routine",
                    member_id="evening",
                    source_type_id="home_member",
                )
            ]
        }
    )
    resolved = resolve_routines(
        RoutineRegistryDefinition(
            agent_types=[home, worker, selected],
            routines=routines,
        )
    ).by_agent_type_id("hybrid")

    assert resolved.routines[0].source_type_id == "home_member"
    assert resolved.routines[0].explicit_override is True
    assert resolved.routines[0].overridden_source_type_ids == ["worker"]


def test_validation_rejects_missing_typed_routines_or_decision_modules():
    person = AgentTypeDefinition(
        id="person",
        name="Person",
        routines=[routine_member("evening", "evening schedule")],
    )
    missing_definition = RoutineRegistryDefinition(agent_types=[person], routines=[])

    missing_validation = validate_routines(missing_definition)

    assert any(
        issue.code == "missing_routine_definition"
        for issue in missing_validation.issues
    )

    typed = RoutineRegistryDefinition(
        agent_types=[person],
        routines=[
            routine(
                "person",
                "evening",
                activity="choose evening",
                decision_module_id="evening_choice",
            )
        ],
    )
    module_validation = validate_routines(
        typed,
        known_decision_tree_module_ids={"other_module"},
    )

    assert any(
        issue.code == "unknown_decision_tree_module"
        and issue.path.endswith("decision_tree_module_id")
        for issue in module_validation.issues
    )


def test_schedule_and_evidence_models_reject_ambiguous_or_false_provenance():
    with pytest.raises(ValidationError, match="end_time"):
        RoutineSchedule(
            days=["monday"],
            start_time="18:00",
            end_time="17:00",
            place_ids=["home"],
            role_ids=["resident"],
        )
    with pytest.raises(ValidationError, match="Measured routines require"):
        RoutineEvidence(status="measured")
    with pytest.raises(ValidationError, match="unique"):
        RoutineDefinition(
            id="duplicate_steps",
            name="Duplicate steps",
            agent_type_id="person",
            evidence=RoutineEvidence(status="unknown"),
            steps=[
                RoutineStep(
                    id="same",
                    name="First",
                    activity="first",
                    schedule=schedule(),
                ),
                RoutineStep(
                    id="same",
                    name="Second",
                    activity="second",
                    schedule=schedule(),
                ),
            ],
        )


def test_overnight_schedule_requires_an_explicit_next_day_boundary():
    overnight = RoutineSchedule(
        days=["friday"],
        start_time="22:00",
        end_time="01:00",
        ends_next_day=True,
        place_ids=["work"],
        role_ids=["night_worker"],
    )

    assert overnight.ends_next_day is True
    assert overnight.duration_minutes == 180
