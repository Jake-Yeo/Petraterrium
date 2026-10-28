import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from petraterrium.main import create_app
from petraterrium.simulation.default_dsl import DefaultDslService, load_shipped_default_dsl
from petraterrium.simulation.global_demo_population import GLOBAL_DEMO_COUNTRIES
from petraterrium.simulation.registry_store import SimulationRegistryStore


def _application(tmp_path, store):
    return create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        simulation_registry_store=store,
    )


def test_checked_in_default_has_verified_version_hash_and_base_inventory():
    package = load_shipped_default_dsl()

    assert package.receipt.version == "base-1.0.0"
    assert package.receipt.hash.startswith("sha256:")
    assert package.receipt.source == "shipped"
    assert "person" in package.inventory.agent_type_ids
    assert "stress" in package.inventory.state_ids
    assert "sleep" in package.inventory.action_ids
    assert package.inventory.routine_ids
    assert package.inventory.decision_tree_ids
    assert package.inventory.interaction_tree_ids
    assert package.inventory.initial_agent_count > 0


def test_checked_in_default_decision_program_is_global_and_has_no_synthetic_fallback():
    package = load_shipped_default_dsl()
    registry = package.content["decision_trees"]
    transitions = [
        edge["id"]
        for module in registry["modules"]
        for edge in module["edges"]
    ]

    assert registry["trees"]
    assert all(tree["place_ids"] == [] for tree in registry["trees"])
    assert "remain-active-without-confirmed-decision-program" not in transitions


def test_checked_in_default_contains_executable_cross_country_interaction_dsl():
    package = load_shipped_default_dsl()
    agents = package.content["initial_population"]["population"]["agents"]
    countries = {agent["agent_id"]: agent["traits"]["country_id"] for agent in agents}
    program = package.content["interaction_program"]

    assert program["status"] == "confirmed"
    assert program["rules"]
    assert all(
        factor["provenance"]["status"] == "default_estimated"
        for rule in program["rules"]
        for factor in (
            rule["base_factor"],
            *rule["relationship_factors"].values(),
            *rule["colocation_factors"].values(),
            *rule["place_factors"].values(),
            *(window["factor"] for window in rule["time_factors"]),
        )
    )
    assert all(len(agent["relationships"]) == 1 for agent in agents)
    assert all(
        countries[agent["agent_id"]]
        != countries[agent["relationships"][0]["target_id"]]
        for agent in agents
    )


def test_checked_in_default_materializes_complete_deterministic_demo_population():
    package = load_shipped_default_dsl()
    population = package.content["initial_population"]["population"]["agents"]
    state_ids = set(package.inventory.state_ids)
    finance_state_ids = {
        "finance.money",
        "finance.income",
        "finance.expenses",
        "finance.savings",
        "finance.debt",
    }
    education_fields = {
        "years_of_education",
        "education_isced",
        "education_country_label",
        "education_mapping_version",
        "specialization_threshold_years",
    }
    finance_fields = {
        "finance_currency",
        "finance_status",
        "finance_source",
        "finance_source_version",
        "finance_source_date",
        "finance_source_place",
        "finance_source_population",
        "finance_uncertainty",
        "finance_default_reason",
    }
    seeded_ids = package.content["initial_seeding_rules"][0]["expected_agent_ids"]

    assert len(population) == 1_000
    assert [agent["agent_id"] for agent in population] == seeded_ids
    assert all("name" not in agent["traits"] for agent in population)
    assert all(state_ids <= set(agent["states"]) for agent in population)
    assert all(finance_state_ids <= set(agent["states"]) for agent in population)
    assert all(education_fields <= set(agent["traits"]) for agent in population)
    assert all(finance_fields <= set(agent["traits"]) for agent in population)

    country_counts = Counter(agent["traits"]["country_id"] for agent in population)
    assert set(country_counts) == set(GLOBAL_DEMO_COUNTRIES)
    assert sum(country_counts.values()) == 1_000
    assert all(
        agent["traits"]["state_initialization_status"] == "default_estimated"
        and agent["traits"]["state_initialization_uncertainty"] == 1
        for agent in population
    )
    assert all(
        "Statistics Canada" not in agent["traits"]["finance_source"]
        and "Statistique Canada" not in agent["traits"]["finance_source"]
        for agent in population
        if agent["traits"]["country_id"] != "CA"
    )


def test_fresh_app_loads_default_without_proposal_or_manual_step(tmp_path):
    store = SimulationRegistryStore(tmp_path / "simulation-registry.json")

    with TestClient(_application(tmp_path, store)) as client:
        status = client.get("/simulation/default-dsl")
        agent_types = client.get("/simulation/agent-types")
        decision_trees = client.get("/simulation/decision-trees")
        population = client.get("/simulation/initial-population")

    assert status.status_code == 200
    assert status.json()["loaded"] is True
    assert status.json()["intact"] is True
    assert status.json()["drifted_sections"] == []
    assert agent_types.json()["configured"] is True
    assert "person" in {
        item["id"] for item in agent_types.json()["resolved"]["types"]
    }
    assert decision_trees.json()["registry"]["trees"]
    assert population.json()["configured"] is True
    assert population.json()["agent_count"] > 0


def test_first_open_loading_is_idempotent_and_does_not_duplicate_content(tmp_path):
    registry_path = tmp_path / "simulation-registry.json"
    store = SimulationRegistryStore(registry_path)

    with TestClient(_application(tmp_path, store)) as client:
        first = client.get("/simulation/default-dsl").json()
    first_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    first_payload["unmanaged_fixture"] = {"preserved": True}
    registry_path.write_text(json.dumps(first_payload), encoding="utf-8")

    reopened_store = SimulationRegistryStore(registry_path)
    with TestClient(_application(tmp_path, reopened_store)) as client:
        second = client.get("/simulation/default-dsl").json()

    second_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert first["receipt"] == second["receipt"]
    assert first["inventory"] == second["inventory"]
    assert second_payload["unmanaged_fixture"] == {"preserved": True}
    assert len(second_payload["agent_types"]["types"]) == len(
        first_payload["agent_types"]["types"]
    )
    assert len(second_payload["decision_trees"]["trees"]) == len(
        first_payload["decision_trees"]["trees"]
    )
    assert len(second_payload["initial_population"]["population"]["agents"]) == len(
        first_payload["initial_population"]["population"]["agents"]
    )


def test_concurrent_first_open_installs_one_identical_default_registry(tmp_path):
    registry_path = tmp_path / "simulation-registry.json"
    store = SimulationRegistryStore(registry_path)
    service = DefaultDslService(store)

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(lambda _: service.ensure(), range(24)))

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    agents = payload["initial_population"]["population"]["agents"]
    assert all(status.intact for status in statuses)
    assert all(status.receipt == statuses[0].receipt for status in statuses)
    assert len(agents) == 1_000
    assert len({item["agent_id"] for item in agents}) == 1_000


def test_reset_preview_and_confirmation_restore_corrupt_and_deleted_sections(tmp_path):
    registry_path = tmp_path / "simulation-registry.json"
    store = SimulationRegistryStore(registry_path)
    application = _application(tmp_path, store)

    with TestClient(application) as client:
        receipt = client.get("/simulation/default-dsl").json()["receipt"]

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    person = next(
        item for item in payload["agent_types"]["types"] if item["id"] == "person"
    )
    person["name"] = ""
    payload.pop("interaction_trees")
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(_application(tmp_path, SimulationRegistryStore(registry_path))) as client:
        preview = client.post("/simulation/default-dsl/reset/preview")
        rejected = client.post(
            "/simulation/default-dsl/reset",
            json={"user_confirmed": True, "expected_hash": "sha256:stale"},
        )
        restored = client.post(
            "/simulation/default-dsl/reset",
            json={"user_confirmed": True, "expected_hash": receipt["hash"]},
        )
        agent_types = client.get("/simulation/agent-types")
        interactions = client.get("/simulation/interaction-trees")

    sections = {item["name"]: item for item in preview.json()["sections"]}
    assert preview.status_code == 200
    assert preview.json()["changed"] is True
    assert preview.json()["receipt"] == receipt
    assert sections["agent_types"]["disposition"] == "replace"
    assert "person" in sections["agent_types"]["restored_ids"]
    assert "person" in sections["agent_types"]["replaced_ids"]
    assert sections["interaction_trees"]["disposition"] == "restore"
    assert rejected.status_code == 409
    assert restored.status_code == 200
    assert restored.json()["intact"] is True
    assert restored.json()["receipt"] == receipt
    assert next(
        item
        for item in agent_types.json()["resolved"]["types"]
        if item["id"] == "person"
    )["name"] == "Person"
    assert interactions.json()


def test_reset_preview_lists_replaced_user_ids_and_preserves_unmanaged_sections(tmp_path):
    registry_path = tmp_path / "simulation-registry.json"
    store = SimulationRegistryStore(registry_path)

    with TestClient(_application(tmp_path, store)) as client:
        receipt = client.get("/simulation/default-dsl").json()["receipt"]

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["agent_types"]["types"].append(
        {
            "id": "custom_person",
            "name": "Custom person",
            "description": "User registry edit",
            "parent_ids": ["person"],
            "traits": [],
            "routines": [],
            "decisions": [],
            "overrides": [],
        }
    )
    payload["unmanaged_fixture"] = {"preserved": True}
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(_application(tmp_path, SimulationRegistryStore(registry_path))) as client:
        preview = client.post("/simulation/default-dsl/reset/preview").json()
        result = client.post(
            "/simulation/default-dsl/reset",
            json={"user_confirmed": True, "expected_hash": receipt["hash"]},
        )

    agent_types = next(
        item for item in preview["sections"] if item["name"] == "agent_types"
    )
    persisted = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "custom_person" in agent_types["replaced_ids"]
    assert result.status_code == 200
    assert persisted["unmanaged_fixture"] == {"preserved": True}
    assert "custom_person" not in {
        item["id"] for item in persisted["agent_types"]["types"]
    }
