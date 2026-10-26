from datetime import date

from fastapi.testclient import TestClient

from petraterrium.atlas.contracts import ImportMetadata
from petraterrium.atlas.imports import stage_import
from petraterrium.main import create_app


def test_drafts_and_private_scopes_remain_accessible_after_server_restart(client):
    run_id = client.post("/runs", json={"countries": ["ITA"], "end_day": 2}).json()["run_id"]
    metadata = ImportMetadata(
        run_id=run_id,
        source="FAKE persistence test",
        source_date=date(2020, 1, 1),
        published_date=date(2020, 1, 2),
        version="test",
    )
    draft = stage_import(
        client.app.state.atlas,
        "draft.json",
        metadata,
        [{"country_code": "IT", "household_size": 2}],
        False,
    )
    with TestClient(create_app(atlas_path=client.app.state.atlas.path)) as restarted:
        assert restarted.get("/runs").json()["runs"] == []
        scopes = restarted.get("/atlas/scopes").json()["scopes"]
        assert scopes == [
            {"run_id": run_id, "label": "Archived scope " + run_id[:8], "run_available": False}
        ]
        reopened = restarted.get(f"/atlas/imports/{draft.import_id}", params={"scope": run_id})
        assert reopened.status_code == 200
        assert reopened.json()["metadata"]["run_id"] == run_id
        assert (
            restarted.get(
                f"/atlas/imports/{draft.import_id}", params={"scope": "other"}
            ).status_code
            == 404
        )
