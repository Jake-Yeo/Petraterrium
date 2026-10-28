import gzip
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.text_dsl import TextDslService, create_text_dsl_router
from petraterrium.text_dsl.models import AggregateEvaluationRequest

SOURCE = '''program Tiny version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
'''


class FakeRustDsl:
    def __init__(self):
        self.validation_calls = 0
        self.last_population_id = None
        self.last_composition_id = None
        self.last_composition_population_id = None
        self.last_neighbourhood_id = None
        self.last_neighbourhood_population_id = None

    def validate_text_dsl(self, source: str):
        self.validation_calls += 1
        return {
            "valid": "invalid" not in source,
            "program_id": "Tiny",
            "version": "1.0",
            "tick_hours": 1,
            "adult_population": 2,
            "archetypes": ["Alpha"],
            "weighted_populations": ["Weighted"],
            "compositions": [{"id": "Metro", "level": "synthetic", "cached": True}],
            "diagnostics": [],
        }

    def run_text_dsl(
        self,
        source: str,
        *,
        seed: int,
        ticks: int,
        continuation=None,
        population_id=None,
        composition_id=None,
        composition_population_id=None,
        neighbourhood_id=None,
        neighbourhood_population_id=None,
    ):
        self.last_population_id = population_id
        self.last_composition_id = composition_id
        self.last_composition_population_id = composition_population_id
        self.last_neighbourhood_id = neighbourhood_id
        self.last_neighbourhood_population_id = neighbourhood_population_id
        rate = 200 if "edited" in source else 100
        return {
            "engine_version": "test-rust",
            "completed_ticks": ticks,
            "state": {"agents": [{"id": "a"}, {"id": "b"}, {"id": "child"}]},
            "results_title": "Rust results",
            "results_subtitle": "DSL-defined statistics",
            "reports": [
                {
                    "id": "places",
                    "title": "Places",
                    "group_by": "place",
                    "display": "table",
                    "record": "final",
                    "columns": [
                        {
                            "id": "population",
                            "label": "Population",
                            "format": "integer",
                            "metric": "Count",
                            "line": 1,
                        },
                        {
                            "id": "actions",
                            "label": "Actions",
                            "format": "action_rates",
                            "metric": {"ActionRates": {"per": 1000, "window": "day"}},
                            "line": 2,
                        },
                    ],
                    "snapshots": [
                        {
                            "tick": ticks,
                            "rows": [
                                {
                                    "group_id": "Home",
                                    "values": {
                                        "population": 3,
                                        "actions": {"home": rate},
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    def evaluate_text_dsl_aggregate(
        self,
        source: str,
        *,
        dsl_source_hash: str,
        function_id: str,
        seed: int,
        days: int,
        evaluated_at_day: int,
        inputs,
        events,
        artifact=None,
        force_relearn=False,
    ):
        version = 1 if artifact is None else int(artifact["version"]) + int(force_relearn)
        learned = artifact or {
            "function_id": function_id,
            "version": version,
            "dsl_source_hash": dsl_source_hash,
            "seed": seed,
            "anchor_inputs": dict(inputs),
            "valid_from": evaluated_at_day,
            "valid_until": evaluated_at_day + 30,
            "inputs_hash": "fnv1a64:test",
            "learning_agent_ticks": 100,
            "points": [],
        }
        if force_relearn:
            learned = {**learned, "version": version}
        return {
            "function_id": function_id,
            "cache_hit": artifact is not None and not force_relearn,
            "invalidation_reason": None if artifact is not None else "cache_miss",
            "agent_ticks": 0 if artifact is not None and not force_relearn else 100,
            "inputs_hash": "fnv1a64:test",
            "valid_from": learned["valid_from"],
            "valid_until": learned["valid_until"],
            "dsl_source_hash": dsl_source_hash,
            "artifact": learned,
            "time_series": [],
            "reports": [],
        }

    def evaluate_cached_composition(
        self,
        source: str,
        *,
        dsl_source_hash: str,
        function_id: str,
        seed: int,
        days: int,
        evaluated_at_day: int,
        inputs,
        branch_inputs,
        input_schedule,
        events,
        artifacts,
        force_relearn=False,
    ):
        cache_hit = function_id in artifacts and not force_relearn
        version = int(artifacts.get(function_id, {}).get("version", 0)) + int(not cache_hit)
        artifact = {
            "function_id": function_id,
            "version": version,
            "dsl_source_hash": dsl_source_hash,
            "seed": seed,
            "anchor_inputs": dict(inputs),
            "valid_from": evaluated_at_day,
            "valid_until": evaluated_at_day + 30,
            "inputs_hash": "fnv1a64:metro",
            "learning_agent_ticks": 50,
            "dependencies": {"Leaf": 1},
            "points": [],
        }
        leaf = artifacts.get("Leaf") or {
            **artifact,
            "function_id": "Leaf",
            "inputs_hash": "fnv1a64:leaf",
            "dependencies": {},
        }
        return {
            "function_id": function_id,
            "cache_hit": cache_hit,
            "invalidation_reason": None if cache_hit else "cache_miss",
            "agent_ticks": 0 if cache_hit else 50,
            "inputs_hash": artifact["inputs_hash"],
            "valid_from": artifact["valid_from"],
            "valid_until": artifact["valid_until"],
            "dsl_source_hash": dsl_source_hash,
            "artifact": artifact,
            "artifacts": {"Leaf": leaf, function_id: artifact},
            "time_series": [],
            "reports": [],
            "cache_tree": {
                "function_id": function_id,
                "version": version,
                "dsl_source_hash": dsl_source_hash,
                "inputs_hash": artifact["inputs_hash"],
                "valid_from": evaluated_at_day,
                "valid_until": evaluated_at_day + 30,
                "seed": seed,
                "original_learning_ticks": 50,
                "evaluation_agent_ticks": 0 if cache_hit else 50,
                "cached": cache_hit,
                "detailed": False,
                "invalidation_reason": None if cache_hit else "cache_miss",
                "children": [],
            },
            "feedback_iterations": 2,
            "feedback_change_percent": 0.5,
        }


def service(tmp_path: Path) -> TextDslService:
    default = tmp_path / "default.dsl"
    default.write_text(SOURCE, encoding="utf-8")
    return TextDslService(
        rust=FakeRustDsl(),
        root=tmp_path / "runtime",
        default_path=default,
    )


def test_text_source_is_saved_and_run_without_python_parsing(tmp_path):
    dsl = service(tmp_path)
    current = dsl.current()
    baseline = dsl.run(type("Request", (), {"seed": 1, "days": 1, "baseline_run_id": None})())
    edited = current.code + "\n# edited"
    saved = dsl.save(edited, current.source_hash)
    compared = dsl.run(
        type(
            "Request",
            (),
            {"seed": 1, "days": 1, "baseline_run_id": baseline.run_id},
        )()
    )

    assert saved.code == edited
    assert compared.comparison[0].values["actions"]["home"] == 100
    assert dsl.get_run(compared.run_id).model_dump() == compared.model_dump()


def test_validation_is_cached_by_dsl_source_hash(tmp_path):
    dsl = service(tmp_path)

    first = dsl.current()
    second = dsl.current()

    assert first.validation == second.validation
    assert dsl.rust.validation_calls == 1


def test_text_dsl_routes_return_code_validation_and_small_run(tmp_path):
    dsl = service(tmp_path)
    app = FastAPI()
    app.include_router(create_text_dsl_router(dsl))
    client = TestClient(app)

    current = client.get("/simulation/text-dsl")
    run = client.post(
        "/simulation/text-dsl/runs",
        json={"seed": 1, "days": 1, "baseline_run_id": None},
    )

    assert current.status_code == 200
    assert current.json()["code"] == SOURCE
    assert current.json()["validation"]["valid"]
    assert run.status_code == 200
    assert run.json()["total_agents"] == 3
    weighted = client.post(
        "/simulation/text-dsl/runs",
        json={
            "seed": 1,
            "days": 1,
            "baseline_run_id": None,
            "population_id": "Weighted",
        },
    )
    assert weighted.status_code == 200
    assert dsl.rust.last_population_id == "Weighted"
    composition = client.post(
        "/simulation/text-dsl/runs",
        json={
            "seed": 1,
            "days": 1,
            "baseline_run_id": None,
            "composition_id": "Metro",
        },
    )
    assert composition.status_code == 200
    assert dsl.rust.last_composition_id == "Metro"
    composition_population = client.post(
        "/simulation/text-dsl/runs",
        json={
            "seed": 1,
            "days": 1,
            "baseline_run_id": None,
            "composition_population_id": "Regions",
        },
    )
    assert composition_population.status_code == 200
    assert dsl.rust.last_composition_population_id == "Regions"
    neighbourhood = client.post(
        "/simulation/text-dsl/runs",
        json={
            "seed": 1,
            "days": 1,
            "baseline_run_id": None,
            "neighbourhood_id": "Shared",
        },
    )
    assert neighbourhood.status_code == 200
    assert dsl.rust.last_neighbourhood_id == "Shared"
    neighbourhood_population = client.post(
        "/simulation/text-dsl/runs",
        json={
            "seed": 1,
            "days": 1,
            "baseline_run_id": None,
            "neighbourhood_population_id": "Districts",
        },
    )
    assert neighbourhood_population.status_code == 200
    assert dsl.rust.last_neighbourhood_population_id == "Districts"


def test_legacy_fixed_aggregate_run_reopens_as_generic_reports(tmp_path):
    dsl = service(tmp_path)
    legacy = {
        "run_id": "legacy",
        "source_hash": "sha256:" + "0" * 64,
        "seed": 1,
        "days": 1,
        "ticks": 24,
        "adult_population": 2,
        "total_agents": 3,
        "generated_children": 1,
        "action_counts": {"home": 4},
        "outcome_counts": {"stay.rest": 4},
        "final_aggregates": [
            {
                "tick": 24,
                "group_kind": "place",
                "group_id": "Home",
                "population": 3,
                "action_rates_per_1000": {"home": 100},
                "mean_money": 10,
                "mean_health": 0.8,
                "mean_stress": 0.4,
                "fights_per_day": 0,
                "average_family_size": 3,
                "average_kids_per_family": 1,
            }
        ],
        "comparison": [],
        "engine_version": "legacy-rust",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    path = dsl.runs_path / "legacy.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"view": legacy}, handle)

    reopened = dsl.get_run("legacy")

    assert reopened.results_subtitle == "Legacy recorded statistics"
    assert [report.id for report in reopened.reports] == ["places", "event_totals"]
    assert reopened.reports[0].snapshots[0].rows[0].values["population"] == 3


def test_aggregate_artifacts_persist_and_are_reused(tmp_path):
    dsl = service(tmp_path)
    request = AggregateEvaluationRequest(
        function_id="Alpha",
        inputs={"shock": 0.1},
    )

    learned = dsl.evaluate_aggregate(request)
    cached = dsl.evaluate_aggregate(request)
    relearned = dsl.evaluate_aggregate(request.model_copy(update={"force_relearn": True}))

    assert not learned.cache_hit
    assert learned.agent_ticks == 100
    assert cached.cache_hit
    assert cached.agent_ticks == 0
    assert not relearned.cache_hit
    assert [version.version for version in dsl.aggregate_versions("Alpha")] == [1, 2]


def test_cached_composition_artifact_catalog_and_metadata_are_persisted(tmp_path):
    dsl = service(tmp_path)
    request = AggregateEvaluationRequest(function_id="Metro", inputs={"shock": 0.1})

    learned = dsl.evaluate_aggregate(request)
    cached = dsl.evaluate_aggregate(request)

    assert learned.agent_ticks == 50
    assert learned.cache_tree is not None
    assert learned.feedback_iterations == 2
    assert cached.cache_hit
    assert cached.agent_ticks == 0
    assert [version.version for version in dsl.aggregate_versions("Metro")] == [1]
    assert [version.version for version in dsl.aggregate_versions("Leaf")] == [1]
