import argparse
import json
from pathlib import Path

from petraterrium.atlas.database import DEFAULT_PATH, AtlasStore
from petraterrium.atlas.feature_dump.registry_dump import (
    EXPECTED_WPP_SHA256,
    build_registry_dump,
)
from petraterrium.atlas.feature_dump.registry_install import install_registry_dump

parser = argparse.ArgumentParser()
parser.add_argument("--data-directory", type=Path, default=Path(__file__).parents[1] / "data")
parser.add_argument("--output", type=Path)
parser.add_argument("--refresh", action="store_true")
parser.add_argument("--skip-digest-pin", action="store_true")
parser.add_argument("--install-shared", action="store_true")
parser.add_argument("--database", type=Path, default=DEFAULT_PATH)
options = parser.parse_args()
manifest = build_registry_dump(
    options.data_directory,
    options.output,
    options.refresh,
    None if options.skip_digest_pin else EXPECTED_WPP_SHA256,
)
if options.install_shared:
    output = (options.output or options.data_directory / "registry_feature_dump").resolve()
    manifest["installed"] = install_registry_dump(AtlasStore(options.database), output)
print(json.dumps(manifest, indent=2))
