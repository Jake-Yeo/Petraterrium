import asyncio
import json
import threading

import pytest

from petraterrium import engine
from petraterrium import service as service_module
from petraterrium.contracts import RunConfig, RunError
from petraterrium.population import PopulationTable
from petraterrium.recorder import RunRecord, RunStore
from petraterrium.service import RunService

CONFIG = {
    "scenario": "pandemic",
    "countries": ["ITA", "FRA", "DEU", "ESP"],
    "start_day": 0,
    "end_day": 30,
    "seed": 42,
}


def parse_events(body):
    events = []
    for block in body.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "id" in fields:
            events.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return events


def test_api_end_to_end_recorded_stream_and_metrics(client):
    response = client.post("/runs", json=CONFIG)
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    identity = response.json()["run_id"]
    stored = client.get(f"/runs/{identity}").json()
    assert stored["status"] == "done"
    assert len(stored["snapshots"]) == 31
    response = client.get(f"/runs/{identity}/stream")
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert [sequence for sequence, _, _ in events] == list(range(1, 34))
    assert [kind for _, kind, _ in events[:-2]] == ["snapshot"] * 31
    assert [snapshot for _, _, snapshot in events[:-2]] == stored["snapshots"]
    assert [snapshot["day"] for _, _, snapshot in events[:-2]] == list(range(31))
    assert events[-2][1] == "ensemble_update"
    assert events[-1][1] == "run-complete"
    assert events[-1][2]["metrics"] == stored["metrics"]
    infections = [sum(place["infected"] for place in day["places"]) for day in stored["snapshots"]]
    assert stored["metrics"]["peak_infected"] == max(infections)
    assert stored["metrics"]["peak_day"] == infections.index(max(infections))
    assert stored["metrics"]["totals"]["population"] == 3_900_000


def test_cache_returns_existing_results_without_recomputation(client, monkeypatch):
    first = client.post("/runs", json=CONFIG).json()

    def should_not_run(*args):
        raise AssertionError("Cached runs must not call the engine")

    monkeypatch.setattr(engine, "simulate", should_not_run)
    second = client.post("/runs", json={**CONFIG, "countries": list(reversed(CONFIG["countries"]))})
    assert second.status_code == 202
    assert second.json()["cached"] is True
    assert second.json()["run_id"] == first["run_id"]
    assert len(second.json()["snapshots"]) == 31
    assert second.json()["metrics"] is not None
    assert len(client.get("/runs").json()["runs"]) == 1


def test_resume_by_sequence_and_last_event_header(client):
    identity = client.post("/runs", json=CONFIG).json()["run_id"]
    original = parse_events(client.get(f"/runs/{identity}/stream").text)
    resumed = parse_events(client.get(f"/runs/{identity}/stream?after=12").text)
    assert resumed == original[12:]
    header = client.get(f"/runs/{identity}/stream?after=1", headers={"Last-Event-ID": "25"})
    assert parse_events(header.text) == original[25:]
    assert parse_events(client.get(f"/runs/{identity}/stream?after=33").text) == []


@pytest.mark.parametrize("cursor", ["-1", "9999", "bad"])
def test_invalid_resume_cursor_is_rejected(client, cursor):
    identity = client.post("/runs", json=CONFIG).json()["run_id"]
    assert (
        client.get(f"/runs/{identity}/stream", headers={"Last-Event-ID": cursor}).status_code == 422
    )


def test_engine_failure_is_stored_and_stream_terminates(client, monkeypatch):
    def broken_engine(*args):
        raise RuntimeError("Deliberate test failure")

    monkeypatch.setattr(engine, "simulate", broken_engine)
    response = client.post("/runs", json=CONFIG)
    assert response.status_code == 202
    identity = response.json()["run_id"]
    stored = client.get(f"/runs/{identity}").json()
    assert stored["status"] == "failed"
    assert stored["error"] == {"code": "engine_failure", "message": "Deliberate test failure"}
    events = parse_events(client.get(f"/runs/{identity}/stream").text)
    assert events == [
        (1, "run-failed", {"run_id": identity, "status": "failed", "error": stored["error"]})
    ]


def test_list_delete_and_recreate(client):
    identity = client.post("/runs", json=CONFIG).json()["run_id"]
    assert client.get("/runs").json()["runs"][0]["run_id"] == identity
    assert client.delete(f"/runs/{identity}").status_code == 204
    assert client.get("/runs").json()["runs"] == []
    assert client.get(f"/runs/{identity}").status_code == 404
    assert client.get(f"/runs/{identity}/stream").status_code == 404
    recreated = client.post("/runs", json=CONFIG).json()
    assert recreated["cached"] is False
    assert recreated["run_id"] == identity


@pytest.mark.parametrize(
    "changes",
    [
        {"countries": []},
        {"countries": ["ITA", "ITA"]},
        {"countries": ["USA"]},
        {"start_day": 5, "end_day": 5},
        {"end_day": 731},
        {"seed": -1},
        {"scenario": "election"},
        {"parameters": {"transmission": -0.1}},
    ],
)
def test_invalid_configuration_is_rejected(client, changes):
    assert client.post("/runs", json={**CONFIG, **changes}).status_code == 422


def test_in_memory_store_is_scoped_to_app(client):
    from fastapi.testclient import TestClient

    from petraterrium.main import create_app

    client.post("/runs", json=CONFIG)
    with TestClient(create_app()) as fresh:
        assert fresh.get("/runs").json()["runs"] == []


def test_catalog_declares_fake_provenance(client):
    catalog = client.get("/catalog").json()
    assert len(catalog["countries"]) == 4
    assert all(country["fake"] is True for country in catalog["countries"])
    assert catalog["data_version"].startswith("FAKE-")
    assert catalog["engine_version"].startswith("rust-vector-engine-")


def test_active_recorder_replays_and_follows_one_computation():
    async def exercise():
        store = RunStore()
        service = RunService(store)
        record, _ = service.create(RunConfig(**CONFIG))
        received = []

        async def consume():
            async for event in record.follow(0):
                if event:
                    received.append(event)

        consumer = asyncio.create_task(consume())
        await service.execute(record)
        await asyncio.wait_for(consumer, timeout=2)
        assert len(received) == 33
        assert [event.data for event in received[:-2]] == record.snapshots
        assert received[-2].kind == "ensemble_update"
        assert [event.sequence for event in received] == list(range(1, 34))

    asyncio.run(exercise())


def test_run_preparation_does_not_block_the_event_loop(monkeypatch):
    preparation_started = threading.Event()
    preparation_release = threading.Event()

    def blocking_population(_dsl, _atlas, seed):
        preparation_started.set()
        if not preparation_release.wait(timeout=0.5):
            raise RuntimeError("Run preparation blocked the event loop")
        return PopulationTable(
            population_id="test-population",
            version="test-v1",
            seed=seed,
            agents=[],
        )

    monkeypatch.setattr(service_module, "generate_population", blocking_population)
    monkeypatch.setattr(service_module, "record_action_logs", lambda *_args: [])

    async def exercise():
        store = RunStore()
        service = RunService(store)
        record, _ = service.create(RunConfig(**{**CONFIG, "end_day": 1}))
        worker = asyncio.create_task(service.execute(record))
        for _ in range(100):
            if preparation_started.is_set():
                break
            await asyncio.sleep(0.001)
        assert preparation_started.is_set()
        preparation_release.set()
        await asyncio.wait_for(worker, timeout=2)
        assert record.status == "done"

    asyncio.run(exercise())


def test_deleting_running_job_stops_worker_and_terminates_follower():
    async def exercise():
        store = RunStore()
        service = RunService(store)
        record, _ = service.create(RunConfig(**CONFIG))
        worker = asyncio.create_task(service.execute(record))
        await asyncio.sleep(0)
        await service.delete(record)
        await worker
        events = [event async for event in record.follow(0)]
        assert events[-1].kind == "run-failed"
        assert record.status == "failed"
        assert store.get(record.run_id) is None

    asyncio.run(exercise())


def test_failed_recorder_wakes_waiting_stream():
    async def exercise():
        record = RunRecord(run_id="test", config=RunConfig(**CONFIG), config_hash="test")

        async def wait_for_event():
            return [event async for event in record.follow(0)]

        listener = asyncio.create_task(wait_for_event())
        await asyncio.sleep(0)
        await record.fail(RunError(code="test", message="Expected failure"))
        events = await asyncio.wait_for(listener, timeout=1)
        assert events[-1].kind == "run-failed"

    asyncio.run(exercise())
