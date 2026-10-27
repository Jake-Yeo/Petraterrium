import json
import time
from datetime import date

from fastapi.testclient import TestClient

from petraterrium.atlas.auto_import_research import SourceCandidate
from petraterrium.atlas.database import AtlasStore
from petraterrium.main import create_app


class ScriptedResearchProvider:
    def __init__(self, failed_places: set[str] | None = None, evidence_kind="measured"):
        self.failed_places = failed_places or set()
        self.evidence_kind = evidence_kind
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


def test_mapping_requires_review_and_explicit_promotion_updates_queue_and_trace(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    store = seed_atlas(path)
    provider = ScriptedResearchProvider()
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
    assert income["research_trace"]["languages"] == ["en"]
    assert len(evidence_attempts) == 1
    assert evidence_attempts[0]["target"]["place_label"] == "Alpha"
    assert evidence_attempts[0]["sources"][0]["original_excerpt"]
    assert "Resolved with measured evidence" in (tmp_path / "MISSING.md").read_text()


def test_wrong_source_is_rejected_and_no_result_keeps_queue_item(tmp_path):
    path = tmp_path / "atlas.sqlite3"
    seed_atlas(path)
    provider = ScriptedResearchProvider(failed_places={"1"})
    with TestClient(create_app(atlas_path=path, research_provider=provider)) as client:
        target = next(item for item in queue(client)["items"] if item["place_id"] == "1")
        attempt = start(client, target, "wrong")
        after = queue(client)
    assert attempt["stage"] == "failed"
    assert attempt["can_promote"] is False
    assert any(source["accepted"] is False for source in attempt["sources"])
    assert any("different place" in check["detail"].lower() for check in attempt["verification"])
    assert attempt["search_log"]
    assert any(item["item_id"] == target["item_id"] for item in after["items"])
    assert "Missing after research" in (tmp_path / "MISSING.md").read_text()


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
        assert batch["summary"]["failed"] == 1
        assert batch["summary"]["promoted"] == 0
        assert batch["summary"]["completed"] == 3
        assert all(item["mappings"] for item in batch["items"] if item["status"] == "ready")
        assert all(
            not item["can_promote"] for item in batch["items"] if item["status"] == "ready"
        )
        states = {item["target"]["place_id"]: item["status"] for item in batch["items"]}
        assert states == {"1": "ready", "2": "failed", "3": "ready"}
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
    assert result["summary"]["promoted"] == 2
    assert next(item for item in result["items"] if item["target"]["place_id"] == "2")[
        "status"
    ] == "failed"


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
