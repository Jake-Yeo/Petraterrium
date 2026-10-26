import json
from datetime import date

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from petraterrium.atlas.contracts import ImportMetadata
from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.source_adapters import source_rows
from petraterrium.atlas.sources import SOURCES, fetch_source
from petraterrium.atlas.validation import validate_value


def metadata(source, **updates):
    return ImportMetadata(
        run_id="FAKE-test-run",
        source="FAKE test source",
        source_id=source,
        source_date=date(2020, 1, 1),
        published_date=date(2020, 1, 2),
        version="test",
        **updates,
    )


def test_us_pums_weights_are_used_without_city_observation_claims(tmp_path):
    rows = [
        {"AGEP": 40, "SEX": 1, "PWGTP": 1, "SCHL": 10, "PINCP": 100},
        {"AGEP": 20, "SEX": 2, "PWGTP": 3, "SCHL": 20, "PINCP": 200},
    ]
    result, meta = source_rows(
        AtlasStore(tmp_path / "atlas.sqlite"),
        "pums.json",
        json.dumps(rows).encode(),
        metadata("us_pums"),
    )
    assert result[0]["country_code"] == "US"
    assert result[0]["income"] == 175
    assert result[0]["education"] == {"SCHL_10": 25, "SCHL_20": 75}
    assert result[0]["age_sex"] == {"male_40": 25, "female_20": 75}
    assert "geonameid" not in result[0]
    assert meta.processing_notes


def test_un_wpp_selects_declared_year_and_excludes_aggregates(tmp_path):
    rows = [
        {"ISO3_code": "", "Time": 2020, "AgeGrp": "0-4", "PopMale": 10000, "PopFemale": 10000},
        {"ISO3_code": "ITA", "Time": 2020, "AgeGrp": "0-4", "PopMale": 10, "PopFemale": 20},
        {"ISO3_code": "ITA", "Time": 2020, "AgeGrp": "5-9", "PopMale": 20, "PopFemale": 10},
        {"ISO3_code": "ITA", "Time": 2021, "AgeGrp": "0-4", "PopMale": 500, "PopFemale": 500},
    ]
    result, _ = source_rows(
        AtlasStore(tmp_path / "atlas.sqlite"),
        "wpp.json",
        json.dumps(rows).encode(),
        metadata("un_wpp"),
    )
    assert len(result) == 1 and result[0]["country_code"] == "IT"
    assert result[0]["age_sex"]["female_0-4"] == pytest.approx(100 / 3)
    validate_value("age_sex", result[0]["age_sex"], "percent")


def test_population_grid_samples_keep_density_separate_from_marginals(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite")
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO cities VALUES(1,'Alpha','Alpha','IT','A','',"
            "42,12,1000,'Europe/Rome','PPL','disaggregated')"
        )
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(10, 44, 2, 2),
        ) as dataset:
            dataset.write(np.full((1, 2, 2), 100, dtype=np.float32))
        result, meta = source_rows(
            store, "grid.tif", memory.read(), metadata("worldpop", unit="persons_per_km2")
        )
    assert meta.kind == "population"
    assert result == [{"geonameid": 1, "country_code": "IT", "density_per_km2": 100}]
    assert "imputed" in " ".join(meta.processing_notes)


def test_canonical_sources_and_license_gates_are_real_loader_entries():
    assert {source.source_id for source in SOURCES} == {
        "ipums",
        "us_pums",
        "un_wpp",
        "worldpop",
        "gpw",
        "dhs",
        "wvs",
        "ess",
        "pew",
        "gallup",
        "anes",
    }

    with pytest.raises(ValueError, match="access rights"):
        fetch_source("gallup", "https://www.gallup.com/file.csv", False)
    with pytest.raises(ValueError, match="approved source host"):
        fetch_source("us_pums", "http://127.0.0.1/private", False)
