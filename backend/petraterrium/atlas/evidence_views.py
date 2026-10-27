import json
from functools import lru_cache
from pathlib import Path

from ..dsl import DSLConfig
from .contracts import (
    ChoiceEvidenceCatalog,
    FeatureResolutionRecord,
    UniversalFeatureOverview,
)
from .features import canonical_feature_registry, resolve_feature_distribution


@lru_cache(maxsize=1)
def smoke_evidence_dsl() -> DSLConfig:
    path = Path(__file__).resolve().parents[3] / "shared" / "dsl-schema" / "smoke-spread.json"
    return DSLConfig.model_validate(json.loads(path.read_text()))


def universal_feature_overview() -> UniversalFeatureOverview:
    registry = smoke_evidence_dsl().feature_registry or canonical_feature_registry()
    resolutions = []
    for feature_id in ("generalized_trust", "mbti"):
        resolved = resolve_feature_distribution(
            registry,
            feature_id,
            city="Vancouver",
            country="CAN",
            region="Northern America",
        )
        evidence = resolved.distribution.provenance if resolved.distribution else None
        resolutions.append(
            FeatureResolutionRecord(
                feature_id=feature_id,
                city="Vancouver",
                country="CAN",
                region="Northern America",
                status=resolved.status,
                resolved_level=resolved.resolved_level,
                source=evidence.source if evidence else None,
                version=evidence.version if evidence else None,
                source_date=evidence.source_date if evidence else None,
                population=resolved.distribution.population if resolved.distribution else None,
                coverage_percent=(
                    resolved.distribution.coverage_percent
                    if resolved.distribution
                    else None
                ),
                region_override=resolved.region_override,
                missing_requirement=resolved.missing_requirement,
            )
        )
    return UniversalFeatureOverview(registry=registry, resolutions=resolutions)


def choice_evidence_catalog() -> ChoiceEvidenceCatalog:
    return ChoiceEvidenceCatalog(rows=smoke_evidence_dsl().choice_evidence)
