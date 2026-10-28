import json
from copy import deepcopy
from pathlib import Path

import pytest

from petraterrium.simulation.default_dsl import load_shipped_default_dsl
from petraterrium.simulation.default_pipeline_contracts import DurationResearchOutput
from petraterrium.simulation.default_pipeline_persistence import (
    JsonDefaultPipelineRepository,
)
from petraterrium.simulation.default_pipeline_service import DefaultPipelineRunService
from petraterrium.simulation.global_duration_research import (
    GlobalDurationResearchPipeline,
    GlobalDurationSourceCatalog,
    global_duration_catalog_path,
    global_duration_receipt_path,
)
from petraterrium.simulation.registry_store import SimulationRegistryStore
from petraterrium.simulation.run_preparation import prepare_registry_run
from petraterrium.simulation.run_service import SimulationRunConfig

COUNTRY_IDS = {
    "AU",
    "BD",
    "BR",
    "CA",
    "CN",
    "ID",
    "IN",
    "MX",
    "NG",
    "PK",
    "RU",
    "US",
}
REGION_IDS = {
    "REGION_AFRICA",
    "REGION_ASIA_EXCLUDING_CHINA_INDIA",
    "REGION_CHINA",
    "REGION_EUROPE",
    "REGION_INDIA",
    "REGION_LATIN_AMERICA_CARIBBEAN",
    "REGION_NORTHERN_AMERICA",
    "REGION_OCEANIA",
}
ACTION_IDS = {
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
}
SOURCE_TIERS = {
    "official_statistics",
    "representative_survey",
    "research_article",
    "government_report",
    "news",
    "online_opinion",
}


def _actions():
    path = (
        Path(__file__).resolve().parents[1]
        / "petraterrium"
        / "simulation"
        / "defaults"
        / "base-v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["content"]["default_actions"]


def _default_sections():
    path = (
        Path(__file__).resolve().parents[1]
        / "petraterrium"
        / "simulation"
        / "defaults"
        / "base-v1.json"
    )
    content = json.loads(path.read_text(encoding="utf-8"))["content"]
    names = (
        "default_actions",
        "default_sources",
        "agent_states",
        "coefficient_registry",
        "finance_initialization",
        "specialization_pipeline",
        "initial_population",
    )
    return {name: deepcopy(content[name]) for name in names}


class DefaultStateFixture:
    def __init__(self):
        self.sections = _default_sections()

    def snapshot_sections(self):
        return deepcopy(self.sections)

    def restore_sections(self, sections, _version):
        self.sections = deepcopy(sections)


def test_global_duration_catalog_covers_every_demo_country_region_action_and_tier():
    pipeline = GlobalDurationResearchPipeline()
    catalog = pipeline.catalog
    countries = {item.place_id for item in catalog.places if item.level == "country"}
    regions = {item.place_id for item in catalog.places if item.level == "region"}

    assert countries == COUNTRY_IDS
    assert regions == REGION_IDS
    assert {item.action_id for item in catalog.action_crosswalk} == ACTION_IDS
    assert set(catalog.requested_source_tiers) == SOURCE_TIERS
    assert all(
        {attempt.source_kind for attempt in place.search_attempts} == SOURCE_TIERS
        for place in catalog.places
    )
    assert all(place.search_attempts[0].language == place.languages[0] for place in catalog.places)


def test_required_local_language_engines_and_official_sources_are_auditable():
    catalog = GlobalDurationResearchPipeline().catalog
    places = {item.place_id: item for item in catalog.places}
    requirements = {
        "CN": ("zh", "Baidu", "National Bureau of Statistics of China"),
        "RU": ("ru", "Yandex", "Rosstat"),
        "BR": ("pt", "Google Brasil", "Instituto Brasileiro"),
        "IN": ("hi", "Google India", "Ministry of Statistics"),
        "PK": ("ur", "Google Pakistan", "Pakistan"),
        "BD": ("bn", "Google Bangladesh", "Bangladesh Bureau"),
        "ID": ("id", "Google Indonesia", "Badan Pusat Statistik"),
        "MX": ("es", "Google México", "Instituto Nacional"),
        "NG": ("ha", "Google Nigeria", "National Bureau of Statistics"),
    }

    for place_id, (language, engine, publisher) in requirements.items():
        place = places[place_id]
        first = place.search_attempts[0]
        assert first.language == language
        assert first.engine == engine
        assert any(publisher in source.publisher for source in place.sources)

    indonesia = places["ID"]
    assert indonesia.search_attempts[0].outcome == "unavailable"
    assert any(
        attempt.engine == "UN ESCAP official repository" and attempt.outcome == "candidate"
        for attempt in indonesia.search_attempts
    )


def test_global_duration_pipeline_returns_all_place_cells_and_estimated_global_defaults():
    pipeline = GlobalDurationResearchPipeline()
    result = pipeline.research(_actions())
    receipt = pipeline.cached_receipt(_actions())
    index = receipt["place_action_index"]

    assert len(result.requests) == 200
    assert len(result.candidates) == 200
    assert len(result.search_log) == 120
    assert len(index) == 200
    assert {(item["place_id"], item["action_id"]) for item in index} == {
        (place_id, action_id) for place_id in COUNTRY_IDS | REGION_IDS for action_id in ACTION_IDS
    }
    assert {item.action_id for item in result.chosen_results} == ACTION_IDS
    assert {item.evidence_kind for item in result.chosen_results} == {"estimated"}
    assert all(item.target_place_id == "GLOBAL" for item in result.chosen_results)
    assert all(len(item.candidate_ids) == 12 for item in result.chosen_results)


def test_non_us_country_results_are_estimated_and_never_relabel_another_country():
    pipeline = GlobalDurationResearchPipeline()
    result = pipeline.research(_actions())
    receipt = pipeline.cached_receipt(_actions())
    candidates = {item.candidate_id: item for item in result.candidates}

    for item in receipt["place_action_index"]:
        if item["level"] != "country" or item["place_id"] == "US":
            continue
        candidate = candidates[item["candidate_id"]]
        assert candidate.evidence_kind == "estimated"
        assert candidate.source_provenance[0].place_id == item["place_id"]
        assert any(
            "No country's value is presented as measured" in assumption
            for assumption in candidate.assumptions
        )
        assert candidate.uncertainty.coverage.startswith("wide")


def test_global_defaults_are_population_weighted_from_all_twelve_country_candidates():
    pipeline = GlobalDurationResearchPipeline()
    result = pipeline.research(_actions())
    receipt = pipeline.cached_receipt(_actions())
    candidates = {item.candidate_id: item for item in result.candidates}
    country_rows = [item for item in receipt["place_action_index"] if item["level"] == "country"]

    for chosen in result.chosen_results:
        rows = [item for item in country_rows if item["action_id"] == chosen.action_id]
        total_population = sum(item["population"] for item in rows)
        expected = (
            sum(
                candidates[item["candidate_id"]].duration.median_hours * item["population"]
                for item in rows
            )
            / total_population
        )
        assert chosen.duration.median_hours == pytest.approx(expected, abs=1e-6)
        source_places = {source.place_id for source in chosen.source_provenance}
        assert COUNTRY_IDS <= source_places


def test_checked_in_global_duration_receipt_matches_pipeline_output_and_contract():
    pipeline = GlobalDurationResearchPipeline()
    checked_in = json.loads(global_duration_receipt_path().read_text(encoding="utf-8"))
    generated = pipeline.cached_receipt(_actions())

    assert checked_in == generated
    output = DurationResearchOutput.model_validate_json(
        json.dumps(checked_in["output"])
    )
    assert len(output.candidates) == 200
    assert len(checked_in["receipt_id"]) == 64
    assert checked_in["input"]["country_ids"] == [
        item.place_id for item in pipeline.catalog.places if item.level == "country"
    ]


def test_existing_default_pipeline_service_caches_the_global_research_output(tmp_path):
    fixture = DefaultStateFixture()
    repository = JsonDefaultPipelineRepository(tmp_path / "global-duration-cache")
    service = DefaultPipelineRunService(
        repository=repository,
        duration_researcher=GlobalDurationResearchPipeline(),
        state_provider=fixture,
        state_restorer=fixture,
        identity=lambda: "d" * 32,
    )

    run = service.run_duration_research()
    snapshot = repository.read_snapshot(run.snapshot)

    assert run.pipeline_version == "global-default-duration-research-v1"
    assert len(run.requests) == 200
    assert len(run.search_log) == 120
    assert len(run.candidates) == 200
    assert len(run.chosen_results) == 10
    assert all(item.evidence_kind == "estimated" for item in run.chosen_results)
    assert len(snapshot["default_actions"]) == 10
    assert all(
        action["duration"]["evidence"]["source_ids"]
        for action in snapshot["default_actions"]
    )
    assert all(
        len(action["duration_resolutions"]) == len(COUNTRY_IDS | REGION_IDS)
        for action in snapshot["default_actions"]
    )
    sleep = next(action for action in snapshot["default_actions"] if action["id"] == "sleep")
    resolutions = {
        resolution["place_ids"][0]: resolution for resolution in sleep["duration_resolutions"]
    }
    assert COUNTRY_IDS | REGION_IDS <= resolutions.keys()
    assert resolutions["CN"]["duration"] != resolutions["US"]["duration"]
    assert resolutions["CN"]["duration"]["evidence"]["status"] == "default_estimated"
    assert resolutions["US"]["duration"]["evidence"]["status"] in {
        "measured",
        "default_estimated",
    }
    assert any(
        resolution["duration"]["evidence"]["status"] == "measured"
        for action in snapshot["default_actions"]
        for resolution in action["duration_resolutions"]
    )


def test_country_duration_candidates_compile_to_disjoint_rust_agent_overrides(tmp_path):
    fixture = DefaultStateFixture()
    package = load_shipped_default_dsl()
    fixture.sections = {
        name: deepcopy(package.content[name]) for name in fixture.sections
    }
    repository = JsonDefaultPipelineRepository(tmp_path / "global-duration-cache")
    service = DefaultPipelineRunService(
        repository=repository,
        duration_researcher=GlobalDurationResearchPipeline(),
        state_provider=fixture,
        state_restorer=fixture,
        identity=lambda: "e" * 32,
    )
    run = service.run_duration_research()
    snapshot = repository.read_snapshot(run.snapshot)
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "petraterrium"
            / "simulation"
            / "defaults"
            / "base-v1.json"
        ).read_text(encoding="utf-8")
    )
    payload = deepcopy(package.content)
    payload.update(snapshot)
    payload["default_dsl"] = {
        "schema_version": "1",
        "version": manifest["dsl_version"],
        "hash": manifest["content_hash"],
        "source": "shipped",
        "managed_sections": manifest["managed_sections"],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    prepared = prepare_registry_run(
        SimulationRegistryStore(registry_path),
        SimulationRunConfig(
            population_size=1_000,
            seed=1,
            days=1,
            tick_interval_hours=1,
            start_date="2026-10-27",
            place_scope={"level": "global", "identifier": None},
            agent_type_mix={},
        ),
    )
    sleep = next(
        action
        for action in prepared.rust_request["state_dynamics"]["time_execution"]["actions"]
        if action["action_id"] == "sleep"
    )
    selected = {
        agent_index: override["duration"]["duration_median_hours"]
        for override in sleep["duration_overrides"]
        for agent_index in override["eligible_agent_indices"]
    }
    countries = [
        profile["geography"]["country_id"] for profile in prepared.initial_agent_profiles
    ]
    china_medians = {selected[index] for index, country in enumerate(countries) if country == "CN"}
    united_states_medians = {
        selected[index] for index, country in enumerate(countries) if country == "US"
    }

    assert len(selected) == 1_000
    assert len(china_medians) == 1
    assert len(united_states_medians) == 1
    assert china_medians != united_states_medians
    statuses = {
        override["duration"]["provenance"]["status"]
        for action in prepared.rust_request["state_dynamics"]["time_execution"]["actions"]
        for override in action["duration_overrides"]
    }
    assert statuses == {"default_estimated", "measured"}


def test_catalog_file_round_trips_under_the_strict_versioned_contract():
    raw = global_duration_catalog_path().read_text(encoding="utf-8")
    catalog = GlobalDurationSourceCatalog.model_validate_json(raw)

    assert catalog.schema_version == "1"
    assert catalog.version == "global-duration-source-catalog-v1"
    assert catalog.pipeline_version == "global-default-duration-research-v1"
    assert catalog.population_source.source_id == "un-wpp-2024-population"
