import sys
from pathlib import Path
from zipfile import ZipFile

from petraterrium.atlas.backbone import load_cities500
from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_catalog import FeatureCatalogStore
from petraterrium.atlas.features import canonical_feature_registry
from petraterrium.dsl import Evidence, FeatureDistribution

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
catalog = FeatureCatalogStore(store)
registry = canonical_feature_registry()
for country_code in ("IT", "FR", "DE"):
    for feature_id, values in (
        ("age_band", {"0-4": 0.2, "5-9": 0.8}),
        ("sex", {"female": 0.51, "male": 0.49}),
    ):
        catalog.attach_distribution(
            registry,
            feature_id,
            FeatureDistribution(
                feature_id=feature_id,
                level="country",
                place=country_code,
                population="FAKE browser-test population",
                coverage_percent=100,
                values=values,
                provenance=Evidence(
                    source="FAKE browser-test distribution",
                    version="FAKE-browser-v1",
                    status="present",
                    uncertainty=0.5,
                    source_date="2020-01-01",
                ),
            ),
        )
