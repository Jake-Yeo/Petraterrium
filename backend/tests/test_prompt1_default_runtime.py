import math
from collections import Counter, defaultdict

from petraterrium.atlas.feature_dump.priority_features import PRIORITY_COUNTRY_CODES
from petraterrium.atlas.regions import CANONICAL_REGIONS
from petraterrium.rust_core import RustCoreClient
from petraterrium.simulation.default_dsl import (
    DefaultDslService,
    load_shipped_default_dsl,
)
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import SimulationPlaceScope, SimulationRunConfig


def _default_run(store):
    return prepare_registry_run(
        store,
        SimulationRunConfig(
            population_size=1000,
            seed=1,
            days=30,
            tick_interval_hours=1,
            start_date="2026-10-27",
            place_scope=SimulationPlaceScope(level="global"),
            agent_type_mix={},
        ),
    )


def test_shipped_default_compiles_state_choices_propagation_and_finance(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    prepared = _default_run(store)

    request = prepared.rust_request
    actions = {item["id"]: item for item in request["meaningful_actions"]}
    dynamics = request["state_dynamics"]
    events = {item["id"]: item for item in dynamics["events"]}
    rules = {item["target_state_id"]: item for item in dynamics["state_rules"]}

    assert {
        "bad_work",
        "eat_lunch",
        "skip_lunch",
        "exercise",
        "work_or_study",
    } <= actions.keys()
    assert actions["eat_lunch"]["exclusive_choice_group"] == "midday_meal"
    assert actions["skip_lunch"]["exclusive_choice_group"] == "midday_meal"
    assert actions["skip_lunch"]["rules"][0]["conditions"][0]["input"] == "memory.stress"
    assert actions["skip_lunch"]["rules"][0]["conditions"][1]["input"] == (
        "memory.financial_stress"
    )
    assert actions["exercise"]["rules"][0]["conditions"][0]["input"] == "context.hour"
    for action_id in (
        "bad_work",
        "eat_lunch",
        "skip_lunch",
        "exercise",
        "work_or_study",
    ):
        for rule in actions[action_id]["rules"]:
            provenance = rule["provenance"]
            assert provenance["status"] == "default_estimated"
            assert provenance["ci_low"] == 0
            assert provenance["ci_high"] == 1
            assert provenance["uncertainty"] == 1
            assert "Statistics Canada" not in provenance["source"]
            assert "Statistique Canada" not in provenance["source"]
    assert events["bad_work"]["effects"][0:1] == [
        {"target": "memory.stress", "operation": "add", "value": 0.08}
    ]
    assert events["exercise"]["effects"][0]["target"] == "memory.stress"
    assert events["work_or_study"]["cash_flow"]["wages"] == 0
    assert events["eat_lunch"]["cash_flow"]["food"] == 0
    assert len(events["work_or_study"]["cash_flow_by_agent"]["wages"]) == 1000
    assert len(set(events["work_or_study"]["cash_flow_by_agent"]["wages"])) > 12
    assert len(events["eat_lunch"]["cash_flow_by_agent"]["food"]) == 1000
    assert len(set(events["eat_lunch"]["cash_flow_by_agent"]["food"])) > 12
    assert rules["health"]["coefficients"]["stress"] < 0
    assert len(dynamics["finance"]["currency"]) == 1000
    assert len(set(dynamics["finance"]["currency"])) > 1
    assert set(request["agents"]["memory"]["finance.income"]) == {0}
    assert set(request["agents"]["memory"]["finance.expenses"]) == {0}
    assert any(request["agents"]["memory"]["finance.annual_income"])
    assert any(request["agents"]["memory"]["finance.annual_expenses"])
    assert request["schedules"]
    assert all(schedule["action"] != "eat lunch" for schedule in request["schedules"])
    assert request["interactions"]["rules"]
    interaction_rule = request["interactions"]["rules"][0]
    assert interaction_rule["channel"] in {"online", "phone_message"}
    assert interaction_rule["base_factor"]["provenance"]["status"] == (
        "default_estimated"
    )
    assert prepared.program_version.startswith("generic-dsl-runtime-v1:")
    assert prepared.default_dsl_version == "base-1.0.0"
    assert prepared.default_dsl_hash is not None
    assert prepared.default_dsl_hash.startswith("sha256:")
    country_counts = Counter(
        profile["geography"]["country_id"] for profile in prepared.initial_agent_profiles
    )
    region_counts = Counter(
        profile["geography"]["region"] for profile in prepared.initial_agent_profiles
    )
    expected_countries = {*PRIORITY_COUNTRY_CODES, "CA", "AU"}
    expected_regions = set(CANONICAL_REGIONS) - {"Rest / unassigned"}
    assert sum(country_counts.values()) == 1000
    assert sum(region_counts.values()) == 1000
    assert expected_countries <= country_counts.keys()
    assert expected_regions <= region_counts.keys()
    assert region_counts["Rest / unassigned"] == 0
    population_by_country = {}
    allocations_by_country = {}
    population_shares_by_country = {}
    coverage_counts = {
        field: Counter()
        for field in (
            "age",
            "sex",
            "education",
            "occupation",
            "personality",
            "values",
            "finance",
        )
    }
    for profile in prepared.initial_agent_profiles:
        country_code = profile["geography"]["country_id"]
        traits = profile["traits"]
        country_population = int(traits["country_population"])
        allocation = int(traits["country_allocation_agents"])
        assert country_population > 0
        assert allocation > 0
        assert math.isclose(
            float(traits["representative_population_weight"]),
            country_population / allocation,
        )
        population_by_country.setdefault(country_code, country_population)
        allocations_by_country.setdefault(country_code, allocation)
        population_shares_by_country.setdefault(
            country_code,
            float(traits["country_population_share"]),
        )
        assert population_by_country[country_code] == country_population
        assert allocations_by_country[country_code] == allocation
        assert population_shares_by_country[country_code] == float(
            traits["country_population_share"]
        )
        assert traits["state_initialization_status"] == "default_estimated"
        assert traits["state_initialization_uncertainty"] == 1
        assert traits["state_initialization_source"]
        for field, counts in coverage_counts.items():
            scope = traits[f"{field}_evidence_scope"]
            assert scope in {"country_measured", "regional_imputed"}
            counts[scope] += 1
        assert traits["age_source_place"] == country_code
        assert traits["sex_source_place"] == country_code
    target_population = sum(population_by_country.values())
    for country_code, population in population_by_country.items():
        assert allocations_by_country[country_code] == country_counts[country_code]
        quota = 1000 * population / target_population
        assert abs(country_counts[country_code] - quota) < 1
        assert math.isclose(
            population_shares_by_country[country_code],
            population / target_population,
        )
    assert coverage_counts["age"] == {"country_measured": 1000}
    assert coverage_counts["sex"] == {"country_measured": 1000}
    assert all(sum(counts.values()) == 1000 for counts in coverage_counts.values())
    finance_sources = dynamics["finance"]["source"]
    for profile, finance_source, finance_currency, finance_status in zip(
        prepared.initial_agent_profiles,
        finance_sources,
        dynamics["finance"]["currency"],
        dynamics["finance"]["status"],
        strict=True,
    ):
        geography = profile["geography"]
        traits = profile["traits"]
        assert finance_currency == traits["finance_currency"]
        assert finance_status == traits["finance_status"]
        if geography["country_id"] == "CA":
            assert any(
                publisher in finance_source
                for publisher in ("Statistics Canada", "Statistique Canada")
            )
            assert traits["finance_evidence_scope"] == "country_measured"
            assert traits["finance_status"] == "imputed"
            continue
        assert "Statistics Canada" not in finance_source
        assert "Statistique Canada" not in finance_source
        source_place = traits["finance_source_place"]
        assert source_place in {
            geography["country_id"],
            geography["country"],
            geography["region"],
            "unknown",
        }
        if source_place == geography["region"]:
            assert traits["finance_evidence_scope"] == "regional_imputed"
            assert traits["finance_status"] == "imputed"
        elif source_place == "unknown":
            assert traits["finance_evidence_scope"] == "unknown"
            assert traits["finance_status"] == "unknown"
        else:
            assert traits["finance_evidence_scope"] == "country_measured"
            assert traits["finance_status"] == "imputed"
    warned_actions = {warning.action_id for warning in prepared.evidence_warnings}
    assert {
        "bad_work",
        "eat_lunch",
        "skip_lunch",
        "exercise",
        "work_or_study",
    } <= warned_actions


def test_default_routines_do_not_record_eating_and_skipping_lunch_together():
    package = load_shipped_default_dsl()
    actions = {
        action["id"]: action for action in package.content["default_actions"]
    }
    activities = {
        step["activity"]
        for routine in package.content["routines"]["routines"]
        for step in routine["steps"]
    }

    assert "skip_lunch" in actions
    assert "eat_lunch" in actions
    assert actions["eat_lunch"]["exclusive_choice_group"] == "midday_meal"
    assert actions["skip_lunch"]["exclusive_choice_group"] == "midday_meal"
    assert "eat lunch" not in activities


def test_shipped_structural_defaults_report_global_coefficient_provenance(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    prepared = _default_run(store)

    structural_defaults = [
        coefficient
        for group in prepared.coefficient_evidence.by_action_place
        for coefficient in group.coefficients
        if coefficient.action_id
        in {"bad_work", "skip_lunch", "exercise", "work_or_study"}
    ]

    assert structural_defaults
    assert all(item.source_place is not None for item in structural_defaults)
    assert all(item.source_place.level == "global" for item in structural_defaults)
    assert all(item.source_place.place_id == "global" for item in structural_defaults)
    assert all(item.resolution_status == "imputed" for item in structural_defaults)
    assert all("Statistics Canada" not in item.source_label for item in structural_defaults)
    assert all("Statistique Canada" not in item.source_label for item in structural_defaults)
    decision_defaults = [
        coefficient
        for group in prepared.coefficient_evidence.by_action_place
        for coefficient in group.coefficients
        if coefficient.action_id == "daily_activity_module"
    ]
    assert decision_defaults
    assert all(item.source_place is not None for item in decision_defaults)
    assert all(item.source_place.level == "global" for item in decision_defaults)
    assert all(item.source_place.place_id == "global" for item in decision_defaults)
    assert all(item.resolution_status == "imputed" for item in decision_defaults)
    assert all("Canada" not in item.source_label for item in decision_defaults)


def test_default_1000_agent_30_day_run_is_deterministic_and_causal(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    prepared = _default_run(store)
    client = RustCoreClient()

    first = client.run_agents(prepared.rust_request)
    repeated = client.run_agents(prepared.rust_request)

    assert first == repeated
    assert first["ticks"] == 720
    assert len(first["agents"]["state"]) == 1000
    assert len(first["state_ticks"]) == 720

    countries = [
        profile["geography"]["country_id"]
        for profile in prepared.initial_agent_profiles
    ]
    cross_country_interactions = [
        interaction
        for interaction in first["interactions"]
        if countries[interaction["initiator_index"]]
        != countries[interaction["target_index"]]
    ]
    assert cross_country_interactions
    assert all(
        factor["factor"]["provenance"]["status"] == "default_estimated"
        for interaction in cross_country_interactions
        for factor in interaction["factors"]
    )

    work_wages_by_country = defaultdict(set)
    for tick in first["state_ticks"]:
        for change in tick["finance_changes"]:
            wages = change["flows"]["wages"]
            if wages > 0:
                work_wages_by_country[countries[change["agent_index"]]].add(wages)
    assert len(work_wages_by_country) > 1
    assert len({wage for values in work_wages_by_country.values() for wage in values}) > 12

    events = first["events"]
    meal_events = [
        event
        for event in events
        if event["action"] in {"eat_lunch", "skip_lunch"}
    ]
    noon_ticks = {13 + 24 * day for day in range(30)}
    meal_events_by_tick_and_agent = Counter(
        (event["tick"], event["agent_index"]) for event in meal_events
    )
    assert len(meal_events) == 30_000
    assert {event["tick"] for event in meal_events} == noon_ticks
    assert set(meal_events_by_tick_and_agent.values()) == {1}
    assert set(meal_events_by_tick_and_agent) == {
        (tick, agent_index)
        for tick in noon_ticks
        for agent_index in range(1000)
    }
    assert {event["action"] for event in meal_events} == {
        "eat_lunch",
        "skip_lunch",
    }
    state_ticks_by_tick = {tick["tick"]: tick for tick in first["state_ticks"]}
    for event in meal_events:
        if event["action"] != "skip_lunch":
            continue
        skip_finance_changes = [
            change
            for change in state_ticks_by_tick[event["tick"]]["finance_changes"]
            if change["agent_index"] == event["agent_index"]
        ]
        assert all(change["flows"]["food"] == 0 for change in skip_finance_changes)
    initial = prepared.rust_request["agents"]["memory"]
    dynamics = prepared.rust_request["state_dynamics"]
    final = first["agents"]["memory"]
    low_stress = {index for index, value in enumerate(initial["stress"]) if value < 0.5}
    high_stress = set(range(1000)) - low_stress
    low_financial_stress = {
        index
        for index, value in enumerate(initial["financial_stress"])
        if value < 0.5
    }
    high_financial_stress = set(range(1000)) - low_financial_stress
    assert low_stress
    assert high_stress
    assert low_financial_stress
    assert high_financial_stress

    def event_count(action, agents):
        return sum(
            event["agent_index"] in agents
            for event in events
            if event["action"] == action
        )

    assert event_count("skip_lunch", high_stress) / len(high_stress) > (
        event_count("skip_lunch", low_stress) / len(low_stress)
    )
    assert event_count("exercise", high_stress) / len(high_stress) > (
        event_count("exercise", low_stress) / len(low_stress)
    )

    events_by_action = {
        action: [event for event in events if event["action"] == action]
        for action in ("bad_work", "skip_lunch", "exercise", "work_or_study")
    }
    assert {event["probability"] for event in events_by_action["skip_lunch"]} == {
        0.05,
        0.2,
        0.35,
        0.55,
    }
    assert {event["probability"] for event in events_by_action["exercise"]} == {
        0.25,
        0.65,
    }
    bad_work_agents = {event["agent_index"] for event in events_by_action["bad_work"]}
    skip_lunch_agents = {
        event["agent_index"]
        for event in events_by_action["skip_lunch"]
        if event["probability"] in {0.35, 0.55}
    }
    exercise_agents = {
        event["agent_index"]
        for event in events_by_action["exercise"]
        if event["probability"] == 0.65
    }
    employed_agents = {
        index for index, value in enumerate(initial["is_employed"]) if value >= 0.5
    }
    causal_agents = {
        index
        for index in employed_agents & bad_work_agents & skip_lunch_agents & exercise_agents
        if final["stress"][index] > initial["stress"][index]
        and final["health"][index] < initial["health"][index]
        and final["finance.money"][index] != initial["finance.money"][index]
    }
    assert causal_agents

    causal_agent = min(causal_agents)
    bad_work_event = next(
        event
        for event in events_by_action["bad_work"]
        if event["agent_index"] == causal_agent
    )
    skip_lunch_event = next(
        event
        for event in events_by_action["skip_lunch"]
        if event["agent_index"] == causal_agent
        and event["probability"] in {0.35, 0.55}
    )
    exercise_event = next(
        event
        for event in events_by_action["exercise"]
        if event["agent_index"] == causal_agent and event["probability"] == 0.65
    )
    assert bad_work_event["draw"] < bad_work_event["probability"]
    assert bad_work_event["provenance"]["status"] == "default_estimated"
    assert skip_lunch_event["probability"] in {0.35, 0.55}
    assert exercise_event["probability"] == 0.65

    bad_work_tick = next(
        tick
        for tick in first["state_ticks"]
        if any(
            effect["event"] == "bad_work"
            and effect["agent_index"] == causal_agent
            and effect["target_state_id"] == "stress"
            for effect in tick["event_effects"]
        )
        and any(
            change["agent_index"] == causal_agent
            and change["target_state_id"] == "stress"
            and change["after"] > change["before"]
            for change in tick["agent_state_changes"]
        )
    )
    bad_work_effect = next(
        effect
        for effect in bad_work_tick["event_effects"]
        if effect["event"] == "bad_work"
        and effect["agent_index"] == causal_agent
        and effect["target_state_id"] == "stress"
    )
    bad_work_change = next(
        change
        for change in bad_work_tick["agent_state_changes"]
        if change["agent_index"] == causal_agent
        and change["target_state_id"] == "stress"
    )
    assert bad_work_effect["delta"] == 0.08
    assert bad_work_change["after"] > bad_work_change["before"]

    exercise_tick = next(
        tick
        for tick in first["state_ticks"]
        if any(
            effect["event"] == "exercise"
            and effect["agent_index"] == causal_agent
            and effect["target_state_id"] == "stress"
            for effect in tick["event_effects"]
        )
    )
    exercise_change = next(
        change
        for change in exercise_tick["agent_state_changes"]
        if change["agent_index"] == causal_agent
        and change["target_state_id"] == "stress"
    )
    assert exercise_change["event_delta"] == -0.12
    assert exercise_change["after"] < exercise_change["before"]

    health_tick = next(
        tick
        for tick in first["state_ticks"]
        if any(
            change["agent_index"] == causal_agent
            and change["target_state_id"] == "health"
            and change["after"] < change["before"]
            for change in tick["agent_state_changes"]
        )
    )
    health_change = next(
        change
        for change in health_tick["agent_state_changes"]
        if change["agent_index"] == causal_agent
        and change["target_state_id"] == "health"
    )
    health_rule = health_tick["state_rules"][health_change["rule_index"]]
    assert health_change["equation_delta"] < 0
    assert health_rule["target_state_id"] == "health"
    assert "stress" in health_rule["formula"]
    assert health_rule["evidence"]["status"] == "default_estimated"

    finance_tick = next(
        tick
        for tick in first["state_ticks"]
        if any(
            change["agent_index"] == causal_agent
            and change["flows"]["wages"] > 0
            and change["flows"]["transport"] > 0
            and change["flows"]["taxes"] > 0
            for change in tick["finance_changes"]
        )
    )
    finance_change = next(
        change
        for change in finance_tick["finance_changes"]
        if change["agent_index"] == causal_agent
        and change["flows"]["wages"] > 0
    )
    ledgers = {item["ledger"]: item for item in finance_change["ledger_changes"]}
    assert finance_change["provenance"]["status"] == dynamics["finance"]["status"][
        causal_agent
    ]
    assert finance_change["provenance"]["source"] == dynamics["finance"]["source"][
        causal_agent
    ]
    assert ledgers["income"]["flow_delta"] == finance_change["flows"]["wages"]
    assert ledgers["expenses"]["flow_delta"] == (
        finance_change["flows"]["transport"] + finance_change["flows"]["taxes"]
    )
    assert ledgers["money"]["after"] > ledgers["money"]["before"]
    assert finance_tick["finance_formula"] is not None
