from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.default_dsl import DefaultDslService
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_preview import (
    SimulationRunPreviewService,
    create_simulation_run_preview_router,
)
from petraterrium.simulation.run_service import (
    SimulationPlaceScope,
    SimulationRunConfig,
    SimulationRunService,
)


class RejectingRustClient:
    def run_agents(self, request):
        raise AssertionError(f"Preview attempted to execute Rust with {request}")


def default_config() -> SimulationRunConfig:
    return SimulationRunConfig(
        population_size=1000,
        seed=1,
        days=30,
        tick_interval_hours=24,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="global"),
        agent_type_mix={"person": 0.178, "student": 0.285, "worker": 0.537},
    )


def test_preview_prepares_shipped_default_evidence_without_queueing_a_run(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    DefaultDslService(store).ensure()

    def prepare(config):
        return prepare_registry_run(store, config)

    run_service = SimulationRunService(prepare, RejectingRustClient())
    preview_service = SimulationRunPreviewService(prepare)
    application = FastAPI()
    application.include_router(
        create_simulation_run_preview_router(preview_service),
        prefix="/api",
    )
    client = TestClient(application)

    response = client.post(
        "/api/simulation/runs/preview",
        json=default_config().model_dump(mode="json"),
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["config"] == default_config().model_dump(mode="json")
    assert preview["agent_count"] == 1000
    assert preview["total_ticks"] == 30
    assert preview["default_dsl_version"] == "base-1.0.0"
    assert preview["default_dsl_hash"].startswith("sha256:")
    assert preview["evidence_summary"]["default_estimated_count"] > 0
    assert preview["evidence_summary"]["fitted_count"] == 0
    groups = {
        (item["action_id"], item["place"]["level"], item["place"]["place_id"]): item
        for item in preview["evidence_summary"]["by_action_place"]
    }
    warnings = {
        (item["action_id"], item["place"]["level"], item["place"]["place_id"]): item
        for item in preview["evidence_warnings"]
    }
    assert warnings
    assert warnings.keys() == {
        key for key, group in groups.items() if group["default_estimated_count"] > 0
    }
    assert all(warning["coefficient_ids"] for warning in warnings.values())
    assert run_service.list() == []
    run_service.shutdown()


def test_preview_rejects_invalid_preparation_without_queueing_a_run():
    def invalid_preparation(config):
        place = config.place_scope.identifier or config.place_scope.level
        raise ValueError(f"No executable evidence for {place}")

    run_service = SimulationRunService(invalid_preparation, RejectingRustClient())
    preview_service = SimulationRunPreviewService(invalid_preparation)
    application = FastAPI()
    application.include_router(
        create_simulation_run_preview_router(preview_service),
        prefix="/api",
    )
    client = TestClient(application, raise_server_exceptions=False)

    response = client.post(
        "/api/simulation/runs/preview",
        json=default_config().model_dump(mode="json"),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "No executable evidence for global"}
    assert run_service.list() == []
    run_service.shutdown()
