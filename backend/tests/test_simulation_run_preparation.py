from copy import deepcopy
from datetime import date

import pytest

from petraterrium.population import Relationship
from petraterrium.rust_core import RustCoreClient
from petraterrium.simulation.agent_types import AgentTypeDefinition, AgentTypeMember
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
from petraterrium.simulation.interaction_trees import (
    AgentRoutineEffect,
    InteractionTransitionEvidence,
    InteractionTreeDefinition,
    InteractionTreeNode,
    InteractionTreeTransition,
)
from petraterrium.simulation.interaction_trees import (
    AgentStateEffect as InteractionTreeAgentStateEffect,
)
from petraterrium.simulation.interactions import (
    InteractionFactor,
    InteractionFactorProvenance,
    InteractionProgramDefinition,
    InteractionRule,
    RelationshipKindEvidence,
    RelationshipProfile,
    TimeFactorWindow,
)
from petraterrium.simulation.mobility import (
    MobilityEvidence,
    MobilityRegistryDefinition,
    PlaceProfileDefinition,
    TravelRouteDefinition,
)
from petraterrium.simulation.population_generation import (
    EvidenceReference,
    HouseholdMemberSeed,
    HouseholdSeed,
    InitialPopulationRequest,
    materialize_initial_population,
)
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
from petraterrium.simulation.runtime_decision_compiler import (
    RuntimeDecisionCompilationError,
    compile_runtime_decisions,
)
from petraterrium.simulation.tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
)


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="joint",
        source="Measured joint fixture",
        source_version="v1",
        observed_at="2025-01-01",
        licence="Test",
        place="CA",
        status="measured_joint",
        fields=["age", "sex", "household_composition"],
        uncertainty="Test sample",
    )


def _single_member_household(identity: str, city: str, age: int, mood: str) -> HouseholdSeed:
    return HouseholdSeed(
        template_id=identity,
        place="CA",
        country="Canada",
        region="Northern America",
        city=city,
        latitude=49.2,
        longitude=-123.1,
        weight=1,
        evidence_id="joint",
        members=[
            HouseholdMemberSeed(
                member_id="resident",
                name=identity.title(),
                age=age,
                sex="female",
                relationship_to_reference="self",
                agent_types=["worker"],
                states={"mood": mood, "label": "calm"},
            )
        ],
    )


def _two_household_population():
    return materialize_initial_population(
        InitialPopulationRequest(
            population_id="two-homes",
            version="v1",
            seed=8,
            target_agents=2,
            evidence=[_evidence()],
            household_templates=[
                _single_member_household("vancouver-home", "Vancouver", 35, "0.25"),
                _single_member_household("toronto-home", "Toronto", 42, "0.75"),
            ],
        )
    )


def _routine_member(identity: str) -> AgentTypeMember:
    return AgentTypeMember(
        id=identity,
        name=identity.replace("_", " ").title(),
        definition=f"{identity} schedule",
    )


def _routine_registry() -> RoutineRegistryDefinition:
    worker = AgentTypeDefinition(
        id="worker",
        name="Worker",
        routines=[
            _routine_member("workday"),
            _routine_member("illustrative_gym"),
            _routine_member("unknown_cafe"),
        ],
    )
    return RoutineRegistryDefinition(
        agent_types=[worker],
        routines=[
            RoutineDefinition(
                id="workday",
                name="Workday",
                agent_type_id="worker",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed test schedule",
                ),
                steps=[
                    RoutineStep(
                        id="work",
                        name="Work",
                        activity="work",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="08:00",
                            end_time="16:00",
                            place_ids=["work"],
                            role_ids=["worker"],
                        ),
                    ),
                    RoutineStep(
                        id="return_home",
                        name="Return home",
                        activity="return home",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="17:00",
                            end_time="23:00",
                            place_ids=["home"],
                            role_ids=["worker"],
                        ),
                    ),
                ],
            ),
            RoutineDefinition(
                id="illustrative_gym",
                name="Illustrative gym",
                agent_type_id="worker",
                evidence=RoutineEvidence(
                    status="illustrative",
                    note="Example only",
                ),
                steps=[
                    RoutineStep(
                        id="gym",
                        name="Gym",
                        activity="visit gym",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="06:00",
                            end_time="07:00",
                            place_ids=["gym"],
                            role_ids=["worker"],
                        ),
                    )
                ],
            ),
            RoutineDefinition(
                id="unknown_cafe",
                name="Unknown cafe",
                agent_type_id="worker",
                evidence=RoutineEvidence(status="unknown", note="No source"),
                steps=[
                    RoutineStep(
                        id="cafe",
                        name="Cafe",
                        activity="visit cafe",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="07:00",
                            end_time="08:00",
                            place_ids=["cafe"],
                            role_ids=["worker"],
                        ),
                    )
                ],
            ),
        ],
    )


def _mobility_registry() -> MobilityRegistryDefinition:
    evidence = MobilityEvidence(
        status="measured",
        source_title="Canadian time-use travel fixture",
        source_version="2025",
        source_date="2025-04-01",
        licence="Test",
        evidence_id="travel-fixture-2025",
        uncertainty=0.05,
    )
    return MobilityRegistryDefinition(
        version="travel-fixture-2025",
        status="confirmed",
        place_profiles=[
            PlaceProfileDefinition(
                id="home",
                place_kind="home",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=8,
                state={"crowd_density": 0.2},
                available_decision_tree_ids=[],
                evidence=evidence,
            ),
            PlaceProfileDefinition(
                id="work",
                place_kind="work",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=200,
                state={"crowd_density": 0.5},
                available_decision_tree_ids=[],
                evidence=evidence,
            ),
            PlaceProfileDefinition(
                id="transit",
                place_kind="transit",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=100,
                state={"crowd_density": 0.7},
                available_decision_tree_ids=[],
                evidence=evidence,
            ),
        ],
        routes=[
            TravelRouteDefinition(
                id="home-work",
                from_place_kind="home",
                to_place_kind="work",
                transit_place_kind="transit",
                duration_minutes=60,
                evidence=evidence,
            ),
            TravelRouteDefinition(
                id="work-home",
                from_place_kind="work",
                to_place_kind="home",
                transit_place_kind="transit",
                duration_minutes=60,
                evidence=evidence,
            ),
        ],
    )


def _run_config() -> SimulationRunConfig:
    return SimulationRunConfig(
        population_size=2,
        seed=99,
        days=1,
        tick_interval_hours=1,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="country", identifier="Canada"),
        agent_type_mix={"worker": 1.0},
    )


def _save_executable_decisions(store: SimulationRegistryStore) -> None:
    decision_id = "fixture-choice"
    factor_ids = ("first-input", "second-input")
    source = ResearchCitation(
        kind="research_paper",
        imported_source_id="fixture-choice-panel-v1",
        title="Canadian fixture choice panel",
        source="Fixture Journal",
        publication_date=date(2025, 1, 1),
        population_studied="Adults in Canada",
        link_or_reference="https://example.test/fixture-choice-panel",
        supports_decision_ids=(decision_id,),
        supports_factor_ids=factor_ids,
    )
    factors = (
        ProbabilityFactor(
            id=factor_ids[0],
            name="First input",
            input_kind="trait",
            input_key="age",
            feature_id="age",
        ),
        ProbabilityFactor(
            id=factor_ids[1],
            name="Second input",
            input_kind="time",
            input_key="weekday",
        ),
    )
    destinations = ("first", "second")
    edges = tuple(
        DecisionEdgeTemplate(
            id=f"choose-{destination}",
            decision_id=decision_id,
            domain="other",
            from_state="choose",
            to_state=destination,
            label=destination.title(),
            formula=DecisionProbabilityFormula(
                id=f"choose-{destination}-formula",
                name=f"Choose {destination}",
                combination="product",
                factors=factors,
            ),
            source=source,
        )
        for destination in destinations
    )
    store.save_decision_trees(
        DecisionTreeRegistryDefinition(
            version="fixture-tree-v1",
            trees=[
                DecisionTreeDefinition(
                    id=decision_id,
                    version="v1",
                    name="Fixture choice",
                    root_module_id="fixture-choice-module",
                    source="Confirmed fixture decision",
                    status="ready",
                )
            ],
            modules=[
                DecisionTreeModule(
                    id="fixture-choice-module",
                    version="v1",
                    name="Fixture choice",
                    entry_node="choose",
                    nodes=[
                        DecisionTreeNode(id="choose", label="Choose", kind="decision"),
                        DecisionTreeNode(id="first", label="First", kind="terminal"),
                        DecisionTreeNode(id="second", label="Second", kind="terminal"),
                    ],
                    edges=[
                        DecisionTreeEdge(
                            id=edge.id,
                            from_node=edge.from_state,
                            to_node=edge.to_state,
                        )
                        for edge in edges
                    ],
                    source="Confirmed fixture decision",
                    status="ready",
                )
            ],
        )
    )
    evidence = [
        DecisionFactorEvidence(
            id=f"{edge.id}-{factor.id}-{city.casefold()}",
            decision_id=decision_id,
            edge_id=edge.id,
            factor_id=factor.id,
            place=EvidencePlace(
                level="city",
                place_id=city,
                region_id="Northern America",
                country_id="CA",
                city_id=city,
            ),
            predicate=EvidencePredicate(operator="any"),
            basis="measured_joint",
            estimate=0.5 if factor.id == "first-input" else 1,
            ci_low=0.5 if factor.id == "first-input" else 1,
            ci_high=0.5 if factor.id == "first-input" else 1,
            sample_size=100,
            fittable=True,
            source=source,
        )
        for edge in edges
        for factor in factors
        for city in ("Vancouver", "Toronto")
    ]
    store.save_decision_evidence(
        DecisionEvidenceRegistryDefinition(
            version="fixture-evidence-v1",
            templates=[
                DecisionTreeTemplate(
                    id=decision_id,
                    name="Fixture choice",
                    domain="other",
                    status="ready",
                    entry_state="choose",
                    terminal_states=destinations,
                    nodes=(
                        DecisionNodeTemplate(id="choose", label="Choose", kind="decision"),
                        DecisionNodeTemplate(id="first", label="First", kind="terminal"),
                        DecisionNodeTemplate(id="second", label="Second", kind="terminal"),
                    ),
                    edges=edges,
                )
            ],
            evidence=evidence,
        )
    )


def _interaction_factor(identity: str, value: float = 1) -> InteractionFactor:
    return InteractionFactor(
        id=identity,
        label=identity.replace("_", " "),
        value=value,
        provenance=InteractionFactorProvenance(
            source="Measured interaction fixture",
            version="v1",
            source_date="2026-10-27",
            evidence_id=identity,
            licence="Test fixture",
            status="measured_joint",
            uncertainty=0,
        ),
    )


def test_run_preparation_blocks_agents_without_executable_decision_evidence(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    materialization = _two_household_population()
    store.save_initial_population(materialization)

    with pytest.raises(RuntimeDecisionCompilationError) as error:
        prepare_registry_run(store, _run_config())

    message = str(error.value)
    assert message.startswith(
        "Run blocked: 2 selected agents have no applicable confirmed executable decision tree"
    )
    for agent in materialization.population.agents:
        assert f"{agent.agent_id} (worker)" in message
    assert (
        "Confirm ready decision trees with measured-joint or fitted-model evidence for every "
        "selected agent type in Simulation > Decision Trees, then run again."
    ) in message


def test_run_blocker_bounds_uncovered_agent_preview_and_reports_total():
    base = _two_household_population().population.agents[0]
    agents = [base.model_copy(update={"agent_id": f"uncovered-{index}"}) for index in range(7)]

    with pytest.raises(RuntimeDecisionCompilationError) as error:
        compile_runtime_decisions(
            DecisionTreeRegistryDefinition(version="1", trees=[], modules=[]),
            None,
            agents,
            date(2026, 10, 27),
        )

    message = str(error.value)
    assert message.startswith("Run blocked: 7 selected agents")
    assert all(f"uncovered-{index} (worker)" in message for index in range(5))
    assert "uncovered-5" not in message
    assert "+2 more" in message


def test_run_blocker_rejects_partial_agent_type_coverage():
    worker = _two_household_population().population.agents[0]
    visitor = worker.model_copy(
        update={
            "agent_id": "visitor-1",
            "role": "visitor",
            "traits": {**worker.traits, "agent_type": "visitor", "agent_types": ["visitor"]},
        }
    )
    registry = DecisionTreeRegistryDefinition(
        version="partial-v1",
        trees=[
            DecisionTreeDefinition(
                id="worker-choice",
                version="v1",
                name="Worker choice",
                root_module_id="worker-module",
                agent_type_ids=["worker"],
                source="Confirmed fixture decision",
                status="ready",
            )
        ],
        modules=[
            DecisionTreeModule(
                id="worker-module",
                version="v1",
                name="Worker module",
                entry_node="done",
                nodes=[DecisionTreeNode(id="done", label="Done", kind="terminal")],
                source="Confirmed fixture decision",
                status="ready",
            )
        ],
    )

    with pytest.raises(RuntimeDecisionCompilationError) as error:
        compile_runtime_decisions(registry, None, [worker, visitor], date(2026, 10, 27))

    message = str(error.value)
    assert message.startswith("Run blocked: 1 selected agent has")
    assert "visitor-1 (visitor)" in message
    assert worker.agent_id not in message


def _relationship_evidence(
    kind: str,
    *,
    weight: float,
    trust: float,
    similarity: float,
) -> RelationshipKindEvidence:
    return RelationshipKindEvidence(
        kind=kind,
        weight=weight,
        trust=trust,
        similarity=similarity,
        provenance=InteractionFactorProvenance(
            source="Measured relationship fixture",
            version="v1",
            source_date="2026-10-27",
            evidence_id=f"{kind}-panel-v1",
            licence="Test fixture",
            status="measured_joint",
            uncertainty=0,
        ),
    )


def test_run_preparation_uses_unique_materialized_agents_and_scope(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    request = InitialPopulationRequest(
        population_id="people",
        version="v1",
        seed=5,
        target_agents=2,
        evidence=[
            EvidenceReference(
                evidence_id="joint",
                source="Measured joint fixture",
                source_version="v1",
                observed_at="2025-01-01",
                licence="Test",
                place="CA",
                status="measured_joint",
                fields=["age", "sex", "household_composition"],
                uncertainty="Test sample",
            )
        ],
        household_templates=[
            HouseholdSeed(
                template_id="couple",
                place="CA",
                country="Canada",
                region="Northern America",
                city="Vancouver",
                latitude=49.2,
                longitude=-123.1,
                weight=1,
                evidence_id="joint",
                members=[
                    HouseholdMemberSeed(
                        member_id="one",
                        name="One",
                        age=40,
                        sex="female",
                        relationship_to_reference="self",
                        agent_types=["worker"],
                    ),
                    HouseholdMemberSeed(
                        member_id="two",
                        name="Two",
                        age=41,
                        sex="male",
                        relationship_to_reference="spouse",
                        agent_types=["worker"],
                    ),
                ],
            )
        ],
    )
    store.save_initial_population(materialize_initial_population(request))
    _save_executable_decisions(store)
    config = SimulationRunConfig(
        population_size=2,
        seed=99,
        days=2,
        tick_interval_hours=6,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="country", identifier="Canada"),
        agent_type_mix={"worker": 1.0},
    )

    first = prepare_registry_run(store, config)
    repeated = prepare_registry_run(store, config)

    assert first == repeated
    assert len(set(first.agent_ids)) == 2
    assert first.rust_request["agents"]["traits"]["age"] == [40.0, 41.0]
    assert [profile["traits"]["age"] for profile in first.initial_agent_profiles] == [
        40,
        41,
    ]
    assert all(
        profile["agent_types"] == ["worker"]
        and profile["geography"]["country"] == "Canada"
        and profile["household"]["id"]
        and profile["relationships"]
        and profile["provenance"]["sampling_basis"] == "measured_joint"
        for profile in first.initial_agent_profiles
    )
    transition_ids = {
        transition["id"]
        for module in first.rust_request["modules"]
        for transition in module["transitions"]
    }
    probabilities = {
        rule["probability"]
        for module in first.rust_request["modules"]
        for transition in module["transitions"]
        for rule in transition["rules"]
    }
    assert "remain-active-without-confirmed-decision-program" not in transition_ids
    assert probabilities == {0.5}
    assert [place.level for place in first.location_places] == [
        "country",
        "region",
        "city",
        "district",
        "building",
    ]
    assert len(set(first.initial_location_ids)) == 1
    assert first.runtime_place_location_ids == first.initial_location_ids[:1]
    assert first.location_places[-2].name == "District unavailable"
    assert first.location_places[-2].state == {"hierarchy_data_available": 0}


def test_confirmed_same_place_relationships_produce_evidence_only_csr(tmp_path):
    request = InitialPopulationRequest(
        population_id="evidenced-couple",
        version="v1",
        seed=5,
        target_agents=2,
        evidence=[_evidence()],
        household_templates=[
            HouseholdSeed(
                template_id="couple",
                place="CA",
                country="Canada",
                region="Northern America",
                city="Vancouver",
                latitude=49.2,
                longitude=-123.1,
                weight=1,
                evidence_id="joint",
                members=[
                    HouseholdMemberSeed(
                        member_id="one",
                        name="One",
                        age=40,
                        sex="female",
                        relationship_to_reference="self",
                        agent_types=["worker"],
                    ),
                    HouseholdMemberSeed(
                        member_id="two",
                        name="Two",
                        age=41,
                        sex="male",
                        relationship_to_reference="spouse",
                        agent_types=["worker"],
                    ),
                ],
            )
        ],
    )
    family = _relationship_evidence(
        "family",
        weight=0.8,
        trust=0.75,
        similarity=0.5,
    )
    materialization = materialize_initial_population(request, (family,))
    rule = InteractionRule(
        id="family-talk",
        source_action="return home",
        interaction_type="talk",
        channel="in_person",
        max_targets_per_initiator=1,
        allowed_relationships=("family",),
        allowed_place_kinds=("home",),
        base_factor=_interaction_factor("base"),
        relationship_factors={"family": _interaction_factor("family")},
        colocation_factors={"same_specific_place": _interaction_factor("same_place")},
        place_factors={"home": _interaction_factor("home")},
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=0,
                end_hour=24,
                factor=_interaction_factor("all_day"),
            ),
        ),
    )
    store = SimulationRegistryStore(tmp_path / "confirmed.json")
    store.save_initial_population(materialization)
    _save_executable_decisions(store)
    store.save_routines(_routine_registry())
    store.save_interaction_program(
        InteractionProgramDefinition(
            version="v1",
            status="confirmed",
            relationship_evidence=(family,),
            rules=(rule,),
        )
    )

    first = prepare_registry_run(store, _run_config())
    repeated = prepare_registry_run(store, _run_config())

    assert first.rust_request["network"] == repeated.rust_request["network"]
    assert {
        key: value for key, value in first.rust_request["network"].items() if key != "weights"
    } == {
        "rows": 2,
        "cols": 2,
        "row_offsets": [0, 1, 2],
        "column_indices": [1, 0],
    }
    assert first.rust_request["network"]["weights"] == pytest.approx([0.3, 0.3])

    unconfirmed = SimulationRegistryStore(tmp_path / "unconfirmed.json")
    unconfirmed.save_initial_population(materialization)
    _save_executable_decisions(unconfirmed)
    unconfirmed.save_routines(_routine_registry())
    assert prepare_registry_run(unconfirmed, _run_config()).rust_request["network"] is None


def test_registry_program_reaches_rust_with_sourced_family_and_stranger_rates(tmp_path):
    household_evidence = [_evidence()]
    request = InitialPopulationRequest(
        population_id="interaction-households",
        version="v1",
        seed=14,
        target_agents=3,
        evidence=household_evidence,
        household_templates=[
            HouseholdSeed(
                template_id="family-home",
                place="CA",
                country="Canada",
                region="Northern America",
                city="Vancouver",
                latitude=49.2,
                longitude=-123.1,
                weight=1,
                evidence_id="joint",
                members=[
                    HouseholdMemberSeed(
                        member_id="parent",
                        name="Parent",
                        age=42,
                        sex="female",
                        relationship_to_reference="self",
                        agent_types=["worker"],
                        states={"mood": "0"},
                    ),
                    HouseholdMemberSeed(
                        member_id="partner",
                        name="Partner",
                        age=44,
                        sex="male",
                        relationship_to_reference="spouse",
                        agent_types=["worker"],
                        states={"mood": "0"},
                    ),
                ],
            ),
            HouseholdSeed(
                template_id="stranger-home",
                place="CA",
                country="Canada",
                region="Northern America",
                city="Vancouver",
                latitude=49.21,
                longitude=-123.11,
                weight=1,
                evidence_id="joint",
                members=[
                    HouseholdMemberSeed(
                        member_id="resident",
                        name="Resident",
                        age=31,
                        sex="nonbinary",
                        relationship_to_reference="self",
                        agent_types=["worker"],
                        states={"mood": "0"},
                    )
                ],
            ),
        ],
    )
    family = _relationship_evidence(
        "family",
        weight=0.86,
        trust=0.79,
        similarity=0.63,
    )
    stranger = _relationship_evidence(
        "stranger",
        weight=0.1,
        trust=0.2,
        similarity=0.3,
    )
    store = SimulationRegistryStore(tmp_path / "registry.json")
    store.save_initial_population(materialize_initial_population(request, (family, stranger)))
    _save_executable_decisions(store)
    store.save_routines(
        RoutineRegistryDefinition(
            agent_types=[
                AgentTypeDefinition(
                    id="worker",
                    name="Worker",
                    routines=[_routine_member("social_time")],
                )
            ],
            routines=[
                RoutineDefinition(
                    id="social_time",
                    name="Social time",
                    agent_type_id="worker",
                    evidence=RoutineEvidence(
                        status="user_defined",
                        note="User-confirmed test schedule",
                    ),
                    steps=[
                        RoutineStep(
                            id="talk",
                            name="Talk",
                            activity="talk",
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
                                role_ids=["worker"],
                            ),
                        )
                    ],
                )
            ],
        )
    )
    tree = InteractionTreeDefinition(
        id="conversation-outcome",
        name="Conversation outcome",
        version="v1",
        entry_node="start",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="start", label="Start", terminal=False),
            InteractionTreeNode(id="talked", label="Talked", terminal=True),
        ),
        transitions=(
            InteractionTreeTransition(
                id="talk",
                from_node="start",
                to_node="talked",
                outcome="conversation",
                probability=1,
                evidence=InteractionTransitionEvidence(
                    source="Measured conversation outcome panel",
                    version="v1",
                    status="measured_joint",
                    uncertainty=0.05,
                    source_date="2026-02-10",
                    evidence_id="conversation-outcome-v1",
                ),
                effects=(
                    InteractionTreeAgentStateEffect(
                        participant="target",
                        field="mood",
                        operation="add",
                        value=0.1,
                        minimum=-1,
                        maximum=1,
                    ),
                ),
            ),
        ),
    )
    store.save_interaction_tree(tree)
    rule = InteractionRule(
        id="sourced-talk",
        source_action="talk",
        interaction_type="talk",
        channel="in_person",
        max_targets_per_initiator=2,
        allowed_relationships=("family", "stranger"),
        allowed_place_kinds=("home",),
        base_factor=_interaction_factor("contact-opportunity", 0.5),
        relationship_factors={
            "family": _interaction_factor("family-contact", 0.7),
            "stranger": _interaction_factor("stranger-contact", 0.03),
        },
        colocation_factors={"same_specific_place": _interaction_factor("same-place")},
        place_factors={"home": _interaction_factor("home")},
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=0,
                end_hour=24,
                factor=_interaction_factor("all-day"),
            ),
        ),
        unrelated_relationship=RelationshipProfile(
            kind="stranger",
            weight=stranger.weight,
            trust=stranger.trust,
            similarity=stranger.similarity,
        ),
        interaction_tree_id=tree.id,
    )
    store.save_interaction_program(
        InteractionProgramDefinition(
            version="v1",
            status="confirmed",
            relationship_evidence=(family, stranger),
            rules=(rule,),
        )
    )
    config = _run_config().model_copy(update={"population_size": 3})
    prepared = prepare_registry_run(store, config)
    relationship = prepared.rust_request["interactions"]["relationships"][0]
    family_indices = {
        relationship["source_index"],
        relationship["target_index"],
    }
    stranger_index = ({0, 1, 2} - family_indices).pop()

    home_request = deepcopy(prepared.rust_request)
    home_request["ticks"] = 200
    home_output = RustCoreClient().run_agents(home_request)
    family_home = [
        event for event in home_output["interactions"] if event["relationship_type"] == "family"
    ]
    strangers_apart = [
        event for event in home_output["interactions"] if event["relationship_type"] == "stranger"
    ]
    assert family_home
    assert not strangers_apart
    assert any(
        item["reason"] == "agents are not at the same specific place"
        for item in home_output["blocked_interactions"]
    )
    assert family_home[0]["state_deltas"][0]["state"] == "mood"
    assert (
        family_home[0]["interaction_tree"]["path"][0]["evidence"]["evidence_id"]
        == "conversation-outcome-v1"
    )

    colocated_request = deepcopy(prepared.rust_request)
    colocated_request["ticks"] = 200
    common_home = colocated_request["agents"]["place"][relationship["source_index"]]
    colocated_request["agents"]["place"] = [common_home, common_home, common_home]
    colocated_output = RustCoreClient().run_agents(colocated_request)
    family_colocated = sum(
        event["relationship_type"] == "family" for event in colocated_output["interactions"]
    )
    stranger_colocated = sum(
        event["relationship_type"] == "stranger" for event in colocated_output["interactions"]
    )
    assert stranger_colocated > 0
    assert family_colocated > stranger_colocated * 5

    away_request = deepcopy(prepared.rust_request)
    away_request["ticks"] = 200
    away_request["agents"]["place"][relationship["target_index"]] = away_request["agents"]["place"][
        stranger_index
    ]
    away_request["network"] = None
    away_output = RustCoreClient().run_agents(away_request)
    assert not any(event["relationship_type"] == "family" for event in away_output["interactions"])


def test_interaction_tree_effect_state_is_required_before_rust_execution(tmp_path):
    materialization = _two_household_population()
    population = materialization.population.model_copy(
        update={
            "agents": [
                agent.model_copy(update={"states": {}})
                for agent in materialization.population.agents
            ]
        }
    )
    store = SimulationRegistryStore(tmp_path / "missing-state.json")
    store.save_initial_population(materialization.model_copy(update={"population": population}))
    _save_executable_decisions(store)
    store.save_routines(_routine_registry())
    tree = InteractionTreeDefinition(
        id="talk-outcome",
        name="Talk outcome",
        version="v1",
        entry_node="start",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="start", label="Start", terminal=False),
            InteractionTreeNode(id="done", label="Done", terminal=True),
        ),
        transitions=(
            InteractionTreeTransition(
                id="finish",
                from_node="start",
                to_node="done",
                outcome="finished",
                probability=1,
                evidence=InteractionTransitionEvidence(
                    source="Measured conversation fixture",
                    version="v1",
                    status="measured_joint",
                    uncertainty=0,
                    evidence_id="conversation-v1",
                ),
                effects=(
                    InteractionTreeAgentStateEffect(
                        participant="target",
                        field="mood",
                        operation="add",
                        value=0.1,
                        minimum=-1,
                        maximum=1,
                    ),
                ),
            ),
        ),
    )
    store.save_interaction_tree(tree)
    family = _relationship_evidence(
        "family",
        weight=0.8,
        trust=0.75,
        similarity=0.5,
    )
    store.save_interaction_program(
        InteractionProgramDefinition(
            version="v1",
            status="confirmed",
            relationship_evidence=(family,),
            rules=(
                InteractionRule(
                    id="talk",
                    source_action="return home",
                    interaction_type="talk",
                    channel="in_person",
                    max_targets_per_initiator=1,
                    allowed_relationships=("family",),
                    allowed_place_kinds=("home",),
                    base_factor=_interaction_factor("base"),
                    relationship_factors={"family": _interaction_factor("family")},
                    colocation_factors={
                        "same_specific_place": _interaction_factor("same-place")
                    },
                    place_factors={"home": _interaction_factor("home")},
                    time_factors=(
                        TimeFactorWindow(
                            weekdays=(0, 1, 2, 3, 4, 5, 6),
                            start_hour=0,
                            end_hour=24,
                            factor=_interaction_factor("all-day"),
                        ),
                    ),
                    interaction_tree_id=tree.id,
                ),
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="interaction tree effects reference unavailable numeric state: talk-outcome:mood",
    ):
        prepare_registry_run(store, _run_config())

    routine_tree = tree.model_copy(
        update={
            "transitions": (
                tree.transitions[0].model_copy(
                    update={
                        "effects": (
                            AgentRoutineEffect(
                                participant="target",
                                operation="add",
                                routine_id="follow-up",
                            ),
                        )
                    }
                ),
            )
        }
    )
    store.save_interaction_tree(routine_tree)
    with pytest.raises(
        ValueError,
        match=(
            "interaction tree routine effects are unavailable in numeric runs: "
            "talk-outcome:follow-up"
        ),
    ):
        prepare_registry_run(store, _run_config())


def test_routines_move_agents_to_scoped_workplaces_and_distinct_homes(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    store.save_initial_population(_two_household_population())
    _save_executable_decisions(store)
    store.save_routines(_routine_registry())
    store.save_mobility(_mobility_registry())

    prepared = prepare_registry_run(store, _run_config())
    schedules = {schedule["action"]: schedule for schedule in prepared.rust_request["schedules"]}
    initial_indices = prepared.rust_request["agents"]["place"]
    home_destinations = schedules["return home"]["destination_place_by_agent"]
    work_destinations = schedules["work"]["destination_place_by_agent"]

    assert len(set(initial_indices)) == 2
    assert home_destinations == initial_indices
    assert len(set(home_destinations)) == 2
    assert len(set(work_destinations)) == 2
    assert set(schedules) == {"return home", "work"}
    assert all(place["kind"] not in {"gym", "cafe"} for place in prepared.rust_request["places"])
    assert all(
        all(plan is not None for plan in schedule["travel_by_agent"])
        for schedule in schedules.values()
    )
    location_ids = {place.id for place in prepared.location_places}
    assert set(prepared.runtime_place_location_ids) <= location_ids
    assert len(prepared.runtime_place_location_ids) == len(prepared.rust_request["places"])
    transit_places = [
        place for place in prepared.rust_request["places"] if place["kind"] == "transit"
    ]
    assert transit_places
    assert all(place["state"] == {"crowd_density": 0.7} for place in transit_places)
    profiles = {profile.place_kind: profile for profile in _mobility_registry().place_profiles}
    for place in prepared.rust_request["places"]:
        profile = profiles.get(place["kind"])
        if profile is None:
            continue
        assert place["accepts_arrivals"] == profile.accepts_arrivals
        assert place["capacity"] == profile.capacity
    profiled_locations = [
        place for place in prepared.location_places if place.evidence is not None
    ]
    assert profiled_locations
    assert {place.evidence.evidence_id for place in profiled_locations} == {
        "travel-fixture-2025"
    }

    output = RustCoreClient().run_agents(prepared.rust_request)
    home_moves = [
        move
        for move in output["location_transitions"]
        if move["source"] == schedules["return home"]["id"] and move["phase"] == "travel_arrived"
    ]

    assert {(move["agent_index"], move["to_place_index"]) for move in home_moves} == set(
        enumerate(home_destinations)
    )
    assert output["agents"]["place"] == home_destinations


def test_multi_typed_agent_runs_business_and_family_routines(tmp_path):
    population = materialize_initial_population(
        InitialPopulationRequest(
            population_id="multi-role-person",
            version="v1",
            seed=17,
            target_agents=1,
            evidence=[_evidence()],
            household_templates=[
                HouseholdSeed(
                    template_id="multi-role-home",
                    place="CA",
                    country="Canada",
                    region="Northern America",
                    city="Vancouver",
                    latitude=49.2,
                    longitude=-123.1,
                    weight=1,
                    evidence_id="joint",
                    members=[
                        HouseholdMemberSeed(
                            member_id="resident",
                            name="Multi Role",
                            age=39,
                            sex="female",
                            relationship_to_reference="self",
                            agent_types=["business_agent", "family_person"],
                        )
                    ],
                )
            ],
        )
    )
    routines = RoutineRegistryDefinition(
        agent_types=[
            AgentTypeDefinition(
                id="business_agent",
                name="Business agent",
                parent_ids=["family_person"],
                routines=[_routine_member("business_work")],
            ),
            AgentTypeDefinition(
                id="family_person",
                name="Family person",
                routines=[_routine_member("family_time")],
            ),
        ],
        routines=[
            RoutineDefinition(
                id="business_work",
                name="Business work",
                agent_type_id="business_agent",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed business schedule",
                ),
                steps=[
                    RoutineStep(
                        id="work",
                        name="Work",
                        activity="business work",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="00:00",
                            end_time="23:59",
                            place_ids=["current"],
                            role_ids=["business_agent"],
                        ),
                    )
                ],
            ),
            RoutineDefinition(
                id="family_time",
                name="Family time",
                agent_type_id="family_person",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed family schedule",
                ),
                steps=[
                    RoutineStep(
                        id="connect",
                        name="Connect",
                        activity="family time",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="00:00",
                            end_time="23:59",
                            place_ids=["current"],
                            role_ids=["family_person"],
                        ),
                    )
                ],
            ),
        ],
    )
    store = SimulationRegistryStore(tmp_path / "registry.json")
    store.save_initial_population(population)
    _save_executable_decisions(store)
    store.save_routines(routines)
    config = SimulationRunConfig(
        population_size=1,
        seed=31,
        days=1,
        tick_interval_hours=24,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="country", identifier="Canada"),
        agent_type_mix={"business_agent": 1},
    )

    prepared = prepare_registry_run(store, config)
    actions = {schedule["action"] for schedule in prepared.rust_request["schedules"]}
    output = RustCoreClient().run_agents(prepared.rust_request)

    assert actions == {"business work", "family time"}
    assert {item["action"] for item in output["routine_actions"]} == actions
    assert len(output["routine_actions"]) == 2


def test_confirmed_interaction_program_rejects_blocked_selected_evidence(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    materialization = _two_household_population()
    first, second = materialization.population.agents
    first = first.model_copy(
        update={
            "relationships": [
                Relationship(
                    target_id=second.agent_id,
                    kind="friend",
                    weight=0.8,
                    trust=0.7,
                    similarity=0.6,
                    evidence_id="friend-panel-v1",
                    evidence_status="measured_joint",
                )
            ]
        }
    )
    second = second.model_copy(
        update={
            "relationships": [
                Relationship(
                    target_id=first.agent_id,
                    kind="friend",
                    weight=0.4,
                    trust=0.3,
                    similarity=0.2,
                    evidence_id="unknown-friend-link",
                    evidence_status="unknown",
                )
            ]
        }
    )
    population = materialization.population.model_copy(update={"agents": [first, second]})
    store.save_initial_population(materialization.model_copy(update={"population": population}))
    _save_executable_decisions(store)
    store.save_routines(_routine_registry())
    tree = InteractionTreeDefinition(
        id="conversation-outcome",
        name="Conversation outcome",
        version="v1",
        entry_node="start",
        allowed_channels=("in_person",),
        co_location_policy="required",
        nodes=(
            InteractionTreeNode(id="start", label="Start", terminal=False),
            InteractionTreeNode(id="done", label="Done", terminal=True),
        ),
        transitions=(
            InteractionTreeTransition(
                id="finish",
                from_node="start",
                to_node="done",
                outcome="finished",
                probability=1,
                evidence=InteractionTransitionEvidence(
                    source="Measured conversation fixture",
                    version="v1",
                    status="measured_joint",
                    uncertainty=0,
                    evidence_id="conversation-v1",
                ),
            ),
        ),
    )
    store.save_interaction_tree(tree)
    rule = InteractionRule(
        id="talk-to-friend",
        source_action="return home",
        interaction_type="talk",
        channel="in_person",
        max_targets_per_initiator=1,
        allowed_relationships=("friend",),
        allowed_place_kinds=("home",),
        base_factor=_interaction_factor("base"),
        relationship_factors={"friend": _interaction_factor("friend")},
        colocation_factors={"same_specific_place": _interaction_factor("same_place")},
        place_factors={"home": _interaction_factor("home")},
        time_factors=(
            TimeFactorWindow(
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=0,
                end_hour=24,
                factor=_interaction_factor("all_day"),
            ),
        ),
        interaction_tree_id=tree.id,
    )
    store.save_interaction_program(
        InteractionProgramDefinition(
            version="v1",
            status="confirmed",
            relationship_evidence=(
                _relationship_evidence(
                    "friend",
                    weight=0.8,
                    trust=0.7,
                    similarity=0.6,
                ),
            ),
            rules=(rule,),
        )
    )

    with pytest.raises(ValueError, match="selected relationships without matching") as error:
        prepare_registry_run(store, _run_config())

    assert second.agent_id in str(error.value)
    assert first.agent_id in str(error.value)
