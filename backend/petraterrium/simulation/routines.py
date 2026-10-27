from collections import Counter
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_types import (
    AgentTypeDefinition,
    AgentTypeMember,
    resolve_agent_types,
    validate_agent_types,
)

IdentifierPattern = r"^[a-z][a-z0-9_-]*$"
TimePattern = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"
DayOfWeek = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
RoutineEvidenceStatus = Literal["measured", "user_defined", "illustrative", "unknown"]


class RoutineModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class RoutineSchedule(RoutineModel):
    days: list[DayOfWeek] = Field(min_length=1)
    start_time: str = Field(pattern=TimePattern)
    end_time: str = Field(pattern=TimePattern)
    ends_next_day: bool = False
    place_ids: list[str] = Field(min_length=1)
    role_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_schedule(self):
        for label, values in (
            ("days", self.days),
            ("place_ids", self.place_ids),
            ("role_ids", self.role_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"Routine schedule {label} must be unique")
        start = _minute_of_day(self.start_time)
        end = _minute_of_day(self.end_time)
        if start == end:
            raise ValueError("Routine end_time must differ from start_time")
        if self.ends_next_day and end >= start:
            raise ValueError(
                "A next-day routine end_time must be earlier than start_time"
            )
        if not self.ends_next_day and end <= start:
            raise ValueError(
                "Routine end_time must be later than start_time or ends_next_day must be true"
            )
        return self

    @property
    def duration_minutes(self) -> int:
        start = _minute_of_day(self.start_time)
        end = _minute_of_day(self.end_time)
        if self.ends_next_day:
            end += 24 * 60
        return end - start


class RoutineEvidence(RoutineModel):
    status: RoutineEvidenceStatus
    source_title: str | None = Field(default=None, min_length=1)
    source_date: str | None = Field(default=None, min_length=1)
    source_uri: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def measured_provenance(self):
        if self.status == "measured" and (
            self.source_title is None or self.source_date is None
        ):
            raise ValueError(
                "Measured routines require source_title and source_date provenance"
            )
        return self


class RoutineStep(RoutineModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1, max_length=160)
    activity: str = Field(min_length=1)
    schedule: RoutineSchedule
    decision_tree_module_id: str | None = Field(
        default=None,
        pattern=IdentifierPattern,
    )


class RoutineDefinition(RoutineModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1, max_length=160)
    agent_type_id: str = Field(pattern=IdentifierPattern)
    description: str | None = Field(default=None, min_length=1)
    evidence: RoutineEvidence
    steps: list[RoutineStep] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_steps(self):
        step_ids = [step.id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("Routine step ids must be unique")
        return self


class RoutineRegistryDefinition(RoutineModel):
    agent_types: list[AgentTypeDefinition] = Field(min_length=1)
    routines: list[RoutineDefinition] = Field(default_factory=list)


class RoutineValidationIssue(RoutineModel):
    code: str
    path: str
    message: str


class RoutineValidationResult(RoutineModel):
    valid: bool
    issues: list[RoutineValidationIssue]


class ResolvedRoutine(RoutineModel):
    routine: RoutineDefinition
    source_type_id: str
    inherited: bool
    explicit_override: bool
    overridden_source_type_ids: list[str] = Field(default_factory=list)


class ResolvedAgentRoutines(RoutineModel):
    agent_type_id: str
    agent_type_name: str
    routines: list[ResolvedRoutine]


class ResolvedRoutineRegistry(RoutineModel):
    agent_types: list[ResolvedAgentRoutines]

    def by_agent_type_id(self, agent_type_id: str) -> ResolvedAgentRoutines:
        for agent_type in self.agent_types:
            if agent_type.agent_type_id == agent_type_id:
                return agent_type
        raise KeyError(agent_type_id)


class RoutineResolutionError(ValueError):
    def __init__(self, validation: RoutineValidationResult):
        self.validation = validation
        message = "; ".join(issue.message for issue in validation.issues)
        super().__init__(message or "Routine registry could not be resolved")


def _minute_of_day(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _issue(code: str, path: str, message: str) -> RoutineValidationIssue:
    return RoutineValidationIssue(code=code, path=path, message=message)


def validate_routines(
    registry: RoutineRegistryDefinition,
    known_decision_tree_module_ids: Iterable[str] | None = None,
) -> RoutineValidationResult:
    issues: list[RoutineValidationIssue] = []
    agent_validation = validate_agent_types(registry.agent_types)
    issues.extend(
        _issue(issue.code, f"agent_types.{issue.path}", issue.message)
        for issue in agent_validation.issues
    )
    types_by_id = {agent_type.id: agent_type for agent_type in registry.agent_types}
    declared = {
        (agent_type.id, member.id)
        for agent_type in registry.agent_types
        for member in agent_type.routines
    }
    definition_keys = [
        (routine.agent_type_id, routine.id) for routine in registry.routines
    ]
    counts = Counter(definition_keys)
    for key, count in sorted(counts.items()):
        if count > 1:
            issues.append(
                _issue(
                    "duplicate_routine_definition",
                    f"routines.{key[0]}.{key[1]}",
                    f"Routine {key[0]}.{key[1]} has {count} typed definitions",
                )
            )
    definition_key_set = set(definition_keys)
    for agent_type_id, routine_id in sorted(declared - definition_key_set):
        issues.append(
            _issue(
                "missing_routine_definition",
                f"agent_types.{agent_type_id}.routines.{routine_id}",
                f"Routine member {agent_type_id}.{routine_id} has no typed schedule definition",
            )
        )
    for index, routine in enumerate(registry.routines):
        key = (routine.agent_type_id, routine.id)
        path = f"routines.{index}"
        if routine.agent_type_id not in types_by_id:
            issues.append(
                _issue(
                    "unknown_routine_agent_type",
                    f"{path}.agent_type_id",
                    f"Routine {routine.id} references unknown agent type {routine.agent_type_id}",
                )
            )
        elif key not in declared:
            issues.append(
                _issue(
                    "undeclared_routine_definition",
                    path,
                    (
                        f"Routine {routine.agent_type_id}.{routine.id} is not declared "
                        "by that agent type"
                    ),
                )
            )
    if known_decision_tree_module_ids is not None:
        known_modules = set(known_decision_tree_module_ids)
        for routine_index, routine in enumerate(registry.routines):
            for step_index, step in enumerate(routine.steps):
                module_id = step.decision_tree_module_id
                if module_id is not None and module_id not in known_modules:
                    issues.append(
                        _issue(
                            "unknown_decision_tree_module",
                            (
                                f"routines.{routine_index}.steps.{step_index}."
                                "decision_tree_module_id"
                            ),
                            (
                                f"Routine step {routine.id}.{step.id} calls missing "
                                f"decision tree module {module_id}"
                            ),
                        )
                    )
    return RoutineValidationResult(valid=not issues, issues=issues)


def resolve_routines(
    registry: RoutineRegistryDefinition,
    known_decision_tree_module_ids: Iterable[str] | None = None,
) -> ResolvedRoutineRegistry:
    validation = validate_routines(registry, known_decision_tree_module_ids)
    if not validation.valid:
        raise RoutineResolutionError(validation)
    resolved_types = resolve_agent_types(registry.agent_types)
    definitions = {
        (routine.agent_type_id, routine.id): routine for routine in registry.routines
    }
    results: list[ResolvedAgentRoutines] = []
    for agent_type in resolved_types.types:
        resolved_routines = [
            ResolvedRoutine(
                routine=definitions[(member.source_type_id, member.member.id)],
                source_type_id=member.source_type_id,
                inherited=member.inherited,
                explicit_override=member.explicit_override,
                overridden_source_type_ids=member.overridden_source_type_ids,
            )
            for member in agent_type.routines
        ]
        results.append(
            ResolvedAgentRoutines(
                agent_type_id=agent_type.id,
                agent_type_name=agent_type.name,
                routines=resolved_routines,
            )
        )
    return ResolvedRoutineRegistry(agent_types=results)


def illustrative_routine_registry() -> RoutineRegistryDefinition:
    family_man = AgentTypeDefinition(
        id="family_man",
        name="FamilyMan",
        routines=[
            AgentTypeMember(
                id="family_dinner",
                name="Family dinner",
                definition="Illustrative weekday household dinner schedule",
            )
        ],
    )
    business_agent = AgentTypeDefinition(
        id="business_agent",
        name="BusinessAgent",
        parent_ids=["family_man"],
        routines=[
            AgentTypeMember(
                id="business_pub_meeting",
                name="Pub business meeting",
                definition="Illustrative Friday business meeting schedule",
            )
        ],
    )
    worker_agent = AgentTypeDefinition(
        id="worker_agent",
        name="WorkerAgent",
        parent_ids=["family_man"],
        routines=[
            AgentTypeMember(
                id="worker_shift",
                name="Worker shift",
                definition="Illustrative weekday work schedule",
            )
        ],
    )
    illustrative_evidence = RoutineEvidence(
        status="illustrative",
        note="Example only; attach observed schedule data before treating it as measured.",
    )
    family_dinner = RoutineDefinition(
        id="family_dinner",
        name="Family dinner",
        agent_type_id="family_man",
        description="An illustrative household dinner routine inherited by family roles.",
        evidence=illustrative_evidence,
        steps=[
            RoutineStep(
                id="family_dinner_at_home",
                name="Family dinner at home",
                activity="eat dinner with household members",
                schedule=RoutineSchedule(
                    days=["monday", "tuesday", "wednesday", "thursday", "friday"],
                    start_time="18:00",
                    end_time="19:00",
                    place_ids=["home"],
                    role_ids=["family_member"],
                ),
                decision_tree_module_id="family_dinner_choice",
            )
        ],
    )
    pub_meeting = RoutineDefinition(
        id="business_pub_meeting",
        name="Pub business meeting",
        agent_type_id="business_agent",
        description="An illustrative meeting schedule for a business role.",
        evidence=illustrative_evidence,
        steps=[
            RoutineStep(
                id="meet_at_pub",
                name="Meet at pub",
                activity="meet another business agent",
                schedule=RoutineSchedule(
                    days=["friday"],
                    start_time="18:30",
                    end_time="20:30",
                    place_ids=["pub"],
                    role_ids=["business_agent"],
                ),
                decision_tree_module_id="pub_business_meeting",
            )
        ],
    )
    worker_shift = RoutineDefinition(
        id="worker_shift",
        name="Worker shift",
        agent_type_id="worker_agent",
        description="An illustrative weekday work schedule for a worker role.",
        evidence=illustrative_evidence,
        steps=[
            RoutineStep(
                id="work_at_assigned_place",
                name="Work at assigned place",
                activity="complete scheduled work",
                schedule=RoutineSchedule(
                    days=["monday", "tuesday", "wednesday", "thursday", "friday"],
                    start_time="08:00",
                    end_time="16:00",
                    place_ids=["work"],
                    role_ids=["worker_agent"],
                ),
                decision_tree_module_id="work_shift_choice",
            )
        ],
    )
    return RoutineRegistryDefinition(
        agent_types=[family_man, business_agent, worker_agent],
        routines=[family_dinner, pub_meeting, worker_shift],
    )
