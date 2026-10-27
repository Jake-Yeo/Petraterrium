import json
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_catalog import FeatureCatalogStore
from petraterrium.atlas.features import canonical_feature_registry
from petraterrium.atlas.joint_estimates import (
    FeatureFilter,
    MeasuredHouseholdMember,
    MeasuredJointData,
    PlaceSelector,
)
from petraterrium.dsl import Evidence, FeatureDistribution
from petraterrium.rust_core import RustCoreClient
from petraterrium.simulation.agent_types import AgentTypeDefinition, AgentTypeMember
from petraterrium.simulation.atlas_population import (
    AtlasPopulationMaterializer,
    AtlasPopulationRequest,
)
from petraterrium.simulation.decision_evidence import (
    DecisionEdgeTemplate,
    DecisionFactorEvidence,
    DecisionNodeTemplate,
    DecisionProbabilityFormula,
    DecisionTreeTemplate,
    EvidencePlace,
    EvidencePredicate,
    ProbabilityFactor,
    ResearchCitation,
)
from petraterrium.simulation.interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    TimeFactorWindow,
)
from petraterrium.simulation.population_routes import create_population_router
from petraterrium.simulation.registry_store import (
    DecisionEvidenceRegistryDefinition,
    SimulationRegistryStore,
)
from petraterrium.simulation.routines import (
    RoutineDefinition,
    RoutineEvidence,
    RoutineRegistryDefinition,
    RoutineSchedule,
    RoutineStep,
)
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import SimulationPlaceScope, SimulationRunConfig
from petraterrium.simulation.tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
)


def distribution(
    feature_id: str,
    *,
    values: dict[str, float] | None = None,
    mean: float | None = None,
    standard_deviation: float | None = None,
) -> FeatureDistribution:
    return FeatureDistribution(
        feature_id=feature_id,
        level="country",
        place="CA",
        population="Canada residents",
        population_count=40_000_000,
        coverage_percent=100,
        values=values or {},
        mean=mean,
        standard_deviation=standard_deviation,
        provenance=Evidence(
            source=f"Test {feature_id} source",
            version="test-v1",
            status="present",
            uncertainty=0.1,
            source_date="2024-01-01",
        ),
    )


def insert_import(
    store: AtlasStore,
    import_id: str,
    scope: str,
    observations: list[tuple[str, dict[str, float], str]],
) -> None:
    now = datetime.now(UTC).isoformat()
    metadata = {
        "license": "Test open licence",
        "population": "Canada residents",
    }
    with store.connection() as connection:
        connection.execute(
            """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
            uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
            audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
            created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                f"Source {import_id}",
                "2024-01-01",
                "2024-02-01",
                "test-v1",
                scope,
                "test",
                "marginals",
                "test.json",
                len(observations),
                "committed",
                json.dumps(metadata),
                "[]",
                "[]",
                "{}",
                json.dumps({"valid": True}),
                "[]",
                None,
                1,
                now,
            ),
        )
        connection.executemany(
            """INSERT INTO observations(
            import_id,geo_level,geo_key,field,value_json,unit,evidence_status
            ) VALUES(?,?,?,?,?,?,?)""",
            [
                (
                    import_id,
                    "country",
                    "CA",
                    field,
                    json.dumps(value),
                    unit,
                    "measured",
                )
                for field, value, unit in observations
            ],
        )
        store.bump(connection)


def seeded_store(tmp_path) -> AtlasStore:
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    with store.connection() as connection:
        connection.execute("INSERT INTO countries VALUES('CA','Canada')")
        connection.execute(
            """INSERT INTO cities VALUES(
            6173331,'Vancouver','Vancouver','CA','02','5915027',49.24966,-123.11934,
            662248,'America/Vancouver','PPLA','simulated'
            )"""
        )
    catalog = FeatureCatalogStore(store)
    registry = canonical_feature_registry()
    catalog.attach_distribution(
        registry,
        "income",
        distribution("income", mean=60_000, standard_deviation=15_000),
    )
    catalog.attach_distribution(
        registry,
        "household_size",
        distribution("household_size", mean=2, standard_deviation=0),
    )
    catalog.attach_distribution(
        registry,
        "education_isced",
        distribution("education_isced", values={"3": 0.5, "6": 0.5}),
    )
    insert_import(
        store,
        "shared-age-sex",
        "shared",
        [
            (
                "age_sex",
                {"female_30": 25, "female_40": 25, "male_30": 25, "male_40": 25},
                "percent",
            )
        ],
    )
    return store


def request(scope: str = "shared", target_agents: int = 1000) -> AtlasPopulationRequest:
    return AtlasPopulationRequest(
        population_id="canada-atlas",
        selector=PlaceSelector(level="country", place="CA", label="Canada"),
        scope=scope,
        seed=73,
        target_agents=target_agents,
    )


def interaction_factor(identity: str) -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=identity.replace("-", " "),
        value=1,
        provenance=InteractionFactorProvenance(
            source="Measured interaction fixture",
            version="v1",
            source_date="2026-10-27",
            evidence_id=identity,
            licence="Test",
            status="measured_joint",
            uncertainty=0,
        ),
    )


def interaction_program() -> InteractionProgramDefinition:
    provenance = InteractionFactorProvenance(
        source="Measured household relationship fixture",
        version="v1",
        source_date="2026-10-27",
        evidence_id="family-panel-v1",
        licence="Test",
        status="measured_joint",
        uncertainty=0.05,
    )
    return InteractionProgramDefinition(
        version="v1",
        status="confirmed",
        relationship_evidence=(
            RelationshipKindEvidence(
                kind="family",
                weight=0.8,
                trust=0.7,
                similarity=0.6,
                provenance=provenance,
            ),
        ),
        rules=(
            InteractionRule(
                id="family-talk",
                source_action="talk",
                interaction_type="talk",
                channel="in_person",
                max_targets_per_initiator=1,
                allowed_relationships=("family",),
                allowed_place_kinds=("home",),
                base_factor=interaction_factor("base"),
                relationship_factors={"family": interaction_factor("family")},
                colocation_factors={
                    "same_specific_place": interaction_factor("same-place")
                },
                place_factors={"home": interaction_factor("home")},
                time_factors=(
                    TimeFactorWindow(
                        weekdays=(0, 1, 2, 3, 4, 5, 6),
                        start_hour=0,
                        end_hour=24,
                        factor=interaction_factor("all-day"),
                    ),
                ),
            ),
        ),
    )


def test_materializes_one_thousand_unique_agents_deterministically(tmp_path):
    store = seeded_store(tmp_path)
    first = AtlasPopulationMaterializer(store).materialize(request())
    second = AtlasPopulationMaterializer(store).materialize(request())

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first.materialization.population.agents) == 1000
    assert len({agent.agent_id for agent in first.materialization.population.agents}) == 1000
    assert first.materialization.validation.valid
    assert len(
        {agent.traits["initial_state_key"] for agent in first.materialization.population.agents}
    ) == 1000
    assert all(
        agent.traits["household_size"] == 2
        for agent in first.materialization.population.agents
    )
    assert {
        (agent.traits["country_id"], agent.traits["country"])
        for agent in first.materialization.population.agents
    } == {("CA", "Canada")}
    assert {
        (agent.traits["city_id"], agent.traits["city"])
        for agent in first.materialization.population.agents
    } == {("6173331", "Vancouver")}
    coverage = {item.feature_id: item for item in first.feature_coverage}
    assert coverage["age"].measured_agents == 1000
    assert coverage["sex"].measured_agents == 1000
    assert coverage["education_isced"].measured_agents == 1000
    assert coverage["income"].imputed_agents == 1000
    assert coverage["ideology_economic"].unknown_agents == 1000
    assert first.agent_type_counts == {"person": 1000}
    first_provenance = next(iter(first.materialization.provenance.values()))
    assert first_provenance.field_evidence["age"].status == "measured_joint"
    assert first_provenance.field_evidence["income"].status == "imputed"
    assert "ideology_economic" in first_provenance.unknown_fields


def test_confirmed_trait_rules_assign_multiple_agent_types_deterministically(tmp_path):
    store = seeded_store(tmp_path)
    configured_request = AtlasPopulationRequest.model_validate(
        {
            **request(target_agents=1000).model_dump(mode="json"),
            "type_assignment": {
                "status": "confirmed",
                "fallback_agent_type_id": "person",
                "rules": [
                    {
                        "id": "older-adult",
                        "agent_type_ids": ["older_adult"],
                        "conditions": [
                            {"field": "age", "operator": "at_least", "value": 40}
                        ],
                    },
                    {
                        "id": "household-reference",
                        "agent_type_ids": ["household_reference"],
                        "conditions": [
                            {
                                "field": "relationship_to_reference",
                                "operator": "equals",
                                "value": "self",
                            }
                        ],
                    },
                    {
                        "id": "graduate",
                        "agent_type_ids": ["graduate"],
                        "conditions": [
                            {
                                "field": "education_isced",
                                "operator": "equals",
                                "value": "6",
                            }
                        ],
                    },
                    {
                        "id": "professional",
                        "agent_type_ids": ["professional"],
                        "conditions": [
                            {
                                "field": "occupation_isco",
                                "operator": "equals",
                                "value": "2",
                            }
                        ],
                    },
                ],
            },
        }
    )

    first = AtlasPopulationMaterializer(store).materialize(configured_request)
    second = AtlasPopulationMaterializer(store).materialize(configured_request)
    assigned = [agent.traits["agent_types"] for agent in first.materialization.population.agents]
    counts = {
        agent_type: sum(agent_type in agent_types for agent_types in assigned)
        for agent_type in {agent_type for agent_types in assigned for agent_type in agent_types}
    }

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.agent_type_counts == counts
    assert counts["person"] > 0
    assert counts["older_adult"] > 0
    assert counts["household_reference"] == 500
    assert counts["graduate"] > 0
    assert "professional" not in counts
    assert any(len(agent_types) > 1 for agent_types in assigned)
    assert any("do not add evidence" in warning for warning in first.warnings)
    for agent in first.materialization.population.agents:
        agent_types = agent.traits["agent_types"]
        if "older_adult" in agent_types:
            assert agent.traits["age"] >= 40
        if "household_reference" in agent_types:
            assert agent.traits["household_role"] == "household_member"
        if "graduate" in agent_types:
            assert agent.traits["education_isced"] == "6"


def test_type_assignment_requires_confirmation_and_supported_atlas_fields(tmp_path):
    base_payload = request(target_agents=10).model_dump(mode="json")
    assignment = {
        "status": "confirmed",
        "fallback_agent_type_id": "person",
        "rules": [
            {
                "id": "unsupported",
                "agent_type_ids": ["runner"],
                "conditions": [
                    {"field": "shoe_size", "operator": "at_least", "value": 10}
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="Input should be 'confirmed'"):
        AtlasPopulationRequest.model_validate(
            {**base_payload, "type_assignment": {**assignment, "status": "draft"}}
        )

    unsupported = AtlasPopulationRequest.model_validate(
        {**base_payload, "type_assignment": assignment}
    )
    with pytest.raises(ValueError, match="unsupported Atlas fields: shoe_size"):
        AtlasPopulationMaterializer(seeded_store(tmp_path)).materialize(unsupported)


def test_run_scoped_observation_overrides_shared_without_crossing_scopes(tmp_path):
    store = seeded_store(tmp_path)
    insert_import(
        store,
        "run-education",
        "run-a",
        [("education", {"8": 100, "0": 0}, "percent")],
    )

    run_result = AtlasPopulationMaterializer(store).materialize(
        request("run-a", target_agents=20)
    )
    shared_result = AtlasPopulationMaterializer(store).materialize(
        request("shared", target_agents=20)
    )

    assert {
        agent.traits["education_isced"]
        for agent in run_result.materialization.population.agents
    } == {"8"}
    assert "8" not in {
        agent.traits["education_isced"]
        for agent in shared_result.materialization.population.agents
    }
    assert all(
        evidence.source == "Source run-education"
        for evidence in run_result.materialization.provenance.values()
        for field, evidence in evidence.field_evidence.items()
        if field == "education_isced"
    )


def test_impossible_child_only_households_block_materialization(tmp_path):
    store = seeded_store(tmp_path)
    with store.connection() as connection:
        connection.execute("DELETE FROM observations WHERE field='age_sex'")
        connection.execute("DELETE FROM imports WHERE import_id='shared-age-sex'")
    insert_import(
        store,
        "shared-child-only",
        "shared",
        [("age_sex", {"female_5": 50, "male_5": 50}, "percent")],
    )

    with pytest.raises(ValueError, match="joint household-age evidence is required"):
        AtlasPopulationMaterializer(store).materialize(request(target_agents=10))


def test_unknown_run_scope_is_rejected_instead_of_falling_back_silently(tmp_path):
    store = seeded_store(tmp_path)

    with pytest.raises(ValueError, match="has no committed imports"):
        AtlasPopulationMaterializer(store).materialize(
            request("another-run", target_agents=10)
        )


def atlas_decision_registries() -> tuple[
    DecisionTreeRegistryDefinition,
    DecisionEvidenceRegistryDefinition,
]:
    source = ResearchCitation(
        kind="research_paper",
        imported_source_id="canada-vancouver-choice-panel",
        title="Canadian and Vancouver choice panel",
        source="Fixture Journal",
        publication_date=date(2025, 1, 1),
        population_studied="Adults in Canada and Vancouver",
        link_or_reference="https://example.test/canada-vancouver-choice",
        supports_decision_ids=("atlas-choice",),
        supports_factor_ids=(
            "country-choice",
            "country-weekday",
            "city-choice",
            "city-weekday",
        ),
    )
    tree_registry = DecisionTreeRegistryDefinition(
        version="atlas-choice-v1",
        trees=[
            DecisionTreeDefinition(
                id="atlas-choice",
                version="v1",
                name="Atlas choice",
                root_module_id="atlas-choice-module",
                agent_type_ids=["person"],
                place_ids=["6173331"],
                source="Confirmed fixture",
                status="ready",
            )
        ],
        modules=[
            DecisionTreeModule(
                id="atlas-choice-module",
                version="v1",
                name="Atlas choice",
                entry_node="choose",
                nodes=[
                    DecisionTreeNode(id="choose", label="Choose", kind="decision"),
                    DecisionTreeNode(id="selected", label="Selected", kind="terminal"),
                    DecisionTreeNode(id="skipped", label="Skipped", kind="terminal"),
                ],
                edges=[
                    DecisionTreeEdge(
                        id="select",
                        from_node="choose",
                        to_node="selected",
                    ),
                    DecisionTreeEdge(
                        id="skip",
                        from_node="choose",
                        to_node="skipped",
                    ),
                ],
                source="Confirmed fixture",
                status="ready",
            )
        ],
    )
    template = DecisionTreeTemplate(
        id="atlas-choice",
        name="Atlas choice",
        domain="other",
        status="ready",
        entry_state="choose",
        terminal_states=("selected", "skipped"),
        nodes=(
            DecisionNodeTemplate(id="choose", label="Choose", kind="decision"),
            DecisionNodeTemplate(id="selected", label="Selected", kind="terminal"),
            DecisionNodeTemplate(id="skipped", label="Skipped", kind="terminal"),
        ),
        edges=(
            DecisionEdgeTemplate(
                id="select",
                decision_id="atlas-choice",
                domain="other",
                from_state="choose",
                to_state="selected",
                label="Select",
                formula=DecisionProbabilityFormula(
                    id="select-formula",
                    name="Country choice rate",
                    combination="product",
                    factors=(
                        ProbabilityFactor(
                            id="country-choice",
                            name="Country choice",
                            input_kind="trait",
                            input_key="age",
                            feature_id="age",
                        ),
                        ProbabilityFactor(
                            id="country-weekday",
                            name="Country weekday",
                            input_kind="time",
                            input_key="weekday",
                        ),
                    ),
                ),
                source=source,
            ),
            DecisionEdgeTemplate(
                id="skip",
                decision_id="atlas-choice",
                domain="other",
                from_state="choose",
                to_state="skipped",
                label="Skip",
                formula=DecisionProbabilityFormula(
                    id="skip-formula",
                    name="City choice rate",
                    combination="product",
                    factors=(
                        ProbabilityFactor(
                            id="city-choice",
                            name="City choice",
                            input_kind="trait",
                            input_key="age",
                            feature_id="age",
                        ),
                        ProbabilityFactor(
                            id="city-weekday",
                            name="City weekday",
                            input_kind="time",
                            input_key="weekday",
                        ),
                    ),
                ),
                source=source,
            ),
        ),
    )
    country_place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="Northern America",
        country_id="CA",
    )
    city_place = EvidencePlace(
        level="city",
        place_id="6173331",
        region_id="Northern America",
        country_id="CA",
        city_id="6173331",
    )
    evidence = []
    for age in (30, 40):
        evidence.extend(
            [
                DecisionFactorEvidence(
                    id=f"country-choice-{age}",
                    decision_id="atlas-choice",
                    edge_id="select",
                    factor_id="country-choice",
                    place=country_place,
                    predicate=EvidencePredicate(operator="exact", value=age),
                    basis="measured_joint",
                    estimate=0.4,
                    ci_low=0.35,
                    ci_high=0.45,
                    sample_size=1000,
                    fittable=True,
                    source=source,
                ),
                DecisionFactorEvidence(
                    id=f"city-choice-{age}",
                    decision_id="atlas-choice",
                    edge_id="skip",
                    factor_id="city-choice",
                    place=city_place,
                    predicate=EvidencePredicate(operator="exact", value=age),
                    basis="measured_joint",
                    estimate=0.6,
                    ci_low=0.55,
                    ci_high=0.65,
                    sample_size=600,
                    fittable=True,
                    source=source,
                ),
            ]
        )
    for weekday in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        evidence.extend(
            [
                DecisionFactorEvidence(
                    id=f"country-weekday-{weekday}",
                    decision_id="atlas-choice",
                    edge_id="select",
                    factor_id="country-weekday",
                    place=country_place,
                    predicate=EvidencePredicate(operator="exact", value=weekday),
                    basis="measured_joint",
                    estimate=1,
                    ci_low=1,
                    ci_high=1,
                    sample_size=1000,
                    fittable=True,
                    source=source,
                ),
                DecisionFactorEvidence(
                    id=f"city-weekday-{weekday}",
                    decision_id="atlas-choice",
                    edge_id="skip",
                    factor_id="city-weekday",
                    place=city_place,
                    predicate=EvidencePredicate(operator="exact", value=weekday),
                    basis="measured_joint",
                    estimate=1,
                    ci_low=1,
                    ci_high=1,
                    sample_size=600,
                    fittable=True,
                    source=source,
                ),
            ]
        )
    evidence_registry = DecisionEvidenceRegistryDefinition(
        version="atlas-choice-evidence-v1",
        templates=[template],
        evidence=evidence,
    )
    return tree_registry, evidence_registry


def atlas_decision_routines() -> RoutineRegistryDefinition:
    routine_id = "atlas-choice-routine"
    return RoutineRegistryDefinition(
        agent_types=[
            AgentTypeDefinition(
                id="person",
                name="Person",
                routines=[
                    AgentTypeMember(
                        id=routine_id,
                        name="Atlas choice",
                        definition="Activate the confirmed Atlas choice module",
                    )
                ],
            )
        ],
        routines=[
            RoutineDefinition(
                id=routine_id,
                name="Atlas choice",
                agent_type_id="person",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="Confirmed integration-test activation",
                ),
                steps=[
                    RoutineStep(
                        id="choose",
                        name="Choose",
                        activity="choose",
                        decision_tree_module_id="atlas-choice-module",
                        schedule=RoutineSchedule(
                            days=[
                                "monday",
                                "tuesday",
                                "wednesday",
                                "thursday",
                                "friday",
                                "saturday",
                                "sunday",
                            ],
                            start_time="00:00",
                            end_time="23:59",
                            place_ids=["current"],
                            role_ids=["person"],
                        ),
                    )
                ],
            )
        ],
    )


@pytest.mark.parametrize(
    ("scope_level", "scope_identifier"),
    [("country", "CA"), ("city", "6173331")],
)
def test_atlas_place_ids_resolve_country_and_city_evidence_in_rust_run(
    tmp_path,
    scope_level,
    scope_identifier,
):
    materialization = AtlasPopulationMaterializer(seeded_store(tmp_path)).materialize(
        request(target_agents=2)
    ).materialization
    registry = SimulationRegistryStore(tmp_path / "simulation.json")
    tree_registry, evidence_registry = atlas_decision_registries()
    registry.save_initial_population(materialization)
    registry.save_decision_trees(tree_registry)
    registry.save_decision_evidence(evidence_registry)
    registry.save_routines(atlas_decision_routines())
    config = SimulationRunConfig(
        population_size=2,
        seed=19,
        days=1,
        tick_interval_hours=24,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level=scope_level, identifier=scope_identifier),
        agent_type_mix={"person": 1},
    )

    prepared = prepare_registry_run(registry, config)
    provenance = {
        transition["id"]: [
            set(rule["provenance"]["evidence_id"].split(","))
            for rule in transition["rules"]
        ]
        for module in prepared.rust_request["modules"]
        for transition in module["transitions"]
    }
    output = RustCoreClient().run_agents(prepared.rust_request)

    assert all(
        any(value in ids for value in {"country-choice-30", "country-choice-40"})
        and any(value.startswith("country-weekday-") for value in ids)
        for ids in provenance["select"]
    )
    assert all(
        any(value in ids for value in {"city-choice-30", "city-choice-40"})
        and any(value.startswith("city-weekday-") for value in ids)
        for ids in provenance["skip"]
    )
    assert output["transition_outcomes"]


def test_atlas_route_saves_generated_population_for_initial_agent_browser(tmp_path):
    store = seeded_store(tmp_path)
    registry = SimulationRegistryStore(tmp_path / "simulation.json")
    registry.save_interaction_program(interaction_program())
    app = FastAPI()
    app.include_router(create_population_router(registry, store))
    client = TestClient(app)

    places = client.get("/simulation/initial-population/atlas/places")
    response = client.post(
        "/simulation/initial-population/atlas/materialize",
        json=request(target_agents=20).model_dump(mode="json"),
    )

    assert places.status_code == 200
    assert any(place["place"] == "CA" for place in places.json()["places"])
    assert response.status_code == 200
    assert len(response.json()["materialization"]["population"]["agents"]) == 20
    assert response.json()["agent_type_counts"] == {"person": 20}
    relationships = [
        relationship
        for agent in response.json()["materialization"]["population"]["agents"]
        for relationship in agent["relationships"]
    ]
    assert relationships
    assert {
        (
            relationship["kind"],
            relationship["trust"],
            relationship["similarity"],
            relationship["evidence_id"],
            relationship["evidence_status"],
        )
        for relationship in relationships
    } == {("family", 0.7, 0.6, "family-panel-v1", "measured_joint")}
    assert client.get("/simulation/initial-population").json()["agent_count"] == 20
    assert client.get("/simulation/initial-agents?page_size=50").json()["total"] == 20

    run_scoped = client.post(
        "/simulation/initial-population/atlas/materialize",
        json=request("private-run", target_agents=20).model_dump(mode="json"),
    )

    assert run_scoped.status_code == 409
    assert "promote" in run_scoped.json()["detail"]
    assert client.get("/simulation/initial-population").json()["agent_count"] == 20


def measured_joint(
    *,
    identity: str,
    level: str = "country",
    place: str = "CA",
    probability: float,
    values: dict[str, str | float],
    household_members: list[MeasuredHouseholdMember] | None = None,
    source: str = "Measured joint fixture",
    distribution_id: str = "population-joint-fixture",
) -> tuple[str, MeasuredJointData]:
    record = MeasuredJointData(
        level=level,
        place=place,
        conditions=[
            FeatureFilter(feature_id=feature, operator="eq", values=[value])
            for feature, value in values.items()
        ],
        probability=probability,
        sample_size=4_000,
        ci_low=probability,
        ci_high=probability,
        population="Canadian residents in weighted microdata",
        coverage_percent=94,
        provenance=Evidence(
            source=source,
            version="joint-v1",
            status="present",
            uncertainty=0.05,
            source_date="2025-01-01",
        ),
        household_members=household_members or [],
        population_distribution_id=distribution_id,
    )
    return identity, record


def insert_measured_joints(
    store: AtlasStore, records: list[tuple[str, MeasuredJointData]]
) -> None:
    with store.connection() as connection:
        connection.executemany(
            """INSERT INTO feature_joint_data(
            record_id,level,place,conditions_key,record_json,created_at
            ) VALUES(?,?,?,?,?,?)""",
            [
                (
                    identity,
                    record.level,
                    record.place,
                    identity,
                    record.model_dump_json(),
                    "2025-01-01T00:00:00+00:00",
                )
                for identity, record in records
            ],
        )


def test_measured_joint_cells_drive_correlated_feature_sampling_and_city_wins(tmp_path):
    store = seeded_store(tmp_path)
    catalog = FeatureCatalogStore(store)
    catalog.attach_distribution(
        canonical_feature_registry(),
        "occupation_isco",
        distribution("occupation_isco", values={"2": 0.5, "9": 0.5}),
    )
    catalog.attach_distribution(
        canonical_feature_registry(),
        "openness",
        distribution("openness", mean=0.5, standard_deviation=0.1),
    )
    insert_measured_joints(
        store,
        [
            measured_joint(
                identity="country-low",
                probability=0.5,
                values={
                    "age": 30,
                    "income": 10_000,
                    "education_isced": "6",
                    "occupation_isco": "2",
                },
            ),
            measured_joint(
                identity="country-high",
                probability=0.5,
                values={
                    "age": 40,
                    "income": 20_000,
                    "education_isced": "3",
                    "occupation_isco": "9",
                },
            ),
            measured_joint(
                identity="city-low",
                level="city",
                place="6173331",
                probability=0.5,
                values={
                    "age": 30,
                    "income": 20_000,
                    "education_isced": "3",
                    "occupation_isco": "9",
                },
            ),
            measured_joint(
                identity="city-high",
                level="city",
                place="6173331",
                probability=0.5,
                values={
                    "age": 40,
                    "income": 100_000,
                    "education_isced": "6",
                    "occupation_isco": "2",
                },
            ),
        ],
    )

    first = AtlasPopulationMaterializer(store).materialize(request(target_agents=100))
    second = AtlasPopulationMaterializer(store).materialize(request(target_agents=100))
    cells = {
        (
            agent.traits["age"],
            agent.traits["income"],
            agent.traits["education_isced"],
            agent.traits["occupation_isco"],
        )
        for agent in first.materialization.population.agents
    }

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert cells == {(30, 20_000.0, "3", "9"), (40, 100_000.0, "6", "2")}
    assert all(
        provenance.field_evidence["income"].status == "measured_joint"
        and provenance.field_evidence["income"].place == "6173331"
        for provenance in first.materialization.provenance.values()
    )


def test_measured_household_composition_creates_linked_age_valid_family_roles(tmp_path):
    store = seeded_store(tmp_path)
    with store.connection() as connection:
        connection.execute(
            """UPDATE observations SET value_json=? WHERE field='age_sex'""",
            (
                json.dumps(
                    {
                        "female_8": 20,
                        "male_8": 20,
                        "female_35": 15,
                        "male_35": 15,
                        "female_40": 15,
                        "male_40": 15,
                    }
                ),
            ),
        )
    members = [
        MeasuredHouseholdMember(
            relationship_to_reference="self", minimum_age=30, maximum_age=55
        ),
        MeasuredHouseholdMember(
            relationship_to_reference="spouse", minimum_age=30, maximum_age=55
        ),
        MeasuredHouseholdMember(
            relationship_to_reference="child", minimum_age=0, maximum_age=17
        ),
    ]
    insert_measured_joints(
        store,
        [
            measured_joint(
                identity="city-family",
                level="city",
                place="6173331",
                probability=1,
                values={"household_size": 3, "household_composition": "couple_child"},
                household_members=members,
                source="Measured household city-family",
                distribution_id="household-composition-fixture",
            )
        ],
    )

    first = AtlasPopulationMaterializer(store).materialize(request(target_agents=12))
    second = AtlasPopulationMaterializer(store).materialize(request(target_agents=12))
    households: dict[str, list] = {}
    for agent in first.materialization.population.agents:
        households.setdefault(agent.traits["household_id"], []).append(agent)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(households) == 4
    for agents in households.values():
        assert sorted(agent.traits["household_role"] for agent in agents) == [
            "child",
            "parent",
            "parent",
        ]
        child = next(agent for agent in agents if agent.traits["household_role"] == "child")
        parents = [agent for agent in agents if agent.traits["household_role"] == "parent"]
        assert child.traits["age"] <= 17
        assert all(parent.traits["age"] >= 30 for parent in parents)
        assert all(parent.traits["age"] - child.traits["age"] >= 12 for parent in parents)
        assert all(len(agent.relationships) == 2 for agent in agents)
    assert all(
        provenance.household_evidence.status == "measured_joint"
        and provenance.household_evidence.source == "Measured household city-family"
        and "family_relationships" in provenance.field_evidence
        for provenance in first.materialization.provenance.values()
    )
    assert any("measured household composition" in warning for warning in first.warnings)
    assert not any("Household membership is an imputation" in warning for warning in first.warnings)


def test_household_size_fallback_keeps_roles_and_composition_imputed_or_unknown(tmp_path):
    result = AtlasPopulationMaterializer(seeded_store(tmp_path)).materialize(
        request(target_agents=20)
    )

    assert {
        agent.traits["household_role"]
        for agent in result.materialization.population.agents
    } == {"household_member"}
    assert all(
        provenance.sampling_basis == "imputed"
        and provenance.household_evidence.status == "imputed"
        and "family_relationships" in provenance.unknown_fields
        for provenance in result.materialization.provenance.values()
    )
    assert any("Household membership is an imputation" in warning for warning in result.warnings)


def test_incomplete_measured_joint_distribution_is_rejected(tmp_path):
    store = seeded_store(tmp_path)
    insert_measured_joints(
        store,
        [
            measured_joint(
                identity="incomplete-a",
                probability=0.4,
                values={"age": 30, "education_isced": "3"},
            ),
            measured_joint(
                identity="incomplete-b",
                probability=0.4,
                values={"age": 40, "education_isced": "6"},
            ),
        ],
    )

    with pytest.raises(ValueError, match="probabilities must sum to 1"):
        AtlasPopulationMaterializer(store).materialize(request(target_agents=20))
