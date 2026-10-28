import json
import sqlite3

from petraterrium.simulation.run_persistence import SimulationRunRecorder


def test_checkpoint_append_does_not_rewrite_large_run_metadata(tmp_path):
    recorder = SimulationRunRecorder(tmp_path / "simulation-runs.sqlite3")
    initial = {"run_id": "run-1", "status": "running", "prepared": {"agents": [1, 2]}}
    recorder.save_metadata("run-1", initial)

    recorder.append_checkpoint(
        "run-1",
        {**initial, "status": "stale", "prepared": {"agents": [3, 4]}},
        0,
        {"tick": 24},
        0,
        [{"kind": "action"}],
    )

    stored = recorder.load()[0]
    assert stored.metadata == initial
    assert stored.frames == [{"tick": 24}]
    assert stored.events == [{"kind": "action"}]


def test_recorder_compresses_repetitive_payloads_and_reads_them_losslessly(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    metadata = {"run_id": "run-1", "evidence": ["same provenance"] * 2_000}

    recorder.save_metadata("run-1", metadata)

    with sqlite3.connect(path) as connection:
        stored_type, stored_size = connection.execute(
            "SELECT typeof(metadata), length(metadata) FROM simulation_runs WHERE run_id = ?",
            ("run-1",),
        ).fetchone()
    assert stored_type == "blob"
    assert stored_size < len(json.dumps(metadata)) // 5
    assert recorder.load()[0].metadata == metadata


def test_recorder_reads_existing_plain_json_rows(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    metadata = {"run_id": "legacy-run", "status": "completed"}
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO simulation_runs (run_id, metadata) VALUES (?, ?)",
            ("legacy-run", json.dumps(metadata)),
        )

    assert recorder.load()[0].metadata == metadata


def test_metadata_load_does_not_decode_checkpoint_history(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    metadata = {"run_id": "run-1", "status": "completed"}
    recorder.save_metadata("run-1", metadata)
    recorder.append_checkpoint(
        "run-1",
        {},
        0,
        {"tick": 24},
        0,
        [{"kind": "action"}],
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE simulation_run_frames SET payload = ? WHERE run_id = ?",
            (sqlite3.Binary(b"invalid-frame"), "run-1"),
        )
        connection.execute(
            "UPDATE simulation_run_events SET payload = ? WHERE run_id = ?",
            (sqlite3.Binary(b"invalid-event"), "run-1"),
        )

    stored = recorder.load_metadata()

    assert stored == [metadata]


def test_metadata_load_discards_legacy_final_output_event_history(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    metadata = {
        "run_id": "run-1",
        "status": "completed",
        "final_output": {
            "agents": {"state": ["home"]},
            "interactions": [{"interaction_type": "talk"}],
            "events": [{"action": "work"}],
        },
    }
    recorder.save_metadata("run-1", metadata)

    restored_metadata = recorder.load_metadata()[0]
    restored_final_output = recorder.load_final_output("run-1")

    assert restored_metadata["final_output"] is None
    assert restored_final_output["agents"] == {"state": ["home"]}
    assert restored_final_output["interactions"] == []
    assert restored_final_output["events"] == []
    assert recorder.load()[0].metadata == metadata


def test_recorder_streams_interactions_and_pages_events_without_loading_history(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    recorder.save_metadata("run-1", {"run_id": "run-1", "status": "completed"})
    recorder.append_checkpoint(
        "run-1",
        {},
        0,
        {"tick": 24},
        0,
        [
            {"kind": "action", "details": {"action": "work"}},
            {"kind": "interaction", "details": {"tick": 1, "interaction_type": "talk"}},
            {"kind": "interaction", "details": {"tick": 2, "interaction_type": "visit"}},
        ],
    )

    page, total = recorder.load_event_page(
        "run-1",
        kind="interaction",
        page=2,
        page_size=1,
    )

    assert total == 2
    assert page == [
        {"kind": "interaction", "details": {"tick": 2, "interaction_type": "visit"}}
    ]
    assert list(recorder.iter_interactions("run-1")) == [
        {"tick": 1, "interaction_type": "talk"},
        {"tick": 2, "interaction_type": "visit"},
    ]


def test_metadata_load_applies_atomic_checkpoint_progress(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    recorder.save_metadata(
        "run-1",
        {
            "run_id": "run-1",
            "status": "running",
            "progress": 0,
            "completed_ticks": 0,
            "location_ids": ["home"],
        },
    )
    recorder.append_checkpoint(
        "run-1",
        {
            "status": "running",
            "progress": 0.5,
            "completed_ticks": 12,
            "location_ids": ["work"],
        },
        0,
        {"tick": 12},
        0,
        [],
    )

    metadata = recorder.load_metadata()[0]

    assert metadata["progress"] == 0.5
    assert metadata["completed_ticks"] == 12
    assert metadata["location_ids"] == ["work"]
    assert recorder.load()[0].metadata["completed_ticks"] == 0


def test_terminal_metadata_replaces_and_clears_checkpoint_state(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    recorder.save_metadata(
        "run-1",
        {"run_id": "run-1", "status": "running", "progress": 0},
    )
    recorder.append_checkpoint(
        "run-1",
        {"status": "running", "progress": 0.5},
        0,
        {"tick": 12},
        0,
        [],
    )
    recorder.save_metadata(
        "run-1",
        {"run_id": "run-1", "status": "completed", "progress": 1},
    )

    assert recorder.load_metadata() == [
        {"run_id": "run-1", "status": "completed", "progress": 1}
    ]


def test_large_run_artifacts_are_lazy_and_lossless(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    metadata = {
        "run_id": "run-1",
        "status": "completed",
        "prepared": {"agent_ids": ["a-1"]},
        "result": {"snapshots": [{"day": 1}]},
        "final_output": {
            "agents": {"state": ["home"], "interactions": ["nested-value"]},
            "interactions": [{"tick": 1}],
            "events": [{"tick": 1}],
        },
        "location_history": [{"agent_id": "a-1", "tick": 1}],
    }

    recorder.save_metadata("run-1", metadata)

    lightweight = recorder.load_metadata()[0]
    assert lightweight["prepared"] is None
    assert lightweight["result"] is None
    assert lightweight["final_output"] is None
    assert lightweight["location_history"] is None
    assert recorder.load_prepared("run-1") == metadata["prepared"]
    assert recorder.load_result("run-1") == metadata["result"]
    assert recorder.load_location_history("run-1") == metadata["location_history"]
    assert recorder.load_final_output("run-1")["agents"]["interactions"] == [
        "nested-value"
    ]
    assert recorder.load()[0].metadata == metadata

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE simulation_run_artifacts SET payload = ? "
            "WHERE run_id = ? AND artifact_kind = ?",
            (sqlite3.Binary(b"invalid-artifact"), "run-1", "prepared"),
        )
    assert recorder.load_metadata()[0] == lightweight


def test_agent_frame_projection_reads_only_the_requested_agent(tmp_path):
    recorder = SimulationRunRecorder(tmp_path / "simulation-runs.sqlite3")
    recorder.save_metadata("run-1", {"run_id": "run-1", "status": "completed"})
    recorder.append_checkpoint(
        "run-1",
        {},
        0,
        {
            "day": 1,
            "date": "2026-10-27",
            "tick": 24,
            "modules": ["home", "work"],
            "states": ["rest", "active"],
            "locations": ["house", "office"],
            "memory": [{"energy": 1}, {"energy": 0.5}],
            "state_receipts": [[], [{"state": "energy"}]],
            "action_receipts": [[], [{"action": "work"}]],
            "actions": [[], ["work"]],
            "routines": [["sleep"], ["commute"]],
            "interactions": [[], ["talk"]],
            "interaction_details": [[], [{"role": "initiator"}]],
            "decisions": [[], [{"node_id": "work"}]],
            "location_transitions": [[], [{"to": "office"}]],
            "live_places": [{"place_id": "office"}],
        },
        0,
        [],
    )

    projected = recorder.load_agent_frames("run-1", 1)

    assert projected[0]["modules"] == ["work"]
    assert projected[0]["states"] == ["active"]
    assert projected[0]["memory"] == [{"energy": 0.5}]
    assert projected[0]["actions"] == [["work"]]
    assert projected[0]["live_places"] == []
