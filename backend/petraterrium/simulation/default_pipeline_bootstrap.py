import argparse
from pathlib import Path

from .default_dsl import DefaultDslService
from .default_pipeline_contracts import ActivateDefaultPipelineRunRequest
from .default_pipeline_persistence import JsonDefaultPipelineRepository
from .default_pipeline_service import (
    DefaultPipelineRunService,
    SimulationRegistryDefaultStateAdapter,
)
from .global_duration_research import GlobalDurationResearchPipeline
from .registry_store import SimulationRegistryStore


def build_default_pipeline_service(
    store: SimulationRegistryStore | None = None,
    cache_path: str | Path | None = None,
    year: int = 2025,
) -> DefaultPipelineRunService:
    if year != 2025:
        raise ValueError("The checked global duration catalog is versioned for 2025")
    selected_store = store or SimulationRegistryStore()
    DefaultDslService(selected_store).ensure()
    adapter = SimulationRegistryDefaultStateAdapter(selected_store)
    return DefaultPipelineRunService(
        repository=JsonDefaultPipelineRepository(cache_path),
        duration_researcher=GlobalDurationResearchPipeline(),
        state_provider=adapter,
        state_restorer=adapter,
    )


def run_default_duration_pipeline(
    store: SimulationRegistryStore | None = None,
    cache_path: str | Path | None = None,
    year: int = 2025,
    activate: bool = False,
):
    service = build_default_pipeline_service(store, cache_path, year)
    run = service.run_duration_research()
    if activate:
        service.activate(
            run.run_id,
            ActivateDefaultPipelineRunRequest(
                expected_run_hash=run.run_hash,
                user_confirmed=True,
            ),
        )
    return run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--cache")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--activate", action="store_true")
    arguments = parser.parse_args()
    store = SimulationRegistryStore(arguments.registry) if arguments.registry else None
    run = run_default_duration_pipeline(
        store=store,
        cache_path=arguments.cache,
        year=arguments.year,
        activate=arguments.activate,
    )
    print(run.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

