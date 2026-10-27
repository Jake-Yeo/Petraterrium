from collections import defaultdict
from copy import deepcopy
from datetime import date

import pytest

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
from petraterrium.simulation.mobility import (
    MobilityEvidence,
    MobilityRegistryDefinition,
    PlaceProfileDefinition,
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


def _population():
    return materialize_initial_population(
        InitialPopulationRequest(
            population_id="decision-people",
            version="v1",
            seed=11,
            target_agents=2,
            evidence=[
                EvidenceReference(
                    evidence_id="population-joint",
                    source="Measured population fixture",
                    source_version="v1",
                    observed_at="2025-01-01",
                    licence="Test",
                    place="CA",
                    status="measured_joint",
                    fields=["age", "sex", "household_composition"],
                    uncertainty="Fixture confidence interval",
                )
            ],
            household_templates=[
                HouseholdSeed(
                    template_id="two-adults",
                    place="CA",
                    country="Canada",
                    region="Northern America",
                    city="Vancouver",
                    latitude=49.2,
                    longitude=-123.1,
                    weight=1,
                    evidence_id="population-joint",
                    members=[
                        HouseholdMemberSeed(
                            member_id="younger",
                            name="Younger",
                            age=30,
                            sex="female",
                            relationship_to_reference="self",
                            agent_types=["worker"],
                            states={"free_evening": "1"},
                        ),
                        HouseholdMemberSeed(
                            member_id="older",
                            name="Older",
                            age=60,
                            sex="male",
                            relationship_to_reference="spouse",
                            agent_types=["worker"],
                            states={"free_evening": "1"},
                        ),
                    ],
                )
            ],
        )
    )


def _source() -> ResearchCitation:
    factor_ids = ("out_age", "out_free", "stay_age", "stay_free")
    return ResearchCitation(
        kind="research_paper",
        imported_source_id="canada-social-panel-2025",
        title="Canadian social activity panel",
        source="Fixture Journal",
        publication_date=date(2025, 6, 1),
        population_studied="Adults in Canada",
        link_or_reference="https://example.test/canada-social-panel",
        supports_decision_ids=("social-choice",),
        supports_factor_ids=factor_ids,
    )


def _factor(identity: str, input_kind: str, input_key: str) -> ProbabilityFactor:
    return ProbabilityFactor(
        id=identity,
        name=identity.replace("_", " "),
        input_kind=input_kind,
        input_key=input_key,
        feature_id="age" if input_kind == "trait" else None,
    )


def _edge(
    identity: str,
    destination: str,
    factor_ids: tuple[str, str],
    source: ResearchCitation,
) -> DecisionEdgeTemplate:
    return DecisionEdgeTemplate(
        id=identity,
        decision_id="social-choice",
        domain="social",
        from_state="decide",
        to_state=destination,
        label=destination.replace("_", " ").title(),
        formula=DecisionProbabilityFormula(
            id=f"{identity}_formula",
            name=f"{identity} probability",
            combination="product",
            factors=(
                _factor(factor_ids[0], "trait", "age"),
                _factor(factor_ids[1], "context", "free_evening"),
            ),
        ),
        source=source,
    )


def _tree_registry() -> DecisionTreeRegistryDefinition:
    return DecisionTreeRegistryDefinition(
        version="confirmed-tree-v1",
        trees=[
            DecisionTreeDefinition(
                id="social-choice",
                version="v1",
                name="Social choice",
                root_module_id="social-choice-module",
                agent_type_ids=["worker"],
                place_ids=["CA"],
                source="User-confirmed registry fixture",
                status="ready",
            )
        ],
        modules=[
            DecisionTreeModule(
                id="social-choice-module",
                version="v1",
                name="Social choice",
                entry_node="decide",
                nodes=[
                    DecisionTreeNode(id="decide", label="Decide", kind="decision"),
                    DecisionTreeNode(id="go_out", label="Go out", kind="terminal"),
                    DecisionTreeNode(id="stay_home", label="Stay home", kind="terminal"),
                ],
                edges=[
                    DecisionTreeEdge(
                        id="choose_out",
                        from_node="decide",
                        to_node="go_out",
                    ),
                    DecisionTreeEdge(
                        id="choose_home",
                        from_node="decide",
                        to_node="stay_home",
                    ),
                ],
                source="User-confirmed registry fixture",
                status="ready",
            )
        ],
    )


def _evidence_registry() -> DecisionEvidenceRegistryDefinition:
    source = _source()
    template = DecisionTreeTemplate(
        id="social-choice",
        name="Social choice",
        domain="social",
        status="ready",
        entry_state="decide",
        terminal_states=("go_out", "stay_home"),
        nodes=(
            DecisionNodeTemplate(id="decide", label="Decide", kind="decision"),
            DecisionNodeTemplate(id="go_out", label="Go out", kind="terminal"),
            DecisionNodeTemplate(id="stay_home", label="Stay home", kind="terminal"),
        ),
        edges=(
            _edge("choose_out", "go_out", ("out_age", "out_free"), source),
            _edge("choose_home", "stay_home", ("stay_age", "stay_free"), source),
        ),
    )
    place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="Northern America",
        country_id="CA",
    )
    rows = []
    for edge_id, factor_id, value, estimate in (
        ("choose_out", "out_age", 30, 0.8),
        ("choose_out", "out_age", 60, 0.25),
        ("choose_out", "out_free", "1", 1.0),
        ("choose_home", "stay_age", 30, 0.2),
        ("choose_home", "stay_age", 60, 0.75),
        ("choose_home", "stay_free", "1", 1.0),
    ):
        rows.append(
            DecisionFactorEvidence(
                id=f"{edge_id}-{factor_id}-{value}",
                decision_id="social-choice",
                edge_id=edge_id,
                factor_id=factor_id,
                place=place,
                predicate=EvidencePredicate(operator="exact", value=value),
                basis="measured_joint",
                estimate=estimate,
                ci_low=max(0, estimate - 0.05),
                ci_high=min(1, estimate + 0.05),
                sample_size=800,
                fittable=True,
                source=source,
            )
        )
    return DecisionEvidenceRegistryDefinition(
        version="confirmed-evidence-v3",
        templates=[template],
        evidence=rows,
    )


def _nested_tree_registry() -> DecisionTreeRegistryDefinition:
    module_specs = (
        (
            "evening-module",
            "Evening choice",
            "decide",
            (
                DecisionTreeNode(id="decide", label="Decide", kind="decision"),
                DecisionTreeNode(
                    id="go_out",
                    label="Go out",
                    kind="module_reference",
                    target_module_id="venue-module",
                ),
                DecisionTreeNode(id="stay_home", label="Stay home", kind="terminal"),
            ),
            (
                ("choose_out", "decide", "go_out", "evening-decision"),
                ("choose_home", "decide", "stay_home", "evening-decision"),
            ),
        ),
        (
            "venue-module",
            "Venue choice",
            "choose_venue",
            (
                DecisionTreeNode(id="choose_venue", label="Choose venue", kind="decision"),
                DecisionTreeNode(
                    id="bar",
                    label="Bar",
                    kind="module_reference",
                    target_module_id="bar-module",
                ),
                DecisionTreeNode(id="park", label="Park", kind="terminal"),
            ),
            (
                ("choose_bar", "choose_venue", "bar", "venue-decision"),
                ("choose_park", "choose_venue", "park", "venue-decision"),
            ),
        ),
        (
            "bar-module",
            "Bar outcome",
            "at_bar",
            (
                DecisionTreeNode(id="at_bar", label="At bar", kind="decision"),
                DecisionTreeNode(id="get_sick", label="Get sick", kind="terminal"),
                DecisionTreeNode(id="go_home", label="Go home", kind="terminal"),
            ),
            (
                ("become_sick", "at_bar", "get_sick", "bar-decision"),
                ("leave_well", "at_bar", "go_home", "bar-decision"),
            ),
        ),
    )
    modules = [
        DecisionTreeModule(
            id=module_id,
            version="v1",
            name=name,
            entry_node=entry_node,
            nodes=list(nodes),
            edges=[
                DecisionTreeEdge(
                    id=edge_id,
                    from_node=from_node,
                    to_node=to_node,
                    decision_id=decision_id,
                    evidence_edge_id=edge_id,
                )
                for edge_id, from_node, to_node, decision_id in edges
            ],
            source="User-confirmed modular registry fixture",
            status="ready",
        )
        for module_id, name, entry_node, nodes, edges in module_specs
    ]
    return DecisionTreeRegistryDefinition(
        version="confirmed-modular-tree-v1",
        trees=[
            DecisionTreeDefinition(
                id="evening-chain",
                version="v1",
                name="Evening chain",
                root_module_id="evening-module",
                agent_type_ids=["worker"],
                place_ids=["CA"],
                source="User-confirmed modular registry fixture",
                status="ready",
            ),
            DecisionTreeDefinition(
                id="bar-arrival",
                version="v1",
                name="Bar arrival",
                root_module_id="bar-module",
                agent_type_ids=["worker"],
                place_ids=["CA"],
                source="User-confirmed modular registry fixture",
                status="ready",
            ),
        ],
        modules=modules,
    )


def _nested_evidence_registry() -> DecisionEvidenceRegistryDefinition:
    decisions = (
        (
            "evening-decision",
            "Evening choice",
            "decide",
            (("choose_out", "go_out", 1.0), ("choose_home", "stay_home", 0.0)),
        ),
        (
            "venue-decision",
            "Venue choice",
            "choose_venue",
            (("choose_bar", "bar", 1.0), ("choose_park", "park", 0.0)),
        ),
        (
            "bar-decision",
            "Bar outcome",
            "at_bar",
            (("become_sick", "get_sick", 1.0), ("leave_well", "go_home", 0.0)),
        ),
    )
    factor_ids = tuple(
        factor_id
        for _, _, _, edges in decisions
        for edge_id, _, _ in edges
        for factor_id in (f"{edge_id}_age", f"{edge_id}_free")
    )
    source = ResearchCitation(
        kind="research_paper",
        imported_source_id="canada-modular-social-panel-2025",
        title="Canadian modular social activity panel",
        source="Fixture Journal",
        publication_date=date(2025, 6, 1),
        population_studied="Adults in Canada",
        link_or_reference="https://example.test/canada-modular-social-panel",
        supports_decision_ids=tuple(item[0] for item in decisions),
        supports_factor_ids=factor_ids,
    )
    templates = []
    evidence = []
    place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="Northern America",
        country_id="CA",
    )
    for decision_id, name, entry_state, edges in decisions:
        templates.append(
            DecisionTreeTemplate(
                id=decision_id,
                name=name,
                domain="social",
                status="ready",
                entry_state=entry_state,
                terminal_states=tuple(destination for _, destination, _ in edges),
                nodes=(
                    DecisionNodeTemplate(
                        id=entry_state,
                        label=name,
                        kind="decision",
                    ),
                    *(
                        DecisionNodeTemplate(
                            id=destination,
                            label=destination.replace("_", " ").title(),
                            kind="terminal",
                        )
                        for _, destination, _ in edges
                    ),
                ),
                edges=tuple(
                    DecisionEdgeTemplate(
                        id=edge_id,
                        decision_id=decision_id,
                        domain="social",
                        from_state=entry_state,
                        to_state=destination,
                        label=destination.replace("_", " ").title(),
                        formula=DecisionProbabilityFormula(
                            id=f"{edge_id}_formula",
                            name=f"{destination} probability",
                            combination="product",
                            factors=(
                                _factor(f"{edge_id}_age", "trait", "age"),
                                _factor(
                                    f"{edge_id}_free",
                                    "context",
                                    "free_evening",
                                ),
                            ),
                        ),
                        source=source,
                    )
                    for edge_id, destination, _ in edges
                ),
            )
        )
        for edge_id, _, estimate in edges:
            for age in (30, 60):
                evidence.append(
                    DecisionFactorEvidence(
                        id=f"{decision_id}-{edge_id}-{age}",
                        decision_id=decision_id,
                        edge_id=edge_id,
                        factor_id=f"{edge_id}_age",
                        place=place,
                        predicate=EvidencePredicate(operator="exact", value=age),
                        basis="measured_joint",
                        estimate=estimate,
                        ci_low=estimate,
                        ci_high=estimate,
                        sample_size=800,
                        fittable=True,
                        source=source,
                    )
                )
            evidence.append(
                DecisionFactorEvidence(
                    id=f"{decision_id}-{edge_id}-free",
                    decision_id=decision_id,
                    edge_id=edge_id,
                    factor_id=f"{edge_id}_free",
                    place=place,
                    predicate=EvidencePredicate(operator="exact", value="1"),
                    basis="measured_joint",
                    estimate=1,
                    ci_low=1,
                    ci_high=1,
                    sample_size=800,
                    fittable=True,
                    source=source,
                )
            )
    return DecisionEvidenceRegistryDefinition(
        version="confirmed-modular-evidence-v1",
        templates=templates,
        evidence=evidence,
    )


def _routines() -> RoutineRegistryDefinition:
    worker = AgentTypeDefinition(
        id="worker",
        name="Worker",
        routines=[
            AgentTypeMember(
                id="evening-choice",
                name="Evening choice",
                definition="User-confirmed evening decision schedule",
            )
        ],
    )
    return RoutineRegistryDefinition(
        agent_types=[worker],
        routines=[
            RoutineDefinition(
                id="evening-choice",
                name="Evening choice",
                agent_type_id="worker",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed fixture schedule",
                ),
                steps=[
                    RoutineStep(
                        id="choose",
                        name="Choose",
                        activity="choose evening activity",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="01:00",
                            end_time="02:00",
                            place_ids=["current_place"],
                            role_ids=["worker"],
                        ),
                        decision_tree_module_id="social-choice-module",
                    )
                ],
            )
        ],
    )


def _bar_routines() -> RoutineRegistryDefinition:
    worker = AgentTypeDefinition(
        id="worker",
        name="Worker",
        routines=[
            AgentTypeMember(
                id="morning-bar-choice",
                name="Morning bar choice",
                definition="User-confirmed decision activation schedule",
            )
        ],
    )
    return RoutineRegistryDefinition(
        agent_types=[worker],
        routines=[
            RoutineDefinition(
                id="morning-bar-choice",
                name="Morning bar choice",
                agent_type_id="worker",
                evidence=RoutineEvidence(
                    status="user_defined",
                    note="User-confirmed fixture schedule",
                ),
                steps=[
                    RoutineStep(
                        id="choose",
                        name="Choose",
                        activity="choose bar outcome",
                        schedule=RoutineSchedule(
                            days=["tuesday"],
                            start_time="09:00",
                            end_time="10:00",
                            place_ids=["current_place"],
                            role_ids=["worker"],
                        ),
                        decision_tree_module_id="bar-module",
                    )
                ],
            )
        ],
    )


def _config() -> SimulationRunConfig:
    return SimulationRunConfig(
        population_size=2,
        seed=77,
        days=1,
        tick_interval_hours=1,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="country", identifier="Canada"),
        agent_type_mix={"worker": 1.0},
    )


def _configured_store(tmp_path) -> SimulationRegistryStore:
    store = SimulationRegistryStore(tmp_path / "registry.json")
    store.save_initial_population(_population())
    store.save_decision_trees(_tree_registry())
    store.save_decision_evidence(_evidence_registry())
    store.save_routines(_routines())
    return store


def _place_restricted_mobility() -> MobilityRegistryDefinition:
    evidence = MobilityEvidence(
        status="user_defined",
        source_title="Confirmed place profile fixture",
        source_version="v1",
        source_date="2026-10-27",
        licence="Test",
        evidence_id="place-profile-v1",
        uncertainty=0,
    )
    return MobilityRegistryDefinition(
        version="place-profile-v1",
        status="confirmed",
        place_profiles=[
            PlaceProfileDefinition(
                id="home",
                place_kind="home",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=4,
                state={},
                available_decision_tree_ids=["social-choice"],
                evidence=evidence,
            ),
            PlaceProfileDefinition(
                id="work",
                place_kind="work",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=10,
                state={},
                available_decision_tree_ids=[],
                evidence=evidence,
            ),
        ],
        routes=[],
    )


def _nested_configured_store(tmp_path) -> SimulationRegistryStore:
    store = SimulationRegistryStore(tmp_path / "nested-registry.json")
    store.save_initial_population(_population())
    store.save_decision_trees(_nested_tree_registry())
    store.save_decision_evidence(_nested_evidence_registry())
    return store


def test_assigned_tree_stays_idle_until_explicit_routine_activation_regardless_of_order(
    tmp_path,
):
    outputs = []
    for reverse in (False, True):
        store = SimulationRegistryStore(tmp_path / f"ordered-{reverse}.json")
        registry = _nested_tree_registry()
        if reverse:
            registry = registry.model_copy(update={"trees": list(reversed(registry.trees))})
        store.save_initial_population(_population())
        store.save_decision_trees(registry)
        store.save_decision_evidence(_nested_evidence_registry())
        store.save_routines(_bar_routines())

        prepared = prepare_registry_run(store, _config())
        entry_by_module = {
            module["id"]: module["entry_state"] for module in prepared.rust_request["modules"]
        }
        initial_modules = prepared.rust_request["agents"]["module"]
        assert {entry_by_module[module_id] for module_id in initial_modules} == {"idle"}

        before_activation = deepcopy(prepared.rust_request)
        before_activation["ticks"] = 9
        before_output = RustCoreClient().run_agents(before_activation)
        assert before_output["transition_outcomes"] == []

        through_activation = deepcopy(prepared.rust_request)
        through_activation["ticks"] = 10
        output = RustCoreClient().run_agents(through_activation)
        assert {(item["tick"], item["transition"]) for item in output["transition_outcomes"]} == {
            (10, "become_sick")
        }
        outputs.append(output["transition_outcomes"])

    assert outputs[0] == outputs[1]


def test_confirmed_registry_compiles_to_rust_and_records_agent_paths(tmp_path):
    prepared = prepare_registry_run(_configured_store(tmp_path), _config())

    modules = prepared.rust_request["modules"]
    idle_modules = [module for module in modules if module["entry_state"] == "idle"]
    decision_modules = [module for module in modules if module["entry_state"] != "idle"]
    assert len(idle_modules) == 1
    assert idle_modules[0]["transitions"] == []
    assert all(
        module["transitions"][0]["id"] != "remain-active-without-confirmed-decision-program"
        for module in decision_modules
    )
    schedule = prepared.rust_request["schedules"][0]
    assert all(schedule["activate_module_by_agent"])
    assert set(schedule["activate_module_by_agent"]).isdisjoint(
        prepared.rust_request["agents"]["module"]
    )

    output = RustCoreClient().run_agents(prepared.rust_request)
    paths = defaultdict(list)
    for outcome in output["transition_outcomes"]:
        paths[outcome["agent_index"]].append(outcome)

    assert set(paths) == {0, 1}
    assert all(len(path) == 1 for path in paths.values())
    assert all({step["tick"] for step in path} == {2} for path in paths.values())
    assert {output["agents"]["state"][index] for index in paths} <= {
        "go_out",
        "stay_home",
    }
    for path in paths.values():
        for step in path:
            provenance = step["provenance"]
            assert provenance["status"] == "measured"
            assert provenance["resolution_status"] == "inherited"
            assert provenance["source_places"] == ["country:CA"]
            assert "Canadian social activity panel" in provenance["source"]
            assert provenance["source_date"] == "2025-06-01"
            assert provenance["evidence_kind"] == "measured_joint"
            assert provenance["ci_low"] <= step["probability"] <= provenance["ci_high"]


def test_place_profiles_compile_tree_availability_into_rust_modules(tmp_path):
    store = _configured_store(tmp_path)
    store.save_mobility(_place_restricted_mobility())

    prepared = prepare_registry_run(store, _config())

    assert prepared.rust_request["places"]
    assert all(
        place["accepts_arrivals"] and place["capacity"] == 4
        for place in prepared.rust_request["places"]
    )
    idle_modules = [
        module for module in prepared.rust_request["modules"] if module["entry_state"] == "idle"
    ]
    decision_modules = [
        module for module in prepared.rust_request["modules"] if module["entry_state"] != "idle"
    ]
    assert all(module["available_place_kinds"] == [] for module in idle_modules)
    assert all(module["available_place_kinds"] == ["home"] for module in decision_modules)

    away = deepcopy(prepared.rust_request)
    for place in away["places"]:
        place["kind"] = "work"
        place["capacity"] = 10
        place.pop("available_decision_modules")
    output = RustCoreClient().run_agents(away)

    assert output["transition_outcomes"] == []
    assert output["routine_unavailable"]
    assert all(
        "requires place kind home" in item["reason"] for item in output["routine_unavailable"]
    )


def test_specific_runtime_place_profile_overrides_all_kind_level_behavior(tmp_path):
    store = _configured_store(tmp_path)
    default_registry = _place_restricted_mobility()
    store.save_mobility(default_registry)
    runtime_place_id = prepare_registry_run(store, _config()).rust_request["places"][0]["id"]
    evidence = default_registry.place_profiles[0].evidence
    exact_profile = PlaceProfileDefinition(
        id="closed-specific-home",
        place_id=runtime_place_id,
        place_kind="home",
        accepts_arrivals=False,
        allows_in_person=False,
        capacity=3,
        state={"contamination": 0.8},
        available_decision_tree_ids=[],
        evidence=evidence,
    )
    store.save_mobility(
        default_registry.model_copy(
            update={"place_profiles": [*default_registry.place_profiles, exact_profile]}
        )
    )

    prepared = prepare_registry_run(store, _config())
    place = prepared.rust_request["places"][0]
    decision_modules = {
        module["id"]
        for module in prepared.rust_request["modules"]
        if module["entry_state"] != "idle"
    }

    assert place == {
        "id": runtime_place_id,
        "kind": "home",
        "accepts_arrivals": False,
        "allows_in_person": False,
        "capacity": 3,
        "state": {"contamination": 0.8},
        "available_decision_modules": [
            module["id"]
            for module in prepared.rust_request["modules"]
            if module["entry_state"] == "idle"
        ],
    }
    assert decision_modules.isdisjoint(place["available_decision_modules"])
    location = next(
        item
        for item in prepared.location_places
        if item.id == prepared.runtime_place_location_ids[0]
    )
    assert location.accepts_arrivals is False
    assert location.allows_in_person is False
    assert location.capacity == 3
    assert location.state == {"contamination": 0.8}
    assert [(item.tree_id, item.available) for item in location.decision_trees] == [
        ("social-choice", False)
    ]

    output = RustCoreClient().run_agents(prepared.rust_request)

    assert output["transition_outcomes"] == []
    assert output["routine_unavailable"]
    assert all("unavailable at place" in item["reason"] for item in output["routine_unavailable"])


def test_confirmed_module_reference_graph_executes_reachable_chain_in_rust(tmp_path):
    prepared = prepare_registry_run(_nested_configured_store(tmp_path), _config())

    entry_by_runtime = {
        module["id"]: module["entry_state"] for module in prepared.rust_request["modules"]
    }
    assert set(entry_by_runtime.values()) == {"idle", "decide", "choose_venue", "at_bar"}
    assert {
        (
            entry_by_runtime[route["from_module"]],
            route["exit_state"],
            entry_by_runtime[route["to_module"]],
        )
        for route in prepared.rust_request["routes"]
    } == {
        ("decide", "go_out", "choose_venue"),
        ("choose_venue", "bar", "at_bar"),
    }

    activated = deepcopy(prepared.rust_request)
    root_module = next(
        module_id for module_id, entry in entry_by_runtime.items() if entry == "decide"
    )
    activated["agents"]["module"] = [root_module] * len(activated["agents"]["module"])
    activated["agents"]["state"] = ["decide"] * len(activated["agents"]["state"])
    output = RustCoreClient().run_agents(activated)
    paths = defaultdict(list)
    for outcome in output["transition_outcomes"]:
        paths[outcome["agent_index"]].append(outcome)

    assert set(paths) == {0, 1}
    assert all(
        [step["transition"] for step in path] == ["choose_out", "choose_bar", "become_sick"]
        for path in paths.values()
    )
    assert all(
        [entry_by_runtime[step["module"]] for step in path] == ["decide", "choose_venue", "at_bar"]
        for path in paths.values()
    )
    assert output["agents"]["state"] == ["get_sick", "get_sick"]


def test_confirmed_tree_rejects_independence_only_factor(tmp_path):
    store = _configured_store(tmp_path)
    registry = _evidence_registry()
    first = registry.evidence[0].model_copy(update={"basis": "marginal", "fittable": False})
    store.save_decision_evidence(
        registry.model_copy(update={"evidence": [first, *registry.evidence[1:]]})
    )

    with pytest.raises(RuntimeDecisionCompilationError, match="independence_estimate"):
        prepare_registry_run(store, _config())


def test_confirmed_tree_rejects_outgoing_probability_gap(tmp_path):
    store = _configured_store(tmp_path)
    registry = _evidence_registry()
    rows = [
        row.model_copy(update={"estimate": 0.1, "ci_low": 0.05, "ci_high": 0.15})
        if row.factor_id == "stay_age" and row.predicate.value == 30
        else row
        for row in registry.evidence
    ]
    store.save_decision_evidence(registry.model_copy(update={"evidence": rows}))

    with pytest.raises(RuntimeDecisionCompilationError, match="sum to 0.9"):
        prepare_registry_run(store, _config())


def _dynamic_evidence_registry(
    input_kind: str,
    input_key: str,
    profiles: tuple[tuple[EvidencePredicate, float], ...],
) -> DecisionEvidenceRegistryDefinition:
    source = _source()
    edges = []
    rows = []
    place = EvidencePlace(
        level="country",
        place_id="CA",
        region_id="Northern America",
        country_id="CA",
    )
    for edge_id, destination, static_factor, dynamic_factor, invert in (
        ("choose_out", "go_out", "out_age", "out_free", False),
        ("choose_home", "stay_home", "stay_age", "stay_free", True),
    ):
        edges.append(
            DecisionEdgeTemplate(
                id=edge_id,
                decision_id="social-choice",
                domain="social",
                from_state="decide",
                to_state=destination,
                label=destination.replace("_", " ").title(),
                formula=DecisionProbabilityFormula(
                    id=f"{edge_id}_formula",
                    name=f"{edge_id} probability",
                    combination="product",
                    factors=(
                        _factor(static_factor, "trait", "age"),
                        _factor(dynamic_factor, input_kind, input_key),
                    ),
                ),
                source=source,
            )
        )
        rows.append(
            DecisionFactorEvidence(
                id=f"{edge_id}-{static_factor}-30",
                decision_id="social-choice",
                edge_id=edge_id,
                factor_id=static_factor,
                place=place,
                predicate=EvidencePredicate(operator="exact", value=30),
                basis="measured_joint",
                estimate=1,
                ci_low=1,
                ci_high=1,
                sample_size=800,
                fittable=True,
                source=source,
            )
        )
        for index, (predicate, out_probability) in enumerate(profiles):
            estimate = 1 - out_probability if invert else out_probability
            rows.append(
                DecisionFactorEvidence(
                    id=f"{edge_id}-{dynamic_factor}-{index}",
                    decision_id="social-choice",
                    edge_id=edge_id,
                    factor_id=dynamic_factor,
                    place=place,
                    predicate=predicate,
                    basis="measured_joint",
                    estimate=estimate,
                    ci_low=estimate,
                    ci_high=estimate,
                    sample_size=800,
                    fittable=True,
                    source=source,
                )
            )
    return DecisionEvidenceRegistryDefinition(
        version=f"dynamic-{input_kind}-{input_key}-v1",
        templates=[
            DecisionTreeTemplate(
                id="social-choice",
                name="Social choice",
                domain="social",
                status="ready",
                entry_state="decide",
                terminal_states=("go_out", "stay_home"),
                nodes=(
                    DecisionNodeTemplate(id="decide", label="Decide", kind="decision"),
                    DecisionNodeTemplate(id="go_out", label="Go out", kind="terminal"),
                    DecisionNodeTemplate(id="stay_home", label="Stay home", kind="terminal"),
                ),
                edges=tuple(edges),
            )
        ],
        evidence=rows,
    )


def _compiled_dynamic_module(
    input_kind: str,
    input_key: str,
    profiles: tuple[tuple[EvidencePredicate, float], ...],
):
    agent = _population().population.agents[0]
    compilation = compile_runtime_decisions(
        _tree_registry(),
        _dynamic_evidence_registry(input_kind, input_key, profiles),
        [agent],
        date(2026, 10, 26),
        runtime_context_keys={input_key} if input_kind == "context" else set(),
    )
    return agent, compilation


def _run_compiled_module(
    compilation,
    *,
    weekday: int = 0,
    hour: float = 12,
    places: list[dict] | None = None,
    place_index: int = 0,
    memory: dict[str, list[float]] | None = None,
):
    runtime_places = places or [
        {"id": "home", "kind": "home", "allows_in_person": True, "state": {}}
    ]
    active_module = compilation.runtime_module_by_source_module_by_agent[0]["social-choice-module"]
    active_state = next(
        module["entry_state"] for module in compilation.modules if module["id"] == active_module
    )
    return RustCoreClient().run_agents(
        {
            "seed": 4,
            "ticks": 1,
            "tick_hours": 1,
            "start_hour": hour,
            "start_weekday": weekday,
            "places": runtime_places,
            "agents": {
                "agent_ids": ["agent-1"],
                "module": [active_module],
                "state": [active_state],
                "place": [place_index],
                "traits": {"age": [30]},
                "trait_dictionaries": {},
                "memory": memory or {},
            },
            "modules": compilation.modules,
            "routes": compilation.routes,
            "network": None,
            "schedules": [],
            "meaningful_actions": [],
            "interactions": {},
            "synchronization": {},
        }
    )


def test_weekday_evidence_is_evaluated_by_rust_at_runtime():
    profiles = tuple(
        (
            EvidencePredicate(operator="exact", value=weekday),
            1.0 if weekday == "monday" else 0.0,
        )
        for weekday in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    )
    _, compilation = _compiled_dynamic_module("time", "weekday", profiles)

    assert {
        condition["input"]
        for transition in compilation.modules[0]["transitions"]
        for rule in transition["rules"]
        for condition in rule["conditions"]
    } == {"context.weekday"}
    assert all(
        len(rule["provenance"]["evidence_id"].split(",")) == 2
        for transition in compilation.modules[0]["transitions"]
        for rule in transition["rules"]
    )
    monday = _run_compiled_module(compilation, weekday=0)
    tuesday = _run_compiled_module(compilation, weekday=1)

    assert monday["agents"]["state"] == ["go_out"]
    assert tuesday["agents"]["state"] == ["stay_home"]


def test_hour_evidence_is_evaluated_by_rust_at_runtime():
    _, compilation = _compiled_dynamic_module(
        "time",
        "hour",
        (
            (EvidencePredicate(operator="between", lower=0, upper=11.99), 0),
            (EvidencePredicate(operator="between", lower=12, upper=24), 1),
        ),
    )

    morning = _run_compiled_module(compilation, hour=8)
    evening = _run_compiled_module(compilation, hour=18)

    assert morning["agents"]["state"] == ["stay_home"]
    assert evening["agents"]["state"] == ["go_out"]


def test_current_place_kind_evidence_is_evaluated_by_rust_at_runtime():
    _, compilation = _compiled_dynamic_module(
        "place",
        "kind",
        (
            (EvidencePredicate(operator="exact", value="home"), 0),
            (EvidencePredicate(operator="exact", value="bar"), 1),
        ),
    )
    places = [
        {"id": "home", "kind": "home", "allows_in_person": True, "state": {}},
        {"id": "bar", "kind": "bar", "allows_in_person": True, "state": {}},
    ]

    at_home = _run_compiled_module(compilation, places=places, place_index=0)
    at_bar = _run_compiled_module(compilation, places=places, place_index=1)

    assert at_home["agents"]["state"] == ["stay_home"]
    assert at_bar["agents"]["state"] == ["go_out"]


def test_place_state_evidence_is_evaluated_by_rust_at_runtime():
    _, compilation = _compiled_dynamic_module(
        "place",
        "contamination",
        (
            (EvidencePredicate(operator="between", lower=0, upper=0.49), 1),
            (EvidencePredicate(operator="between", lower=0.5, upper=1), 0),
        ),
    )

    clean = _run_compiled_module(
        compilation,
        places=[
            {
                "id": "clean-bar",
                "kind": "bar",
                "allows_in_person": True,
                "state": {"contamination": 0.2},
            }
        ],
    )
    contaminated = _run_compiled_module(
        compilation,
        places=[
            {
                "id": "contaminated-bar",
                "kind": "bar",
                "allows_in_person": True,
                "state": {"contamination": 0.8},
            }
        ],
    )

    assert clean["agents"]["state"] == ["go_out"]
    assert contaminated["agents"]["state"] == ["stay_home"]


def test_memory_evidence_is_evaluated_by_rust_at_runtime():
    _, compilation = _compiled_dynamic_module(
        "context",
        "bar_aversion",
        (
            (EvidencePredicate(operator="between", lower=0, upper=0.49), 1),
            (EvidencePredicate(operator="between", lower=0.5, upper=1), 0),
        ),
    )

    low_aversion = _run_compiled_module(
        compilation,
        memory={"bar_aversion": [0.2]},
    )
    high_aversion = _run_compiled_module(
        compilation,
        memory={"bar_aversion": [0.8]},
    )

    assert low_aversion["agents"]["state"] == ["go_out"]
    assert high_aversion["agents"]["state"] == ["stay_home"]


def test_context_factor_without_live_memory_binding_is_blocked():
    agent = _population().population.agents[0]

    with pytest.raises(
        RuntimeDecisionCompilationError,
        match="no live numeric memory binding.*cannot be frozen",
    ):
        compile_runtime_decisions(
            _tree_registry(),
            _dynamic_evidence_registry(
                "context",
                "bar_aversion",
                ((EvidencePredicate(operator="between", lower=0, upper=1), 1),),
            ),
            [agent],
            date(2026, 10, 26),
        )


def test_ready_tree_with_free_text_condition_is_blocked(tmp_path):
    store = _configured_store(tmp_path)
    registry = _tree_registry()
    conditioned_edge = (
        registry.modules[0].edges[0].model_copy(update={"condition": "Friday after work"})
    )
    conditioned_module = registry.modules[0].model_copy(
        update={"edges": [conditioned_edge, *registry.modules[0].edges[1:]]}
    )
    store.save_decision_trees(registry.model_copy(update={"modules": [conditioned_module]}))

    with pytest.raises(
        RuntimeDecisionCompilationError,
        match="free-text condition.*typed evidence predicate",
    ):
        prepare_registry_run(store, _config())
