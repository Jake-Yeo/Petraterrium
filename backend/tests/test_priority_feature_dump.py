import json
from pathlib import Path

import pyarrow.parquet as pq

from petraterrium.atlas.feature_dump.priority_features import PRIORITY_COUNTRY_CODES
from petraterrium.atlas.features import canonical_feature_registry
from petraterrium.atlas.regions import CANONICAL_REGIONS
from petraterrium.dsl import FeatureDistribution

DUMP = Path(__file__).resolve().parents[1] / "data" / "registry_feature_dump"


def test_priority_dump_covers_every_feature_for_priority_places():
    rows = pq.read_table(DUMP / "priority_feature_distributions.parquet").to_pylist()
    distributions = [
        FeatureDistribution.model_validate_json(row["distribution_json"]) for row in rows
    ]
    expected_features = {
        feature.id for feature in canonical_feature_registry().definitions
    } - {"age", "sex"}
    country_pairs = {
        (distribution.feature_id, distribution.place)
        for distribution in distributions
        if distribution.level == "country"
    }
    region_pairs = {
        (distribution.feature_id, distribution.place)
        for distribution in distributions
        if distribution.level == "region"
    }
    assert expected_features == {feature for feature, _ in country_pairs}
    assert expected_features == {feature for feature, _ in region_pairs}
    assert not {
        (feature, country)
        for feature in expected_features
        for country in PRIORITY_COUNTRY_CODES
    } - country_pairs
    assert not {
        (feature, region)
        for feature in expected_features
        for region in CANONICAL_REGIONS
    } - region_pairs
    assert all(distribution.provenance.source_date for distribution in distributions)
    assert all(distribution.population_count is not None for distribution in distributions)
    assert all(
        distribution.population_count > 0
        for distribution in distributions
        if distribution.level == "region"
    )


def test_wpp_dump_covers_every_canonical_region_with_explicit_fallbacks():
    rows = pq.read_table(DUMP / "wpp_region_age_sex.parquet").to_pylist()
    assert {row["region"] for row in rows} == set(CANONICAL_REGIONS)
    rest = [row for row in rows if row["region"] == "Rest / unassigned"]
    assert rest
    assert {row["evidence_status"] for row in rest} == {"imputed"}
    assert {row["distribution_population"] for row in rest} == {47}


def test_priority_dump_manifest_records_sources_and_limitations():
    manifest = json.loads((DUMP / "manifest.json").read_text())
    pack = manifest["priority_features"]
    assert pack["priority_countries"] == list(PRIORITY_COUNTRY_CODES)
    assert pack["country_feature_pairs"] >= 180
    assert pack["region_feature_pairs"] >= 162
    assert "World Values Survey" in pack["sources"]
    assert "OpenPsychometrics" in pack["sources"]
