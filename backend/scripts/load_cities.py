import argparse
from pathlib import Path

from petraterrium.atlas.backbone import load_cities500
from petraterrium.atlas.database import AtlasStore

parser = argparse.ArgumentParser()
parser.add_argument("--archive", type=Path)
parser.add_argument("--database", type=Path)
options = parser.parse_args()
print(load_cities500(AtlasStore(options.database), options.archive).model_dump_json(indent=2))
