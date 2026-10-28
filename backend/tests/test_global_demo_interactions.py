from petraterrium.simulation.default_dsl import DefaultDslService
from petraterrium.simulation.global_demo_interactions import (
    GLOBAL_DEMO_INTERACTION_REASON,
    GLOBAL_DEMO_INTERACTION_VERSION,
    GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID,
    attach_global_demo_cross_country_relationships,
    global_demo_interaction_program,
)
from petraterrium.simulation.global_demo_population import (
    GLOBAL_DEMO_COUNTRIES,
    build_global_demo_population,
    summarize_global_demo,
)
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import SimulationPlaceScope, SimulationRunConfig


def test_cross_country_relationships_are_deterministic_and_never_same_country():
    population = build_global_demo_population(
        target_agents=len(GLOBAL_DEMO_COUNTRIES)
    ).population

    first = attach_global_demo_cross_country_relationships(population)
    repeated = attach_global_demo_cross_country_relationships(population)
    country_by_agent = {
        agent.agent_id: agent.traits["country_id"] for agent in first.agents
    }

    assert first == repeated
    assert attach_global_demo_cross_country_relationships(first) == first
    assert len(first.agents) == len(GLOBAL_DEMO_COUNTRIES)
    assert all(len(agent.relationships) == 1 for agent in first.agents)
    for agent in first.agents:
        relationship = agent.relationships[0]
        assert country_by_agent[relationship.target_id] != agent.traits["country_id"]
        assert relationship.kind == "friend"
        assert relationship.weight == 0
        assert relationship.trust == 0
        assert relationship.similarity == 0
        assert relationship.evidence_id == GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID
        assert relationship.evidence_status == "default_estimated"

    summary = summarize_global_demo(first)
    assert summary.cross_country_relationships.relationship_count == len(first.agents)
    assert summary.cross_country_relationships.linked_agent_count == len(first.agents)
    assert summary.cross_country_relationships.countries == sorted(GLOBAL_DEMO_COUNTRIES)
    assert not any(
        item.id == "interactions:cross-country-missing"
        for item in summary.deviations
    )


def test_cross_country_program_is_confirmed_with_widest_explicit_uncertainty():
    program = global_demo_interaction_program()

    assert program.version == GLOBAL_DEMO_INTERACTION_VERSION
    assert program.status == "confirmed"
    assert len(program.relationship_evidence) == 1
    relationship = program.relationship_evidence[0]
    assert relationship.provenance.executable is True
    assert relationship.provenance.status == "default_estimated"
    assert relationship.provenance.uncertainty == 1
    assert relationship.provenance.source == GLOBAL_DEMO_INTERACTION_REASON
    assert "default-estimated" in relationship.provenance.source
    assert "base × relationship × colocation × place × time" in (
        relationship.provenance.source
    )
    assert relationship.provenance.evidence_id == (
        GLOBAL_DEMO_RELATIONSHIP_EVIDENCE_ID
    )

    rule = program.rules[0]
    assert rule.channel == "online"
    assert rule.source_action == "choose exercise or recovery"
    assert rule.allowed_relationships == ("friend",)
    assert "different_specific_place" in rule.colocation_factors
    factors = (
        rule.base_factor,
        *rule.relationship_factors.values(),
        *rule.colocation_factors.values(),
        *rule.place_factors.values(),
        *(window.factor for window in rule.time_factors),
    )
    assert all(factor.provenance.executable for factor in factors)
    assert all(factor.provenance.uncertainty == 1 for factor in factors)
    assert all(factor.provenance.source == GLOBAL_DEMO_INTERACTION_REASON for factor in factors)

    payload = rule.rust_payload()
    assert payload["channel"] == "online"
    assert payload["colocation_factors"]["different_specific_place"]["value"] == 1


def test_cross_country_helper_compiles_through_generic_run_preparation(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    materialization = store.initial_population()
    assert materialization is not None
    population = attach_global_demo_cross_country_relationships(
        materialization.population
    )
    store.save_initial_population(
        materialization.model_copy(update={"population": population})
    )
    store.save_interaction_program(global_demo_interaction_program())

    prepared = prepare_registry_run(
        store,
        SimulationRunConfig(
            population_size=1_000,
            seed=1,
            days=1,
            tick_interval_hours=1,
            start_date="2026-10-27",
            place_scope=SimulationPlaceScope(level="global"),
            agent_type_mix={},
        ),
    )

    relationships = prepared.rust_request["interactions"]["relationships"]
    rules = prepared.rust_request["interactions"]["rules"]
    country_by_index = [
        profile["geography"]["country_id"]
        for profile in prepared.initial_agent_profiles
    ]
    assert len(relationships) == 1_000
    assert len(rules) == 1
    assert rules[0]["id"] == "global-demo-cross-country-contact"
    assert all(
        country_by_index[item["source_index"]]
        != country_by_index[item["target_index"]]
        for item in relationships
    )
