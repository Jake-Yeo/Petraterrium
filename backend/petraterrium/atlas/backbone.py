import csv
import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import httpx
import pycountry

from .contracts import Backbone
from .database import AtlasStore

GEONAMES_URL = "https://download.geonames.org/export/dump/cities500.zip"
EXCLUDED_CODES = {"PPLX", "PPLQ", "PPLW", "PPLH"}


def load_cities500(store: AtlasStore, archive_path: Path | None = None) -> Backbone:
    with store.connection() as conn:
        previous = store.metadata(conn, "backbone")
        if previous and previous.get("loaded"):
            return Backbone(**previous)
    source_date = datetime.now(UTC).date().isoformat()
    if archive_path is None:
        archive_path = store.path.parent / "cities500.zip"
        if not archive_path.exists():
            with httpx.stream("GET", GEONAMES_URL, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                temporary = archive_path.with_suffix(".part")
                with temporary.open("wb") as destination:
                    for chunk in response.iter_bytes():
                        destination.write(chunk)
                temporary.replace(archive_path)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    rows = []
    original = excluded = duplicates = 0
    seen = set()
    with ZipFile(archive_path) as archive:
        source_date = datetime(*archive.getinfo("cities500.txt").date_time).date().isoformat()
        with archive.open("cities500.txt") as source:
            for values in csv.reader(io.TextIOWrapper(source, encoding="utf-8"), delimiter="\t"):
                original += 1
                if len(values) != 19:
                    raise ValueError(
                        f"Invalid GeoNames record at line {original}: expected 19 columns"
                    )
                identity = int(values[0])
                if identity in seen:
                    duplicates += 1
                    continue
                seen.add(identity)
                population = int(values[14] or 0)
                if values[6] != "P" or values[7] in EXCLUDED_CODES:
                    excluded += 1
                    continue
                rows.append(
                    (
                        identity,
                        values[1],
                        values[2],
                        values[8],
                        values[10],
                        values[11],
                        float(values[4]),
                        float(values[5]),
                        population,
                        values[17],
                        values[7],
                        "disaggregated",
                    )
                )
    metadata = Backbone(
        loaded=True,
        version="sha256:" + digest,
        downloaded_at=datetime.now(UTC).isoformat(),
        source_date=source_date,
        original_rows=original,
        retained_rows=len(rows),
        excluded_rows=excluded,
        duplicate_rows=duplicates,
    )
    with store.connection() as conn:
        if store.metadata(conn, "backbone", {}).get("loaded"):
            return Backbone(**store.metadata(conn, "backbone"))
        conn.executemany(
            "INSERT OR IGNORE INTO countries VALUES(?,?)",
            [(c.alpha_2, c.name) for c in pycountry.countries],
        )
        conn.executemany("INSERT INTO cities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.execute("""UPDATE cities SET simulation_tier='simulated' WHERE geonameid IN (
            SELECT geonameid FROM (SELECT geonameid,population,
            ROW_NUMBER() OVER(PARTITION BY country_code ORDER BY population DESC,geonameid) r
            FROM cities) WHERE r<=3 AND population>=1000000)""")
        store.set_metadata(conn, "backbone", metadata.model_dump())
        store.bump(conn)
    return metadata
