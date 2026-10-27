import json
from pathlib import Path

SMOKE_PATH = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"


def smoke_payload(seed=17):
    dsl = json.loads(SMOKE_PATH.read_text())
    return {"scenario": dsl["id"], "seed": seed, "dsl": dsl}


def stream_kinds(body):
    return [
        line.removeprefix("event: ") for line in body.splitlines() if line.startswith("event: ")
    ]


def test_dsl_schema_validation_and_plain_language_routes(client):
    dsl = smoke_payload()["dsl"]
    schema = client.get("/dsl/schema")
    assert schema.status_code == 200
    assert schema.json()["title"] == "DSLConfig"
    validation = client.post("/dsl/validate", json=dsl).json()
    assert validation["valid"] is True
    rendered = client.post("/dsl/render", json=dsl).json()
    assert "signal-system" in rendered["plain_language"]
    assert {slider["parameter"] for slider in rendered["sliders"]} == {
        "spread_rate",
        "resolution_rate",
        "place_mixing",
    }
    invalid = json.loads(json.dumps(dsl))
    invalid["systems"][0]["state"] = "absent"
    report = client.post("/dsl/validate", json=invalid).json()
    assert report["valid"] is False
    assert "missing state" in " ".join(item["message"] for item in report["errors"]).lower()


def test_custom_dsl_run_records_generic_states_stories_agents_and_ensemble(client):
    response = client.post("/runs", json=smoke_payload())
    assert response.status_code == 202
    created = response.json()
    run_id = created["run_id"]
    run = client.get(f"/runs/{run_id}").json()
    assert run["status"] == "done"
    assert len(run["snapshots"]) == 8
    assert [snapshot["day"] for snapshot in run["snapshots"]] == list(range(8))
    for snapshot in run["snapshots"]:
        assert sum(sum(place["states"]["signal"].values()) for place in snapshot["places"]) == 1200
    assert run["ensemble_updates"][0]["seeds"] == [17]
    kinds = stream_kinds(client.get(f"/runs/{run_id}/stream").text)
    assert kinds == ["snapshot"] * 8 + ["ensemble_update", "run-complete"]
    assert run["stories"]
    story = run["stories"][0]
    story_detail = client.get(f"/stories/{story['story_id']}", params={"run_id": run_id}).json()
    assert story_detail["place_metrics"][next(iter(story["metrics"]))] == next(
        iter(story["metrics"].values())
    )
    agents = client.get(
        f"/runs/{run_id}/agents", params={"place": "Northport", "limit": 1000}
    ).json()
    assert agents["total"] == 600
    assert agents["returned"] == 600
    assert all(agent["place"] == "Northport" for agent in agents["agents"])
    agent = client.get(
        f"/agents/{agents['agents'][0]['agent_id']}", params={"run_id": run_id}
    ).json()
    assert agent["synthetic"] is True
    assert agent["timeline"]
    place = client.get("/places/Northport", params={"run_id": run_id}).json()
    assert place["run_id"] == run_id
    assert place["metrics"] == run["snapshots"][-1]["places"][0]["metrics"]


def test_custom_dsl_cache_and_version_invalidation(client):
    payload = smoke_payload(9)
    created = client.post("/runs", json=payload).json()
    first = client.get(f"/runs/{created['run_id']}").json()
    second = client.post("/runs", json=payload).json()
    assert second["cached"] is True
    assert second["run_id"] == first["run_id"]
    assert second["snapshots"] == first["snapshots"]
    evidence_changed = client.post(
        "/runs", json={**payload, "evidence_table_version": "FAKE-evidence-v2"}
    ).json()
    assert evidence_changed["run_id"] != first["run_id"]
    changed = json.loads(json.dumps(payload))
    changed["dsl"]["population"]["version"] = "FAKE-population-v2"
    population_changed = client.post("/runs", json=changed).json()
    assert population_changed["run_id"] != first["run_id"]


def test_engine_core_contains_no_scenario_names():
    root = Path(__file__).resolve().parents[1] / "petraterrium"
    source = "\n".join((root / name).read_text().lower() for name in ("engine.py", "runtime.py"))
    for name in ("pandemic", "election", "controversy", "zombie"):
        assert name not in source
