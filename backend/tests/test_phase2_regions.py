from pathlib import Path

import pytest

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.regions import (
    CANONICAL_REGIONS,
    DatasetRegionMappingRegistry,
    aggregate_region_populations,
    country_region,
    population_weighted_average,
)


def test_canonical_region_assignments_are_mutually_exclusive():
    assert country_region("MX") == "Latin America & Caribbean"
    assert country_region("RU") == "Europe"
    assert country_region("CN") == "China"
    assert country_region("IN") == "India"
    assert country_region("JP") == "Asia excluding China and India"
    assert country_region("CA") == "Northern America"
    assert len(CANONICAL_REGIONS) == len(set(CANONICAL_REGIONS))


def test_region_population_totals_split_china_and_india_without_double_counting():
    populations = {
        "CN": 1_410,
        "IN": 1_480,
        "JP": 125,
        "ID": 280,
        "CA": 41,
        "MX": 132,
        "RU": 144,
    }
    totals = aggregate_region_populations(populations)
    assert totals["China"] == 1_410
    assert totals["India"] == 1_480
    assert totals["Asia excluding China and India"] == 405
    assert totals["Northern America"] == 41
    assert totals["Latin America & Caribbean"] == 132
    assert totals["Europe"] == 144
    assert sum(totals.values()) == sum(populations.values())


@pytest.mark.parametrize("country_code", ["CN", "IN", "MX", "RU"])
def test_region_population_totals_reject_double_counted_special_countries(country_code):
    with pytest.raises(ValueError, match="double-counted"):
        aggregate_region_populations([(country_code, 100), (country_code, 100)])


def test_population_weighted_average_reports_weight_source_and_coverage():
    result = population_weighted_average(
        values={"small": 0.9, "large": 0.1},
        populations={"small": 10, "large": 90, "missing": 100},
        weight_source="UN WPP 2024",
    )
    assert result.value == pytest.approx(0.18)
    assert result.value != pytest.approx(0.5)
    assert result.covered_population == 100
    assert result.total_population == 200
    assert result.coverage_percent == 50
    assert result.weight_source == "UN WPP 2024"


def test_dataset_region_mapping_is_versioned_and_rejects_inconsistent_special_regions(
    tmp_path: Path,
):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    registry = DatasetRegionMappingRegistry(store)
    mapping = registry.register(
        dataset="UN WPP",
        version="2024-r1",
        mappings={
            "Northern America": "Northern America",
            "Latin America and the Caribbean": "Latin America & Caribbean",
            "Eastern Asia excluding China": "Asia excluding China and India",
            "China": "China",
            "India": "India",
        },
    )
    assert mapping.version == "2024-r1"
    assert registry.resolve("UN WPP", "China") == "China"
    with pytest.raises(ValueError, match="Mexico"):
        registry.register(
            dataset="broken",
            version="1",
            mappings={"Mexico": "Northern America"},
        )
    with pytest.raises(ValueError, match="Russia"):
        registry.register(dataset="broken", version="2", mappings={"Russia": "Asia"})
