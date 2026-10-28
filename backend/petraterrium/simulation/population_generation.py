import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..population import AgentRecord, PopulationTable, Relationship
from .interactions import RelationshipKindEvidence


class InitialPopulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvidenceReference(InitialPopulationModel):
    evidence_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)
    licence: str = Field(min_length=1)
    place: str = Field(min_length=1)
    status: Literal["measured_joint", "measured_marginal", "imputed", "unknown"]
    fields: list[str] = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    url: str | None = None


class HouseholdMemberSeed(InitialPopulationModel):
    member_id: str = Field(min_length=1)
    age: int = Field(ge=0, le=125)
    sex: str = Field(min_length=1)
    relationship_to_reference: Literal[
        "self", "spouse", "child", "parent", "sibling", "other"
    ]
    agent_types: list[str] = Field(min_length=1)
    traits: dict[str, Any] = Field(default_factory=dict)
    states: dict[str, str] = Field(default_factory=dict)
    field_evidence: dict[str, str] = Field(default_factory=dict)


class HouseholdSeed(InitialPopulationModel):
    template_id: str = Field(min_length=1)
    place: str = Field(min_length=1)
    country: str = Field(min_length=1)
    country_id: str | None = Field(default=None, min_length=1)
    region: str | None = None
    city: str = Field(min_length=1)
    city_id: str | None = Field(default=None, min_length=1)
    neighbourhood: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    weight: float = Field(gt=0)
    evidence_id: str = Field(min_length=1)
    members: list[HouseholdMemberSeed] = Field(min_length=1)


class InitialPopulationRequest(InitialPopulationModel):
    population_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    seed: int
    target_agents: int = Field(ge=1)
    household_templates: list[HouseholdSeed] = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(min_length=1)


class InitialPopulationValidationIssue(InitialPopulationModel):
    code: str
    path: str
    message: str


class InitialPopulationValidation(InitialPopulationModel):
    valid: bool
    issues: list[InitialPopulationValidationIssue]


class AgentInitialStateProvenance(InitialPopulationModel):
    source_template_id: str
    sampling_basis: Literal[
        "measured_joint", "measured_marginal", "imputed", "unknown"
    ]
    household_evidence: EvidenceReference
    field_evidence: dict[str, EvidenceReference]
    unknown_fields: list[str]


class InitialPopulationMaterialization(InitialPopulationModel):
    population: PopulationTable
    provenance: dict[str, AgentInitialStateProvenance]
    validation: InitialPopulationValidation
    input_hash: str


class InitialPopulationValidationError(ValueError):
    def __init__(self, validation: InitialPopulationValidation):
        self.validation = validation
        super().__init__("; ".join(issue.message for issue in validation.issues))


RESERVED_TRAITS = {
    "age",
    "sex",
    "name",
    "agent_type",
    "agent_types",
    "country",
    "country_id",
    "region",
    "city",
    "city_id",
    "neighbourhood",
    "specific_place",
    "household_id",
    "household_role",
    "family_status",
    "family_relationships",
    "initial_state_key",
    "source_template_id",
}


def issue(code: str, path: str, message: str) -> InitialPopulationValidationIssue:
    return InitialPopulationValidationIssue(code=code, path=path, message=message)


def request_hash(
    request: InitialPopulationRequest,
    relationship_evidence: tuple[RelationshipKindEvidence, ...] = (),
) -> str:
    value: Any = request.model_dump(mode="json")
    if relationship_evidence:
        value = {
            "request": value,
            "relationship_evidence": [
                item.model_dump(mode="json")
                for item in sorted(relationship_evidence, key=lambda item: item.kind)
            ],
        }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _family_role(member: HouseholdMemberSeed, has_children: bool) -> str:
    if member.relationship_to_reference in {"self", "spouse"} and has_children:
        return "parent"
    if member.relationship_to_reference == "spouse":
        return "partner"
    if member.relationship_to_reference in {"child", "parent", "sibling"}:
        return member.relationship_to_reference
    return "household_member"


def _validate_template(
    template: HouseholdSeed,
    template_index: int,
    evidence_by_id: dict[str, EvidenceReference],
) -> list[InitialPopulationValidationIssue]:
    path = f"household_templates.{template_index}"
    issues: list[InitialPopulationValidationIssue] = []
    member_ids = [member.member_id for member in template.members]
    if len(set(member_ids)) != len(member_ids):
        issues.append(
            issue(
                "duplicate_member_id",
                f"{path}.members",
                f"Household template {template.template_id!r} has duplicate member ids",
            )
        )
    references = [
        member for member in template.members if member.relationship_to_reference == "self"
    ]
    if len(references) != 1:
        issues.append(
            issue(
                "invalid_reference_member",
                f"{path}.members",
                "A household template requires exactly one reference member",
            )
        )
        return issues
    if template.evidence_id not in evidence_by_id:
        issues.append(
            issue(
                "unknown_household_evidence",
                f"{path}.evidence_id",
                f"Unknown household evidence {template.evidence_id!r}",
            )
        )
    adults = [member for member in template.members if member.age >= 18]
    if not adults:
        issues.append(
            issue(
                "household_without_adult",
                f"{path}.members",
                f"Household template {template.template_id!r} has no adult",
            )
        )
    has_children = any(
        member.relationship_to_reference == "child" for member in template.members
    )
    parents = [
        member
        for member in template.members
        if _family_role(member, has_children) == "parent"
    ]
    children = [
        member
        for member in template.members
        if _family_role(member, has_children) == "child"
    ]
    for member_index, member in enumerate(template.members):
        member_path = f"{path}.members.{member_index}"
        if RESERVED_TRAITS.intersection(member.traits):
            labels = ", ".join(sorted(RESERVED_TRAITS.intersection(member.traits)))
            issues.append(
                issue(
                    "reserved_trait_override",
                    f"{member_path}.traits",
                    f"Reserved initial-state traits cannot be overridden: {labels}",
                )
            )
        for field, evidence_id in member.field_evidence.items():
            if evidence_id not in evidence_by_id:
                issues.append(
                    issue(
                        "unknown_field_evidence",
                        f"{member_path}.field_evidence.{field}",
                        f"Unknown evidence {evidence_id!r} for field {field!r}",
                    )
                )
            elif field not in evidence_by_id[evidence_id].fields:
                issues.append(
                    issue(
                        "evidence_field_mismatch",
                        f"{member_path}.field_evidence.{field}",
                        f"Evidence {evidence_id!r} does not cover field {field!r}",
                    )
                )
        role = _family_role(member, has_children)
        if role == "parent" and member.age < 16:
            issues.append(
                issue(
                    "parent_too_young",
                    f"{member_path}.age",
                    f"Parent {member.member_id!r} is younger than 16",
                )
            )
        if role == "partner" and member.age < 16:
            issues.append(
                issue(
                    "spouse_too_young",
                    f"{member_path}.age",
                    f"Spouse {member.member_id!r} is younger than 16",
                )
            )
    for child in children:
        for parent in parents:
            if child.age >= parent.age:
                message = (
                    f"Child {child.member_id!r} is not younger than "
                    f"parent {parent.member_id!r}"
                )
                issues.append(
                    issue(
                        "child_older_than_parent",
                        f"{path}.members",
                        message,
                    )
                )
            elif parent.age - child.age < 12:
                message = (
                    f"Parent {parent.member_id!r} is less than 12 years "
                    f"older than child {child.member_id!r}"
                )
                issues.append(
                    issue(
                        "parent_age_gap_implausible",
                        f"{path}.members",
                        message,
                    )
                )
    reference = references[0]
    for spouse in (
        member
        for member in template.members
        if member.relationship_to_reference == "spouse"
    ):
        if abs(reference.age - spouse.age) > 50:
            issues.append(
                issue(
                    "spouse_age_gap_implausible",
                    f"{path}.members",
                    f"Spouse ages differ by more than 50 years in {template.template_id!r}",
                )
            )
    return issues


def validate_population_request(
    request: InitialPopulationRequest,
) -> InitialPopulationValidation:
    issues: list[InitialPopulationValidationIssue] = []
    evidence_ids = [item.evidence_id for item in request.evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        issues.append(
            issue("duplicate_evidence_id", "evidence", "Evidence ids must be unique")
        )
    template_ids = [template.template_id for template in request.household_templates]
    if len(set(template_ids)) != len(template_ids):
        issues.append(
            issue(
                "duplicate_template_id",
                "household_templates",
                "Household template ids must be unique",
            )
        )
    evidence_by_id = {item.evidence_id: item for item in request.evidence}
    for index, template in enumerate(request.household_templates):
        issues.extend(_validate_template(template, index, evidence_by_id))
    sizes = sorted({len(template.members) for template in request.household_templates})
    reusable_sizes = _reachable_sizes(
        request.household_templates,
        request.target_agents,
        reuse_templates=True,
    )
    unique_sizes = _reachable_sizes(
        request.household_templates,
        request.target_agents,
        reuse_templates=False,
    )
    if not reusable_sizes[request.target_agents]:
        message = (
            f"Target {request.target_agents} cannot be formed from whole household "
            f"sizes {sizes}"
        )
        issues.append(
            issue(
                "population_size_unreachable",
                "target_agents",
                message,
            )
        )
    elif not unique_sizes[request.target_agents]:
        message = (
            f"Target {request.target_agents} requires reusing an evidence-backed "
            "household template, which would create cloned substantive initial states"
        )
        issues.append(
            issue(
                "insufficient_unique_initial_states",
                "household_templates",
                message,
            )
        )
    return InitialPopulationValidation(valid=not issues, issues=issues)


def _sex_label(sex: str, female: str, male: str, neutral: str) -> str:
    normalized = sex.casefold()
    if normalized in {"female", "woman", "girl", "f"}:
        return female
    if normalized in {"male", "man", "boy", "m"}:
        return male
    return neutral


def _relationship_label(
    actor: HouseholdMemberSeed, target: HouseholdMemberSeed
) -> str:
    actor_relation = actor.relationship_to_reference
    target_relation = target.relationship_to_reference
    if actor_relation == "self":
        if target_relation == "spouse":
            return _sex_label(target.sex, "wife", "husband", "spouse")
        if target_relation == "child":
            return _sex_label(target.sex, "daughter", "son", "child")
        if target_relation == "parent":
            return _sex_label(target.sex, "mother", "father", "parent")
        if target_relation == "sibling":
            return _sex_label(target.sex, "sister", "brother", "sibling")
    if target_relation == "self":
        if actor_relation == "spouse":
            return _sex_label(target.sex, "wife", "husband", "spouse")
        if actor_relation == "child":
            return _sex_label(target.sex, "mother", "father", "parent")
        if actor_relation == "parent":
            return _sex_label(target.sex, "daughter", "son", "child")
        if actor_relation == "sibling":
            return _sex_label(target.sex, "sister", "brother", "sibling")
    if {actor_relation, target_relation} == {"spouse", "child"}:
        if actor_relation == "spouse":
            return _sex_label(target.sex, "daughter", "son", "child")
        return _sex_label(target.sex, "mother", "father", "parent")
    if actor_relation == target_relation == "child":
        return _sex_label(target.sex, "sister", "brother", "sibling")
    return "household member"


def _family_status(role: str, has_spouse: bool) -> str:
    if role == "parent":
        return "parent"
    if role == "child":
        return "child"
    if role == "partner" or has_spouse:
        return "partnered"
    return "household"


def _stable_id(*parts: object) -> str:
    value = ":".join(str(part) for part in parts)
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _reachable_sizes(
    templates: list[HouseholdSeed], target: int, *, reuse_templates: bool
) -> list[bool]:
    reachable = [False] * (target + 1)
    reachable[0] = True
    if reuse_templates:
        sizes = {len(template.members) for template in templates}
        for total in range(1, target + 1):
            reachable[total] = any(
                size <= total and reachable[total - size] for size in sizes
            )
        return reachable
    for template in templates:
        size = len(template.members)
        for total in range(target, size - 1, -1):
            reachable[total] = reachable[total] or reachable[total - size]
    return reachable


def _select_households(
    request: InitialPopulationRequest, rng: np.random.Generator
) -> list[HouseholdSeed]:
    templates = sorted(request.household_templates, key=lambda item: item.template_id)
    priorities = rng.exponential(
        scale=np.reciprocal(np.array([template.weight for template in templates]))
    )
    ordered = [
        template
        for _, template in sorted(
            zip(priorities, templates, strict=True),
            key=lambda item: (item[0], item[1].template_id),
        )
    ]
    reachable = [False] * (request.target_agents + 1)
    reachable[0] = True
    predecessors: dict[int, tuple[int, HouseholdSeed]] = {}
    for template in ordered:
        size = len(template.members)
        for total in range(request.target_agents, size - 1, -1):
            previous = total - size
            if reachable[total] or not reachable[previous]:
                continue
            reachable[total] = True
            predecessors[total] = (previous, template)
    selected: list[HouseholdSeed] = []
    total = request.target_agents
    while total:
        previous, template = predecessors[total]
        selected.append(template)
        total = previous
    selected.reverse()
    return selected


def _provenance(
    member: HouseholdMemberSeed,
    template: HouseholdSeed,
    evidence_by_id: dict[str, EvidenceReference],
) -> AgentInitialStateProvenance:
    fields = {
        "age",
        "sex",
        "household_composition",
        "family_relationships",
        *member.traits,
        *member.states,
    }
    field_evidence = {
        field: evidence_by_id[evidence_id]
        for field, evidence_id in member.field_evidence.items()
        if field in fields
    }
    return AgentInitialStateProvenance(
        source_template_id=template.template_id,
        sampling_basis=evidence_by_id[template.evidence_id].status,
        household_evidence=evidence_by_id[template.evidence_id],
        field_evidence=field_evidence,
        unknown_fields=sorted(fields - field_evidence.keys()),
    )


def _household_agents(
    template: HouseholdSeed,
    input_hash: str,
    household_index: int,
    first_agent_index: int,
    evidence_by_id: dict[str, EvidenceReference],
    relationship_evidence_by_kind: dict[str, RelationshipKindEvidence],
) -> tuple[list[AgentRecord], dict[str, AgentInitialStateProvenance]]:
    household_id = _stable_id(input_hash, "household", household_index, template.template_id)
    members = list(template.members)
    ids = {
        member.member_id: _stable_id(input_hash, "agent", household_index, member.member_id)
        for member in members
    }
    has_children = any(
        member.relationship_to_reference == "child" for member in members
    )
    has_spouse = any(
        member.relationship_to_reference == "spouse" for member in members
    )
    agents: list[AgentRecord] = []
    provenance: dict[str, AgentInitialStateProvenance] = {}
    for offset, member in enumerate(members):
        agent_id = ids[member.member_id]
        role = _family_role(member, has_children)
        relationship_labels = {
            ids[target.member_id]: _relationship_label(member, target)
            for target in members
            if target.member_id != member.member_id
        }
        specific_place = f"home:{household_id}"
        traits = {
            **member.traits,
            "age": member.age,
            "sex": member.sex,
            "agent_type": member.agent_types[0],
            "agent_types": member.agent_types,
            "country": template.country,
            "region": template.region,
            "city": template.city,
            "neighbourhood": template.neighbourhood,
            "specific_place": specific_place,
            "household_id": household_id,
            "household_role": role,
            "family_status": _family_status(role, has_spouse),
            "family_relationships": relationship_labels,
            "initial_state_key": _stable_id(input_hash, "state", household_index, member.member_id),
            "source_template_id": template.template_id,
        }
        if template.country_id is not None:
            traits["country_id"] = template.country_id
        if template.city_id is not None:
            traits["city_id"] = template.city_id
        family_evidence = relationship_evidence_by_kind.get("family")
        relationships = []
        for target in members:
            if target.member_id == member.member_id:
                continue
            relationship_values: dict[str, Any] = {
                "target_id": ids[target.member_id],
                "kind": "family",
                "weight": 1,
            }
            if family_evidence is not None:
                relationship_values.update(
                    weight=family_evidence.weight,
                    trust=family_evidence.trust,
                    similarity=family_evidence.similarity,
                    evidence_id=family_evidence.provenance.evidence_id,
                    evidence_status=family_evidence.provenance.status,
                )
            relationships.append(Relationship(**relationship_values))
        index = first_agent_index + offset
        agents.append(
            AgentRecord(
                agent_id=agent_id,
                place=template.place,
                latitude=template.latitude,
                longitude=template.longitude,
                role=member.agent_types[0],
                log_tier="spotlight" if index < 10 else "sampled" if index < 30 else "mass",
                traits=traits,
                states={**member.states, "location": specific_place},
                behaviour={},
                behaviour_provenance={},
                relationships=relationships,
                weight=1,
            )
        )
        provenance[agent_id] = _provenance(member, template, evidence_by_id)
    return agents, provenance


def _canonical_relationship(label: str) -> str:
    normalized = label.casefold()
    if normalized in {"wife", "husband", "spouse", "partner"}:
        return "spouse"
    if normalized in {"daughter", "son", "child"}:
        return "child"
    if normalized in {"mother", "father", "parent"}:
        return "parent"
    if normalized in {"sister", "brother", "sibling"}:
        return "sibling"
    return normalized


def _roles_are_reciprocal(left: str, right: str) -> bool:
    pair = (_canonical_relationship(left), _canonical_relationship(right))
    return pair in {
        ("spouse", "spouse"),
        ("child", "parent"),
        ("parent", "child"),
        ("sibling", "sibling"),
        ("household member", "household member"),
    }


NON_SUBSTANTIVE_TRAITS = {
    "name",
    "household_id",
    "specific_place",
    "initial_state_key",
    "source_template_id",
}


def _substantive_initial_state(agent: AgentRecord) -> str:
    traits = {
        key: value
        for key, value in agent.traits.items()
        if key not in NON_SUBSTANTIVE_TRAITS and key != "family_relationships"
    }
    family_relationships = agent.traits.get("family_relationships")
    if isinstance(family_relationships, dict):
        traits["family_relationships"] = sorted(
            str(value) for value in family_relationships.values()
        )
    specific_place = agent.traits.get("specific_place")
    states = {
        key: "household_home" if key == "location" and value == specific_place else value
        for key, value in agent.states.items()
    }
    relationships = sorted(
        (
            relationship.kind,
            relationship.weight,
            relationship.trust,
            relationship.similarity,
            relationship.evidence_id,
            relationship.evidence_status,
        )
        for relationship in agent.relationships
    )
    value = {
        "place": agent.place,
        "latitude": agent.latitude,
        "longitude": agent.longitude,
        "role": agent.role,
        "traits": traits,
        "states": states,
        "behaviour": agent.behaviour,
        "behaviour_provenance": {
            key: evidence.model_dump(mode="json")
            for key, evidence in agent.behaviour_provenance.items()
        },
        "relationships": relationships,
        "weight": agent.weight,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_initial_population(population: PopulationTable) -> InitialPopulationValidation:
    issues: list[InitialPopulationValidationIssue] = []
    counts = Counter(agent.agent_id for agent in population.agents)
    for agent_id, count in counts.items():
        if count > 1:
            issues.append(
                issue(
                    "duplicate_agent_id",
                    "agents",
                    f"Agent id {agent_id!r} occurs {count} times",
                )
            )
    by_id = {agent.agent_id: agent for agent in population.agents}
    edge_keys = {
        (agent.agent_id, relationship.target_id, relationship.kind)
        for agent in population.agents
        for relationship in agent.relationships
    }
    households: dict[str, list[AgentRecord]] = defaultdict(list)
    signatures: dict[str, str] = {}
    for index, agent in enumerate(population.agents):
        path = f"agents.{index}"
        if "name" in agent.traits:
            issues.append(
                issue(
                    "agent_name_not_allowed",
                    f"{path}.traits.name",
                    "Population agents use agent_id only and cannot carry a name",
                )
            )
        age = agent.traits.get("age")
        if isinstance(age, bool) or not isinstance(age, int):
            issues.append(
                issue(
                    "age_not_concrete",
                    f"{path}.traits.age",
                    f"Agent {agent.agent_id!r} requires one concrete integer age",
                )
            )
        if "age_band" in agent.traits:
            issues.append(
                issue(
                    "age_band_not_allowed",
                    f"{path}.traits.age_band",
                    "Initial agents use concrete age, not an age band",
                )
            )
        household_id = str(agent.traits.get("household_id", "")).strip()
        if household_id:
            households[household_id].append(agent)
        labels = agent.traits.get("family_relationships")
        label_map = labels if isinstance(labels, dict) else {}
        for relationship in agent.relationships:
            target = by_id.get(relationship.target_id)
            if target is None:
                issues.append(
                    issue(
                        "unknown_relationship_target",
                        f"{path}.relationships",
                        f"Relationship target {relationship.target_id!r} does not exist",
                    )
                )
                continue
            if (relationship.target_id, agent.agent_id, relationship.kind) not in edge_keys:
                message = (
                    f"{relationship.kind.title()} relationship from {agent.agent_id!r} "
                    f"to {relationship.target_id!r} is not reciprocal"
                )
                issues.append(
                    issue(
                        "nonreciprocal_relationship",
                        f"{path}.relationships",
                        message,
                    )
                )
            target_labels = target.traits.get("family_relationships")
            target_map = target_labels if isinstance(target_labels, dict) else {}
            left_label = label_map.get(relationship.target_id)
            right_label = target_map.get(agent.agent_id)
            if relationship.kind == "family" and (
                not isinstance(left_label, str)
                or not isinstance(right_label, str)
                or not _roles_are_reciprocal(left_label, right_label)
            ):
                message = (
                    f"Family roles between {agent.agent_id!r} and "
                    f"{relationship.target_id!r} are inconsistent"
                )
                issues.append(
                    issue(
                        "inconsistent_family_roles",
                        f"{path}.traits.family_relationships",
                        message,
                    )
                )
        signature = _substantive_initial_state(agent)
        previous = signatures.get(signature)
        if previous:
            issues.append(
                issue(
                    "duplicate_initial_state",
                    path,
                    f"Agents {previous!r} and {agent.agent_id!r} have identical initial states",
                )
            )
        signatures[signature] = agent.agent_id
    for household_id, agents in households.items():
        def concrete_age(agent: AgentRecord) -> int | None:
            value = agent.traits.get("age")
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        adults = [
            agent
            for agent in agents
            if concrete_age(agent) is not None and concrete_age(agent) >= 18
        ]
        if not adults:
            issues.append(
                issue(
                    "household_without_adult",
                    f"households.{household_id}",
                    f"Household {household_id!r} has no adult",
                )
            )
        parents = [agent for agent in agents if agent.traits.get("household_role") == "parent"]
        children = [agent for agent in agents if agent.traits.get("household_role") == "child"]
        for agent in agents:
            labels = agent.traits.get("family_relationships")
            label_map = labels if isinstance(labels, dict) else {}
            categories = {
                _canonical_relationship(str(label)) for label in label_map.values()
            }
            role = agent.traits.get("household_role")
            expected = {
                "parent": "child",
                "child": "parent",
                "partner": "spouse",
                "sibling": "sibling",
            }.get(str(role))
            if expected and expected not in categories:
                message = (
                    f"Household role {role!r} for {agent.agent_id!r} does not "
                    "match its family relationships"
                )
                issues.append(
                    issue(
                        "inconsistent_household_role",
                        f"agents.{agent.agent_id}.traits.household_role",
                        message,
                    )
                )
        for parent in parents:
            parent_age = concrete_age(parent)
            if parent_age is not None and parent_age < 16:
                issues.append(
                    issue(
                        "parent_too_young",
                        f"agents.{parent.agent_id}.traits.age",
                        f"Parent {parent.agent_id!r} is younger than 16",
                    )
                )
        for child in children:
            if not parents:
                issues.append(
                    issue(
                        "child_without_parent",
                        f"agents.{child.agent_id}.traits.household_role",
                        f"Child {child.agent_id!r} has no parent in its household",
                    )
                )
            for parent in parents:
                child_age = concrete_age(child)
                parent_age = concrete_age(parent)
                if (
                    child_age is not None
                    and parent_age is not None
                    and child_age >= parent_age
                ):
                    message = (
                        f"Child {child.agent_id!r} is not younger than "
                        f"parent {parent.agent_id!r}"
                    )
                    issues.append(
                        issue(
                            "child_older_than_parent",
                            f"households.{household_id}",
                            message,
                        )
                    )
                elif (
                    child_age is not None
                    and parent_age is not None
                    and parent_age - child_age < 12
                ):
                    message = (
                        f"Parent {parent.agent_id!r} is less than 12 years older "
                        f"than child {child.agent_id!r}"
                    )
                    issues.append(
                        issue(
                            "parent_age_gap_implausible",
                            f"households.{household_id}",
                            message,
                        )
                    )
        for agent in agents:
            labels = agent.traits.get("family_relationships")
            label_map = labels if isinstance(labels, dict) else {}
            for target_id, label in label_map.items():
                if _canonical_relationship(str(label)) != "spouse":
                    continue
                target = by_id.get(str(target_id))
                left_age = concrete_age(agent)
                right_age = concrete_age(target) if target else None
                if (
                    target is not None
                    and left_age is not None
                    and right_age is not None
                    and abs(left_age - right_age) > 50
                ):
                    issues.append(
                        issue(
                            "spouse_age_gap_implausible",
                            f"households.{household_id}",
                            f"Spouse ages differ by more than 50 years in {household_id!r}",
                        )
                    )
    return InitialPopulationValidation(valid=not issues, issues=issues)


def materialize_initial_population(
    request: InitialPopulationRequest,
    relationship_evidence: tuple[RelationshipKindEvidence, ...] = (),
) -> InitialPopulationMaterialization:
    request_validation = validate_population_request(request)
    if not request_validation.valid:
        raise InitialPopulationValidationError(request_validation)
    executable_relationship_evidence = tuple(
        item for item in relationship_evidence if item.provenance.executable
    )
    input_hash = request_hash(request, executable_relationship_evidence)
    rng = np.random.default_rng(request.seed)
    selected = _select_households(request, rng)
    evidence_by_id = {item.evidence_id: item for item in request.evidence}
    relationship_evidence_by_kind = {
        item.kind: item for item in executable_relationship_evidence
    }
    agents: list[AgentRecord] = []
    provenance: dict[str, AgentInitialStateProvenance] = {}
    for household_index, template in enumerate(selected):
        household_agents, household_provenance = _household_agents(
            template,
            input_hash,
            household_index,
            len(agents),
            evidence_by_id,
            relationship_evidence_by_kind,
        )
        agents.extend(household_agents)
        provenance.update(household_provenance)
    population = PopulationTable(
        population_id=request.population_id,
        version=request.version,
        seed=request.seed,
        agents=agents,
    )
    validation = validate_initial_population(population)
    if any(item.code == "duplicate_initial_state" for item in validation.issues):
        validation = validation.model_copy(
            update={
                "issues": [
                    *validation.issues,
                    issue(
                        "insufficient_unique_initial_states",
                        "household_templates",
                        "The selected evidence-backed household templates contain "
                        "duplicate substantive states; provide distinct observed "
                        "records instead of identity-only variants",
                    ),
                ]
            }
        )
    if not validation.valid:
        raise InitialPopulationValidationError(validation)
    return InitialPopulationMaterialization(
        population=population,
        provenance=provenance,
        validation=validation,
        input_hash=input_hash,
    )


def attach_relationship_evidence(
    materialization: InitialPopulationMaterialization,
    relationship_evidence: tuple[RelationshipKindEvidence, ...],
) -> InitialPopulationMaterialization:
    executable = {
        item.kind: item
        for item in relationship_evidence
        if item.provenance.executable
    }
    if not executable:
        return materialization
    changed = False
    agents: list[AgentRecord] = []
    for agent in materialization.population.agents:
        relationships: list[Relationship] = []
        for relationship in agent.relationships:
            evidence = executable.get(relationship.kind)
            if evidence is None:
                relationships.append(relationship)
                continue
            expected = (
                evidence.weight,
                evidence.trust,
                evidence.similarity,
                evidence.provenance.evidence_id,
                evidence.provenance.status,
            )
            current = (
                relationship.weight,
                relationship.trust,
                relationship.similarity,
                relationship.evidence_id,
                relationship.evidence_status,
            )
            if relationship.evidence_id is not None and current != expected:
                raise ValueError(
                    f"Relationship {agent.agent_id!r} to {relationship.target_id!r} "
                    "already has different evidence"
                )
            if current == expected:
                relationships.append(relationship)
                continue
            changed = True
            relationships.append(
                relationship.model_copy(
                    update={
                        "weight": evidence.weight,
                        "trust": evidence.trust,
                        "similarity": evidence.similarity,
                        "evidence_id": evidence.provenance.evidence_id,
                        "evidence_status": evidence.provenance.status,
                    }
                )
            )
        agents.append(agent.model_copy(update={"relationships": relationships}))
    if not changed:
        return materialization
    evidence_payload = [
        item.model_dump(mode="json")
        for item in sorted(executable.values(), key=lambda item: item.kind)
    ]
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "materialization": materialization.input_hash,
                "relationship_evidence": evidence_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    population = materialization.population.model_copy(update={"agents": agents})
    validation = validate_initial_population(population)
    if not validation.valid:
        raise InitialPopulationValidationError(validation)
    return materialization.model_copy(
        update={
            "population": population,
            "validation": validation,
            "input_hash": input_hash,
        }
    )
