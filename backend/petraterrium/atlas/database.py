import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "atlas.sqlite3"
FIELDS = ("age_sex", "income", "education", "ideology", "household_size")
SUGGESTIONS = {
    "age_sex": ("Census/IPUMS; UN WPP for a country archetype", "https://population.un.org/wpp/"),
    "income": ("Census/PUMS or licensed IPUMS microdata", "https://international.ipums.org/"),
    "education": ("Census/IPUMS or DHS education tables", "https://international.ipums.org/"),
    "ideology": ("WVS, ESS, Pew, Gallup or ANES survey", "https://www.worldvaluessurvey.org/"),
    "household_size": ("Census household microdata or DHS", "https://dhsprogram.com/data/"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES('revision', '0');
CREATE TABLE IF NOT EXISTS countries(code TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cities(
 geonameid INTEGER PRIMARY KEY, name TEXT NOT NULL, asciiname TEXT NOT NULL,
 country_code TEXT NOT NULL, admin1 TEXT NOT NULL, admin2 TEXT NOT NULL,
 latitude REAL NOT NULL, longitude REAL NOT NULL, population INTEGER NOT NULL,
 timezone TEXT NOT NULL, feature_code TEXT NOT NULL, simulation_tier TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cities_country_population ON cities(country_code,population DESC);
CREATE INDEX IF NOT EXISTS cities_population ON cities(population DESC,geonameid);
CREATE INDEX IF NOT EXISTS cities_name ON cities(asciiname COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS imports(
 import_id TEXT PRIMARY KEY, source TEXT NOT NULL, source_date TEXT NOT NULL,
 published_date TEXT NOT NULL, version TEXT NOT NULL, scope TEXT NOT NULL,
 uploader TEXT NOT NULL, kind TEXT NOT NULL, filename TEXT NOT NULL,
 row_count INTEGER NOT NULL, status TEXT NOT NULL, metadata_json TEXT NOT NULL,
 rows_json TEXT NOT NULL, mapping_json TEXT NOT NULL, audit_json TEXT NOT NULL,
 validation_json TEXT, validated_json TEXT, promoted_from TEXT,
 redistribution_allowed INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS imports_scope ON imports(scope,status);
CREATE TABLE IF NOT EXISTS observations(
 id INTEGER PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(import_id),
 geo_level TEXT NOT NULL, geo_key TEXT NOT NULL, field TEXT NOT NULL,
 value_json TEXT NOT NULL, unit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_geo ON observations(geo_level,geo_key,field,id DESC);
CREATE INDEX IF NOT EXISTS observations_import ON observations(import_id);
CREATE TABLE IF NOT EXISTS models(
 id INTEGER PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(import_id),
 country_code TEXT NOT NULL, behaviour TEXT NOT NULL, fitted INTEGER NOT NULL,
 label_only INTEGER NOT NULL, active INTEGER NOT NULL, specification_json TEXT NOT NULL,
 heldout_loss REAL, baseline_loss REAL, training_rows INTEGER NOT NULL,
 heldout_rows INTEGER NOT NULL, traits_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS models_country ON models(country_code,active);
CREATE TABLE IF NOT EXISTS densities(
 id INTEGER PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(import_id),
 geonameid INTEGER NOT NULL REFERENCES cities(geonameid), density REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS density_city ON densities(geonameid,id DESC);
CREATE TABLE IF NOT EXISTS llm_cache(
 cache_key TEXT PRIMARY KEY, proposal_json TEXT, audit_json TEXT
);
"""


class AtlasStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("PETRATERRIUM_ATLAS_PATH", DEFAULT_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def revision(conn) -> int:
        return int(conn.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])

    @staticmethod
    def bump(conn) -> None:
        conn.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    @staticmethod
    def metadata(conn, key: str, default=None):
        result = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(result[0]) if result else default

    @staticmethod
    def set_metadata(conn, key: str, value) -> None:
        conn.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, json.dumps(value)))
