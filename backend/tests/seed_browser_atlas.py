import sys
from pathlib import Path
from zipfile import ZipFile

from petraterrium.atlas.backbone import load_cities500
from petraterrium.atlas.database import AtlasStore

path = Path(sys.argv[1])
if path.parent.name != ".playwright":
    raise ValueError("Browser fixtures must use their isolated .playwright directory")
path.parent.mkdir(parents=True, exist_ok=True)
for suffix in ("", "-wal", "-shm"):
    Path(str(path) + suffix).unlink(missing_ok=True)
archive = path.parent / "cities500-test.zip"
rows = []
for identity, name, code, population in [
    (1, "Alpha", "IT", 1000),
    (2, "Alpha Town", "IT", 2000),
    (3, "Beta", "FR", 3000),
    (4, "Gamma", "DE", 4000),
    (5, "Delta", "DE", 5000),
]:
    rows.append(
        "\t".join(
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
                    "PPL",
                    code,
                    "",
                    "A",
                    "001",
                    "",
                    "",
                    population,
                    "",
                    0,
                    "Europe/Rome",
                    "2020-01-01",
                ],
            )
        )
    )
with ZipFile(archive, "w") as target:
    target.writestr("cities500.txt", "\n".join(rows))
store = AtlasStore(path)
backbone = load_cities500(store, archive)
with store.connection() as conn:
    store.set_metadata(
        conn,
        "backbone",
        backbone.model_copy(update={"source": "FAKE browser-test cities500 fixture"}).model_dump(),
    )
