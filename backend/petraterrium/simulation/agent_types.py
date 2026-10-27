from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IdentifierPattern = r"^[a-z][a-z0-9_-]*$"
MemberKind = Literal["trait", "routine", "decision"]


class AgentTypeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class AgentTypeMember(AgentTypeModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1)
    description: str | None = Field(default=None, min_length=1)
    source_feature_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_source_features(self):
        if len(set(self.source_feature_ids)) != len(self.source_feature_ids):
            raise ValueError("Member source feature ids must be unique")
        return self


class AgentTypeOverride(AgentTypeModel):
    member_kind: MemberKind
    member_id: str = Field(pattern=IdentifierPattern)
    source_type_id: str = Field(pattern=IdentifierPattern)


class AgentTypeDefinition(AgentTypeModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1)
    parent_ids: list[str] = Field(default_factory=list)
    traits: list[AgentTypeMember] = Field(default_factory=list)
    routines: list[AgentTypeMember] = Field(default_factory=list)
    decisions: list[AgentTypeMember] = Field(default_factory=list)
    overrides: list[AgentTypeOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_collections(self):
        if len(set(self.parent_ids)) != len(self.parent_ids):
            raise ValueError("Agent type parent ids must be unique")
        for label, members in (
            ("Trait", self.traits),
            ("Routine", self.routines),
            ("Decision", self.decisions),
        ):
            identities = [member.id for member in members]
            if len(set(identities)) != len(identities):
                raise ValueError(f"{label} ids must be unique within an agent type")
        override_keys = [
            (override.member_kind, override.member_id) for override in self.overrides
        ]
        if len(set(override_keys)) != len(override_keys):
            raise ValueError("Overrides must be unique by member kind and id")
        return self


class AgentTypeValidationIssue(AgentTypeModel):
    code: str
    path: str
    message: str


class AgentTypeConflict(AgentTypeModel):
    type_id: str
    member_kind: MemberKind
    member_id: str
    source_type_ids: list[str]


class AgentTypeValidationResult(AgentTypeModel):
    valid: bool
    issues: list[AgentTypeValidationIssue]
    conflicts: list[AgentTypeConflict]


class ResolvedAgentTypeMember(AgentTypeModel):
    member: AgentTypeMember
    source_type_id: str
    inherited: bool
    explicit_override: bool
    overridden_source_type_ids: list[str] = Field(default_factory=list)


class ResolvedAgentType(AgentTypeModel):
    id: str
    name: str
    description: str | None = None
    parent_ids: list[str]
    traits: list[ResolvedAgentTypeMember]
    routines: list[ResolvedAgentTypeMember]
    decisions: list[ResolvedAgentTypeMember]


class ResolvedAgentTypeRegistry(AgentTypeModel):
    types: list[ResolvedAgentType]

    def by_id(self, type_id: str) -> ResolvedAgentType:
        for agent_type in self.types:
            if agent_type.id == type_id:
                return agent_type
        raise KeyError(type_id)


class AgentTypeProposalAudit(AgentTypeModel):
    provider: Literal["openai_cli", "openai_api", "deterministic", "manual"]
    model: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class AgentTypeProposalDraft(AgentTypeModel):
    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=IdentifierPattern)
    prompt: str = Field(min_length=1, max_length=12_000)
    imported_feature_ids: list[str] = Field(default_factory=list)
    types: list[AgentTypeDefinition] = Field(min_length=1)
    audit: AgentTypeProposalAudit
    status: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def unique_imported_features(self):
        if len(set(self.imported_feature_ids)) != len(self.imported_feature_ids):
            raise ValueError("Imported feature ids must be unique")
        return self


class ConfirmAgentTypeProposalRequest(AgentTypeModel):
    draft: AgentTypeProposalDraft
    user_confirmed: Literal[True]


class ConfirmedAgentTypeRegistry(AgentTypeModel):
    schema_version: Literal["1"] = "1"
    id: str
    imported_feature_ids: list[str]
    types: list[AgentTypeDefinition]
    resolved: ResolvedAgentTypeRegistry
    audit: AgentTypeProposalAudit
    confirmed: Literal[True] = True
    revision: int


class AgentTypeResolutionError(ValueError):
    def __init__(self, validation: AgentTypeValidationResult):
        self.validation = validation
        message = "; ".join(issue.message for issue in validation.issues)
        super().__init__(message or "Agent type inheritance could not be resolved")


class _Candidate:
    def __init__(
        self,
        member: AgentTypeMember,
        source_type_id: str,
        branch_type_id: str,
        overridden_source_type_ids: Iterable[str] = (),
        explicit_override: bool = False,
    ):
        self.member = member
        self.source_type_id = source_type_id
        self.branch_type_id = branch_type_id
        self.overridden_source_type_ids = set(overridden_source_type_ids)
        self.explicit_override = explicit_override


def _members(
    agent_type: AgentTypeDefinition, kind: MemberKind
) -> list[AgentTypeMember]:
    if kind == "trait":
        return agent_type.traits
    if kind == "routine":
        return agent_type.routines
    return agent_type.decisions


def _resolved_members(
    agent_type: ResolvedAgentType, kind: MemberKind
) -> list[ResolvedAgentTypeMember]:
    if kind == "trait":
        return agent_type.traits
    if kind == "routine":
        return agent_type.routines
    return agent_type.decisions


def _inheritance_cycles(types_by_id: dict[str, AgentTypeDefinition]) -> list[list[str]]:
    cycles: set[tuple[str, ...]] = set()
    active: list[str] = []
    visited: set[str] = set()

    def visit(type_id: str):
        if type_id in active:
            cycle = active[active.index(type_id) :]
            rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
            cycles.add(min(rotations))
            return
        if type_id in visited:
            return
        active.append(type_id)
        for parent_id in types_by_id[type_id].parent_ids:
            if parent_id in types_by_id:
                visit(parent_id)
        active.pop()
        visited.add(type_id)

    for type_id in sorted(types_by_id):
        visit(type_id)
    return [list(cycle) for cycle in sorted(cycles)]


def _ancestor_sets(
    types_by_id: dict[str, AgentTypeDefinition]
) -> dict[str, set[str]]:
    cache: dict[str, set[str]] = {}

    def ancestors(type_id: str) -> set[str]:
        if type_id in cache:
            return cache[type_id]
        result: set[str] = set()
        for parent_id in types_by_id[type_id].parent_ids:
            if parent_id in types_by_id:
                result.add(parent_id)
                result.update(ancestors(parent_id))
        cache[type_id] = result
        return result

    for type_id in types_by_id:
        ancestors(type_id)
    return cache


def _structural_issues(
    types: list[AgentTypeDefinition], types_by_id: dict[str, AgentTypeDefinition]
) -> list[AgentTypeValidationIssue]:
    issues: list[AgentTypeValidationIssue] = []
    counts: defaultdict[str, int] = defaultdict(int)
    for agent_type in types:
        counts[agent_type.id] += 1
    for type_id, count in sorted(counts.items()):
        if count > 1:
            issues.append(
                AgentTypeValidationIssue(
                    code="duplicate_type_id",
                    path=f"types.{type_id}",
                    message=f"Agent type id {type_id!r} appears {count} times",
                )
            )
    for agent_type in types:
        for parent_id in agent_type.parent_ids:
            if parent_id not in types_by_id:
                issues.append(
                    AgentTypeValidationIssue(
                        code="unknown_parent",
                        path=f"types.{agent_type.id}.parent_ids",
                        message=(
                            f"Unknown parent {parent_id!r} for agent type {agent_type.id!r}"
                        ),
                    )
                )
    for cycle in _inheritance_cycles(types_by_id):
        path = " -> ".join([*cycle, cycle[0]])
        issues.append(
            AgentTypeValidationIssue(
                code="inheritance_cycle",
                path="types",
                message=f"Agent type inheritance contains a cycle: {path}",
            )
        )
    return issues


def _topological_ids(types_by_id: dict[str, AgentTypeDefinition]) -> list[str]:
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(type_id: str):
        if type_id in visited:
            return
        for parent_id in types_by_id[type_id].parent_ids:
            visit(parent_id)
        visited.add(type_id)
        ordered.append(type_id)

    for type_id in sorted(types_by_id):
        visit(type_id)
    return ordered


def _maximally_specific(
    candidates: list[_Candidate], ancestor_sets: dict[str, set[str]]
) -> list[_Candidate]:
    result: list[_Candidate] = []
    for candidate in candidates:
        less_specific = any(
            candidate.branch_type_id in ancestor_sets[other.branch_type_id]
            for other in candidates
            if other is not candidate
        )
        if not less_specific:
            result.append(candidate)
    unique: dict[tuple[str, str], _Candidate] = {}
    for candidate in result:
        key = (candidate.source_type_id, candidate.member.model_dump_json())
        if key in unique:
            unique[key].overridden_source_type_ids.update(
                candidate.overridden_source_type_ids
            )
            unique[key].explicit_override = (
                unique[key].explicit_override or candidate.explicit_override
            )
        else:
            unique[key] = candidate
    return list(unique.values())


def _resolve_kind(
    definition: AgentTypeDefinition,
    kind: MemberKind,
    resolved_by_id: dict[str, ResolvedAgentType],
    ancestor_sets: dict[str, set[str]],
    issues: list[AgentTypeValidationIssue],
    conflicts: list[AgentTypeConflict],
) -> list[ResolvedAgentTypeMember]:
    candidates_by_member: defaultdict[str, list[_Candidate]] = defaultdict(list)
    for parent_id in definition.parent_ids:
        for inherited in _resolved_members(resolved_by_id[parent_id], kind):
            candidates_by_member[inherited.member.id].append(
                _Candidate(
                    member=inherited.member,
                    source_type_id=inherited.source_type_id,
                    branch_type_id=parent_id,
                    overridden_source_type_ids=inherited.overridden_source_type_ids,
                    explicit_override=inherited.explicit_override,
                )
            )
    for own_member in _members(definition, kind):
        candidates_by_member[own_member.id].append(
            _Candidate(
                member=own_member,
                source_type_id=definition.id,
                branch_type_id=definition.id,
            )
        )
    override_by_member = {
        override.member_id: override
        for override in definition.overrides
        if override.member_kind == kind
    }
    resolved: list[ResolvedAgentTypeMember] = []
    used_overrides: set[str] = set()
    for member_id, candidates in sorted(candidates_by_member.items()):
        finalists = _maximally_specific(candidates, ancestor_sets)
        override = override_by_member.get(member_id)
        winner: _Candidate | None = None
        explicit_override = False
        if len(finalists) == 1:
            winner = finalists[0]
            explicit_override = winner.explicit_override or (
                winner.source_type_id == definition.id and len(candidates) > 1
            )
            if override is not None:
                if override.source_type_id != winner.source_type_id:
                    issues.append(
                        AgentTypeValidationIssue(
                            code="invalid_override_source",
                            path=f"types.{definition.id}.overrides.{kind}.{member_id}",
                            message=(
                                f"Override for {kind} {member_id!r} selects "
                                f"{override.source_type_id!r}, but the most-specific source is "
                                f"{winner.source_type_id!r}"
                            ),
                        )
                    )
                else:
                    used_overrides.add(member_id)
                    explicit_override = True
        elif override is not None:
            matches = [
                candidate
                for candidate in finalists
                if candidate.source_type_id == override.source_type_id
            ]
            if len(matches) == 1:
                winner = matches[0]
                explicit_override = True
                used_overrides.add(member_id)
            else:
                issues.append(
                    AgentTypeValidationIssue(
                        code="invalid_override_source",
                        path=f"types.{definition.id}.overrides.{kind}.{member_id}",
                        message=(
                            f"Override source {override.source_type_id!r} does not provide a "
                            f"maximally specific {kind} {member_id!r}"
                        ),
                    )
                )
        if winner is None and len(finalists) > 1:
            source_type_ids = sorted(
                {candidate.source_type_id for candidate in finalists}
            )
            conflicts.append(
                AgentTypeConflict(
                    type_id=definition.id,
                    member_kind=kind,
                    member_id=member_id,
                    source_type_ids=source_type_ids,
                )
            )
            issues.append(
                AgentTypeValidationIssue(
                    code="ambiguous_inherited_member",
                    path=f"types.{definition.id}.{kind}s.{member_id}",
                    message=(
                        f"Agent type {definition.id!r} inherits conflicting {kind} "
                        f"{member_id!r} from {', '.join(source_type_ids)}; add an explicit "
                        "override selecting one source"
                    ),
                )
            )
        if winner is None:
            continue
        overridden_sources = set(winner.overridden_source_type_ids)
        for candidate in candidates:
            if candidate is winner:
                continue
            overridden_sources.add(candidate.source_type_id)
            overridden_sources.update(candidate.overridden_source_type_ids)
        overridden_sources.discard(winner.source_type_id)
        resolved.append(
            ResolvedAgentTypeMember(
                member=winner.member,
                source_type_id=winner.source_type_id,
                inherited=winner.source_type_id != definition.id,
                explicit_override=explicit_override,
                overridden_source_type_ids=sorted(overridden_sources),
            )
        )
    for member_id, override in sorted(override_by_member.items()):
        if member_id in used_overrides or member_id in candidates_by_member:
            continue
        issues.append(
            AgentTypeValidationIssue(
                code="invalid_override_source",
                path=f"types.{definition.id}.overrides.{kind}.{member_id}",
                message=(
                    f"Override source {override.source_type_id!r} does not provide "
                    f"{kind} {member_id!r}"
                ),
            )
        )
    return resolved


def _resolve_with_validation(
    types: list[AgentTypeDefinition],
) -> tuple[ResolvedAgentTypeRegistry | None, AgentTypeValidationResult]:
    types_by_id = {agent_type.id: agent_type for agent_type in types}
    issues = _structural_issues(types, types_by_id)
    conflicts: list[AgentTypeConflict] = []
    structural_codes = {issue.code for issue in issues}
    if structural_codes & {"duplicate_type_id", "unknown_parent", "inheritance_cycle"}:
        result = AgentTypeValidationResult(valid=False, issues=issues, conflicts=conflicts)
        return None, result
    ancestor_sets = _ancestor_sets(types_by_id)
    resolved_by_id: dict[str, ResolvedAgentType] = {}
    for type_id in _topological_ids(types_by_id):
        definition = types_by_id[type_id]
        resolved_by_id[type_id] = ResolvedAgentType(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            parent_ids=definition.parent_ids,
            traits=_resolve_kind(
                definition,
                "trait",
                resolved_by_id,
                ancestor_sets,
                issues,
                conflicts,
            ),
            routines=_resolve_kind(
                definition,
                "routine",
                resolved_by_id,
                ancestor_sets,
                issues,
                conflicts,
            ),
            decisions=_resolve_kind(
                definition,
                "decision",
                resolved_by_id,
                ancestor_sets,
                issues,
                conflicts,
            ),
        )
    result = AgentTypeValidationResult(
        valid=not issues,
        issues=issues,
        conflicts=conflicts,
    )
    registry = ResolvedAgentTypeRegistry(
        types=[resolved_by_id[type_id] for type_id in sorted(resolved_by_id)]
    )
    return registry, result


def validate_agent_types(
    types: Iterable[AgentTypeDefinition],
) -> AgentTypeValidationResult:
    _, validation = _resolve_with_validation(list(types))
    return validation


def resolve_agent_types(
    types: Iterable[AgentTypeDefinition],
) -> ResolvedAgentTypeRegistry:
    registry, validation = _resolve_with_validation(list(types))
    if not validation.valid or registry is None:
        raise AgentTypeResolutionError(validation)
    return registry


def confirm_agent_type_proposal(
    draft: AgentTypeProposalDraft, user_confirmed: bool
) -> ConfirmedAgentTypeRegistry:
    if not user_confirmed:
        raise ValueError("Explicit user confirmation is required before saving agent types")
    resolved = resolve_agent_types(draft.types)
    return ConfirmedAgentTypeRegistry(
        id=draft.id,
        imported_feature_ids=draft.imported_feature_ids,
        types=draft.types,
        resolved=resolved,
        audit=draft.audit,
        revision=draft.revision,
    )
