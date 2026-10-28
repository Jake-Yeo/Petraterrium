import gzip
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.text_dsl import TextDslService, create_text_dsl_router

SOURCE = '''program Tiny version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
'''


class FakeRustDsl:
    def validate_text_dsl(self, source: str):
        return {
            "valid": "invalid" not in source,
            "program_id": "Tiny",
            "version": "1.0",
            "tick_hours": 1,
            "adult_population": 2,
            "diagnostics": [],
        }

    def run_text_dsl(self, source: str, *, seed: int, ticks: int, continuation=None):
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
