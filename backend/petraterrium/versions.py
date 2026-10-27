import hashlib
import json
from pathlib import Path

from .contracts import RunConfig
from .data import DATA_VERSION
from .engine import ENGINE_MODEL


def source_digest() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for source in sorted(root.rglob("*.py")):
        digest.update(str(source.relative_to(root)).encode())
        digest.update(source.read_bytes())
    shared_schema = root.parents[1] / "shared" / "dsl-schema" / "petraterrium-dsl.schema.json"
    if shared_schema.exists():
        digest.update(shared_schema.read_bytes())
    rust_root = root.parents[1] / "engine-rust"
    for source in sorted((rust_root / "src").rglob("*.rs")):
        digest.update(str(source.relative_to(rust_root)).encode())
        digest.update(source.read_bytes())
    for manifest in (rust_root / "Cargo.toml", rust_root / "Cargo.lock"):
        digest.update(manifest.read_bytes())
    return digest.hexdigest()[:16]


ENGINE_VERSION = ENGINE_MODEL + "+" + source_digest()


def population_version(config: RunConfig) -> str:
    population = config.population or (config.dsl.population if config.dsl else None)
    return population.version if population else DATA_VERSION


def config_hash(
    config: RunConfig,
    engine_version: str = ENGINE_VERSION,
    data_version: str = DATA_VERSION,
    evidence_version: str | None = None,
    resolved_population_version: str | None = None,
) -> str:
    canonical = json.dumps(
        {
            "config": config.model_dump(),
            "engine_version": engine_version,
            "data_version": data_version,
            "evidence_table_version": evidence_version or config.evidence_table_version,
            "population_version": resolved_population_version or population_version(config),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
