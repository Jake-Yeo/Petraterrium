from zipfile import ZipFile

from petraterrium.atlas.backbone import load_cities500
from petraterrium.atlas.database import AtlasStore


def record(identity, name, population=1000, code="PPL", country="IT"):
    return "\t".join(
        map(
            str,
            [
                identity,
                name,
                name,
                "",
                42,
                12,
                "P",
                code,
                country,
                "",
                "01",
                "001",
                "",
                "",
                population,
                "",
                0,
                "Europe/Rome",
                "2026-01-01",
            ],
        )
    )


def test_complete_backbone_keeps_administrative_seat_exceptions_and_deduplicates(tmp_path):
    archive = tmp_path / "cities500.zip"
    lines = [
        record(1, "Alpha"),
        record(1, "Alpha duplicate"),
        record(2, "Administrative seat", 100, "PPLA4"),
        record(3, "Neighbourhood", 2000, "PPLX"),
        record(4, "Abandoned", 2000, "PPLQ"),
        record(5, "French Alpha", 2000, country="FR"),
    ]
    with ZipFile(archive, "w") as target:
        target.writestr("cities500.txt", "\n".join(lines))
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    loaded = load_cities500(store, archive)
    assert loaded.retained_rows == 3
    assert loaded.duplicate_rows == 1
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(DISTINCT geonameid) FROM cities").fetchone()[0] == 3
        assert conn.execute("SELECT population FROM cities WHERE geonameid=2").fetchone()[0] == 100
    assert load_cities500(store, archive) == loaded
