import io
from zipfile import ZipFile

import pyarrow as pa
from shapely import to_wkb
from shapely.geometry import Polygon

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_dump.households import (
    latest_household_rows,
    latest_household_values,
)
from petraterrium.atlas.feature_dump.install import install_shared_marginals
from petraterrium.atlas.feature_dump.ucdb import (
    attribute_pattern,
    catalog_rows,
    country_code,
    decode_name,
    match_cities_to_urban_centres,
)
from petraterrium.atlas.feature_dump.wdi import derive_wdi_marginals, redistributable_series
from petraterrium.atlas.feature_dump.xlsx import read_sheet


def test_wdi_redistribution_and_canonical_marginals_require_consistent_years():
    series = [
        {"Series Code": "allowed", "License Type": "CC BY-4.0"},
        {"Series Code": "igo", "License Type": "CC BY 3.0 IGO"},
        {"Series Code": "restricted", "License Type": "SIPRI terms and conditions"},
    ]
    assert {row["Series Code"] for row in redistributable_series(series)} == {
        "allowed",
        "igo",
    }
    observations = []
    age_values = {
        "SP.POP.0014.FE.IN": 10,
        "SP.POP.0014.MA.IN": 12,
        "SP.POP.1564.FE.IN": 30,
        "SP.POP.1564.MA.IN": 28,
        "SP.POP.65UP.FE.IN": 12,
        "SP.POP.65UP.MA.IN": 8,
    }
    income_values = {
        "SI.DST.FRST.20": 5,
        "SI.DST.02ND.20": 10,
        "SI.DST.03RD.20": 15,
        "SI.DST.04TH.20": 25,
        "SI.DST.05TH.20": 45,
    }
    for feature_id, value in age_values.items() | income_values.items():
        observations.append(
            {"country_code": "AA", "feature_id": feature_id, "year": 2022, "value": value}
        )
    observations.append(
        {
            "country_code": "BB",
            "feature_id": "SP.POP.0014.FE.IN",
            "year": 2022,
            "value": 10,
        }
    )
    marginals = derive_wdi_marginals(observations)
    assert {(row["country_code"], row["field"]) for row in marginals} == {
        ("AA", "age_sex"),
        ("AA", "income"),
    }
    age = next(row for row in marginals if row["field"] == "age_sex")
    assert age["value"] == {
        "female_0_14": 10,
        "male_0_14": 12,
        "female_15_64": 30,
        "male_15_64": 28,
        "female_65_plus": 12,
        "male_65_plus": 8,
    }
    income = next(row for row in marginals if row["field"] == "income")
    assert sum(income["value"].values()) == 100


def test_ucdb_polygon_matches_are_spatial_imputations():
    assert decode_name(None) == ""
    assert country_code("Kosovo (under UNSC res. 1244)") == "XK"
    assert country_code("Dem. People's Republic of Korea") == "KP"
    assert country_code("China, Taiwan Province of China") == "TW"
    assert country_code("Turkey") == "TR"
    assert attribute_pattern("SD_LUE_LPR_XXXX_XXXX").match(
        "SD_LUE_LPR_1975_1990"
    ).groups() == ("1975", "1990")
    fallback = catalog_rows({"UNINDEXED": "climate.parquet"}, [])[0]
    assert fallback["theme"] == "Climate"
    assert fallback["source"] == "GHS-UCDB R2024A"
    cities = pa.table(
        {
            "geonameid": [1, 2],
            "country_code": ["AA", "AA"],
            "latitude": [0.0, 5.0],
            "longitude": [0.0, 5.0],
        }
    )
    urban_centres = [
        {
            "ucdb_id": 10,
            "country_code": "AA",
            "geometry": to_wkb(Polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)])),
            "area_km2": 100,
            "centroid_latitude": 0.0,
            "centroid_longitude": 0.0,
        }
    ]
    matches = match_cities_to_urban_centres(cities, urban_centres, projected=False)
    assert matches.to_pylist() == [
        {
            "geonameid": 1,
            "ucdb_id": 10,
            "status": "imputed",
            "match_method": "inside_urban_centre",
            "distance_km": 0.0,
        }
    ]


def test_household_latest_rows_and_streaming_xlsx_reader():
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<si><t>country</t></si><si><t>AA</t></si></sst>'
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr">'
        '<is><t>value</t></is></c></row><row r="2"><c r="A2" t="s"><v>1</v></c>'
        '<c r="B2"><v>2.5</v></c></row></sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        '</Relationships>'
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    assert list(read_sheet(buffer.getvalue(), "Data")) == [
        ["country", "value"],
        ["AA", 2.5],
    ]
    latest = latest_household_rows(
        [
            {"country_code": "AA", "year": 2020, "average_household_size": 3.0},
            {"country_code": "AA", "year": 2022, "average_household_size": 2.8},
            {"country_code": "BB", "year": 2021, "average_household_size": 4.0},
        ]
    )
    assert [(row["country_code"], row["year"]) for row in latest] == [
        ("AA", 2022),
        ("BB", 2021),
    ]
    feature_values = latest_household_values(
        [
            {
                "country_code": "AA",
                "year": 2020,
                "source_catalog_id": "1",
                "features": {"household_size": 3.0, "female_head": 20.0},
            },
            {
                "country_code": "AA",
                "year": 2022,
                "source_catalog_id": "2",
                "features": {"household_size": 2.8},
            },
        ]
    )
    assert {(row["feature_id"], row["year"]) for row in feature_values} == {
        ("household_size", 2022),
        ("female_head", 2020),
    }


def test_shared_bulk_install_is_versioned_and_idempotent(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    rows = [
        {
            "country_code": "AA",
            "field": "household_size",
            "year": 2022,
            "value": 2.8,
            "unit": "members",
            "source": "FAKE public source",
            "published_date": "2023-01-01",
            "version": "sha256:fake",
            "filename": "fake.parquet",
        }
    ]
    assert install_shared_marginals(store, rows) == 1
    assert install_shared_marginals(store, rows) == 0
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
