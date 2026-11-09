from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def test_authenticated_pipeline_report_and_escaped_data(tmp_path):
    token = "test-pipeline-token-at-least-32-characters"
    config = Settings(
        _env_file=None,
        collector_enabled=False,
        admin_token=token,
        database_url=f"sqlite:///{tmp_path / 'reports.sqlite3'}",
    )
    payload = {
        "id": 42659495375,
        "title": "<script>alert(1)</script>",
        "status": "failure",
        "commit_sha": "a" * 40,
        "branch": "main",
        "started_at": "2026-11-09T00:00:00Z",
        "updated_at": "2026-11-09T00:01:00Z",
        "jobs": [],
    }
    with TestClient(create_app(config)) as client:
        assert client.post("/api/pipelines", json=payload).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert client.post("/api/pipelines", json=payload, headers=headers).status_code == 201
        assert client.post("/api/pipelines", json=payload, headers=headers).status_code == 201
        data = client.get("/api/dashboard").json()
        assert len(data["pipelines"]) == 1
        assert data["pipelines"][0]["url"].endswith("/42659495375")
        assert data["github"]["success"]
        assert (
            client.post("/api/pipelines", content=b"x" * 33000, headers=headers).status_code == 413
        )
        payload["commit_sha"] = "invalid"
        assert client.post("/api/pipelines", json=payload, headers=headers).status_code == 422
