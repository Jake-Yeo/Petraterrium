from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.text_dsl import TextDslService, create_text_dsl_router
from petraterrium.text_dsl.models import AggregateEvaluationRequest

SOURCE = '''program Tiny version "1.0":
  tick_hours = 1 placeholder
  placeholder = "estimated pending the research pipeline"
  uncertainty = wide
'''


class FakeRustDsl:
    def __init__(self):
        self.validation_calls = 0
        self.last_composition_id = None
        self.last_total_represented_pool = None

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
        composition_id=None,
        total_represented_pool=6_999_999_999,
        dsl_source_hash=None,
        exemplar_cache=None,
        exemplar_inputs=None,
        events=None,
        role_parameters=None,
    ):
        self.last_composition_id = composition_id
        self.last_total_represented_pool = total_represented_pool
        exemplar_cache = dict(exemplar_cache or {})
        exemplar_cache.setdefault("Metro__urban__01", {"version": 1})
        rate = 200 if "edited" in source else 100
        return {
            "engine_version": "test-rust",
            "completed_ticks": ticks,
            "state": {"agents": []},
            "exemplar_plan": {
                "total_represented_pool": total_represented_pool,
                "total_represented_households": 10,
                "total_real_neighbourhood_instances": 1,
                "total_exemplars": 1,
                "cities": [],
            },
            "cache_stats": {
                "cache_hit": bool(exemplar_cache),
                "mass_agent_ticks": 0,
                "relearned_exemplars": [],
                "reused_exemplars": ["Metro__urban__01"],
                "invalidations": {},
            },
            "leader_assignments": {},
            "unassigned_required_roles": 0,
            "exemplar_cache": exemplar_cache,
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
    baseline = dsl.run(
        type(
            "Request",
            (),
            {
                "seed": 1,
                "days": 1,
                "baseline_run_id": None,
                "total_represented_pool": 6_999_999_999,
                "exemplar_inputs": {},
                "events": (),
            },
        )()
    )
    edited = current.code + "\n# edited"
    saved = dsl.save(edited, current.source_hash)
    compared = dsl.run(
        type(
            "Request",
            (),
            {
                "seed": 1,
                "days": 1,
                "baseline_run_id": baseline.run_id,
                "total_represented_pool": 6_999_999_999,
                "exemplar_inputs": {},
                "events": (),
            },
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
    assert run.json()["exemplar_plan"]["total_exemplars"] == 1
    assert run.json()["total_represented_pool"] == 6_999_999_999
    assert dsl.rust.last_total_represented_pool == 6_999_999_999
    invalid_total = client.post(
        "/simulation/text-dsl/runs",
        json={"seed": 1, "days": 1, "total_represented_pool": 0},
    )
    assert invalid_total.status_code == 422
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
