import asyncio
import json
import threading
import time
from datetime import date

import httpx
from fastapi.testclient import TestClient

from petraterrium.ai_settings import AISourceProvenance
from petraterrium.atlas.auto_import_research import SourceCandidate
from petraterrium.atlas.auto_import_service import AutoImportResearchService
from petraterrium.atlas.database import AtlasStore
from petraterrium.main import create_app


class ScriptedResearchProvider:
    def __init__(
        self,
        failed_places: set[str] | None = None,
        evidence_kind="measured",
        ai_provenance: AISourceProvenance | None = None,
    ):
        self.failed_places = failed_places or set()
        self.evidence_kind = evidence_kind
        self.ai_provenance = ai_provenance
        self.steps = []

    def candidate(self, target, source_kind, language="en"):
        return SourceCandidate(
            title=f"{target.place_label} income table",
            url=f"https://example.test/{target.place_id}",
            source_kind=source_kind,
            feature="income",
            place=target.place_label,
            place_level=target.level,
            denominator="persons",
            population=max(1, target.population),
            observation_date=date(2024, 1, 1),
            published_date=date(2024, 2, 1),
            time_unit="annual",
            unit="percent",
            distribution={"under 50k": 60, "50k or more": 40},
            evidence_kind=self.evidence_kind,
            credible=True,
            credibility_reason="Published tabulation with a stated universe",
            language=language,
            original_excerpt="收入分布 60 40" if language == "zh" else "Income 60 40",
            translated_excerpt="Income distribution 60 40" if language != "en" else None,
            sample_size=1_000,
            source_version="2024-table-1",
            license="CC BY 4.0",
            ai_provenance=self.ai_provenance,
        )

    def inspect_user_source(self, source, target, requirement):
        if source.content == "wrong":
            candidate = self.candidate(target, "user_text")
            return [candidate.model_copy(update={"place": "Different place"})]
        if source.content:
            return [self.candidate(target, "user_text")]
        return []

    def search(self, step, target, requirement):
        self.steps.append((target.place_id, step.language, step.engine, step.sequence))
        if target.place_id in self.failed_places or step.sequence != 1:
            return []
        return [self.candidate(target, step.source_kind, step.language)]


def seed_atlas(path):
    store = AtlasStore(path)
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO countries(code,name) VALUES(?,?)",
            (("US", "United States"), ("CN", "China"), ("JP", "Japan")),
        )
        connection.executemany(
            """INSERT INTO cities(
            geonameid,name,asciiname,country_code,admin1,admin2,latitude,longitude,
            population,timezone,feature_code,simulation_tier
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    1,
                    "Alpha",
                    "Alpha",
                    "US",
                    "CA",
                    "",
                    1,
                    1,
                    1_200_000,
                    "America/Los_Angeles",
                    "PPL",
                    "simulated",
                ),
                (
                    2,
                    "Beta",
                    "Beta",
                    "US",
                    "CA",
                    "",
                    2,
                    2,
                    900_000,
                    "America/Los_Angeles",
                    "PPL",
                    "disaggregated",
                ),
                (
                    3,
                    "上海",
                    "Shanghai",
                    "CN",
                    "23",
                    "",
                    31,
                    121,
                    24_000_000,
                    "Asia/Shanghai",
                    "PPL",
                    "simulated",
                ),
                (
                    4,
                    "東京",
                    "Tokyo",
                    "JP",
                    "40",
                    "",
                    35,
                    139,
                    14_000_000,
                    "Asia/Tokyo",
                    "PPL",
                    "simulated",
                ),
            ),
        )
    return store


def queue(client, priority="primary", threshold=1_000_000):
    response = client.get(
        "/atlas/auto-import/queue",
        params={
            "level": "city",
            "feature_id": "income",
            "priority": priority,
            "city_population_threshold": threshold,
            "page_size": 50,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def start(client, target, text="source", scope="shared"):
    response = client.post(
        "/atlas/auto-import/attempts",
        data={
            "target": json.dumps(target),
            "scope": scope,
            "urls": "[]",
            "pasted_text": text,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, attempt):
    response = client.post(
        f"/atlas/auto-import/attempts/{attempt['attempt_id']}/mapping",
        json={
            "reviewed": True,
            "mappings": [
                {"column": row["column"], "target": row["target"]}
                for row in attempt["mappings"]
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_queue_uses_default_city_threshold_and_separate_lower_priority_cohort(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    application = create_app(atlas_path=path, research_provider=ScriptedResearchProvider())
    with TestClient(application) as client:
        primary = queue(client)
        lower = queue(client, "lower")
    assert {item["place_id"] for item in primary["items"]} == {"1", "3", "4"}
    assert {item["place_id"] for item in lower["items"]} == {"2"}
    assert primary["lower_priority_count"] == 1
    assert lower["primary_count"] == 3


def test_attempt_creation_does_not_block_the_event_loop(tmp_path, monkeypatch):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    application = create_app(
        atlas_path=path,
        research_provider=ScriptedResearchProvider(),
    )
    persistence_started = threading.Event()
    persistence_release = threading.Event()
    original_create_attempt = AutoImportResearchService.create_attempt

    def blocking_create_attempt(self, target, user_sources=()):
        persistence_started.set()
        if not persistence_release.wait(timeout=0.3):
            raise RuntimeError("Test did not release attempt persistence")
        return original_create_attempt(self, target, user_sources)

    monkeypatch.setattr(
        AutoImportResearchService,
        "create_attempt",
        blocking_create_attempt,
    )
    target = {
        "place_id": "1",
        "place_label": "Alpha",
        "level": "city",
        "country_code": "US",
        "geonameid": 1,
        "population": 1_200_000,
        "field_id": "income",
        "field_label": "Income",
        "current_status": "missing",
        "as_of": "2026-10-27",
        "required_distribution": {},
        "missing_impact": 1_200_000,
        "place_item_count": 1,
        "priority": "primary",
    }

    async def exercise():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            started_at = time.monotonic()

            async def heartbeat():
                await asyncio.sleep(0.01)
                return time.monotonic() - started_at

            heartbeat_task = asyncio.create_task(heartbeat())
            request_task = asyncio.create_task(
                client.post(
                    "/atlas/auto-import/attempts",
                    data={
                        "target": json.dumps(target),
                        "scope": "shared",
                        "urls": "[]",
                        "pasted_text": "source",
                    },
                )
            )
            release_timer = threading.Timer(0.2, persistence_release.set)
            release_timer.start()
            try:
                response = await request_task
                heartbeat_elapsed = await heartbeat_task
            finally:
                persistence_release.set()
                release_timer.cancel()
            assert persistence_started.is_set()
            assert response.status_code == 200, response.text
            assert heartbeat_elapsed < 0.1

    asyncio.run(exercise())


def test_mapping_requires_review_and_explicit_promotion_updates_queue_and_trace(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    store = seed_atlas(path)
    provider = ScriptedResearchProvider(
        ai_provenance=AISourceProvenance(
            source="openai_cli",
            source_label="OpenAI CLI",
            model="gpt-test",
            generated_at="2026-10-27T12:00:00Z",
            prompt_version="atlas-source-extraction-v1",
        )
    )
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target)
        assert attempt["stage"] == "mapping"
        assert attempt["can_promote"] is False
        with store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        ready = confirm(client, attempt)
        assert ready["stage"] == "ready"
        assert ready["can_promote"] is True
        with store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        promoted = client.post(
            f"/atlas/auto-import/attempts/{attempt['attempt_id']}/promote",
            json={"redistribution_confirmed": True},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["stage"] == "promoted"
        assert not any(item["item_id"] == target["item_id"] for item in queue(client)["items"])
        detail = client.get("/atlas/cities/1").json()
        evidence = client.get("/atlas/auto-import/evidence/income")
        assert evidence.status_code == 200, evidence.text
        evidence_attempts = evidence.json()["attempts"]
    income = next(field for field in detail["city"]["fields"] if field["field"] == "income")
    assert income["status"] == "present"
    assert income["research_trace"]["languages"][0] == "es"
    assert set(income["research_trace"]["languages"]) >= {"en"}
    assert len(evidence_attempts) == 1
    assert evidence_attempts[0]["target"]["place_label"] == "Alpha"
    assert evidence_attempts[0]["sources"][0]["original_excerpt"]
    assert evidence_attempts[0]["sources"][0]["ai_provenance"]["source_label"] == "OpenAI CLI"
    assert income["research_trace"]["sources"]["accepted"][0]["ai_provenance"][
        "prompt_version"
    ] == "atlas-source-extraction-v1"
    assert "Resolved with measured evidence" in (tmp_path / "MISSING.md").read_text()


def test_mapping_review_can_edit_distribution_and_exposes_diff_and_promotion_record(
    tmp_path,
):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    with TestClient(
        create_app(atlas_path=path, research_provider=ScriptedResearchProvider())
    ) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target)
        response = client.post(
            f"/atlas/auto-import/attempts/{attempt['attempt_id']}/mapping",
            json={
                "reviewed": True,
                "mappings": [
                    {"column": row["column"], "target": row["target"]}
                    for row in attempt["mappings"]
                ],
                "distribution": {"under 50k": 55, "50k or more": 45},
            },
        )
        assert response.status_code == 200, response.text
        ready = response.json()
        assert ready["candidate_values"] == {"under 50k": 55, "50k or more": 45}
        assert ready["distribution_changes"] == [
            {
                "source_label": "under 50k",
                "target_label": "under 50k",
                "before": 60,
                "after": 55,
            },
            {
                "source_label": "50k or more",
                "target_label": "50k or more",
                "before": 40,
                "after": 45,
            },
        ]
        promoted = client.post(
            f"/atlas/auto-import/attempts/{attempt['attempt_id']}/promote",
            json={"redistribution_confirmed": True},
        )
        assert promoted.status_code == 200, promoted.text
        promoted_view = promoted.json()
        assert promoted_view["promotion_id"]
        assert promoted_view["draft_status"] == "promoted"


def test_wrong_source_is_rejected_and_pipeline_estimate_keeps_queue_item(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    provider = ScriptedResearchProvider(failed_places={"1"})
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target, "wrong")
        after = queue(client)
    assert attempt["stage"] == "mapping"
    assert attempt["can_promote"] is False
    assert attempt["evidence_kind"] == "estimated"
    assert attempt["draft_status"] == "editable_draft"
    assert attempt["usable_in_demo"] is True
    assert any(source["accepted"] is False for source in attempt["sources"])
    assert any("different place" in check["detail"].lower() for check in attempt["verification"])
    assert attempt["search_log"]
    assert any(item["item_id"] == target["item_id"] for item in after["items"])
    assert "Research or review in progress" in (tmp_path / "MISSING.md").read_text()


def test_hint_promotes_only_as_estimated_with_wide_interval(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    provider = ScriptedResearchProvider(evidence_kind="hint")
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target)
        assert attempt["evidence_kind"] == "estimated"
        assert "30" in attempt["estimate_trace"]["calculation"]
        ready = confirm(client, attempt)
        promoted = client.post(
            f"/atlas/auto-import/attempts/{ready['attempt_id']}/promote",
            json={"redistribution_confirmed": True},
        )
        assert promoted.status_code == 200, promoted.text
        detail = client.get("/atlas/cities/1").json()
        assert not any(item["item_id"] == target["item_id"] for item in queue(client)["items"])
    income = next(field for field in detail["city"]["fields"] if field["field"] == "income")
    assert income["status"] == "estimated"
    assert income["research_trace"]["estimate_trace"]["confidence_intervals"]
    assert "Estimated with a stored uncertainty" in (tmp_path / "MISSING.md").read_text()


def test_bulk_continues_after_failure_and_waits_for_promotion(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    provider = ScriptedResearchProvider(failed_places={"2"})
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        all_cities = queue(client, threshold=0)
        selected = [
            item["item_id"]
            for item in all_cities["items"]
            if item["place_id"] in {"1", "2", "3"}
        ]
        response = client.post(
            "/atlas/auto-import/batches",
            json={
                "scope": "shared",
                "as_of": "2026-10-26",
                "concurrency": 2,
                "selection": {"mode": "explicit", "item_ids": selected},
            },
        )
        assert response.status_code == 200, response.text
        batch = response.json()
        for _ in range(100):
            batch = client.get(f"/atlas/auto-import/batches/{batch['batch_id']}").json()
            if batch["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert batch["summary"]["measured"] == 2
        assert batch["summary"]["estimated"] == 1
        assert batch["summary"]["failed"] == 0
        assert batch["summary"]["promoted"] == 0
        assert batch["summary"]["completed"] == 3
        assert all(item["mappings"] for item in batch["items"] if item["status"] == "ready")
        assert all(
            not item["can_promote"] for item in batch["items"] if item["status"] == "ready"
        )
        states = {item["target"]["place_id"]: item["status"] for item in batch["items"]}
        assert states == {"1": "ready", "2": "ready", "3": "ready"}
        blocked = client.post(
            f"/atlas/auto-import/batches/{batch['batch_id']}/promote",
            json={
                "mode": "all_eligible",
                "item_ids": [],
                "mapping_confirmed": False,
                "redistribution_confirmed": True,
            },
        )
        assert blocked.status_code == 422
        promoted = client.post(
            f"/atlas/auto-import/batches/{batch['batch_id']}/promote",
            json={
                "mode": "all_eligible",
                "item_ids": [],
                "mapping_confirmed": True,
                "redistribution_confirmed": True,
            },
        )
        assert promoted.status_code == 200, promoted.text
        result = promoted.json()
        latest = client.get("/atlas/auto-import/batches/latest", params={"scope": "shared"})
        assert latest.status_code == 200
        assert latest.json()["batch_id"] == batch["batch_id"]
    assert result["summary"]["promoted"] == 3
    assert next(item for item in result["items"] if item["target"]["place_id"] == "2")[
        "status"
    ] == "promoted"


def test_multi_country_bulk_keeps_each_distribution_and_provenance_place_specific(tmp_path):
    class CountrySpecificProvider(ScriptedResearchProvider):
        distributions = {
            "CN": {"under 50k": 82, "50k or more": 18},
            "JP": {"under 50k": 63, "50k or more": 37},
            "US": {"under 50k": 54, "50k or more": 46},
        }

        def candidate(self, target, source_kind, language="en"):
            return super().candidate(target, source_kind, language).model_copy(
                update={
                    "title": f"{target.place_label} national income table",
                    "url": f"https://example.test/{target.place_id}/income",
                    "distribution": self.distributions[target.place_id],
                }
            )

    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    with TestClient(
        create_app(atlas_path=path, research_provider=CountrySpecificProvider())
    ) as client:
        queue_response = client.get(
            "/atlas/auto-import/queue",
            params={
                "level": "country",
                "feature_id": "income",
                "page_size": 50,
            },
        )
        assert queue_response.status_code == 200, queue_response.text
        targets = {
            item["place_id"]: item["item_id"] for item in queue_response.json()["items"]
        }
        selected = [targets[country] for country in ("CN", "JP", "US")]
        response = client.post(
            "/atlas/auto-import/batches",
            json={
                "scope": "shared",
                "as_of": "2026-10-26",
                "concurrency": 3,
                "selection": {"mode": "explicit", "item_ids": selected},
            },
        )
        assert response.status_code == 200, response.text
        batch = response.json()
        for _ in range(100):
            batch = client.get(
                f"/atlas/auto-import/batches/{batch['batch_id']}"
            ).json()
            if batch["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)
        attempts = {
            item["target"]["place_id"]: client.get(
                f"/atlas/auto-import/attempts/{item['attempt_id']}"
            ).json()
            for item in batch["items"]
        }

    assert batch["summary"]["measured"] == 3
    assert batch["summary"]["failed"] == 0
    assert {
        country: attempt["candidate_values"] for country, attempt in attempts.items()
    } == CountrySpecificProvider.distributions
    for country, attempt in attempts.items():
        accepted = [source for source in attempt["sources"] if source["accepted"]]
        assert len(accepted) == 1
        assert accepted[0]["url"] == f"https://example.test/{country}/income"
        assert (
            country in accepted[0]["title"]
            or attempt["target"]["place_label"] in accepted[0]["title"]
        )
        assert all(
            other_country not in accepted[0]["url"]
            for other_country in CountrySpecificProvider.distributions
            if other_country != country
        )


def test_feature_evidence_respects_run_scope_and_availability_date(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    provider = ScriptedResearchProvider()
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target, scope="run-a")
        ready = confirm(client, attempt)
        promoted = client.post(
            f"/atlas/auto-import/attempts/{ready['attempt_id']}/promote",
            json={"redistribution_confirmed": True},
        )
        assert promoted.status_code == 200, promoted.text

        shared = client.get(
            "/atlas/auto-import/evidence/income",
            params={"scope": "shared", "as_of": "2026-10-26"},
        )
        own_run = client.get(
            "/atlas/auto-import/evidence/income",
            params={"scope": "run-a", "as_of": "2026-10-26"},
        )
        other_run = client.get(
            "/atlas/auto-import/evidence/income",
            params={"scope": "run-b", "as_of": "2026-10-26"},
        )
        before_publication = client.get(
            "/atlas/auto-import/evidence/income",
            params={"scope": "run-a", "as_of": "2024-01-15"},
        )

    assert shared.json()["attempts"] == []
    assert len(own_run.json()["attempts"]) == 1
    assert other_run.json()["attempts"] == []
    assert before_publication.json()["attempts"] == []
