import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from petraterrium.simulation.finance_initialization import (
    FinanceInitializationProgram,
    default_canada_finance_initialization_program,
    deterministic_weighted_index,
    evaluate_finance_initialization,
    resolve_categorical_alias,
    select_numeric_bucket,
)

INCOME_ARCHIVE = "statscan_98100407_fra.zip"
WEALTH_ARCHIVE = "statscan_11100016_fra.zip"
SPENDING_ARCHIVE = "statscan_11100223_fra.zip"
SOURCE_DIGESTS = {
    INCOME_ARCHIVE: "sha256:8aa74b6f770add9aa5499d4e685b0ae8f76c0d78ab8f391f93d505da70c946b2",
    WEALTH_ARCHIVE: "sha256:7e98cf68cb27d92ed107f3dfe2f5fcaef315d21fbfde76f7dcd7af9e92d9c499",
    SPENDING_ARCHIVE: "sha256:3cc1e9dff645ef313b1090df8cb04c9345750478e6c969ca721fb5331925a71f",
}
ORIGINAL_TITLES = (
    "Tranches de revenu d’emploi, selon le plus haut niveau de scolarité : "
    "Canada, provinces et territoires",
    "Actifs et dettes détenus selon le type de famille économique, par groupe d’âge, "
    "Canada, provinces et certaines régions métropolitaines de recensement, enquête "
    "sur la sécurité financière",
    "Dépenses des ménages selon le quintile de revenu du ménage, Canada, régions "
    "et provinces",
)
SEARCH_SOURCE = (
    "Recherche Web en français puis téléchargement officiel de Statistique Canada"
)
INCOME_COLUMNS = (
    ("Sans revenu d'emploi[2]", 0.0, 0.0),
    ("Moins de 5 000 $ (comprend les pertes)[4]", 0.0, 5_000.0),
    ("5 000 $ à 9 999 $[5]", 5_000.0, 10_000.0),
    ("10 000 $ à 19 999 $[6]", 10_000.0, 20_000.0),
    ("20 000 $ à 29 999 $[7]", 20_000.0, 30_000.0),
    ("30 000 $ à 39 999 $[8]", 30_000.0, 40_000.0),
    ("40 000 $ à 49 999 $[9]", 40_000.0, 50_000.0),
    ("50 000 $ à 59 999 $[10]", 50_000.0, 60_000.0),
    ("60 000 $ à 69 999 $[11]", 60_000.0, 70_000.0),
    ("70 000 $ à 79 999 $[12]", 70_000.0, 80_000.0),
    ("80 000 $ à 89 999 $[13]", 80_000.0, 90_000.0),
    ("90 000 $ à 99 999 $[14]", 90_000.0, 100_000.0),
    ("100 000 $ et plus[15]", 100_000.0, None),
)
WEALTH_ASSETS = (
    "Dépôts dans des institutions financières",
    "Actifs financiers hors pension",
    "Dette totale",
)
WEALTH_FAMILY = "Familles économiques et personnes hors famille économique"
WEALTH_HOLDING = "Pourcentage détenant l'actif ou la dette"
WEALTH_MEDIAN = "Valeur médiane pour ceux détenant l'actif ou la dette"
SPENDING_CATEGORY = "Dépenses totales"
SPENDING_STATISTIC = "Dépense moyenne par ménage"


@dataclass(frozen=True)
class CanadaFinanceProfile:
    agent_id: str
    age: int
    sex: str
    years_of_education: int
    specialization: str | None
    occupation: str


@dataclass(frozen=True)
class FinanceBand:
    label: str
    minimum: float
    maximum: float | None
    count: float


@dataclass(frozen=True)
class WealthCell:
    holding_percent: float
    median: float


@dataclass(frozen=True)
class CanadaFinanceDataset:
    source_digests: dict[str, str]
    income_bands: dict[tuple[str, str, str], tuple[FinanceBand, ...]]
    wealth: dict[tuple[str, str], WealthCell]
    spending: dict[str, float]


@dataclass(frozen=True)
class SampledCanadaFinances:
    values: dict[str, float]
    status: str
    distribution_id: str
    income_cell_id: str
    cell_id: str
    original_titles: tuple[str, str, str]
    language: str
    search_source: str
    source: str
    source_version: str
    source_date: str
    source_place: str
    source_population: str
    uncertainty: float


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _archive_rows(path: Path, member: str):
    with zipfile.ZipFile(path) as archive, archive.open(member) as binary:
        text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text, delimiter=";")


def _income_column(row: dict[str, str], suffix: str) -> float | None:
    key = next((name for name in row if name.endswith(suffix)), None)
    return _float(row.get(key, "")) if key else None


def _load_income(path: Path) -> dict[tuple[str, str, str], tuple[FinanceBand, ...]]:
    result: dict[tuple[str, str, str], tuple[FinanceBand, ...]] = {}
    for row in _archive_rows(path, "98100407.csv"):
        if row["GÉO"] != "Canada" or row["Statistiques (2A)"] != "Nombre":
            continue
        age = row["Âge (15A)"]
        education = row["Plus haut certificat, diplôme ou grade (16)"]
        sex = row["Genre (3)"]
        if age == "Total - Âge" or education.startswith("Total -"):
            continue
        bands = []
        for suffix, minimum, maximum in INCOME_COLUMNS:
            count = _income_column(row, suffix)
            if count is not None and count > 0:
                bands.append(FinanceBand(suffix, minimum, maximum, count))
        if bands:
            result[(sex, age, education)] = tuple(bands)
    return result


def _load_wealth(path: Path) -> dict[tuple[str, str], WealthCell]:
    raw: dict[tuple[str, str], dict[str, float]] = {}
    for row in _archive_rows(path, "11100016.csv"):
        if (
            row["PÉRIODE DE RÉFÉRENCE"] != "2023"
            or row["GÉO"] != "Canada"
            or row["Type de famille économique"] != WEALTH_FAMILY
            or row["Intervalles de confiance"] != "Estimation"
            or row["Actifs et dettes"] not in WEALTH_ASSETS
        ):
            continue
        statistic = row["Statistiques"]
        if statistic not in {WEALTH_HOLDING, WEALTH_MEDIAN}:
            continue
        value = _float(row["VALEUR"])
        if value is not None:
            raw.setdefault((row["Groupe d'âge"], row["Actifs et dettes"]), {})[
                statistic
            ] = value
    return {
        key: WealthCell(
            holding_percent=values[WEALTH_HOLDING],
            median=values[WEALTH_MEDIAN],
        )
        for key, values in raw.items()
        if WEALTH_HOLDING in values and WEALTH_MEDIAN in values
    }


def _load_spending(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in _archive_rows(path, "11100223.csv"):
        if (
            row["PÉRIODE DE RÉFÉRENCE"] == "2023"
            and row["GÉO"] == "Canada"
            and row["Statistique"] == SPENDING_STATISTIC
            and row["Dépenses des ménages, catégories de niveau sommaire"]
            == SPENDING_CATEGORY
        ):
            value = _float(row["VALEUR"])
            if value is not None:
                result[row["Quintile de revenu du ménage avant impôt"]] = value
    return result


@lru_cache(maxsize=4)
def _load_canada_finance_dataset(source_dir: str) -> CanadaFinanceDataset:
    directory = Path(source_dir)
    actual_digests = {
        name: _digest(directory / name)
        for name in (INCOME_ARCHIVE, WEALTH_ARCHIVE, SPENDING_ARCHIVE)
    }
    for name, expected in SOURCE_DIGESTS.items():
        if actual_digests[name] != expected:
            raise ValueError(
                f"Official finance source digest mismatch for {name}: "
                f"expected {expected}, found {actual_digests[name]}"
            )
    dataset = CanadaFinanceDataset(
        source_digests=actual_digests,
        income_bands=_load_income(directory / INCOME_ARCHIVE),
        wealth=_load_wealth(directory / WEALTH_ARCHIVE),
        spending=_load_spending(directory / SPENDING_ARCHIVE),
    )
    if not dataset.income_bands or not dataset.wealth or len(dataset.spending) < 5:
        raise ValueError("Official Canada finance sources did not contain required cells")
    return dataset


def load_canada_finance_dataset(source_dir: Path) -> CanadaFinanceDataset:
    return _load_canada_finance_dataset(str(source_dir.resolve()))


def _select_band(
    bands: tuple[FinanceBand, ...], profile: CanadaFinanceProfile, seed: int
) -> FinanceBand:
    index = deterministic_weighted_index(
        tuple(band.count for band in bands),
        seed,
        profile.agent_id,
        (
            profile.specialization or "none",
            profile.occupation,
            "income-band",
        ),
    )
    return bands[index]


def sample_canada_finances(
    profile: CanadaFinanceProfile,
    dataset: CanadaFinanceDataset,
    seed: int,
    program: FinanceInitializationProgram | None = None,
) -> SampledCanadaFinances:
    active_program = program or default_canada_finance_initialization_program()
    sex = resolve_categorical_alias(active_program, "sex", profile.sex)
    income_age = select_numeric_bucket(active_program, "income_age", profile.age)
    education = select_numeric_bucket(
        active_program, "education", profile.years_of_education
    )
    income_key = (sex, income_age, education)
    bands = dataset.income_bands.get(income_key)
    if not bands:
        fallback_key = (
            str(active_program.constants["income_sex_fallback"]),
            income_age,
            education,
        )
        bands = dataset.income_bands.get(fallback_key)
    if not bands:
        raise ValueError(f"No official income cell found for {income_key}")
    band = _select_band(bands, profile, seed)
    band_maximum = (
        band.maximum
        if band.maximum is not None
        else float(active_program.constants["open_income_band_maximum"])
    )
    wealth_age = select_numeric_bucket(active_program, "wealth_age", profile.age)
    deposit_cell = dataset.wealth[
        (wealth_age, "Dépôts dans des institutions financières")
    ]
    financial_assets_cell = dataset.wealth[
        (wealth_age, "Actifs financiers hors pension")
    ]
    debt_cell = dataset.wealth[(wealth_age, "Dette totale")]
    base_context = {
        "income_band_minimum": band.minimum,
        "income_band_maximum": band_maximum,
        "deposits_holding_percent": deposit_cell.holding_percent,
        "deposits_median": deposit_cell.median,
        "financial_assets_holding_percent": financial_assets_cell.holding_percent,
        "financial_assets_median": financial_assets_cell.median,
        "debt_holding_percent": debt_cell.holding_percent,
        "debt_median": debt_cell.median,
    }
    income_result = evaluate_finance_initialization(
        active_program,
        base_context,
        seed,
        profile.agent_id,
        output_ids=("income",),
    )
    income = float(income_result.values["income"])
    quintile = select_numeric_bucket(active_program, "spending_quintile", income)
    result = evaluate_finance_initialization(
        active_program,
        {**base_context, "annual_expenses": dataset.spending[quintile]},
        seed,
        profile.agent_id,
    )
    income_cell_id = "|".join((sex, income_age, education, band.label))
    cell_id = "|".join((income_cell_id, wealth_age, quintile))
    return SampledCanadaFinances(
        values={
            component: float(result.values[component])
            for component in ("money", "income", "expenses", "savings", "debt")
        },
        status="imputed",
        distribution_id="statscan-canada-finance-2021-2023-v1",
        income_cell_id=income_cell_id,
        cell_id=cell_id,
        original_titles=ORIGINAL_TITLES,
        language="fr",
        search_source=SEARCH_SOURCE,
        source="Statistique Canada tables 98-10-0407-01, 11-10-0016-01, and 11-10-0223-01",
        source_version="98-10-0407-01:2021|11-10-0016-01:2023|11-10-0223-01:2023",
        source_date="2026-09-18",
        source_place="Canada",
        source_population=(
            "Canada Census 2021 residents aged 15+ and 2023 Canadian households or families"
        ),
        uncertainty=float(active_program.constants["profile_uncertainty"]),
    )
