import time
from copy import deepcopy
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.aggregate_statistics import (
    ActionAggregateContribution,
    AggregateStatisticsProgram,
    AggregateValueReference,
    EmploymentAggregateDefinition,
    FinanceAggregateDefinition,
    FinanceMetricDefinition,
    HistogramAggregateDefinition,
    HistogramBucket,
    PredicateDefinition,
    TimelineSubject,
    collect_daily_aggregate_statistics,
)
from petraterrium.simulation.locations import LocationPlace
from petraterrium.simulation.run_persistence import SimulationRunRecorder
from petraterrium.simulation.run_routes import create_simulation_run_router
from petraterrium.simulation.run_service import (
    PreparedRustRun,
    SimulationPlaceScope,
    SimulationRunConfig,
    SimulationRunService,
)

COUNTRIES = (
    ("IN", "India", "India", 307),
    ("CN", "China", "China", 304),
    ("US", "United States", "Northern America", 73),
    ("ID", "Indonesia", "Asia excluding China and India", 60),
    ("PK", "Pakistan", "Asia excluding China and India", 53),
    ("NG", "Nigeria", "Africa", 49),
    ("BR", "Brazil", "Latin America and the Caribbean", 45),
    ("BD", "Bangladesh", "Asia excluding China and India", 36),
    ("RU", "Russia", "Europe", 31),
    ("MX", "Mexico", "Latin America and the Caribbean", 28),
    ("CA", "Canada", "Northern America", 8),
    ("AU", "Australia", "Oceania", 6),
)


class DailyAggregateRustClient:
    def run_agents(self, request: dict) -> dict:
        start_tick = int(request.get("continuation", {}).get("completed_tick", 0))
        completed_tick = start_tick + int(request["ticks"])
        agents = deepcopy(request["agents"])
        population = len(agents["state"])
        return {
            "protocol_version": "1",
            "engine_version": "aggregate-test-rust",
            "seed": request["seed"],
            "ticks": completed_tick,
            "agents": agents,
            "transition_counts": [],
            "transition_evidence": [],
            "transition_outcomes": [],
            "events": [
                {
                    "tick": completed_tick,
                    "agent_index": index,
                    "place_index": agents["place"][index],
                    "action": "work",
                }
                for index in range(0, population, 10)
            ],
            "routine_actions": [
                {
                    "tick": completed_tick,
                    "action": "commute",
                    "agent_indices": list(range(population)),
                }
            ],
            "routine_unavailable": [],
            "location_transitions": [],
            "interactions": [],
            "blocked_interactions": [],
            "relationships": [],
            "state_ticks": [],
            "synchronization": [],
            "shard_populations": [],
            "continuation": {
                "completed_tick": completed_tick,
                "rng_word_position": str(completed_tick),
                "active_travel": [None] * population,
                "relationships": [],
            },
        }


def value(source: str, field: str) -> AggregateValueReference:
    return AggregateValueReference(source=source, field=field)


def aggregate_program() -> AggregateStatisticsProgram:
    finance_status = (value("trait", "finance_source_status"),)
    finance_source = (value("trait", "finance_source_id"),)
    finance_unit = (value("trait", "finance_currency"),)
    return AggregateStatisticsProgram(
        version="global-demo-aggregates-v1",
        action_contributions=(
            ActionAggregateContribution(
                action_id="work",
                statistic_id="work",
                event_source="events",
                label_field="action",
                agent_index_field="agent_index",
            ),
            ActionAggregateContribution(
                action_id="commute",
                statistic_id="commute",
                event_source="routine_actions",
                label_field="action",
                agent_indices_field="agent_indices",
            ),
        ),
        finance=FinanceAggregateDefinition(
            metrics=(
                FinanceMetricDefinition(
                    id="income",
                    values=(value("trait", "finance_annual_income"),),
                    units=finance_unit,
                    evidence_statuses=finance_status,
                    source_ids=finance_source,
                    basis="annual_person_income",
                ),
                FinanceMetricDefinition(
                    id="expenses",
                    values=(value("trait", "finance_annual_expenses"),),
                    units=finance_unit,
                    evidence_statuses=finance_status,
                    source_ids=finance_source,
                    basis="annual_person_expenses",
                ),
                FinanceMetricDefinition(
                    id="savings",
                    values=(value("memory", "finance.savings"),),
                    units=finance_unit,
                    evidence_statuses=finance_status,
                    source_ids=finance_source,
                    basis="current_balance",
                ),
                FinanceMetricDefinition(
                    id="debt",
                    values=(value("memory", "finance.debt"),),
                    units=finance_unit,
                    evidence_statuses=finance_status,
                    source_ids=finance_source,
                    basis="current_balance",
                ),
            )
        ),
        employment=EmploymentAggregateDefinition(
            employed=PredicateDefinition(
                values=(value("memory", "is_employed"),),
                operator="greater_than_or_equal",
                expected=0.5,
            ),
            labour_force=PredicateDefinition(
                operator="all",
                operands=(
                    PredicateDefinition(
                        values=(value("trait", "age"),),
                        operator="greater_than_or_equal",
                        expected=15,
                    ),
                    PredicateDefinition(
                        operator="not",
                        operands=(
                            PredicateDefinition(
                                values=(value("memory", "is_retired"),),
                                operator="greater_than_or_equal",
                                expected=0.5,
                            ),
                        ),
                    ),
                ),
            ),
            student=PredicateDefinition(
                values=(value("memory", "is_student"),),
                operator="greater_than_or_equal",
                expected=0.5,
            ),
            caregiver=PredicateDefinition(
                values=(value("trait", "is_caregiver"),),
                operator="truthy",
            ),
            retired=PredicateDefinition(
                values=(value("memory", "is_retired"),),
                operator="greater_than_or_equal",
                expected=0.5,
            ),
            worker=PredicateDefinition(
                values=(value("trait", "is_worker"),),
                operator="truthy",
            ),
            age=(value("trait", "age"),),
            sex=(value("trait", "sex"),),
            age_groups=(
                HistogramBucket(label="15-24", minimum=15, maximum_exclusive=25),
                HistogramBucket(label="25-54", minimum=25, maximum_exclusive=55),
                HistogramBucket(label="55+", minimum=55),
            ),
        ),
        histograms=(
            HistogramAggregateDefinition(
                id="age",
                values=(value("trait", "age"),),
                buckets=(
                    HistogramBucket(label="0-14", minimum=0, maximum_exclusive=15),
                    HistogramBucket(label="15-64", minimum=15, maximum_exclusive=65),
                    HistogramBucket(label="65+", minimum=65),
                ),
            ),
            HistogramAggregateDefinition(
                id="education",
                values=(value("trait", "education_isced"),),
            ),
            HistogramAggregateDefinition(
                id="income",
                values=(value("trait", "finance_annual_income"),),
                buckets=(
                    HistogramBucket(label="under 20k", maximum_exclusive=20_000),
                    HistogramBucket(
                        label="20k-50k", minimum=20_000, maximum_exclusive=50_000
                    ),
                    HistogramBucket(label="50k+", minimum=50_000),
                ),
            ),
            HistogramAggregateDefinition(
                id="ideology_economic",
                values=(value("trait", "ideology_economic"),),
                buckets=(
                    HistogramBucket(label="planned", maximum_exclusive=-0.25),
                    HistogramBucket(
                        label="mixed", minimum=-0.25, maximum_exclusive=0.25
                    ),
                    HistogramBucket(label="market", minimum=0.25),
                ),
            ),
            HistogramAggregateDefinition(
                id="ideology_state",
                values=(value("trait", "ideology_state"),),
                buckets=(
                    HistogramBucket(label="authoritarian", maximum_exclusive=-0.25),
                    HistogramBucket(
                        label="mixed", minimum=-0.25, maximum_exclusive=0.25
                    ),
                    HistogramBucket(label="anti-authoritarian", minimum=0.25),
                ),
            ),
            HistogramAggregateDefinition(
                id="ideology_cultural",
                values=(value("trait", "ideology_cultural"),),
                buckets=(
                    HistogramBucket(label="traditional", maximum_exclusive=-0.25),
                    HistogramBucket(
                        label="mixed", minimum=-0.25, maximum_exclusive=0.25
                    ),
                    HistogramBucket(label="progressive", minimum=0.25),
                ),
            ),
            HistogramAggregateDefinition(
                id="household_size",
                values=(value("trait", "household_size"),),
                buckets=(
                    HistogramBucket(label="1", minimum=1, maximum_exclusive=2),
                    HistogramBucket(label="2-4", minimum=2, maximum_exclusive=5),
                    HistogramBucket(label="5+", minimum=5),
                ),
            ),
        ),
    )


def prepared_run(config: SimulationRunConfig) -> PreparedRustRun:
    profiles = []
    places = []
    place_index_by_country = {}
    for country_index, (country_code, country, region, count) in enumerate(COUNTRIES):
        place_index_by_country[country_code] = len(places)
        places.append({"id": country_code, "state": {}})
        for local_index in range(count):
            employed = local_index % 4 != 0
            profiles.append(
                {
                    "agent_id": f"agent-{len(profiles) + 1}",
                    "agent_types": ["person", "worker"],
                    "role": "worker",
                    "geography": {
                        "country_id": country_code,
                        "country": country,
                        "region": region,
                        "city_id": f"city-{country_code}",
                        "city": f"{country} demo city",
                        "latitude": -45 + country_index * 7,
                        "longitude": -150 + country_index * 20,
                    },
                    "traits": {
                        "agent_type": "worker",
                        "age": 20 + local_index % 60,
                        "sex": "female" if local_index % 2 else "male",
                        "education_isced": str(local_index % 9),
                        "ideology_economic": (local_index % 21 - 10) / 10,
                        "ideology_state": (local_index % 17 - 8) / 8,
                        "ideology_cultural": (local_index % 19 - 9) / 9,
                        "household_size": 1 + local_index % 6,
                        "finance_annual_income": 20_000 + local_index,
                        "finance_annual_expenses": 15_000 + local_index,
                        "finance_currency": "PPP",
                        "finance_source_status": "imputed",
                        "finance_source_id": f"wdi:{country_code}",
                        "is_caregiver": local_index % 9 == 0,
                        "is_worker": True,
                        "representative_population_weight": 1,
                    },
                    "states": {
                        "finance.savings": str(5_000 + local_index),
                        "finance.debt": str(2_000 + local_index),
                        "is_employed": "1" if employed else "0",
                        "is_student": "1" if local_index % 7 == 0 else "0",
                        "is_retired": "0",
                    },
                }
            )
    assert len(profiles) == config.population_size == 1_000
    memory_keys = (
        "finance.savings",
        "finance.debt",
        "is_employed",
        "is_student",
        "is_retired",
    )
    return PreparedRustRun(
        rust_request={
            "seed": config.seed,
            "ticks": 1,
            "tick_hours": config.tick_interval_hours,
            "start_hour": 0,
            "start_weekday": config.start_date.weekday(),
            "places": places,
            "agents": {
                "agent_ids": [profile["agent_id"] for profile in profiles],
                "module": ["day"] * len(profiles),
                "state": ["active"] * len(profiles),
                "place": [
                    place_index_by_country[profile["geography"]["country_id"]]
                    for profile in profiles
                ],
                "traits": {},
                "trait_dictionaries": {},
                "memory": {
                    key: [float(profile["states"][key]) for profile in profiles]
                    for key in memory_keys
                },
            },
            "modules": [],
            "routes": [],
            "network": None,
            "schedules": [],
            "meaningful_actions": [],
            "synchronization": {},
        },
        agent_ids=[profile["agent_id"] for profile in profiles],
        data_version="global-fixture-v1",
        program_version="global-program-v1",
        initial_agent_profiles=profiles,
        aggregate_statistics=aggregate_program(),
    )


def wait_for_completion(service: SimulationRunService, run_id: str):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        run = service.get(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Global aggregate run did not finish")


def test_place_aggregates_follow_recorded_runtime_location():
    profiles = [
        {
            "agent_id": "traveller",
            "geography": {
                "country_id": "AA",
                "country": "Alpha",
                "region": "Alpha region",
                "city_id": "alpha-city",
                "city": "Alpha City",
                "latitude": 10.0,
                "longitude": 20.0,
            },
        },
        {
            "agent_id": "resident",
            "geography": {
                "country_id": "BB",
                "country": "Beta",
                "region": "Beta region",
                "city_id": "beta-city",
                "city": "Beta City",
                "latitude": 40.0,
                "longitude": 50.0,
            },
        },
    ]
    places = [
        LocationPlace(id="country-a", name="Alpha", level="country"),
        LocationPlace(
            id="region-a", name="Alpha region", level="region", parent_id="country-a"
        ),
        LocationPlace(id="city-a", name="Alpha City", level="city", parent_id="region-a"),
        LocationPlace(id="country-b", name="Beta", level="country"),
        LocationPlace(
            id="region-b", name="Beta region", level="region", parent_id="country-b"
        ),
        LocationPlace(id="city-b", name="Beta City", level="city", parent_id="region-b"),
    ]
    records = collect_daily_aggregate_statistics(
        run_id="runtime-place-run",
        program=AggregateStatisticsProgram(version="runtime-place-v1"),
        agent_ids=("traveller", "resident"),
        profiles=profiles,
        output={"agents": {"place": [1, 1]}},
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        location_places=places,
        initial_location_ids=("city-a", "city-b"),
        runtime_place_location_ids=("city-a", "city-b"),
    )

    by_level = {
        level: [record for record in records if record.place_level == level]
        for level in ("country", "region", "city", "global")
    }
    assert [(record.place_id, record.agent_count) for record in by_level["country"]] == [
        ("BB", 2)
    ]
    assert [(record.place_id, record.agent_count) for record in by_level["region"]] == [
        ("Beta region", 2)
    ]
    assert [(record.place_id, record.agent_count) for record in by_level["city"]] == [
        ("beta-city", 2)
    ]
    assert by_level["global"][0].agent_count == 2


def test_global_demo_persists_daily_place_aggregates_without_routine_agent_logs(
    tmp_path: Path,
):
    recorder = SimulationRunRecorder(tmp_path / "runs.sqlite3")
    service = SimulationRunService(
        prepared_run,
        DailyAggregateRustClient(),
        persistence=recorder,
    )
    config = SimulationRunConfig(
        population_size=1_000,
        seed=1,
        days=30,
        tick_interval_hours=24,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="global"),
        agent_type_mix={"worker": 1.0},
    )

    launched = service.launch(config)
    completed = wait_for_completion(service, launched.run_id)

    assert completed.status == "completed", completed.error
    statistics = service.statistics(launched.run_id, page_size=1_000)
    assert statistics.total == 30 * (12 + 8 + 12 + 1)
    assert {item.place_id for item in statistics.items if item.place_level == "country"} == {
        country_code for country_code, _, _, _ in COUNTRIES
    }
    assert len(
        {item.place_id for item in statistics.items if item.place_level == "region"}
    ) == 8
    assert {
        item.place_id for item in statistics.items if item.place_level == "city"
    } == {f"city-{country_code}" for country_code, _, _, _ in COUNTRIES}
    global_days = [item for item in statistics.items if item.place_level == "global"]
    assert len(global_days) == 30
    assert all(item.agent_count == 1_000 for item in global_days)
    assert all(item.action_counts == {"commute": 1_000, "work": 100} for item in global_days)
    assert all(
        item.action_rates_per_1000 == {"commute": 1_000.0, "work": 100.0}
        for item in global_days
    )
    assert all(
        set(item.histograms)
        == {
            "age",
            "education",
            "income",
            "ideology_economic",
            "ideology_state",
            "ideology_cultural",
            "household_size",
        }
        for item in global_days
    )
    for country_code, _, _, _ in COUNTRIES:
        country_rows = [
            item
            for item in statistics.items
            if item.place_level == "country" and item.place_id == country_code
        ]
        assert len(country_rows) == 30
        assert all(set(item.finances) == {"income", "expenses", "savings", "debt"}
                   for item in country_rows)
        assert all(
            statistic.unit == "PPP"
            and statistic.evidence_status == "estimated"
            and statistic.comparable
            and statistic.total is not None
            and statistic.mean is not None
            and statistic.median is not None
            for item in country_rows
            for statistic in item.finances.values()
        )
        assert all(item.employment is not None for item in country_rows)
        assert all(item.employment.unemployment_rate > 0 for item in country_rows)
    assert service.events(launched.run_id).total == 0
    assert recorder.load_events(launched.run_id) == []
    assert all(
        frame["agent_ids"] == [] and frame["actions"] == []
        for frame in recorder.load_frames(launched.run_id)
    )
    assert service.agent(launched.run_id, "agent-1").timeline == []
    assert completed.aggregate_record_count == 30 * (12 + 8 + 12 + 1)
    service.shutdown()

    restored = SimulationRunService(
        prepared_run,
        DailyAggregateRustClient(),
        persistence=recorder,
    )
    persisted = restored.statistics(
        launched.run_id,
        place_level="country",
        place_id="CN",
        page_size=100,
    )
    assert persisted.total == 30
    assert [item.day for item in persisted.items] == list(range(1, 31))
    assert all(item.place_label == "China" for item in persisted.items)
    assert restored.get(launched.run_id).aggregate_record_count == 30 * (12 + 8 + 12 + 1)
    application = FastAPI()
    application.include_router(create_simulation_run_router(restored), prefix="/api")
    response = TestClient(application).get(
        f"/api/simulation/runs/{launched.run_id}/statistics",
        params={"place_level": "global", "day": 30},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["agent_count"] == 1_000
    restored.shutdown()


def test_only_promoted_timeline_subjects_persist_from_their_promotion_tick(
    tmp_path: Path,
):
    def spotlight_prepared(config: SimulationRunConfig) -> PreparedRustRun:
        prepared = prepared_run(config)
        program = prepared.aggregate_statistics
        assert program is not None
        return prepared.model_copy(
            update={
                "aggregate_statistics": program.model_copy(
                    update={
                        "timeline_subjects": (
                            TimelineSubject(
                                agent_id="agent-1",
                                role="spotlight",
                                start_tick=48,
                            ),
                        )
                    }
                )
            }
        )

    service = SimulationRunService(
        spotlight_prepared,
        DailyAggregateRustClient(),
        persistence=SimulationRunRecorder(tmp_path / "spotlight.sqlite3"),
    )
    config = SimulationRunConfig(
        population_size=1_000,
        seed=1,
        days=2,
        tick_interval_hours=1,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="global"),
        agent_type_mix={"worker": 1.0},
    )

    launched = service.launch(config)
    completed = wait_for_completion(service, launched.run_id)

    assert completed.status == "completed", completed.error
    spotlight = service.agent(launched.run_id, "agent-1")
    routine = service.agent(launched.run_id, "agent-2")
    assert [point.tick for point in spotlight.timeline] == [48]
    assert spotlight.timeline[0].actions == ["work"]
    assert spotlight.timeline[0].routine_actions == ["commute"]
    assert routine.timeline == []
    events = service.events(launched.run_id)
    assert [(item.kind, item.tick, item.agent_ids) for item in events.items] == [
        ("action", 48, ["agent-1"]),
        ("routine", 48, ["agent-1"]),
    ]
    assert all("agent_indices" not in item.details for item in events.items)
    service.shutdown()
