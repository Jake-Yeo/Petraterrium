import json
from pathlib import Path

from petraterrium.simulation.agent_state import finance_state_from_values
from petraterrium.simulation.default_finance import (
    CanadaFinanceProfile,
    load_canada_finance_dataset,
    sample_canada_finances,
)

ROOT = Path(__file__).resolve().parents[1]


def test_official_canada_finance_dumps_drive_reproducible_profile_specific_values():
    dataset = load_canada_finance_dataset(ROOT / "data" / "sources")
    experienced = sample_canada_finances(
        CanadaFinanceProfile(
            agent_id="74cd98e7861c2be1e5b1",
            age=40,
            sex="female",
            years_of_education=16,
            specialization="engineering",
            occupation="worker",
        ),
        dataset,
        seed=1,
    )
    student = sample_canada_finances(
        CanadaFinanceProfile(
            agent_id="eb196847aeae31770e80",
            age=20,
            sex="male",
            years_of_education=12,
            specialization=None,
            occupation="student",
        ),
        dataset,
        seed=1,
    )

    assert dataset.source_digests == {
        "statscan_98100407_fra.zip": (
            "sha256:8aa74b6f770add9aa5499d4e685b0ae8f76c0d78ab8f391f93d505da70c946b2"
        ),
        "statscan_11100016_fra.zip": (
            "sha256:7e98cf68cb27d92ed107f3dfe2f5fcaef315d21fbfde76f7dcd7af9e92d9c499"
        ),
        "statscan_11100223_fra.zip": (
            "sha256:3cc1e9dff645ef313b1090df8cb04c9345750478e6c969ca721fb5331925a71f"
        ),
    }
    assert experienced.status == student.status == "imputed"
    assert experienced.income_cell_id != student.income_cell_id
    assert experienced.values != student.values
    assert experienced.original_titles == (
        "Tranches de revenu d’emploi, selon le plus haut niveau de scolarité : "
        "Canada, provinces et territoires",
        "Actifs et dettes détenus selon le type de famille économique, par groupe d’âge, "
        "Canada, provinces et certaines régions métropolitaines de recensement, enquête "
        "sur la sécurité financière",
        "Dépenses des ménages selon le quintile de revenu du ménage, Canada, régions "
        "et provinces",
    )
    assert experienced.language == "fr"
    assert experienced.search_source == (
        "Recherche Web en français puis téléchargement officiel de Statistique Canada"
    )
    assert all(value >= 0 for value in experienced.values.values())
    assert all(value >= 0 for value in student.values.values())


def test_shipped_agents_match_the_imported_finance_sampler():
    manifest_path = (
        ROOT / "petraterrium" / "simulation" / "defaults" / "base-v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest["content"]["initial_population"]["population"]["agents"]
    dataset = load_canada_finance_dataset(ROOT / "data" / "sources")

    canada_agents = [agent for agent in agents if agent["traits"]["country_id"] == "CA"]

    for agent in canada_agents[:2]:
        traits = agent["traits"]
        sampled = sample_canada_finances(
            CanadaFinanceProfile(
                agent_id=agent["agent_id"],
                age=traits["age"],
                sex=traits["sex"],
                years_of_education=traits["years_of_education"],
                specialization=None,
                occupation=traits["occupation"],
            ),
            dataset,
            seed=1,
        )

        assert {
            key: float(agent["states"][f"finance.{key}"])
            for key in ("money", "savings", "debt")
        } == {
            key: sampled.values[key] for key in ("money", "savings", "debt")
        }
        assert float(agent["states"]["finance.income"]) == 0
        assert float(agent["states"]["finance.expenses"]) == 0
        assert float(agent["states"]["finance.annual_income"]) == sampled.values["income"]
        assert float(agent["states"]["finance.annual_expenses"]) == sampled.values["expenses"]
        assert traits["finance_distribution_id"] == sampled.distribution_id
        assert traits["finance_cell_id"] == sampled.cell_id
        assert traits["finance_status"] == "imputed"


def test_shipped_finance_provenance_keeps_original_language_discovery_context():
    manifest_path = (
        ROOT / "petraterrium" / "simulation" / "defaults" / "base-v1.json"
    )
    agents = json.loads(manifest_path.read_text(encoding="utf-8"))["content"][
        "initial_population"
    ]["population"]["agents"]
    agent = next(item for item in agents if item["traits"]["country_id"] == "CA")

    finance = finance_state_from_values(agent["place"], agent["traits"], agent["states"])

    assert finance.evidence.language == "fr"
    assert "Tranches de revenu d’emploi" in finance.evidence.original_title
    assert finance.evidence.search_source == (
        "Recherche Web en français puis téléchargement officiel de Statistique Canada"
    )
    assert finance.evidence.url.startswith("https://www150.statcan.gc.ca/")
