import csv
import io
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from zipfile import ZipFile

import pyarrow.parquet as pq
import pycountry

from ...dsl import Evidence, FeatureDistribution
from ..features import canonical_feature_registry
from ..regions import CANONICAL_REGIONS, country_region

PRIORITY_COUNTRY_CODES = ("IN", "CN", "US", "ID", "PK", "NG", "BR", "BD", "RU", "MX")
PACK_VERSION = "priority-features-v1"
PACK_SOURCES = (
    "World Bank World Development Indicators",
    "UN DESA Database on Household Size and Composition",
    "ILOSTAT",
    "World Values Survey",
    "Global Preferences Survey via Our World in Data",
    "OpenPsychometrics",
    "Schwartz cultural value orientations",
    "Petraterrium in-app specialization research pipeline",
)


@dataclass(frozen=True)
class Estimate:
    values: dict[str, float]
    mean: float | None
    standard_deviation: float | None
    source: str
    version: str
    source_date: str
    status: str
    uncertainty: float
    method: str
    sample_size: int | None = None


class Moments:
    def __init__(self):
        self.weight = 0.0
        self.total = 0.0
        self.squares = 0.0
        self.count = 0

    def add(self, value: float, weight: float = 1) -> None:
        if not math.isfinite(value) or not math.isfinite(weight) or weight <= 0:
            return
        self.weight += weight
        self.total += value * weight
        self.squares += value * value * weight
        self.count += 1

    def result(self) -> tuple[float, float]:
        if self.weight <= 0:
            raise ValueError("Weighted moments need at least one observation")
        mean = self.total / self.weight
        variance = max(0, self.squares / self.weight - mean * mean)
        return mean, variance**0.5


def normalize(values: dict[str, float]) -> dict[str, float]:
    positive = {key: max(0, float(value)) for key, value in values.items()}
    total = sum(positive.values())
    if total <= 0:
        raise ValueError("A feature distribution needs positive values")
    result = {key: value / total for key, value in sorted(positive.items())}
    last = next(reversed(result))
    result[last] += 1 - sum(result.values())
    return result


def alpha2(alpha3: str) -> str | None:
    country = pycountry.countries.get(alpha_3=alpha3.upper())
    return country.alpha_2 if country else None


def value(row: dict[str, str], key: str, low: float, high: float) -> float | None:
    try:
        parsed = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    if parsed < low or parsed > high:
        return None
    return (parsed - low) / (high - low)


def mean_available(values: list[float | None], minimum: int = 1) -> float | None:
    present = [item for item in values if item is not None]
    return sum(present) / len(present) if len(present) >= minimum else None


def source_path(data_directory: Path, filename: str) -> Path:
    path = data_directory / "sources" / filename
    if not path.exists():
        raise FileNotFoundError(f"Required registry source is missing: {path}")
    return path


def load_wdi_estimates(data_directory: Path) -> dict[str, dict[str, Estimate]]:
    output: dict[str, dict[str, Estimate]] = defaultdict(dict)
    dump = data_directory / "city_feature_dump"
    canonical = pq.read_table(dump / "canonical_country_marginals.parquet").to_pylist()
    for row in canonical:
        if row["field"] != "education":
            continue
        broad = json.loads(row["value_json"])
        mapped = {
            "0": broad.get("below_primary", 0),
            "1": broad.get("primary", 0),
            "2": broad.get("lower_secondary", 0),
            "3": broad.get("upper_secondary", 0),
            "4": broad.get("postsecondary_below_bachelor", 0),
            "5": 0,
            "6": broad.get("bachelor_or_higher", 0),
            "7": 0,
            "8": 0,
            "unknown": 0,
        }
        output["education_isced"][row["country_code"]] = Estimate(
            values=normalize(mapped),
            mean=None,
            standard_deviation=None,
            source=row["source"],
            version=row["version"],
            source_date=f"{row['year']}-12-31",
            status="present",
            uncertainty=0.28,
            method="compositional",
        )
    latest = pq.read_table(dump / "wdi_country_latest.parquet").to_pylist()
    indexed = {(row["country_code"], row["feature_id"]): row for row in latest}
    countries = {row["country_code"] for row in latest}
    for code in countries:
        income = indexed.get((code, "NY.GNP.PCAP.PP.CD"))
        gini = indexed.get((code, "SI.POV.GINI"))
        if not income or not gini or income["value"] <= 0:
            continue
        sigma = math.sqrt(2) * NormalDist().inv_cdf((gini["value"] / 100 + 1) / 2)
        standard_deviation = income["value"] * math.sqrt(math.exp(sigma * sigma) - 1)
        year = min(income["year"], gini["year"])
        output["income"][code] = Estimate(
            values={},
            mean=income["value"],
            standard_deviation=standard_deviation,
            source="World Bank WDI GNI per capita, PPP and Gini",
            version="WDI release 2026-10-08; lognormal transform v1",
            source_date=f"{year}-12-31",
            status="literature_estimate",
            uncertainty=0.55,
            method="compositional",
        )
    return output


def load_household_estimates(data_directory: Path) -> dict[str, Estimate]:
    rows = pq.read_table(
        data_directory / "city_feature_dump" / "un_household_country_latest.parquet"
    ).to_pylist()
    wanted = {
        "un_household.1_member": 1,
        "un_household.2_3_members": 2.5,
        "un_household.4_5_members": 4.5,
        "un_household.6_or_more_members": 7,
    }
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["feature_id"] in wanted:
            grouped[row["country_code"]].append(row)
    result = {}
    for code, country_rows in grouped.items():
        newest = max(row["year"] for row in country_rows)
        selected = [row for row in country_rows if row["year"] == newest]
        if len(selected) != 4:
            continue
        probabilities = normalize({row["feature_id"]: row["value"] for row in selected})
        mean = sum(wanted[key] * probability for key, probability in probabilities.items())
        variance = sum(
            probability * (wanted[key] - mean) ** 2 for key, probability in probabilities.items()
        )
        source_names = sorted({row["source_name"] for row in selected})
        result[code] = Estimate(
            values={},
            mean=mean,
            standard_deviation=variance**0.5,
            source="UN DESA household composition: " + "; ".join(source_names),
            version="UN DESA 2026; grouped-household transform v1",
            source_date=f"{newest}-12-31",
            status="present",
            uncertainty=0.24,
            method="compositional",
        )
    return result


def load_wvs_estimates(data_directory: Path) -> dict[str, dict[str, Estimate]]:
    features = (
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
        "generalized_trust",
        "religiosity",
    )
    moments: dict[str, dict[str, Moments]] = {
        feature: defaultdict(Moments) for feature in features
    }
    years: dict[str, list[int]] = defaultdict(list)
    path = source_path(data_directory, "wvs7.csv")
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            code = alpha2(row.get("B_COUNTRY_ALPHA", ""))
            if not code:
                continue
            try:
                weight = float(row.get("W_WEIGHT") or 1)
                years[code].append(int(row["A_YEAR"]))
            except (TypeError, ValueError):
                continue
            economic = mean_available(
                [
                    value(row, "Q106", 1, 10),
                    None
                    if value(row, "Q107", 1, 10) is None
                    else 1 - value(row, "Q107", 1, 10),
                    None
                    if value(row, "Q109", 1, 10) is None
                    else 1 - value(row, "Q109", 1, 10),
                ],
                2,
            )
            state = mean_available(
                [
                    value(row, "Q250", 1, 10),
                    value(row, "Q235", 1, 4),
                    value(row, "Q237", 1, 4),
                ],
                2,
            )
            cultural = mean_available(
                [
                    value(row, "Q182", 1, 10),
                    value(row, "Q184", 1, 10),
                    value(row, "Q185", 1, 10),
                    value(row, "Q29", 1, 4),
                    value(row, "Q30", 1, 4),
                    value(row, "Q169", 1, 4),
                ],
                3,
            )
            trust = value(row, "Q57", 1, 2)
            if trust is not None:
                trust = 1 - trust
            religion_importance = value(row, "Q6", 1, 4)
            religiosity = mean_available(
                [
                    None if religion_importance is None else 1 - religion_importance,
                    value(row, "Q164", 1, 10),
                ],
                1,
            )
            scores = {
                "ideology_economic": None if economic is None else economic * 2 - 1,
                "ideology_state": None if state is None else state * 2 - 1,
                "ideology_cultural": None if cultural is None else cultural * 2 - 1,
                "generalized_trust": trust,
                "religiosity": religiosity,
            }
            for feature, score in scores.items():
                if score is not None:
                    moments[feature][code].add(score, weight)
    result: dict[str, dict[str, Estimate]] = {feature: {} for feature in features}
    for feature, by_country in moments.items():
        for code, aggregate in by_country.items():
            mean, standard_deviation = aggregate.result()
            result[feature][code] = Estimate(
                values={},
                mean=mean,
                standard_deviation=standard_deviation,
                source="World Values Survey Wave 7",
                version="WVS 7 v6.0.0 (2024-04-30); weighted-axis transform v1",
                source_date=f"{max(years[code])}-12-31",
                status="present",
                uncertainty=0.2,
                method="measured",
                sample_size=aggregate.count,
            )
    return result


BIG_FIVE_ITEMS = {
    "extraversion": ([1, 3, 5, 7, 9], [2, 4, 6, 8, 10], "E"),
    "neuroticism": ([1, 3, 5, 6, 7, 8, 9, 10], [2, 4], "N"),
    "agreeableness": ([2, 4, 6, 8, 9, 10], [1, 3, 5, 7], "A"),
    "conscientiousness": ([1, 3, 5, 7, 9, 10], [2, 4, 6, 8], "C"),
    "openness": ([1, 3, 5, 7, 8, 9, 10], [2, 4, 6], "O"),
}


def big_five_score(row: dict[str, str], positive: list[int], reverse: list[int], prefix: str):
    try:
        scores = [float(row[f"{prefix}{index}"]) for index in positive]
        scores.extend(6 - float(row[f"{prefix}{index}"]) for index in reverse)
    except (KeyError, TypeError, ValueError):
        return None
    if any(score < 1 or score > 5 for score in scores):
        return None
    return (sum(scores) / len(scores) - 1) / 4


def load_big_five_estimates(data_directory: Path) -> dict[str, dict[str, Estimate]]:
    moments = {feature: defaultdict(Moments) for feature in BIG_FIVE_ITEMS}
    types: dict[str, Counter] = defaultdict(Counter)
    path = source_path(data_directory, "openpsychometrics_BIG5.zip")
    with ZipFile(path) as archive:
        with archive.open("BIG5/data.csv") as raw:
            source = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            for row in csv.DictReader(source, delimiter="\t"):
                code = row.get("country", "").upper()
                if len(code) != 2:
                    continue
                scores = {
                    feature: big_five_score(row, positive, reverse, prefix)
                    for feature, (positive, reverse, prefix) in BIG_FIVE_ITEMS.items()
                }
                if any(score is None for score in scores.values()):
                    continue
                for feature, score in scores.items():
                    moments[feature][code].add(score)
                personality_type = "".join(
                    [
                        "E" if scores["extraversion"] >= 0.5 else "I",
                        "N" if scores["openness"] >= 0.5 else "S",
                        "F" if scores["agreeableness"] >= 0.5 else "T",
                        "J" if scores["conscientiousness"] >= 0.5 else "P",
                    ]
                )
                types[code][personality_type] += 1
    result: dict[str, dict[str, Estimate]] = {feature: {} for feature in BIG_FIVE_ITEMS}
    result["mbti"] = {}
    for feature, countries in moments.items():
        for code, aggregate in countries.items():
            mean, standard_deviation = aggregate.result()
            result[feature][code] = Estimate(
                values={},
                mean=mean,
                standard_deviation=standard_deviation,
                source="OpenPsychometrics Big Five 50-item public responses",
                version="OpenPsychometrics BIG5 2014; IPIP scoring v1",
                source_date="2012-12-31",
                status="literature_estimate",
                uncertainty=0.82,
                method="measured",
                sample_size=aggregate.count,
            )
    for code, counts in types.items():
        result["mbti"][code] = Estimate(
            values=normalize(counts),
            mean=None,
            standard_deviation=None,
            source="Exploratory Big Five threshold proxy; not measured MBTI",
            version="OpenPsychometrics BIG5 2014; MBTI-label proxy v1",
            source_date="2012-12-31",
            status="imputed",
            uncertainty=1,
            method="compositional",
            sample_size=sum(counts.values()),
        )
    return result


def load_gps_estimates(data_directory: Path) -> dict[str, dict[str, Estimate]]:
    files = {
        "risk_aversion": (
            "gps_risk.csv",
            "Risk taking (Falk et al. (2018) GPS)",
            True,
        ),
        "time_preference": (
            "gps_patience.csv",
            "Patience (time preference) (Falk et al. (2018) GPS)",
            False,
        ),
    }
    result = {feature: {} for feature in files}
    for feature, (filename, column, invert) in files.items():
        with source_path(data_directory, filename).open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                code = alpha2(row["Code"])
                if not code:
                    continue
                score = NormalDist().cdf(float(row[column]))
                if invert:
                    score = 1 - score
                result[feature][code] = Estimate(
                    values={},
                    mean=score,
                    standard_deviation=0.2,
                    source="Global Preferences Survey via Our World in Data",
                    version="Falk et al. 2018 GPS; normal-CDF transform v1",
                    source_date=f"{row['Year']}-12-31",
                    status="present",
                    uncertainty=0.3,
                    method="measured",
                )
    return result


def load_occupation_estimates(data_directory: Path) -> dict[str, Estimate]:
    candidates: dict[tuple[str, int, str], dict[str, float]] = defaultdict(dict)
    path = source_path(data_directory, "ilostat_employment_sex_occupation.csv.gz")
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["sex"] != "SEX_T" or not row["classif1"].startswith("OCU_ISCO"):
                continue
            suffix = row["classif1"].rsplit("_", 1)[-1]
            if suffix not in set("0123456789"):
                continue
            code = alpha2(row["ref_area"])
            if not code:
                continue
            standard = "ISCO-08" if "ISCO08" in row["classif1"] else "ISCO-88"
            try:
                candidates[(code, int(row["time"]), standard)][suffix] = float(row["obs_value"])
            except ValueError:
                continue
    result = {}
    countries = {key[0] for key in candidates}
    for code in countries:
        options = [key for key, values in candidates.items() if key[0] == code and len(values) >= 9]
        if not options:
            continue
        selected = max(options, key=lambda key: (key[2] == "ISCO-08", key[1]))
        year, standard = selected[1], selected[2]
        values = {str(index): candidates[selected].get(str(index), 0) for index in range(10)}
        values["unknown"] = 0
        harmonized = standard != "ISCO-08"
        result[code] = Estimate(
            values=normalize(values),
            mean=None,
            standard_deviation=None,
            source=f"ILOSTAT employment by occupation ({standard})",
            version=f"ILOSTAT bulk 2026-10-26; {standard} major-group transform v1",
            source_date=f"{year}-12-31",
            status="imputed" if harmonized else "present",
            uncertainty=0.45 if harmonized else 0.18,
            method="compositional" if harmonized else "measured",
        )
    return result


SCHWARTZ_ORIENTATIONS = {
    "CN": (3.78, 3.74, 3.49, 4.41, 3.30, 4.18, 4.23),
    "IN": (3.92, 3.97, 3.05, 4.28, 3.48, 4.02, 4.45),
    "ID": (3.82, 4.27, 2.56, 3.84, 3.41, 3.94, 4.32),
    "PK": (3.99, 4.31, 2.44, 4.00, 3.11, 3.76, 4.65),
    "NG": (3.75, 4.41, 2.72, 3.90, 2.54, 3.66, 4.79),
    "BR": (4.03, 3.62, 2.37, 3.93, 3.52, 4.27, 4.89),
    "RU": (3.90, 3.81, 2.72, 3.96, 3.51, 4.30, 4.38),
    "MX": (4.50, 3.90, 2.13, 3.90, 2.83, 4.36, 4.73),
    "US": (3.46, 3.67, 2.37, 4.09, 3.87, 4.19, 4.68),
    "AU": (3.99, 3.59, 2.29, 3.97, 3.86, 4.35, 4.79),
}


def load_schwartz_estimates() -> dict[str, Estimate]:
    result = {}
    for code, scores in SCHWARTZ_ORIENTATIONS.items():
        harmony, embeddedness, hierarchy, mastery, affective, intellectual, egalitarian = scores
        result[code] = Estimate(
            values=normalize(
                {
                    "self_direction": intellectual,
                    "stimulation": affective,
                    "hedonism": affective,
                    "achievement": mastery,
                    "power": hierarchy,
                    "security": embeddedness,
                    "conformity": embeddedness,
                    "tradition": embeddedness,
                    "benevolence": egalitarian,
                    "universalism": (harmony + egalitarian) / 2,
                }
            ),
            mean=None,
            standard_deviation=None,
            source="Schwartz 2008 culture-level value orientation means",
            version="Schwartz 2008 Table 5; basic-values crosswalk v1",
            source_date="2008-01-01",
            status="literature_estimate",
            uncertainty=0.78,
            method="compositional",
        )
    return result


def load_specialization_estimates(data_directory: Path) -> dict[str, Estimate]:
    pipeline_directory = data_directory / "sources" / "specialization" / "pipeline"
    if not pipeline_directory.exists():
        raise FileNotFoundError(
            f"Required specialization pipeline receipts are missing: {pipeline_directory}"
        )
    specialization = next(
        feature
        for feature in canonical_feature_registry().definitions
        if feature.id == "specialization"
    )
    expected_values = set(specialization.canonical_values)
    estimates = {}
    for receipt_path in sorted(pipeline_directory.glob("*.json")):
        receipt = json.loads(receipt_path.read_text())
        target = receipt.get("target", {})
        if target.get("level") != "country" or target.get("feature_id") != "specialization":
            continue
        if receipt.get("status") not in {"ready", "promoted"}:
            continue
        result_kind = receipt.get("result_kind")
        if result_kind not in {"measured", "estimated"}:
            continue
        country_code = str(target.get("country_code") or target.get("place_id", "")).upper()
        mapped_distribution = receipt.get("mapped_distribution")
        if not country_code or not isinstance(mapped_distribution, dict):
            raise ValueError(f"Invalid specialization pipeline receipt: {receipt_path}")
        if set(mapped_distribution) != expected_values:
            raise ValueError(
                f"Specialization receipt {receipt_path.name} has non-canonical values"
            )
        values = {
            str(label): float(percentage) / 100
            for label, percentage in sorted(mapped_distribution.items())
        }
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in values.values()):
            raise ValueError(
                f"Specialization receipt {receipt_path.name} has invalid probabilities"
            )
        if not math.isclose(sum(values.values()), 1, abs_tol=1e-9):
            raise ValueError(
                f"Specialization receipt {receipt_path.name} does not sum to one"
            )
        selected_source_ids = set(receipt.get("selected_source_ids") or ())
        selected_sources = [
            source
            for source in receipt.get("sources", ())
            if source.get("candidate_id") in selected_source_ids
        ]
        if not selected_sources:
            raise ValueError(
                f"Specialization receipt {receipt_path.name} has no selected source"
            )
        source_titles = sorted(
            {str(source["title"]) for source in selected_sources if source.get("title")}
        )
        source_versions = sorted(
            {
                str(source["source_version"])
                for source in selected_sources
                if source.get("source_version")
            }
        )
        licences = sorted(
            {
                str(source["license"])
                for source in selected_sources
                if source.get("license")
            }
        )
        source_dates = [
            str(source.get("observation_date") or source.get("published_date"))
            for source in selected_sources
            if source.get("observation_date") or source.get("published_date")
        ]
        source_date = max(source_dates) if source_dates else str(receipt["updated_at"])[:10]
        mapping_version = str(receipt.get("mapping_preview", {}).get("version") or "pending")
        version_parts = [
            *(source_versions or [f"pipeline-attempt-{receipt['attempt_id']}"]),
            f"mapping {mapping_version}",
            f"pipeline attempt {receipt['attempt_id']}",
            *(f"licence {licence}" for licence in licences),
        ]
        sample_size = next(
            (
                int(source.get("sample_size") or source.get("population"))
                for source in selected_sources
                if source.get("sample_size") or source.get("population")
            ),
            None,
        )
        if result_kind == "estimated":
            intervals = (receipt.get("estimate_trace") or {}).get(
                "confidence_intervals", {}
            )
            interval_widths = [
                float(interval["upper"]) - float(interval["lower"])
                for interval in intervals.values()
                if isinstance(interval, dict)
                and "lower" in interval
                and "upper" in interval
            ]
            uncertainty = min(1, max([0.3, *(width / 100 for width in interval_widths)]))
        else:
            uncertainty = 0.05 if receipt.get("mapping_confirmed") else 0.3
        estimates[country_code] = Estimate(
            values=values,
            mean=None,
            standard_deviation=None,
            source="; ".join(source_titles),
            version="; ".join(version_parts),
            source_date=source_date,
            status="present" if result_kind == "measured" else "literature_estimate",
            uncertainty=uncertainty,
            method="measured" if result_kind == "measured" else "compositional",
            sample_size=sample_size,
        )
    return estimates


def merge_estimates(*groups: dict[str, dict[str, Estimate]]) -> dict[str, dict[str, Estimate]]:
    result: dict[str, dict[str, Estimate]] = defaultdict(dict)
    for group in groups:
        for feature, estimates in group.items():
            result[feature].update(estimates)
    return dict(result)


def aggregate_estimates(
    estimates: list[tuple[Estimate, int]],
    population_count: int,
) -> Estimate:
    covered_population = sum(population for _, population in estimates)
    source_dates = [estimate.source_date for estimate, _ in estimates]
    sources = sorted({estimate.source for estimate, _ in estimates})
    uncertainties = [estimate.uncertainty for estimate, _ in estimates]
    if estimates[0][0].values:
        keys = sorted({key for estimate, _ in estimates for key in estimate.values})
        values = normalize(
            {
                key: sum(
                    estimate.values.get(key, 0) * population
                    for estimate, population in estimates
                )
                / covered_population
                for key in keys
            }
        )
        mean = None
        standard_deviation = None
    else:
        mean = (
            sum(estimate.mean * population for estimate, population in estimates)
            / covered_population
        )
        variance = sum(
            population
            * (estimate.standard_deviation**2 + (estimate.mean - mean) ** 2)
            for estimate, population in estimates
        ) / covered_population
        values = {}
        standard_deviation = variance**0.5
    return Estimate(
        values=values,
        mean=mean,
        standard_deviation=standard_deviation,
        source="Population-weighted aggregate: " + "; ".join(sources),
        version=PACK_VERSION,
        source_date=max(source_dates),
        status="imputed",
        uncertainty=min(1, sum(uncertainties) / len(uncertainties) + 0.1),
        method="compositional",
        sample_size=covered_population if population_count else None,
    )


def distribution(
    feature_id: str,
    level: str,
    place: str,
    estimate: Estimate,
    population_count: int,
    coverage_percent: float,
) -> FeatureDistribution:
    sample = f"; source n={estimate.sample_size:,}" if estimate.sample_size else ""
    return FeatureDistribution(
        feature_id=feature_id,
        level=level,
        place=place,
        population=f"{place} residents{sample}",
        population_count=population_count,
        coverage_percent=max(0, min(100, coverage_percent)),
        values=estimate.values,
        mean=estimate.mean,
        standard_deviation=estimate.standard_deviation,
        provenance=Evidence(
            source=estimate.source,
            version=estimate.version,
            status=estimate.status,
            uncertainty=estimate.uncertainty,
            source_date=estimate.source_date,
        ),
        method=estimate.method,
    )


def build_priority_feature_distributions(
    data_directory: Path,
    country_population_rows: list[dict],
    region_population_rows: list[dict],
    fallback_region_populations: dict[str, int] | None = None,
) -> tuple[list[FeatureDistribution], dict]:
    country_populations = {
        row["country_code"]: int(row["population"]) for row in country_population_rows
    }
    region_populations = {row["region"]: int(row["population"]) for row in region_population_rows}
    for region, population in (fallback_region_populations or {}).items():
        region_populations.setdefault(region, population)
    wdi = load_wdi_estimates(data_directory)
    estimates = merge_estimates(
        wdi,
        {"household_size": load_household_estimates(data_directory)},
        load_wvs_estimates(data_directory),
        load_big_five_estimates(data_directory),
        load_gps_estimates(data_directory),
        {"occupation_isco": load_occupation_estimates(data_directory)},
        {"schwartz_values": load_schwartz_estimates()},
        {"specialization": load_specialization_estimates(data_directory)},
    )
    expected_features = {
        feature.id for feature in canonical_feature_registry().definitions
    } - {"age", "sex"}
    missing_builders = expected_features - set(estimates)
    if missing_builders:
        raise ValueError(f"No priority source builder for {sorted(missing_builders)}")
    output = []
    region_estimates: dict[str, dict[str, Estimate]] = defaultdict(dict)
    region_coverage: dict[str, dict[str, float]] = defaultdict(dict)
    for feature in sorted(expected_features):
        country_estimates = estimates[feature]
        global_inputs = [
            (estimate, country_populations[code])
            for code, estimate in country_estimates.items()
            if country_populations.get(code, 0) > 0
        ]
        if not global_inputs:
            raise ValueError(f"No population-weighted estimates for {feature}")
        global_estimate = aggregate_estimates(global_inputs, sum(country_populations.values()))
        for region in CANONICAL_REGIONS:
            population_count = region_populations.get(region, 0)
            inputs = [
                (estimate, country_populations[code])
                for code, estimate in country_estimates.items()
                if country_populations.get(code, 0) > 0 and country_region(code) == region
            ]
            if inputs:
                estimate = aggregate_estimates(inputs, population_count)
                coverage = (
                    sum(population for _, population in inputs) * 100 / population_count
                    if population_count
                    else 0
                )
            else:
                estimate = Estimate(
                    **{
                        **global_estimate.__dict__,
                        "source": f"Global fallback: {global_estimate.source}",
                        "status": "imputed",
                        "uncertainty": 1,
                        "method": "fallback",
                    }
                )
                coverage = 0
            region_estimates[feature][region] = estimate
            region_coverage[feature][region] = coverage
            output.append(
                distribution(feature, "region", region, estimate, population_count, coverage)
            )
        for code in PRIORITY_COUNTRY_CODES:
            population_count = country_populations[code]
            estimate = country_estimates.get(code)
            coverage = 100.0
            if estimate is None:
                region = country_region(code)
                inherited = region_estimates[feature][region]
                estimate = Estimate(
                    **{
                        **inherited.__dict__,
                        "source": f"Regional fallback for {code}: {inherited.source}",
                        "status": "imputed",
                        "uncertainty": min(1, inherited.uncertainty + 0.1),
                        "method": "fallback",
                    }
                )
                coverage = region_coverage[feature][region]
            output.append(
                distribution(feature, "country", code, estimate, population_count, coverage)
            )
    output.sort(key=lambda item: (item.feature_id, item.level, item.place))
    metadata = {
        "version": PACK_VERSION,
        "priority_countries": list(PRIORITY_COUNTRY_CODES),
        "canonical_regions": list(CANONICAL_REGIONS),
        "country_feature_pairs": sum(item.level == "country" for item in output),
        "region_feature_pairs": sum(item.level == "region" for item in output),
        "sources": list(PACK_SOURCES),
        "semantics": {
            "direct": "Country rows retain source evidence status and uncertainty.",
            "regional": "Regional rows are population-weighted aggregates of covered countries.",
            "fallback": (
                "Missing priority-country rows use their canonical regional distribution and "
                "remain imputed."
            ),
            "mbti": (
                "An exploratory Big Five threshold proxy kept label-only; it is not measured MBTI."
            ),
            "income": (
                "GNI PPP and Gini parameterize a lognormal estimate; it is not observed "
                "individual income."
            ),
        },
    }
    return output, metadata
