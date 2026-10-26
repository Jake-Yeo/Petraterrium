import argparse
import json
from pathlib import Path

from petraterrium.atlas.feature_dump import build_feature_dump

parser = argparse.ArgumentParser()
parser.add_argument("--data-directory", type=Path, default=Path(__file__).parents[1] / "data")
parser.add_argument("--output", type=Path)
parser.add_argument("--database", type=Path)
parser.add_argument("--refresh", action="store_true")
parser.add_argument("--install-shared", action="store_true")
options = parser.parse_args()
result = build_feature_dump(
    options.data_directory,
    options.output,
    options.database,
    options.refresh,
    options.install_shared,
)
print(json.dumps(result, indent=2))
