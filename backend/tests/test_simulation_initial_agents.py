from petraterrium.population import AgentRecord, PopulationTable, Relationship
from petraterrium.simulation.initial_agents import (
    DecisionTreeLink,
    InitialAgentCatalog,
    InitialAgentQuery,
    RoutineLink,
)
from petraterrium.simulation.interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    TimeFactorWindow,
)


def interaction_provenance(evidence_id: str) -> InteractionFactorProvenance:
    return InteractionFactorProvenance(
        source="Canadian General Social Survey contact panel",
        version="2025-v1",
        source_date="2025-09-17",
        evidence_id=evidence_id,
        licence="Statistics Canada Open Licence",
        status="measured_joint",
        uncertainty=0.06,
    )


def interaction_factor(identity: str, value: float) -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=identity.replace("-", " "),
        value=value,
        provenance=interaction_provenance(identity),
    )


def interaction_program() -> InteractionProgramDefinition:
    return InteractionProgramDefinition(
        version="contact-panel-2025-v1",
        status="confirmed",
        relationship_evidence=(
            RelationshipKindEvidence(
                kind="family",
                weight=0.95,
                trust=0.82,
                similarity=0.67,
                provenance=interaction_provenance("family-profile"),
            ),
        ),
        rules=(
            InteractionRule(
                id="family-conversation",
                source_action="return-home",
                interaction_type="talk",
                channel="in_person",
                max_targets_per_initiator=1,
                allowed_relationships=("family",),
                allowed_place_kinds=("home",),
                base_factor=interaction_factor("hourly-contact", 0.4),
                relationship_factors={
                    "family": interaction_factor("family-rate", 0.9)
                },
                colocation_factors={
                    "same_specific_place": interaction_factor("same-place", 1)
                },
                place_factors={"home": interaction_factor("home-rate", 0.8)},
                time_factors=(
                    TimeFactorWindow(
                        weekdays=(0, 1, 2, 3, 4, 5, 6),
                        start_hour=17,
                        end_hour=23,
                        factor=interaction_factor("evening-rate", 0.7),
                    ),
                ),
            ),
        ),
    )


def agent(
    agent_id: str,
    age: int,
    agent_type: str,
    relationship_labels: dict[str, str],
    relationships: list[Relationship],
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        place="CA",
        latitude=49.28,
        longitude=-123.12,
        role=agent_type,
        log_tier="spotlight",
        traits={
            "agent_types": [agent_type, "FamilyMember"],
            "age": age,
            "sex": "female" if agent_id in {"agent-avery", "agent-mira"} else "male",
            "country": "Canada",
            "region": "Northern America",
            "city": "Vancouver",
            "household_id": "household-1",
            "family_status": "parent" if age == 40 else "child",
            "family_relationships": relationship_labels,
            "occupation": "Founder" if agent_type == "BusinessAgent" else "Student",
            "years_of_education": 16 if age == 40 else max(0, age - 5),
            "education_isced": 6 if age == 40 else 1,
            "education_country_label": "Bachelor's degree" if age == 40 else "Primary school",
            "education_mapping_version": "ca-isced-2023-v1",
            "education_status": "measured_marginal",
            "education_source": "Imported Canadian education mapping",
            "education_source_population": "Canadian residents",
            "education_uncertainty": 0.04,
            "specialization_threshold_years": 12,
            "specialization": "business" if age == 40 else None,
            "finance_currency": "CAD",
            "finance_status": "measured_joint",
            "finance_source": "Imported Canadian finance joint table",
            "finance_source_version": "2023-v1",
            "finance_source_population": "Canadian residents",
            "finance_uncertainty": 0.06,
            "big_five_extraversion": 0.72 if agent_type == "BusinessAgent" else 0.41,
            "age_evidence_scope": "country_measured",
            "sex_evidence_scope": "country_measured",
            "education_evidence_scope": "country_measured",
            "occupation_evidence_scope": "unknown",
            "personality_evidence_scope": "country_measured",
            "values_evidence_scope": "regional_imputed",
            "finance_evidence_scope": "country_measured",
        },
        states={
            "health": "0.9",
            "location": "home:household-1",
            "finance.money": "40000" if age == 40 else "500",
            "finance.income": "125000" if age == 40 else "0",
            "finance.expenses": "70000" if age == 40 else "0",
            "finance.savings": "80000" if age == 40 else "100",
            "finance.debt": "20000" if age == 40 else "0",
        },
        behaviour={},
        behaviour_provenance={},
        relationships=relationships,
        weight=1,
    )


def population() -> PopulationTable:
    members = [
        agent(
            "agent-avery",
            40,
            "BusinessAgent",
            {"agent-sam": "spouse", "agent-mira": "daughter", "agent-noah": "son"},
            [
                Relationship(
                    target_id="agent-sam",
                    kind="family",
                    weight=0.95,
                    trust=0.82,
                    similarity=0.67,
                    evidence_id="family-profile",
                    evidence_status="measured_joint",
                ),
                Relationship(target_id="agent-mira", kind="family", weight=0.9),
                Relationship(target_id="agent-noah", kind="family", weight=0.9),
            ],
        ),
        agent(
            "agent-sam",
            41,
            "WorkerAgent",
            {"agent-avery": "spouse", "agent-mira": "daughter", "agent-noah": "son"},
            [Relationship(target_id="agent-avery", kind="family", weight=0.95)],
        ),
        agent(
            "agent-mira",
            4,
            "StudentAgent",
            {"agent-avery": "mother", "agent-sam": "father", "agent-noah": "brother"},
            [Relationship(target_id="agent-avery", kind="family", weight=0.9)],
        ),
        agent(
            "agent-noah",
            6,
            "StudentAgent",
            {"agent-avery": "mother", "agent-sam": "father", "agent-mira": "sister"},
            [Relationship(target_id="agent-avery", kind="family", weight=0.9)],
        ),
    ]
    return PopulationTable(population_id="initial", version="v1", seed=7, agents=members)


def catalog() -> InitialAgentCatalog:
    return InitialAgentCatalog.from_population(
        population(),
        routines_by_type={
            "BusinessAgent": [
                RoutineLink(
                    routine_id="business-weekday",
                    name="Business weekday",
                    agent_type="BusinessAgent",
                )
            ],
            "FamilyMember": [
                RoutineLink(
                    routine_id="family-evening",
                    name="Family evening",
                    agent_type="FamilyMember",
                    inherited_from="FamilyMember",
                )
            ],
        },
        decision_trees_by_type={
            "BusinessAgent": [
                DecisionTreeLink(
                    tree_id="business-social",
                    name="Business social decisions",
                    agent_type="BusinessAgent",
                )
            ]
        },
        interaction_program=interaction_program(),
    )


def test_initial_agent_catalog_searches_and_filters_without_loading_every_detail() -> None:
    page = catalog().search(
        InitialAgentQuery(
            search="avery",
            agent_type="BusinessAgent",
            country="Canada",
            city="Vancouver",
            age_min=35,
            age_max=45,
            household="household-1",
            family_status="parent",
            page=1,
            page_size=2,
        )
    )

    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].agent_id == "agent-avery"
    assert page.items[0].current_location == "home:household-1"
    assert "BusinessAgent" in page.facets.agent_types
    assert page.pages == 1
    assert page.evidence_summary.country_agent_counts == {"Canada": 4}
    assert page.evidence_summary.region_agent_counts == {"Northern America": 4}
    assert page.evidence_summary.fields["age"].own_country_inherited == ["Canada"]
    assert page.evidence_summary.fields["values"].regional_imputed == ["Canada"]
    assert page.evidence_summary.fields["occupation"].estimated == ["Canada"]


def test_initial_agent_detail_links_household_family_routines_and_decision_trees() -> None:
    detail = catalog().detail("agent-avery")

    assert detail.agent_types == ["BusinessAgent", "FamilyMember"]
    assert detail.household is not None
    assert [(member.agent_id, member.age) for member in detail.household.members] == [
        ("agent-avery", 40),
        ("agent-mira", 4),
        ("agent-noah", 6),
        ("agent-sam", 41),
    ]
    assert {relationship.relationship for relationship in detail.family_relationships} == {
        "daughter",
        "son",
        "spouse",
    }
    assert [routine.routine_id for routine in detail.routines] == [
        "business-weekday",
        "family-evening",
    ]
    assert detail.decision_trees[0].tree_id == "business-social"
    assert detail.occupation == "Founder"
    assert detail.education_profile.years_of_education == 16
    assert detail.education_profile.country_label == "Bachelor's degree"
    assert detail.education_profile.specialization == "business"
    assert detail.finances.income.value == 125000
    assert detail.finances.money.value == 40000
    assert detail.health == "0.9"
    assert next(
        value for value in detail.state_vector.values if value.state_id == "health"
    ).value == 0.9
    assert detail.traits["big_five_extraversion"] == 0.72
    assert "name" not in detail.traits


def test_initial_agent_detail_reports_truthful_pre_run_interaction_context() -> None:
    detail = catalog().detail("agent-avery")

    assert detail.interaction_context.program_status == "confirmed"
    assert detail.interaction_context.program_version == "contact-panel-2025-v1"
    sam = next(
        item
        for item in detail.interaction_context.counterparts
        if item.target_agent_id == "agent-sam"
    )
    assert sam.same_specific_place is True
    assert sam.specific_place == "home:household-1"
    assert sam.in_person_eligibility == "eligible"
    assert sam.relationship_kind == "family"
    assert sam.weight == 0.95
    assert sam.trust == 0.82
    assert sam.similarity == 0.67
    assert sam.evidence.status == "measured_joint"
    assert sam.evidence.source == "Canadian General Social Survey contact panel"
    assert sam.applicable_rule_ids == ["family-conversation"]
    rule = detail.interaction_context.rules[0]
    assert rule.formula == (
        "P(talk | return-home) = base × relationship × co-location × place × time"
    )
    assert {factor.kind for factor in rule.factors} == {
        "base",
        "relationship",
        "co_location",
        "place",
        "time",
    }
    assert all(
        factor.provenance.source == "Canadian General Social Survey contact panel"
        for factor in rule.factors
    )
    assert detail.interaction_context.history_available is False
    assert "No interaction frequency or history exists before a run" in (
        detail.interaction_context.history_message
    )


def test_initial_agent_catalog_pages_and_reports_unknown_agent() -> None:
    initial_agents = catalog()
    first = initial_agents.search(InitialAgentQuery(page=1, page_size=2))
    second = initial_agents.search(InitialAgentQuery(page=2, page_size=2))

    assert first.total == 4
    assert first.pages == 2
    assert {item.agent_id for item in first.items}.isdisjoint(
        item.agent_id for item in second.items
    )

    try:
        initial_agents.detail("missing")
    except KeyError as error:
        assert error.args == ("missing",)
    else:
        raise AssertionError("Missing agents must not produce a fabricated detail")
