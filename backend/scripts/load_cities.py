import argparse
import json
from pathlib import Path

from petraterrium.atlas.backbone import load_cities500
from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_dump.registry_install import install_registry_dump

DEFAULT_REGISTRY_DUMP = Path(__file__).resolve().parents[1] / "data" / "registry_feature_dump"

parser = argparse.ArgumentParser()
parser.add_argument("--archive", type=Path)
parser.add_argument("--database", type=Path)
parser.add_argument("--registry-dump", type=Path, default=DEFAULT_REGISTRY_DUMP)
parser.add_argument("--skip-registry", action="store_true")
options = parser.parse_args()
store = AtlasStore(options.database)
result = load_cities500(store, options.archive).model_dump(mode="json")
if not options.skip_registry:
    result["registry"] = install_registry_dump(store, options.registry_dump)
print(json.dumps(result, indent=2))
