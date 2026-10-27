from collections import defaultdict
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .population_generation import HouseholdMemberSeed, InitialPopulationMaterialization


class AtlasTypeAssignmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


AgentTypeValue = str | float
AgentTypeId = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")]


class AtlasAgentTypeCondition(AtlasTypeAssignmentModel):
    field: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    operator: Literal["equals", "not_equals", "one_of", "at_least", "at_most", "between"]
    value: AgentTypeValue | None = None
    upper_value: AgentTypeValue | None = None
    values: list[AgentTypeValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operands(self) -> "AtlasAgentTypeCondition":
        if self.operator == "one_of":
            if not self.values:
                raise ValueError("one_of conditions require at least one value")
            if self.value is not None or self.upper_value is not None:
                raise ValueError("one_of conditions accept values only")
            return self
        if self.value is None:
            raise ValueError(f"{self.operator} conditions require a value")
        if self.values:
            raise ValueError(f"{self.operator} conditions do not accept values")
        if self.operator == "between":
            if self.upper_value is None:
                raise ValueError("between conditions require an upper value")
            try:
                lower = float(self.value)
                upper = float(self.upper_value)
            except (TypeError, ValueError) as error:
                raise ValueError("between values must be numeric") from error
            if lower > upper:
                raise ValueError("between lower value cannot exceed upper value")
        elif self.upper_value is not None:
            raise ValueError(f"{self.operator} conditions do not accept an upper value")
        if self.operator in {"at_least", "at_most"}:
            try:
                float(self.value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{self.operator} values must be numeric") from error
        return self


class AtlasAgentTypeRule(AtlasTypeAssignmentModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    agent_type_ids: list[AgentTypeId] = Field(min_length=1)
    conditions: list[AtlasAgentTypeCondition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_agent_type_ids(self) -> "AtlasAgentTypeRule":
        if len(set(self.agent_type_ids)) != len(self.agent_type_ids):
            raise ValueError("agent type IDs in a rule must be unique")
        return self


class AtlasAgentTypeAssignment(AtlasTypeAssignmentModel):
    status: Literal["confirmed"]
    fallback_agent_type_id: AgentTypeId
    rules: list[AtlasAgentTypeRule] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rule_ids(self) -> "AtlasAgentTypeAssignment":
        rule_ids = [rule.id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("agent type assignment rule IDs must be unique")
        return self


def validate_type_assignment(
    assignment: AtlasAgentTypeAssignment | None,
    supported_fields: set[str],
) -> None:
    if assignment is None:
        return
    unknown = sorted(
        {
            condition.field
            for rule in assignment.rules
            for condition in rule.conditions
            if condition.field not in supported_fields
        }
    )
    if unknown:
        raise ValueError(
            "Agent type rules reference unsupported Atlas fields: " + ", ".join(unknown)
        )


def assign_agent_types(
    assignment: AtlasAgentTypeAssignment | None,
    members: list[HouseholdMemberSeed],
) -> list[HouseholdMemberSeed]:
    if assignment is None:
        return members
    has_children = any(
        member.relationship_to_reference == "child" for member in members
    )
    assigned_members = []
    for member in members:
        context = {
            **member.traits,
            "age": member.age,
            "sex": member.sex,
            "relationship_to_reference": member.relationship_to_reference,
            "household_role": _household_role(member, has_children),
            "household_size": len(members),
        }
        matched = [
            agent_type_id
            for rule in assignment.rules
            if all(
                _condition_matches(context.get(condition.field), condition)
                for condition in rule.conditions
            )
            for agent_type_id in rule.agent_type_ids
        ]
        unique_types = list(dict.fromkeys(matched))
        assigned_members.append(
            member.model_copy(
                update={
                    "agent_types": unique_types or [assignment.fallback_agent_type_id]
                }
            )
        )
    return assigned_members


def agent_type_counts(result: InitialPopulationMaterialization) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for agent in result.population.agents:
        values = agent.traits.get("agent_types", [agent.role])
        for agent_type in values if isinstance(values, list) else [agent.role]:
            counts[str(agent_type)] += 1
    return dict(sorted(counts.items()))


def _household_role(member: HouseholdMemberSeed, has_children: bool) -> str:
    relationship = member.relationship_to_reference
    if relationship in {"self", "spouse"} and has_children:
        return "parent"
    if relationship == "spouse":
        return "partner"
    if relationship in {"child", "parent", "sibling"}:
        return relationship
    return "household_member"


def _condition_matches(
    sampled_value: Any,
    condition: AtlasAgentTypeCondition,
) -> bool:
    if sampled_value is None:
        return False
    if condition.operator == "equals":
        return _values_equal(sampled_value, condition.value)
    if condition.operator == "not_equals":
        return not _values_equal(sampled_value, condition.value)
    if condition.operator == "one_of":
        return any(_values_equal(sampled_value, value) for value in condition.values)
    try:
        numeric_value = float(sampled_value)
        lower = float(condition.value)
    except (TypeError, ValueError):
        return False
    if condition.operator == "at_least":
        return numeric_value >= lower
    if condition.operator == "at_most":
        return numeric_value <= lower
    if condition.operator == "between" and condition.upper_value is not None:
        return lower <= numeric_value <= float(condition.upper_value)
    return False


def _values_equal(left: Any, right: Any) -> bool:
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        or isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return False
    return str(left).strip().casefold() == str(right).strip().casefold()
