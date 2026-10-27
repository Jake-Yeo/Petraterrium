from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..population import AgentRecord, PopulationTable
from .interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
)


class InitialAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentLocation(InitialAgentModel):
    country: str
    region: str | None = None
    city: str
    neighbourhood: str | None = None
    specific_place: str | None = None


class RoutineLink(InitialAgentModel):
    routine_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    inherited_from: str | None = None


class DecisionTreeLink(InitialAgentModel):
    tree_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    inherited_from: str | None = None


class FamilyRelationship(InitialAgentModel):
    target_agent_id: str
    display_name: str
    relationship: str
    age: float | None = Field(default=None, ge=0)
    weight: float = Field(ge=-1, le=1)


class InitialInteractionEvidence(InitialAgentModel):
    status: str = Field(min_length=1)
    source: str | None = None
    version: str | None = None
    source_date: date | None = None
    evidence_id: str | None = None
    licence: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)


class InitialInteractionCounterpart(InitialAgentModel):
    target_agent_id: str
    display_name: str
    relationship: str
    relationship_kind: str
    weight: float = Field(ge=-1, le=1)
    trust: float | None = Field(default=None, ge=-1, le=1)
    similarity: float | None = Field(default=None, ge=-1, le=1)
    evidence: InitialInteractionEvidence
    specific_place: str | None = None
    target_specific_place: str | None = None
    same_specific_place: bool | None
    in_person_eligibility: Literal["eligible", "ineligible", "unknown"]
    eligibility_reason: str = Field(min_length=1)
    applicable_rule_ids: list[str]


class InitialInteractionFactor(InitialAgentModel):
    kind: Literal["base", "relationship", "co_location", "place", "time", "context"]
    condition: str = Field(min_length=1)
    factor_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float = Field(ge=0, le=1)
    provenance: InitialInteractionEvidence


class InitialInteractionRule(InitialAgentModel):
    rule_id: str = Field(min_length=1)
    source_action: str = Field(min_length=1)
    interaction_type: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    interaction_tree_id: str | None = None
    formula: str = Field(min_length=1)
    factors: list[InitialInteractionFactor]


class InitialInteractionContext(InitialAgentModel):
    program_status: Literal["absent", "draft", "confirmed"]
    program_version: str | None = None
    history_available: bool = False
    history_message: str = Field(min_length=1)
    counterparts: list[InitialInteractionCounterpart]
    rules: list[InitialInteractionRule]


class HouseholdMember(InitialAgentModel):
    agent_id: str
    display_name: str
    age: float | None = Field(default=None, ge=0)
    relationship: str
    agent_types: list[str]


class AgentHousehold(InitialAgentModel):
    household_id: str
    members: list[HouseholdMember]


class InitialAgentListItem(InitialAgentModel):
    agent_id: str
    display_name: str
    agent_types: list[str] = Field(min_length=1)
    age: float | None = Field(default=None, ge=0)
    sex: str
    country: str
    city: str
    current_location: str | None = None
    household_id: str | None = None
    household_size: int = Field(ge=0)
    family_status: str


class InitialAgentDetail(InitialAgentListItem):
    location: AgentLocation
    household: AgentHousehold | None = None
    family_relationships: list[FamilyRelationship]
    traits: dict[str, Any]
    initial_states: dict[str, str]
    occupation: str | None = None
    income: str | int | float | None = None
    education: str | None = None
    health: str | None = None
    routines: list[RoutineLink]
    decision_trees: list[DecisionTreeLink]
    interaction_context: InitialInteractionContext
    representative_weight: float = Field(gt=0)


class InitialAgentFacets(InitialAgentModel):
    agent_types: list[str]
    countries: list[str]
    cities: list[str]
    family_statuses: list[str]


class InitialAgentQuery(InitialAgentModel):
    search: str = ""
    agent_type: str | None = None
    country: str | None = None
    city: str | None = None
    age_min: float | None = Field(default=None, ge=0)
    age_max: float | None = Field(default=None, ge=0)
    household: str | None = None
    family_status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def valid_age_range(self):
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("Minimum age cannot exceed maximum age")
        return self


class InitialAgentPage(InitialAgentModel):
    items: list[InitialAgentListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)
    facets: InitialAgentFacets


def text_trait(agent: AgentRecord, key: str) -> str | None:
    value = agent.traits.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def numeric_age(agent: AgentRecord) -> float | None:
    value = agent.traits.get("age")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def agent_types(agent: AgentRecord) -> list[str]:
    values = agent.traits.get("agent_types")
    if isinstance(values, list):
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if normalized:
            return list(dict.fromkeys(normalized))
    agent_type = text_trait(agent, "agent_type")
    return [agent_type or agent.role]


def family_status(agent: AgentRecord) -> str:
    explicit = text_trait(agent, "family_status")
    if explicit:
        return explicit
    labels = agent.traits.get("family_relationships")
    relationship_labels = {
        str(value).lower() for value in labels.values()
    } if isinstance(labels, dict) else set()
    if relationship_labels & {"spouse", "wife", "husband", "partner"}:
        return "partnered"
    if relationship_labels & {"daughter", "son", "child"}:
        return "parent"
    if relationship_labels & {"mother", "father", "parent"}:
        return "child"
    if any(relationship.kind == "family" for relationship in agent.relationships):
        return "family"
    if text_trait(agent, "household_id"):
        return "household"
    return "unknown"


def links_for_types[T](
    types: list[str],
    links_by_type: Mapping[str, Sequence[T]],
    identity,
) -> list[T]:
    resolved: list[T] = []
    seen: set[str] = set()
    for agent_type in types:
        for link in links_by_type.get(agent_type, []):
            link_id = identity(link)
            if link_id in seen:
                continue
            seen.add(link_id)
            resolved.append(link)
    return resolved


def _specific_place(agent: AgentRecord) -> str | None:
    value = agent.states.get("location") or text_trait(agent, "current_location")
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _specific_place_kind(agent: AgentRecord) -> str | None:
    explicit = text_trait(agent, "specific_place_kind") or text_trait(agent, "place_kind")
    if explicit:
        return explicit
    place = _specific_place(agent)
    if place is None:
        return None
    return "home" if place.startswith("home:") else "building"


def _evidence_view(
    provenance: InteractionFactorProvenance | None,
    status: str,
    evidence_id: str | None,
) -> InitialInteractionEvidence:
    if provenance is None:
        return InitialInteractionEvidence(status=status, evidence_id=evidence_id)
    return InitialInteractionEvidence(
        status=status,
        source=provenance.source,
        version=provenance.version,
        source_date=provenance.source_date,
        evidence_id=evidence_id or provenance.evidence_id,
        licence=provenance.licence,
        uncertainty=provenance.uncertainty,
    )


def _factor_view(
    kind: Literal["base", "relationship", "co_location", "place", "time", "context"],
    condition: str,
    factor: InteractionFactor,
) -> InitialInteractionFactor:
    return InitialInteractionFactor(
        kind=kind,
        condition=condition,
        factor_id=factor.id,
        label=factor.label,
        value=factor.value,
        provenance=_evidence_view(
            factor.provenance,
            factor.provenance.status,
            factor.provenance.evidence_id,
        ),
    )


def _relationship_allowed(rule: InteractionRule, relationship_kind: str) -> bool:
    return not rule.allowed_relationships or relationship_kind in rule.allowed_relationships


def _place_allowed(rule: InteractionRule, place_kind: str | None) -> bool | None:
    if not rule.allowed_place_kinds:
        return True
    if place_kind is None:
        return None
    return place_kind in rule.allowed_place_kinds


def _rule_applies_now(
    rule: InteractionRule,
    relationship_kind: str,
    place_kind: str | None,
    same_specific_place: bool,
) -> bool:
    if not _relationship_allowed(rule, relationship_kind):
        return False
    if _place_allowed(rule, place_kind) is not True:
        return False
    return rule.channel != "in_person" or same_specific_place


def _in_person_eligibility(
    program: InteractionProgramDefinition | None,
    relationship_kind: str,
    place_kind: str | None,
    specific_place: str | None,
    target_specific_place: str | None,
) -> tuple[Literal["eligible", "ineligible", "unknown"], str]:
    if specific_place is None or target_specific_place is None:
        return "unknown", "An exact current place is missing for one or both agents."
    if specific_place != target_specific_place:
        return "ineligible", "The agents are currently at different exact places."
    if program is None or program.status != "confirmed":
        return "unknown", "No confirmed interaction program can establish in-person eligibility."
    matching = [
        rule
        for rule in program.rules
        if rule.channel == "in_person" and _relationship_allowed(rule, relationship_kind)
    ]
    if not matching:
        return "ineligible", "No confirmed in-person rule allows this relationship kind."
    place_matches = [_place_allowed(rule, place_kind) for rule in matching]
    if True in place_matches:
        return (
            "eligible",
            "Both agents are currently at the same exact place and a confirmed "
            "in-person rule applies.",
        )
    if None in place_matches:
        return "unknown", "The exact place kind needed by a confirmed in-person rule is unknown."
    return "ineligible", "No confirmed in-person rule allows the current place kind."


def _rule_factors(
    rule: InteractionRule,
    relationship_kinds: set[str],
    colocation_keys: set[str],
    place_kind: str | None,
) -> list[InitialInteractionFactor]:
    factors = [_factor_view("base", "all eligible pairs", rule.base_factor)]
    factors.extend(
        _factor_view("relationship", relationship_kind, factor)
        for relationship_kind, factor in sorted(rule.relationship_factors.items())
        if relationship_kind in relationship_kinds
    )
    factors.extend(
        _factor_view("co_location", condition.replace("_", " "), factor)
        for condition, factor in sorted(rule.colocation_factors.items())
        if condition in colocation_keys
    )
    if place_kind is not None and place_kind in rule.place_factors:
        factors.append(_factor_view("place", place_kind, rule.place_factors[place_kind]))
    weekday_names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    factors.extend(
        _factor_view(
            "time",
            f"{', '.join(weekday_names[day] for day in window.weekdays)} "
            f"{window.start_hour:g}:00–{window.end_hour:g}:00",
            window.factor,
        )
        for window in rule.time_factors
    )
    factors.extend(
        _factor_view("context", factor.label, factor) for factor in rule.context_factors
    )
    return factors


def _rule_view(
    rule: InteractionRule,
    relationship_kinds: set[str],
    colocation_keys: set[str],
    place_kind: str | None,
) -> InitialInteractionRule:
    context_term = " × context" if rule.context_factors else ""
    return InitialInteractionRule(
        rule_id=rule.id,
        source_action=rule.source_action,
        interaction_type=rule.interaction_type,
        channel=rule.channel,
        interaction_tree_id=rule.interaction_tree_id,
        formula=(
            f"P({rule.interaction_type} | {rule.source_action}) = base × relationship "
            f"× co-location × place × time{context_term}"
        ),
        factors=_rule_factors(rule, relationship_kinds, colocation_keys, place_kind),
    )


def _interaction_context(
    agent: AgentRecord,
    agents_by_id: Mapping[str, AgentRecord],
    program: InteractionProgramDefinition | None,
) -> InitialInteractionContext:
    program_status = program.status if program is not None else "absent"
    confirmed_rules = program.rules if program is not None and program.status == "confirmed" else ()
    evidence_by_kind = {
        evidence.kind: evidence for evidence in (program.relationship_evidence if program else ())
    }
    labels_value = agent.traits.get("family_relationships")
    labels = labels_value if isinstance(labels_value, dict) else {}
    specific_place = _specific_place(agent)
    place_kind = _specific_place_kind(agent)
    counterparts = []
    relationship_kinds = set()
    colocation_keys = set()
    for relationship in agent.relationships:
        target = agents_by_id.get(relationship.target_id)
        target_specific_place = _specific_place(target) if target is not None else None
        same_specific_place = (
            specific_place == target_specific_place
            if specific_place is not None and target_specific_place is not None
            else None
        )
        if same_specific_place is True:
            colocation_keys.add("same_specific_place")
        elif same_specific_place is False:
            colocation_keys.add("different_specific_place")
        relationship_kinds.add(relationship.kind)
        registered = evidence_by_kind.get(relationship.kind)
        provenance = (
            registered.provenance
            if registered is not None
            and relationship.evidence_id == registered.provenance.evidence_id
            else None
        )
        eligibility, eligibility_reason = _in_person_eligibility(
            program,
            relationship.kind,
            place_kind,
            specific_place,
            target_specific_place,
        )
        rule_ids = sorted(
            rule.id
            for rule in confirmed_rules
            if _rule_applies_now(
                rule,
                relationship.kind,
                place_kind,
                same_specific_place is True,
            )
        )
        counterparts.append(
            InitialInteractionCounterpart(
                target_agent_id=relationship.target_id,
                display_name=(text_trait(target, "name") if target else None)
                or f"Agent {relationship.target_id[:8]}",
                relationship=str(labels.get(relationship.target_id, relationship.kind)),
                relationship_kind=relationship.kind,
                weight=relationship.weight,
                trust=relationship.trust,
                similarity=relationship.similarity,
                evidence=_evidence_view(
                    provenance,
                    relationship.evidence_status or "unknown",
                    relationship.evidence_id,
                ),
                specific_place=specific_place,
                target_specific_place=target_specific_place,
                same_specific_place=same_specific_place,
                in_person_eligibility=eligibility,
                eligibility_reason=eligibility_reason,
                applicable_rule_ids=rule_ids,
            )
        )
    relevant_rules = [
        rule
        for rule in confirmed_rules
        if any(_relationship_allowed(rule, kind) for kind in relationship_kinds)
    ]
    return InitialInteractionContext(
        program_status=program_status,
        program_version=program.version if program is not None else None,
        history_message=(
            "No interaction frequency or history exists before a run. Run the simulation, "
            "then open Run Results for recorded interactions."
        ),
        counterparts=sorted(
            counterparts,
            key=lambda counterpart: (counterpart.display_name, counterpart.target_agent_id),
        ),
        rules=[
            _rule_view(rule, relationship_kinds, colocation_keys, place_kind)
            for rule in sorted(relevant_rules, key=lambda item: item.id)
        ],
    )


class InitialAgentCatalog:
    def __init__(self, records: Sequence[InitialAgentDetail]):
        by_id = {record.agent_id: record for record in records}
        if len(by_id) != len(records):
            raise ValueError("Initial agent IDs must be unique")
        self._records = tuple(
            sorted(records, key=lambda record: (record.display_name, record.agent_id))
        )
        self._by_id = by_id
        self._facets = InitialAgentFacets(
            agent_types=sorted({value for record in records for value in record.agent_types}),
            countries=sorted({record.country for record in records}),
            cities=sorted({record.city for record in records}),
            family_statuses=sorted({record.family_status for record in records}),
        )

    @classmethod
    def from_population(
        cls,
        population: PopulationTable,
        routines_by_type: Mapping[str, Sequence[RoutineLink]] | None = None,
        decision_trees_by_type: Mapping[str, Sequence[DecisionTreeLink]] | None = None,
        interaction_program: InteractionProgramDefinition | None = None,
    ) -> "InitialAgentCatalog":
        routines = routines_by_type or {}
        decision_trees = decision_trees_by_type or {}
        agents_by_id = {agent.agent_id: agent for agent in population.agents}
        household_agents: dict[str, list[AgentRecord]] = defaultdict(list)
        for agent in population.agents:
            household_id = text_trait(agent, "household_id")
            if household_id:
                household_agents[household_id].append(agent)
        records = [
            cls._record(
                agent,
                agents_by_id,
                household_agents,
                routines,
                decision_trees,
                interaction_program,
            )
            for agent in population.agents
        ]
        return cls(records)

    @staticmethod
    def _record(
        agent: AgentRecord,
        agents_by_id: Mapping[str, AgentRecord],
        household_agents: Mapping[str, Sequence[AgentRecord]],
        routines_by_type: Mapping[str, Sequence[RoutineLink]],
        decision_trees_by_type: Mapping[str, Sequence[DecisionTreeLink]],
        interaction_program: InteractionProgramDefinition | None,
    ) -> InitialAgentDetail:
        types = agent_types(agent)
        country = text_trait(agent, "country") or agent.place
        city = text_trait(agent, "city") or agent.place
        display_name = text_trait(agent, "name") or f"Agent {agent.agent_id[:8]}"
        household_id = text_trait(agent, "household_id")
        relationship_labels = agent.traits.get("family_relationships")
        labels = relationship_labels if isinstance(relationship_labels, dict) else {}
        relationships = []
        for relationship in agent.relationships:
            if relationship.kind not in {"family", "household"}:
                continue
            target = agents_by_id.get(relationship.target_id)
            relationships.append(
                FamilyRelationship(
                    target_agent_id=relationship.target_id,
                    display_name=(
                        text_trait(target, "name") if target else None
                    ) or f"Agent {relationship.target_id[:8]}",
                    relationship=str(labels.get(relationship.target_id, relationship.kind)),
                    age=numeric_age(target) if target else None,
                    weight=relationship.weight,
                )
            )
        members = []
        for member in household_agents.get(household_id or "", []):
            member_name = text_trait(member, "name") or f"Agent {member.agent_id[:8]}"
            relationship = "self" if member.agent_id == agent.agent_id else str(
                labels.get(member.agent_id, "household member")
            )
            members.append(
                HouseholdMember(
                    agent_id=member.agent_id,
                    display_name=member_name,
                    age=numeric_age(member),
                    relationship=relationship,
                    agent_types=agent_types(member),
                )
            )
        household = None
        if household_id:
            household = AgentHousehold(
                household_id=household_id,
                members=sorted(members, key=lambda member: (member.display_name, member.agent_id)),
            )
        current_location = agent.states.get("location") or text_trait(agent, "current_location")
        return InitialAgentDetail(
            agent_id=agent.agent_id,
            display_name=display_name,
            agent_types=types,
            age=numeric_age(agent),
            sex=text_trait(agent, "sex") or "unknown",
            country=country,
            city=city,
            current_location=current_location,
            household_id=household_id,
            household_size=len(members),
            family_status=family_status(agent),
            location=AgentLocation(
                country=country,
                region=text_trait(agent, "region"),
                city=city,
                neighbourhood=text_trait(agent, "neighbourhood"),
                specific_place=current_location,
            ),
            household=household,
            family_relationships=sorted(
                relationships,
                key=lambda relationship: (relationship.display_name, relationship.target_agent_id),
            ),
            traits=dict(agent.traits),
            initial_states=dict(agent.states),
            occupation=text_trait(agent, "occupation"),
            income=agent.traits.get("income"),
            education=text_trait(agent, "education"),
            health=agent.states.get("health") or text_trait(agent, "health"),
            routines=links_for_types(types, routines_by_type, lambda link: link.routine_id),
            decision_trees=links_for_types(
                types, decision_trees_by_type, lambda link: link.tree_id
            ),
            interaction_context=_interaction_context(agent, agents_by_id, interaction_program),
            representative_weight=agent.weight,
        )

    def search(self, query: InitialAgentQuery | None = None) -> InitialAgentPage:
        selected = query or InitialAgentQuery()
        search = selected.search.strip().casefold()
        matches = []
        for record in self._records:
            searchable = " ".join(
                [record.agent_id, record.display_name, record.occupation or "", *record.agent_types]
            ).casefold()
            if search and search not in searchable:
                continue
            if selected.agent_type and selected.agent_type not in record.agent_types:
                continue
            if selected.country and selected.country != record.country:
                continue
            if selected.city and selected.city != record.city:
                continue
            if selected.age_min is not None and (
                record.age is None or record.age < selected.age_min
            ):
                continue
            if selected.age_max is not None and (
                record.age is None or record.age > selected.age_max
            ):
                continue
            if selected.household and selected.household.casefold() not in (
                record.household_id or ""
            ).casefold():
                continue
            if selected.family_status and selected.family_status != record.family_status:
                continue
            matches.append(record)
        total = len(matches)
        start = (selected.page - 1) * selected.page_size
        page_items = matches[start : start + selected.page_size]
        return InitialAgentPage(
            items=[
                InitialAgentListItem(
                    **item.model_dump(include=set(InitialAgentListItem.model_fields))
                )
                for item in page_items
            ],
            total=total,
            page=selected.page,
            page_size=selected.page_size,
            pages=ceil(total / selected.page_size) if total else 0,
            facets=self._facets,
        )

    def detail(self, agent_id: str) -> InitialAgentDetail:
        try:
            return self._by_id[agent_id]
        except KeyError:
            raise KeyError(agent_id) from None
