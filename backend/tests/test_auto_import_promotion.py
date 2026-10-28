import json
from datetime import date

import pytest

from petraterrium.atlas import auto_import_promotion
from petraterrium.atlas.auto_import_promotion import AtlasAutoImportPromotionWriter
from petraterrium.atlas.auto_import_research import (
    LabelMapping,
    MappingPreview,
    PlaceFeatureTarget,
    SourceCandidate,
    SourceVerification,
)
from petraterrium.atlas.auto_import_service import PromotionPayload
from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_catalog import FeatureCatalogStore
from petraterrium.atlas.features import canonical_feature_registry


def promotion_payload(
    attempt_id: str = "a" * 32,
    scope: str = "run-17",
) -> PromotionPayload:
    source = SourceCandidate(
        candidate_id="b" * 32,
        title="National education table",
        url="https://statistics.example.test/education",
        source_kind="official_statistics",
        feature="education",
        place="Vancouver",
        place_level="city",
        denominator="residents aged 25 and older",
        population=500_000,
        observation_date=date(2024, 1, 1),
        published_date=date(2024, 3, 1),
        time_unit="point-in-time census or survey wave",
        unit="percent",
        distribution={"1": 30, "2": 70},
        evidence_kind="measured",
        credible=True,
        credibility_reason="Published methodology and sampling frame",
        original_excerpt="Educational attainment distribution",
        source_version="2024.1",
        license="Open Government Licence",
    )
    mapping = MappingPreview(
        version="education-v1",
        rows=(
            LabelMapping(
                source_label="1",
                proposed_label="1",
                confidence="exact",
                reason="Canonical value",
            ),
            LabelMapping(
                source_label="2",
                proposed_label="2",
                confidence="exact",
                reason="Canonical value",
            ),
        ),
    )
    target = PlaceFeatureTarget(
        level="city",
        place_id="6173331",
        place_label="Vancouver",
        feature_id="education",
        population=662_248,
        current_status="missing",
        scope=scope,
        country_code="CA",
    )
    return PromotionPayload(
        attempt_id=attempt_id,
        target=target,
        evidence_status="measured",
        distribution={"1": 30.0, "2": 70.0},
        unit="percent",
        coverage_percent=100,
        sources=(source,),
        mapping=mapping,
        verifications=(
            SourceVerification(
                candidate_id=source.candidate_id,
                accepted=True,
                direct_measurement=True,
                checks=(),
                reasons=(),
            ),
        ),
        search_log=(),
        languages_searched=("en",),
        predictive_evidence_eligible=True,
    )


def record_counts(store: AtlasStore) -> tuple[int, int, int]:
    with store.connection() as connection:
        imports = connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        revision = store.revision(connection)
    return imports, observations, revision


def test_repeated_promotion_reuses_one_import_and_observation(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    writer = AtlasAutoImportPromotionWriter(store, tmp_path / "MISSING.md")
    payload = promotion_payload()

    first_id = writer.promote(payload)
    second_id = writer.promote(payload)

    assert second_id == first_id
    assert record_counts(store) == (1, 1, 1)
    with store.connection() as connection:
        stored = connection.execute(
            "SELECT scope,metadata_json FROM imports WHERE import_id=?",
            (first_id,),
        ).fetchone()
    assert stored["scope"] == "run-17"
    metadata = json.loads(stored["metadata_json"])
    assert metadata["attempt_id"] == payload.attempt_id
    assert metadata["sources"][0]["source_version"] == "2024.1"
    assert metadata["sources"][0]["license"] == "Open Government Licence"


def test_missing_document_failure_retries_without_duplicate_evidence(
    tmp_path,
    monkeypatch,
):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    writer = AtlasAutoImportPromotionWriter(store, tmp_path / "MISSING.md")
    payload = promotion_payload()
    sync_calls = 0

    def flaky_sync(*_args, **_kwargs):
        nonlocal sync_calls
        sync_calls += 1
        if sync_calls == 1:
            raise OSError("MISSING.md is temporarily unavailable")

    monkeypatch.setattr(auto_import_promotion, "sync_missing_document", flaky_sync)

    with pytest.raises(OSError, match="temporarily unavailable"):
        writer.promote(payload)

    assert record_counts(store) == (1, 1, 1)
    with store.connection() as connection:
        committed_id = connection.execute("SELECT import_id FROM imports").fetchone()[0]

    retried_id = writer.promote(payload)

    assert retried_id == committed_id
    assert sync_calls == 2
    assert record_counts(store) == (1, 1, 1)


def test_retry_rejects_scope_or_provenance_changes(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    writer = AtlasAutoImportPromotionWriter(store, tmp_path / "MISSING.md")
    payload = promotion_payload()
    promotion_id = writer.promote(payload)
    changed_target = payload.target.model_copy(update={"scope": "run-99"})
    changed_payload = payload.model_copy(update={"target": changed_target})

    with pytest.raises(RuntimeError, match="scope"):
        writer.promote(changed_payload)

    assert record_counts(store) == (1, 1, 1)
    with store.connection() as connection:
        scope = connection.execute(
            "SELECT scope FROM imports WHERE import_id=?",
            (promotion_id,),
        ).fetchone()[0]
    assert scope == "run-17"


def test_promoted_specialization_is_visible_as_a_ready_feature_distribution(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    writer = AtlasAutoImportPromotionWriter(store, tmp_path / "MISSING.md")
    base = promotion_payload(scope="shared")
    values = {f"{code:02d}": 100 / 11 for code in range(11)}
    first_key = next(iter(values))
    values[first_key] += 100 - sum(values.values())
    source = base.sources[0].model_copy(
        update={
            "feature": "specialization",
            "place": "Canada",
            "place_level": "country",
            "denominator": "tertiary graduates",
            "distribution": values,
        }
    )
    mapping = MappingPreview(
        version="specialization-isced-f-2013-v1",
        rows=tuple(
            LabelMapping(
                source_label=label,
                proposed_label=label,
                confidence="exact",
                reason="Canonical ISCED-F broad field",
            )
            for label in values
        ),
    )
    target = base.target.model_copy(
        update={
            "level": "country",
            "place_id": "CA",
            "place_label": "Canada",
            "feature_id": "specialization",
            "country_code": "CA",
        }
    )
    payload = base.model_copy(
        update={
            "target": target,
            "distribution": values,
            "sources": (source,),
            "mapping": mapping,
            "verifications": (
                base.verifications[0].model_copy(
                    update={"candidate_id": source.candidate_id}
                ),
            ),
        }
    )

    writer.promote(payload)
    detail = FeatureCatalogStore(store).detail(
        canonical_feature_registry(), "specialization"
    )

    assert detail.status == "ready"
    assert len(detail.distributions) == 1
    distribution = detail.distributions[0]
    assert distribution.level == "country"
    assert distribution.place == "CA"
    assert distribution.provenance.status == "present"
    assert sum(distribution.values.values()) == pytest.approx(1)
