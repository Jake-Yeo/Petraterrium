import hashlib
import json
from pathlib import Path

import numpy as np

from .contracts import RunConfig
from .data import DATA_VERSION
from .engine import ENGINE_MODEL


def source_digest() -> str:
    digest = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    digest.update(np.__version__.encode())
    return digest.hexdigest()[:16]


ENGINE_VERSION = ENGINE_MODEL + "+" + source_digest()


def config_hash(
    config: RunConfig,
    engine_version: str = ENGINE_VERSION,
    data_version: str = DATA_VERSION,
) -> str:
    canonical = json.dumps(
        {
            "config": config.model_dump(),
            "engine_version": engine_version,
            "data_version": data_version,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
