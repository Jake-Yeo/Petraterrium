import csv
import io
import json
import zipfile
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.default_dsl import DefaultDslService
from petraterrium.simulation.default_pipeline_contracts import (
    ActivateDefaultPipelineRunRequest,
    RestoreDefaultPipelineRunRequest,
)
from petraterrium.simulation.default_pipeline_persistence import (
    JsonDefaultPipelineRepository,
)
from petraterrium.simulation.default_pipeline_routes import (
    create_default_pipeline_router,
)
from petraterrium.simulation.default_pipeline_service import (
    DefaultPipelineRunService,
    SimulationRegistryDefaultStateAdapter,
)
from petraterrium.simulation.duration_research import (
    AtusDurationResearchPipeline,
    FetchedDurationResource,
)
from petraterrium.simulation.editable_dsl_contracts import (
    ConfirmEditableDslRequest,
    PreviewEditableDslRequest,
)
from petraterrium.simulation.editable_dsl_persistence import JsonEditableDslRepository
from petraterrium.simulation.editable_dsl_service import EditableDslService
from petraterrium.simulation.global_duration_research import GlobalDurationResearchPipeline
from petraterrium.simulation.registry_store import SimulationRegistryStore


class FixtureDurationClient:
    def __init__(self, resources):
        self.resources = resources
        self.requests = []

    def fetch(self, url):
        self.requests.append(url)
        return self.resources[url]


def _zip_csv(name, rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr(name, text.getvalue())
    return buffer.getvalue()


def _resources():
    case_ids = [f"case-{index}" for index in range(1, 8)]
    durations = [5, 15, 30, 45, 60, 90, 180]
    activity_rows = []
    mappings = [
        ("010101", "23:00:00"),
        ("010101", "03:00:00"),
        ("010201", "07:00:00"),
        ("050101", "09:00:00"),
        ("060101", "10:00:00"),
        ("110101", "08:00:00"),
        ("110101", "12:00:00"),
        ("110101", "18:00:00"),
        ("120101", "19:00:00"),
        ("130101", "17:00:00"),
    ]
    for case_id, duration in zip(case_ids, durations, strict=True):
        for activity_number, (code, start) in enumerate(mappings, start=1):
            activity_rows.append(
                {
                    "TUCASEID": case_id,
                    "TUACTIVITY_N": activity_number,
                    "TUACTDUR24": duration + activity_number,
                    "TUSTARTTIM": start,
                    "TRCODE": code,
                }
            )
    respondent_rows = [
        {"TUCASEID": case_id, "TUFINLWGT": 1_000 + index * 100}
        for index, case_id in enumerate(case_ids)
    ]
    activity_url = AtusDurationResearchPipeline.activity_url(2025)
    respondent_url = AtusDurationResearchPipeline.respondent_url(2025)
    catalog_url = AtusDurationResearchPipeline.catalog_url(2025)
    hetus_url = AtusDurationResearchPipeline.hetus_url()
    return {
        catalog_url: FetchedDurationResource(
            url=catalog_url,
            content=b"ATUS 2025 Activity file Respondent file",
            content_type="text/html",
            retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
            last_modified="2026-06-25",
        ),
        activity_url: FetchedDurationResource(
            url=activity_url,
            content=_zip_csv("atusact_2025.dat", activity_rows),
            content_type="application/x-zip-compressed",
            retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
            last_modified="2026-06-25",
        ),
        respondent_url: FetchedDurationResource(
            url=respondent_url,
            content=_zip_csv("atusresp_2025.dat", respondent_rows),
            content_type="application/x-zip-compressed",
            retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
            last_modified="2026-06-25",
        ),
        hetus_url: FetchedDurationResource(
            url=hetus_url,
            content=b"HETUS scientific use files require research entity access",
            content_type="text/html",
            retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
            last_modified="2026-10-01",
        ),
    }


def _action(action_id):
    return {
        "id": action_id,
        "name": action_id.replace("_", " ").title(),
        "description": "Fixture action",
        "duration": {
            "minimum_minutes": 1,
            "typical_minutes": 2,
            "maximum_minutes": 3,
            "shape": "triangular",
        },
        "formula": "fixture",
        "conditions": [],
        "place_requirements": [],
        "time_requirements": [],
        "state_inputs": [],
        "outcomes": [],
        "evidence": {
            "status": "default_estimated",
            "explicit_default_reason": "Fixture default",
            "uncertainty_low": 0.0,
            "uncertainty_high": 1.0,
            "source_ids": [],
        },
        "runtime_rules": [],
        "cash_flow": {},
    }


def _registry_payload():
    action_ids = (
        "bad_work",
        "eat_breakfast",
        "eat_dinner",
        "eat_lunch",
        "exercise",
        "personal_care",
        "skip_lunch",
        "sleep",
        "social_activity",
        "work_or_study",
    )
    return {
        "default_dsl": {
            "schema_version": "1",
            "version": "fixture",
            "hash": f"sha256:{'1' * 64}",
            "source": "shipped",
            "managed_sections": [
                "default_actions",
                "default_sources",
                "agent_states",
                "coefficient_registry",
                "finance_initialization",
                "specialization_pipeline",
                "initial_population",
            ],
        },
        "default_actions": [_action(action_id) for action_id in action_ids],
        "default_sources": [],
        "agent_states": {"version": "1", "definitions": []},
        "coefficient_registry": {"version": "1", "defaults": []},
        "finance_initialization": {"schema_version": "1", "programs": []},
        "specialization_pipeline": {"schema_version": "1", "countries": []},
        "initial_population": {"population": {"agents": [{"agent_id": "one"}]}},
    }


def _service(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(_registry_payload()), encoding="utf-8")
    store = SimulationRegistryStore(registry_path)
    repository = JsonDefaultPipelineRepository(tmp_path / "pipeline-cache")
    researcher = AtusDurationResearchPipeline(
        client=FixtureDurationClient(_resources()),
        year=2025,
        clock=lambda: datetime(2026, 10, 27, tzinfo=UTC),
    )
    adapter = SimulationRegistryDefaultStateAdapter(store)
    service = DefaultPipelineRunService(
        repository=repository,
        duration_researcher=researcher,
        state_provider=adapter,
        state_restorer=adapter,
        clock=lambda: datetime(2026, 10, 27, tzinfo=UTC),
        identity=iter(("a" * 32, "b" * 32)).__next__,
    )
    return service, store


def test_duration_pipeline_returns_source_backed_measured_or_estimated_results():
    pipeline = AtusDurationResearchPipeline(
        client=FixtureDurationClient(_resources()),
        year=2025,
        clock=lambda: datetime(2026, 10, 27, tzinfo=UTC),
    )

    result = pipeline.research([_action("sleep"), _action("bad_work")])

    assert {item.evidence_kind for item in result.candidates} == {"measured", "estimated"}
    assert {item.evidence_kind for item in result.chosen_results} == {"estimated"}
    assert all(item.source_provenance for item in result.chosen_results)
    assert all(
        item.duration.minimum_hours <= item.duration.median_hours for item in result.chosen_results
    )
    assert all(
        item.duration.median_hours <= item.duration.maximum_hours for item in result.chosen_results
    )
    assert {entry.place_id for entry in result.search_log} == {"US", "EUROPE"}
    assert {entry.language for entry in result.search_log} == {"en"}
    assert any(entry.engine == "BLS official data catalog" for entry in result.search_log)
    assert any(entry.outcome == "unavailable" for entry in result.search_log)
    sleep = next(item for item in result.candidates if item.action_id == "sleep")
    assert sleep.duration.median_hours > 1.0


def test_global_pipeline_uses_confirmed_new_actions_and_logs_live_source_attempts(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    editor = EditableDslService(store, JsonEditableDslRepository(tmp_path / "editor"))
    current = editor.current()
    template = current.document.actions[0]
    new_action = template.model_copy(
        update={
            "id": "visit_library",
            "name": "Visit library",
            "formula": "0.1",
            "coefficients": (),
            "place_requirements": (),
            "time_requirements": (),
        }
    )
    document = current.document.model_copy(
        update={"actions": (*current.document.actions, new_action)}
    )
    preview = editor.preview(
        PreviewEditableDslRequest(expected_active_hash=current.document_hash, document=document)
    )
    assert preview.validation.valid
    editor.confirm(
        ConfirmEditableDslRequest(
            expected_active_hash=current.document_hash,
            preview_hash=preview.preview_hash,
            document=document,
            user_confirmed=True,
        )
    )
    client = FixtureDurationClient(_resources())
    live = AtusDurationResearchPipeline(client=client, year=2025)
    adapter = SimulationRegistryDefaultStateAdapter(editor.registry_overlay())
    pipeline = DefaultPipelineRunService(
        JsonDefaultPipelineRepository(tmp_path / "cache"),
        GlobalDurationResearchPipeline(additional_action_researcher=live),
        adapter,
        adapter,
    )
    run = pipeline.run_duration_research()
    result = next(item for item in run.chosen_results if item.action_id == "visit_library")
    assert result.evidence_kind == "estimated"
    assert client.requests
    assert any("visit_library" in entry.action_ids for entry in run.search_log)
    assert "decision_trees" in run.snapshot.section_hashes
    assert any(
        action["id"] == "visit_library"
        for action in pipeline.repository.read_snapshot(run.snapshot)["default_actions"]
    )


def test_new_unmapped_action_uses_an_estimated_pipeline_draft_without_code_change():
    pipeline = AtusDurationResearchPipeline(
        client=FixtureDurationClient(_resources()),
        year=2025,
        clock=lambda: datetime(2026, 10, 27, tzinfo=UTC),
    )

    result = pipeline.research([_action("new_action")])

    assert pipeline.mapping_catalog.version == "atus-2025-action-mapping-v1"
    assert result.candidates[0].evidence_kind == "estimated"
    assert result.chosen_results[0].evidence_kind == "estimated"
    assert result.chosen_results[0].source_provenance[0].source_id == (
        "petraterrium-duration-prior-v1"
    )
    assert "No action mapping exists" in result.candidates[0].reasoning


def test_cached_runs_are_versioned_inspectable_diffable_and_activatable(tmp_path):
    service, _store = _service(tmp_path)

    first = service.run_duration_research()
    second = service.run_duration_research()
    inspected = service.inspect(first.run_id)
    diff = service.diff(first.run_id, second.run_id)
    activated = service.activate(
        second.run_id,
        ActivateDefaultPipelineRunRequest(
            expected_run_hash=second.run_hash,
            user_confirmed=True,
        ),
    )

    assert [item.version for item in service.list_runs().runs] == [2, 1]
    assert first.previous_run_id is None
    assert second.previous_run_id == first.run_id
    assert inspected.search_log
    assert inspected.candidates
    assert inspected.chosen_results
    assert inspected.snapshot.section_counts["initial_population"] == 1
    assert diff.from_run_id == first.run_id
    assert diff.to_run_id == second.run_id
    assert activated.active is True
    assert service.list_runs().active_run_id == second.run_id


def test_restore_uses_saved_snapshot_without_research_and_restores_all_sections(tmp_path):
    service, store = _service(tmp_path)
    run = service.run_duration_research()
    service.activate(
        run.run_id,
        ActivateDefaultPipelineRunRequest(
            expected_run_hash=run.run_hash,
            user_confirmed=True,
        ),
    )
    original = store.payload_snapshot()
    changed = dict(original)
    changed["default_actions"] = []
    changed["agent_states"] = {"version": "broken", "definitions": []}
    changed["initial_population"] = {"population": {"agents": []}}
    store.path.write_text(json.dumps(changed), encoding="utf-8")

    receipt = service.restore(
        RestoreDefaultPipelineRunRequest(
            run_id=None,
            expected_run_hash=run.run_hash,
            user_confirmed=True,
        )
    )
    restored = store.payload_snapshot()

    assert receipt.run_id == run.run_id
    assert len(restored["default_actions"]) == 10
    assert all(
        action["duration"]["evidence"]["source_ids"] for action in restored["default_actions"]
    )
    assert restored["agent_states"] == original["agent_states"]
    assert restored["initial_population"] == original["initial_population"]
    assert restored["default_sources"]


def test_repository_rejects_a_tampered_snapshot(tmp_path):
    service, _store = _service(tmp_path)
    run = service.run_duration_research()
    snapshot_path = service.repository.root / run.snapshot.relative_path
    snapshot_path.write_bytes(snapshot_path.read_bytes() + b"tampered")

    try:
        service.repository.read_snapshot(run.snapshot)
    except ValueError as error:
        assert "snapshot" in str(error).casefold()
    else:
        raise AssertionError("Tampered snapshot was accepted")


def test_default_pipeline_router_exposes_run_history_diff_activation_and_restore(tmp_path):
    service, store = _service(tmp_path)
    first = service.run_duration_research()
    second = service.run_duration_research()
    application = FastAPI()
    application.include_router(create_default_pipeline_router(service))

    with TestClient(application) as client:
        listed = client.get("/simulation/default-pipeline")
        inspected = client.get(f"/simulation/default-pipeline/{first.run_id}")
        diff = client.get(f"/simulation/default-pipeline/{first.run_id}/diff/{second.run_id}")
        activated = client.post(
            f"/simulation/default-pipeline/{second.run_id}/activate",
            json={"expected_run_hash": second.run_hash, "user_confirmed": True},
        )
        current = store.payload_snapshot()
        current["default_actions"] = []
        store.path.write_text(json.dumps(current), encoding="utf-8")
        restored = client.post(
            "/simulation/default-pipeline/restore",
            json={
                "run_id": None,
                "expected_run_hash": second.run_hash,
                "user_confirmed": True,
            },
        )

    assert listed.status_code == 200
    assert [item["version"] for item in listed.json()["runs"]] == [2, 1]
    assert inspected.status_code == 200
    assert inspected.json()["search_log"]
    assert diff.status_code == 200
    assert diff.json()["from_run_id"] == first.run_id
    assert activated.status_code == 200
    assert restored.status_code == 200
    assert len(store.payload_snapshot()["default_actions"]) == 10


def test_checked_in_active_snapshot_restores_pipeline_sourced_default(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()
    repository = JsonDefaultPipelineRepository()
    adapter = SimulationRegistryDefaultStateAdapter(store)
    service = DefaultPipelineRunService(
        repository=repository,
        duration_researcher=AtusDurationResearchPipeline(
            client=FixtureDurationClient(_resources()),
            year=2025,
        ),
        state_provider=adapter,
        state_restorer=adapter,
    )
    active_run_id = repository.active_run_id()
    assert active_run_id is not None
    active_run = repository.get(active_run_id)

    receipt = service.restore_active()
    payload = store.payload_snapshot()

    assert receipt is not None
    assert receipt.version == active_run.version
    assert len(payload["initial_population"]["population"]["agents"]) == 1_000
    assert all(
        action["duration"]["evidence"]["source_ids"] for action in payload["default_actions"]
    )
    assert any(
        source["id"] == "atus-2025-activity-microdata" for source in payload["default_sources"]
    )
