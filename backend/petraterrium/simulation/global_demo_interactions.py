from collections import defaultdict
from datetime import date

from ..population import PopulationTable, Relationship
from .interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    TimeFactorWindow,
)

GLOBAL_DEMO_INTERACTION_VERSION = "global-demo-cross-country-v1"
GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID = "global-demo-synthetic-friend-link-v1"
GLOBAL_DEMO_INTERACTION_REASON = (
    "Shipped default-estimated synthetic cross-country demo contact. Its probability "
    "is base × relationship × colocation × place × time. The relationship and factor "
    "values are neutral structural defaults, not measured social evidence. Replace them "
    "with place-specific joint relationship and contact data before analytical use."
)


def _provenance(evidence_id: str) -> InteractionFactorProvenance:
    return InteractionFactorProvenance(
        source=GLOBAL_DEMO_INTERACTION_REASON,
        version=GLOBAL_DEMO_INTERACTION_VERSION,
        source_date=date(2026, 10, 27),
        evidence_id=evidence_id,
        status="default_estimated",
        uncertainty=1,
    )


def _factor(identity: str, label: str, value: float) -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=label,
        value=value,
        provenance=_provenance(f"global-demo:{identity}"),
    )


def global_demo_interaction_program() -> InteractionProgramDefinition:
    relationship = RelationshipKindEvidence(
        kind="friend",
        weight=0,
        trust=0,
        similarity=0,
        provenance=_provenance(GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID),
    )
    rule = InteractionRule(
        id="global-demo-cross-country-contact",
        source_action="choose exercise or recovery",
        interaction_type="cross_country_social_contact",
        channel="online",
        max_targets_per_initiator=1,
        allowed_relationships=("friend",),
        allowed_place_kinds=("home",),
        base_factor=_factor(
            "global-demo-contact-base",
            "Neutral synthetic contact opportunity",
            0.5,
        ),
        relationship_factors={
            "friend": _factor(
                "global-demo-synthetic-friend",
                "Synthetic cross-country friend link",
                0.5,
            )
        },
        colocation_factors={
            "different_specific_place": _factor(
                "global-demo-remote-location",
                "Remote contact across specific places",
                1,
            )
        },
        place_factors={
            "home": _factor(
                "global-demo-home-online",
                "Online contact from home",
                1,
            )
        },
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=17,
                end_hour=21,
                factor=_factor(
                    "global-demo-evening-window",
                    "Shipped daily demo window",
                    1,
                ),
            ),
        ),
    )
    return InteractionProgramDefinition(
        version=GLOBAL_DEMO_INTERACTION_VERSION,
        status="confirmed",
        relationship_evidence=(relationship,),
        rules=(rule,),
    )


def attach_global_demo_cross_country_relationships(
    population: PopulationTable,
) -> PopulationTable:
    agents_by_country = defaultdict(list)
    for agent in population.agents:
        country = str(agent.traits.get("country_id", "")).strip()
        if not country:
            raise ValueError(f"Agent {agent.agent_id} has no country_id")
        agents_by_country[country].append(agent)
    countries = sorted(agents_by_country)
    if len(countries) < 2:
        raise ValueError("Cross-country demo interactions require at least two countries")
    ordered_agents = [
        agent
        for country in countries
        for agent in sorted(agents_by_country[country], key=lambda item: item.agent_id)
    ]
    if len(ordered_agents) % 2:
        raise ValueError("Cross-country demo relationship pairing requires an even population")
    largest_country = max(len(agents) for agents in agents_by_country.values())
    if largest_country > len(ordered_agents) // 2:
        raise ValueError(
            "Cross-country demo relationship pairing requires every country to contain "
            "at most half of the selected population"
        )
    target_by_agent = {}
    midpoint = len(ordered_agents) // 2
    for source, target in zip(
        ordered_agents[:midpoint], ordered_agents[midpoint:], strict=True
    ):
        source_country = str(source.traits["country_id"])
        target_country = str(target.traits["country_id"])
        if source_country == target_country:
            raise ValueError("Cross-country demo relationship pairing produced a same-country pair")
        target_by_agent[source.agent_id] = target
        target_by_agent[target.agent_id] = source
    updated_agents = []
    for agent in population.agents:
        target = target_by_agent[agent.agent_id]
        relationships = [
            relationship
            for relationship in agent.relationships
            if relationship.evidence_id != GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID
        ]
        relationships.append(
            Relationship(
                target_id=target.agent_id,
                kind="friend",
                weight=0,
                trust=0,
                similarity=0,
                evidence_id=GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID,
                evidence_status="default_estimated",
            )
        )
        updated_agents.append(agent.model_copy(update={"relationships": relationships}))
    return population.model_copy(update={"agents": updated_agents})
