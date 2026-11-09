import asyncio
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from backend.collector import check_service, record_check, sync_github
from backend.config import Settings
from backend.database import Base, Check, Database, Incident, Pipeline, Release, SyncState
from backend.main import create_app

TOKEN = "test-only-token-not-a-real-secret-12345678"
SHA = "a" * 40


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        admin_token=TOKEN,
        app_version=SHA,
        collector_enabled=False,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def test_empty_dashboard_is_unknown(client):
    data = client.get("/api/dashboard").json()
    assert data["service"]["status"] == "unknown"
    assert data["service"]["sample_success_percent"] is None
    assert data["releases"] == []
    assert data["pipeline_success_percent"] is None


def test_health_and_metrics(client):
    assert client.get("/health").json()["version"] == SHA
    assert "deploylens_http_requests_total" in client.get("/metrics").text
    assert client.get("/health").headers["x-request-id"]


@pytest.mark.parametrize("authorization", ["", "Bearer wrong"])
def test_release_requires_authentication(client, authorization):
    assert (
        client.post("/api/releases", headers={"Authorization": authorization}, json={}).status_code
        == 401
    )


def test_release_must_match_running_version(client):
    response = client.post(
        "/api/releases",
        headers={"Authorization": "Bearer " + TOKEN},
        json={"commit_sha": "b" * 40, "run_id": 1, "version": "v1"},
    )
    assert response.status_code == 409


def test_release_is_idempotent_and_persisted(client):
    args = {
        "headers": {"Authorization": "Bearer " + TOKEN},
        "json": {"commit_sha": SHA, "run_id": 1, "version": "release-aaaaaaa"},
    }
    first = client.post("/api/releases", **args)
    second = client.post("/api/releases", **args)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/dashboard").json()["releases"]) == 1


@pytest.mark.parametrize("body,code", [(b"x" * 5000, 413), (b'{"bad":true}', 422)])
def test_release_limits_and_validation(client, body, code):
    assert (
        client.post(
            "/api/releases", content=body, headers={"Authorization": "Bearer " + TOKEN}
        ).status_code
        == code
    )


def test_logs_do_not_contain_secrets_or_query_strings(client):
    client.get("/health?token=DO_NOT_LOG_ME", headers={"Authorization": "Bearer " + TOKEN})
    data = client.get("/api/dashboard").text
    assert "DO_NOT_LOG_ME" not in data
    assert TOKEN not in data
    assert "Content-Security-Policy" in client.get("/").headers


def test_untrusted_host_rejected(client):
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400


def test_incident_opens_once_and_recovers(client):
    db = client.app.state.database
    record_check(db, "Feedback Board", False, 12, 503, "HTTP 503")
    record_check(db, "Feedback Board", False, 11, 503, "HTTP 503")
    data = client.get("/api/dashboard").json()
    assert len(data["incidents"]) == 1
    assert data["incidents"][0]["resolved_at"] is None
    assert data["service"]["status"] == "down"
    record_check(db, "Feedback Board", True, 10, 200, "Healthy")
    data = client.get("/api/dashboard").json()
    assert data["incidents"][0]["resolved_at"]
    assert data["service"]["status"] == "healthy"
    assert data["service"]["sample_success_percent"] == 33.3


def test_stale_health_is_unknown(client):
    db = client.app.state.database
    record_check(db, "Feedback Board", True, 10, 200, "Healthy")
    with db.session() as session:
        check = session.scalar(select(Check))
        check.checked_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    assert client.get("/api/dashboard").json()["service"]["status"] == "unknown"


@pytest.mark.parametrize(
    "status,payload,healthy",
    [
        (200, {"status": "ok"}, True),
        (200, {"status": "bad"}, False),
        (503, {"status": "ok"}, False),
        (200, [], False),
    ],
)
def test_probe_validates_response(settings, status, payload, healthy):
    db = Database(settings)
    db.initialize()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
        ) as client:
            await check_service(settings, db, client)

    asyncio.run(run())
    with db.session() as session:
        assert session.scalar(select(Check)).healthy == healthy


def test_github_outage_keeps_saved_results(settings):
    db = Database(settings)
    db.initialize()
    with db.session() as session:
        session.add(
            Pipeline(
                id=1,
                title="Saved run",
                status="success",
                commit_sha=SHA,
                branch="main",
                started_at="2026-11-09T00:00:00Z",
                updated_at="2026-11-09T00:00:00Z",
                url="https://github.com",
                jobs=[],
            )
        )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403))
        ) as client:
            await sync_github(settings, db, client)

    asyncio.run(run())
    with db.session() as session:
        assert session.get(Pipeline, 1)
        assert not session.get(SyncState, "github").success


def test_github_imports_job_results(settings):
    db = Database(settings)
    db.initialize()

    def handler(request):
        if "/jobs?" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "name": "Docker",
                            "conclusion": "success",
                            "status": "completed",
                            "started_at": "2026-11-09T00:00:00Z",
                            "completed_at": "2026-11-09T00:01:00Z",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "workflow_runs": [
                    {
                        "id": 9,
                        "display_title": "Real run",
                        "conclusion": "success",
                        "status": "completed",
                        "head_sha": SHA,
                        "head_branch": "main",
                        "created_at": "2026-11-09T00:00:00Z",
                        "updated_at": "2026-11-09T00:01:00Z",
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await sync_github(settings, db, client)

    asyncio.run(run())
    with db.session() as session:
        assert session.get(Pipeline, 9).jobs[0]["status"] == "success"
        assert session.get(SyncState, "github").success


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "sqlite:///bad.sqlite3"},
        {"database_sslmode": "disable"},
        {"admin_token": "short"},
        {"monitor_url": "http://example.com/health"},
    ],
)
def test_production_config_rejects_unsafe_settings(overrides):
    values = {
        "environment": "production",
        "database_url": "postgresql://example/db",
        "admin_token": TOKEN,
        **overrides,
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Requires PostgreSQL")
def test_postgres_integration(tmp_path):
    assert urlsplit(os.environ["TEST_POSTGRES_URL"]).path.endswith("_test"), (
        "Integration tests require a disposable database named *_test"
    )
    config = Settings(
        _env_file=None,
        environment="test",
        database_sslmode="disable",
        database_url=os.environ["TEST_POSTGRES_URL"],
        collector_enabled=False,
    )
    db = Database(config)
    Base.metadata.create_all(db.engine)
    with db.session() as session:
        # This URL must point to the disposable CI database.
        for model in (Check, Incident, Release):
            session.query(model).delete()
    record_check(db, "Integration service", False, 15, 503, "Unavailable")
    record_check(db, "Integration service", True, 10, 200, "Recovered")
    with db.session() as session:
        assert session.scalar(select(Incident)).resolved_at
        assert len(list(session.scalars(select(Check)))) == 2
        session.add(Release(commit_sha="c" * 40, run_id=42659495375, version="test"))
    with db.session() as session:
        assert session.scalar(select(Release)).run_id == 42659495375
