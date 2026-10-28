import pytest

from petraterrium.population import AgentRecord, PopulationTable, Relationship
from petraterrium.simulation.interactions import (
    InteractionFactorProvenance,
    RelationshipKindEvidence,
)
from petraterrium.simulation.population_generation import (
    EvidenceReference,
    HouseholdMemberSeed,
    HouseholdSeed,
    InitialPopulationRequest,
    InitialPopulationValidationError,
    materialize_initial_population,
    validate_initial_population,
)


def evidence() -> list[EvidenceReference]:
    return [
        EvidenceReference(
            evidence_id="ca-household-joint-2024",
            source="Statistics Canada household microdata",
            source_version="2021-census-pumf-v1",
            observed_at="2021-05-11",
            licence="Statistics Canada Open Licence",
            place="CA",
            status="measured_joint",
            fields=[
                "age",
                "sex",
                "household_composition",
                "family_relationships",
                "occupation",
                "income",
                "education",
                "health",
            ],
            uncertainty="Weighted public-use microdata sample",
        )
    ]


def family_household() -> HouseholdSeed:
    shared_evidence = {
        field: "ca-household-joint-2024"
        for field in (
            "age",
            "sex",
            "household_composition",
            "family_relationships",
            "occupation",
            "income",
            "education",
            "health",
        )
    }
    return HouseholdSeed(
        template_id="family-40-wife-two-kids",
        place="CA",
        country="Canada",
        region="Northern America",
        city="Vancouver",
        neighbourhood="Kitsilano",
        latitude=49.2684,
        longitude=-123.1683,
        weight=1,
        evidence_id="ca-household-joint-2024",
        members=[
            HouseholdMemberSeed(
                member_id="reference",
                age=40,
                sex="male",
                relationship_to_reference="self",
                agent_types=["BusinessAgent", "FamilyMan"],
                traits={
                    "occupation": "Business owner",
                    "income": 125000,
                    "education": "Bachelor's degree",
                    "health": "good",
                    "big_five_extraversion": 0.71,
                },
                states={"health": "healthy"},
                field_evidence=shared_evidence,
            ),
            HouseholdMemberSeed(
                member_id="spouse",
                age=39,
                sex="female",
                relationship_to_reference="spouse",
                agent_types=["WorkerAgent", "FamilyMan"],
                traits={
                    "occupation": "Accountant",
                    "income": 78000,
                    "education": "Bachelor's degree",
                    "health": "good",
                },
                states={"health": "healthy"},
                field_evidence=shared_evidence,
            ),
            HouseholdMemberSeed(
                member_id="child-four",
                age=4,
                sex="female",
                relationship_to_reference="child",
                agent_types=["StudentAgent", "FamilyMember"],
                traits={
                    "occupation": "Preschool student",
                    "income": 0,
                    "education": "Early childhood",
                    "health": "good",
                },
                states={"health": "healthy"},
                field_evidence=shared_evidence,
            ),
            HouseholdMemberSeed(
                member_id="child-six",
                age=6,
                sex="male",
                relationship_to_reference="child",
                agent_types=["StudentAgent", "FamilyMember"],
                traits={
                    "occupation": "Primary student",
                    "income": 0,
                    "education": "Primary school",
                    "health": "good",
                },
                states={"health": "healthy"},
                field_evidence=shared_evidence,
            ),
        ],
    )


def request(seed: int = 23, target_agents: int = 4) -> InitialPopulationRequest:
    return InitialPopulationRequest(
        population_id="canada-demo",
        version="2026-10-27",
        seed=seed,
        target_agents=target_agents,
        household_templates=[family_household()],
        evidence=evidence(),
    )


def alternate_family_household() -> HouseholdSeed:
    original = family_household()
    ages = [55, 52, 14, 16]
    members = [
        member.model_copy(update={"age": ages[index]})
        for index, member in enumerate(original.members)
    ]
    return original.model_copy(
        update={
            "template_id": "family-55-spouse-two-teens",
            "city": "Toronto",
            "neighbourhood": "Danforth",
            "latitude": 43.6777,
            "longitude": -79.3522,
            "members": members,
        }
    )


def varied_request(seed: int) -> InitialPopulationRequest:
    base = request(seed=seed)
    return base.model_copy(
        update={
            "household_templates": [family_household(), alternate_family_household()]
        }
    )


def test_joint_household_materializes_four_linked_agents_instead_of_clones() -> None:
    result = materialize_initial_population(request())

    assert result.validation.valid
    assert len(result.population.agents) == 4
    assert len({agent.agent_id for agent in result.population.agents}) == 4
    assert {agent.traits["age"] for agent in result.population.agents} == {4, 6, 39, 40}
    assert all("name" not in agent.traits for agent in result.population.agents)
    assert len({agent.traits["initial_state_key"] for agent in result.population.agents}) == 4

    reference, spouse, *children = result.population.agents
    assert reference.traits["family_status"] == "parent"
    assert spouse.traits["family_status"] == "parent"
    assert {child.traits["family_status"] for child in children} == {"child"}
    assert reference.traits["family_relationships"][spouse.agent_id] == "wife"
    assert spouse.traits["family_relationships"][reference.agent_id] == "husband"
    assert {reference.traits["family_relationships"][child.agent_id] for child in children} == {
        "daughter",
        "son",
    }
    for child in children:
        assert child.traits["family_relationships"][reference.agent_id] == "father"
        assert child.traits["family_relationships"][spouse.agent_id] == "mother"
        assert child.traits["household_id"] == reference.traits["household_id"]
    assert all(
        len(agent.relationships) == 3 for agent in result.population.agents
    )
    assert result.provenance[reference.agent_id].sampling_basis == "measured_joint"
    assert result.provenance[reference.agent_id].field_evidence["age"].source == (
        "Statistics Canada household microdata"
    )


def test_household_relationships_attach_only_executable_registered_evidence() -> None:
    profile = RelationshipKindEvidence(
        kind="family",
        weight=0.86,
        trust=0.79,
        similarity=0.63,
        provenance=InteractionFactorProvenance(
            source="Measured family contact panel",
            version="2025-v1",
            source_date="2025-11-14",
            evidence_id="family-contact-panel-2025",
            licence="Test fixture",
            status="measured_joint",
            uncertainty=0.07,
        ),
    )

    result = materialize_initial_population(request(), (profile,))

    relationships = [
        relationship
        for agent in result.population.agents
        for relationship in agent.relationships
    ]
    assert relationships
    assert {
        (
            item.weight,
            item.trust,
            item.similarity,
            item.evidence_id,
            item.evidence_status,
        )
        for item in relationships
    } == {
        (0.86, 0.79, 0.63, "family-contact-panel-2025", "measured_joint")
    }


def test_materialization_is_deterministic_for_inputs_and_seed() -> None:
    first = materialize_initial_population(varied_request(seed=0))
    repeated = materialize_initial_population(varied_request(seed=0))
    changed_seed = materialize_initial_population(varied_request(seed=1))

    assert first.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert first.input_hash == repeated.input_hash
    assert first.input_hash != changed_seed.input_hash
    assert sorted(agent.traits["age"] for agent in first.population.agents) != sorted(
        agent.traits["age"] for agent in changed_seed.population.agents
    )


def test_reusing_one_household_template_is_rejected_as_clone_generation() -> None:
    with pytest.raises(InitialPopulationValidationError) as raised:
        materialize_initial_population(request(target_agents=8))

    assert "insufficient_unique_initial_states" in {
        item.code for item in raised.value.validation.issues
    }


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda household: setattr(household.members[2], "age", 45), "child_older_than_parent"),
        (lambda household: setattr(household.members[0], "age", 5), "parent_too_young"),
        (lambda household: setattr(household.members[1], "age", 95), "spouse_age_gap_implausible"),
    ],
)
def test_impossible_households_block_materialization(mutate, expected_code: str) -> None:
    payload = request().model_dump()
    household = payload["household_templates"][0]
    mutate_object = type("Mutable", (), {})()
    mutate_object.members = [type("Member", (), member)() for member in household["members"]]
    mutate(mutate_object)
    for source, changed in zip(household["members"], mutate_object.members, strict=True):
        source["age"] = changed.age
    invalid = InitialPopulationRequest.model_validate(payload)

    with pytest.raises(InitialPopulationValidationError) as raised:
        materialize_initial_population(invalid)

    assert expected_code in {issue.code for issue in raised.value.validation.issues}


def base_agent(
    agent_id: str,
    age: int,
    household_id: str,
    labels: dict[str, str],
    relationships: list[Relationship],
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        place="CA",
        latitude=49.2,
        longitude=-123.1,
        role="FamilyMember",
        log_tier="spotlight",
        traits={
            "age": age,
            "sex": "unknown",
            "household_id": household_id,
            "household_role": "child" if age < 18 else "parent",
            "family_relationships": labels,
            "initial_state_key": agent_id,
        },
        states={"location": f"home:{household_id}"},
        behaviour={},
        behaviour_provenance={},
        relationships=relationships,
        weight=1,
    )


def test_validation_rejects_duplicate_ids_and_nonreciprocal_family_links() -> None:
    parent = base_agent(
        "same",
        40,
        "household-1",
        {"child": "daughter"},
        [Relationship(target_id="child", kind="family", weight=1)],
    )
    duplicate = base_agent("same", 6, "household-1", {}, [])
    population = PopulationTable(
        population_id="invalid",
        version="v1",
        seed=1,
        agents=[parent, duplicate],
    )

    validation = validate_initial_population(population)

    assert not validation.valid
    assert {issue.code for issue in validation.issues} >= {
        "duplicate_agent_id",
        "unknown_relationship_target",
    }


def test_generated_identity_fields_do_not_make_cloned_states_unique() -> None:
    first = base_agent("first", 40, "household-1", {}, [])
    second = base_agent("second", 40, "household-2", {}, [])
    first = first.model_copy(
        update={
            "traits": {
                **first.traits,
                "specific_place": "home:household-1",
                "source_template_id": "template-one",
            }
        }
    )
    second = second.model_copy(
        update={
            "traits": {
                **second.traits,
                "specific_place": "home:household-2",
                "source_template_id": "template-two",
            }
        }
    )
    population = PopulationTable(
        population_id="cloned",
        version="v1",
        seed=1,
        agents=[first, second],
    )

    validation = validate_initial_population(population)

    assert "duplicate_initial_state" in {
        item.code for item in validation.issues
    }


def test_validation_rejects_a_household_role_that_disagrees_with_relationships() -> None:
    first = base_agent(
        "first",
        40,
        "household-1",
        {"second": "spouse"},
        [Relationship(target_id="second", kind="family", weight=1)],
    )
    second = base_agent(
        "second",
        39,
        "household-1",
        {"first": "spouse"},
        [Relationship(target_id="first", kind="family", weight=1)],
    )
    population = PopulationTable(
        population_id="invalid-role",
        version="v1",
        seed=1,
        agents=[first, second],
    )

    validation = validate_initial_population(population)

    assert "inconsistent_household_role" in {
        issue.code for issue in validation.issues
    }


def test_population_size_never_splits_a_household() -> None:
    with pytest.raises(InitialPopulationValidationError) as raised:
        materialize_initial_population(request(target_agents=5))

    assert "population_size_unreachable" in {
        issue.code for issue in raised.value.validation.issues
    }
