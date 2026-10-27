import json
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CANONICAL_REGIONS = (
    "Northern America",
    "Latin America & Caribbean",
    "Europe",
    "Africa",
    "Asia excluding China and India",
    "China",
    "India",
    "Oceania",
    "Rest / unassigned",
)
NORTHERN_AMERICA_CODES = {"BM", "CA", "GL", "PM", "US"}
CONTINENT_REGIONS = {
    "EU": "Europe",
    "AF": "Africa",
    "AS": "Asia excluding China and India",
    "OC": "Oceania",
    "SA": "Latin America & Caribbean",
}
SPECIAL_REGIONS = {
    "CN": "China",
    "IN": "India",
    "MX": "Latin America & Caribbean",
    "RU": "Europe",
}
SPECIAL_LABEL_REGIONS = {
    "china": "China",
    "india": "India",
    "mexico": "Latin America & Caribbean",
    "russia": "Europe",
}


class RegionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegionalAggregate(RegionModel):
    value: float
    covered_population: int = Field(ge=0)
    total_population: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)
    weight_source: str


class DatasetRegionMapping(RegionModel):
    dataset: str
    version: str
    mappings: dict[str, str]


@lru_cache(maxsize=1)
def country_continents() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / "data" / "countryInfo.txt"
    result = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) > 8:
            result[columns[0]] = columns[8]
    return result


@lru_cache(maxsize=1)
def country_languages() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[2] / "data" / "countryInfo.txt"
    result = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) <= 15:
            continue
        languages = tuple(
            dict.fromkeys(
                language.split("-", 1)[0].strip().lower()
                for language in columns[15].split(",")
                if language.strip()
            )
        )
        result[columns[0]] = languages
    return result


def country_region(country_code: str) -> str:
    code = country_code.upper()
    if code in SPECIAL_REGIONS:
        return SPECIAL_REGIONS[code]
    continent = country_continents().get(code)
    if continent == "NA":
        return (
            "Northern America"
            if code in NORTHERN_AMERICA_CODES
            else "Latin America & Caribbean"
        )
    return CONTINENT_REGIONS.get(continent, "Rest / unassigned")


def aggregate_region_populations(
    populations: Mapping[str, int] | Iterable[tuple[str, int]],
) -> dict[str, int]:
    totals = {region: 0 for region in CANONICAL_REGIONS}
    rows = populations.items() if isinstance(populations, Mapping) else populations
    seen = set()
    for country_code, population in rows:
        code = country_code.upper()
        if code in seen:
            raise ValueError(f"Country {code} is double-counted in regional totals")
        seen.add(code)
        if population < 0:
            raise ValueError(f"Population for {code} cannot be negative")
        totals[country_region(code)] += population
    return totals


def population_weighted_average(
    values: dict[str, float],
    populations: dict[str, int],
    weight_source: str,
) -> RegionalAggregate:
    covered = sum(populations.get(place, 0) for place in values)
    total = sum(populations.values())
    if covered <= 0:
        raise ValueError("Population-weighted aggregation needs covered population")
    value = sum(values[place] * populations.get(place, 0) for place in values) / covered
    return RegionalAggregate(
        value=value,
        covered_population=covered,
        total_population=total,
        coverage_percent=round(covered * 100 / total, 6) if total else 0,
        weight_source=weight_source,
    )


class DatasetRegionMappingRegistry:
    def __init__(self, store):
        self.store = store

    def register(
        self, dataset: str, version: str, mappings: dict[str, str]
    ) -> DatasetRegionMapping:
        for source, target in mappings.items():
            required = SPECIAL_LABEL_REGIONS.get(source.casefold().strip())
            if required and target != required:
                name = source.strip().title()
                raise ValueError(f"{name} must map to {required}")
            if target not in CANONICAL_REGIONS:
                raise ValueError(f"Unknown canonical region {target}")
        record = DatasetRegionMapping(dataset=dataset, version=version, mappings=mappings)
        with self.store.connection() as conn:
            conn.execute("UPDATE region_mappings SET active=0 WHERE dataset=?", (dataset,))
            conn.execute(
                "INSERT OR REPLACE INTO region_mappings VALUES(?,?,?,1)",
                (dataset, version, json.dumps(mappings, sort_keys=True)),
            )
        return record

    def active(self, dataset: str) -> DatasetRegionMapping | None:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM region_mappings WHERE dataset=? AND active=1",
                (dataset,),
            ).fetchone()
        if row is None:
            return None
        return DatasetRegionMapping(
            dataset=row["dataset"],
            version=row["version"],
            mappings=json.loads(row["mappings_json"]),
        )

    def resolve(self, dataset: str, source_region: str) -> str:
        record = self.active(dataset)
        if record is None or source_region not in record.mappings:
            raise KeyError(f"No active region mapping for {dataset}: {source_region}")
        return record.mappings[source_region]
