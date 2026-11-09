import asyncio
import hmac
import json
import logging
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .collector import collect
from .config import Settings
from .database import Check, Database, Incident, Pipeline, Release, SyncState, now

logger = logging.getLogger("deploylens")
logging.basicConfig(level=logging.INFO, format="%(message)s")
STATIC = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class ReleaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commit_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    run_id: int = Field(gt=0)
    version: str = Field(min_length=1, max_length=80)


def row_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    db = Database(config)
    recent_requests: deque[dict] = deque(maxlen=100)
    counters = {"requests": 0, "errors": 0, "duration_ms": 0.0}
    started = time.monotonic()

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(db.initialize)
        task = asyncio.create_task(collect(config, db)) if config.collector_enabled else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        db.engine.dispose()

    app = FastAPI(
        title="DeployLens", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.database = db

    @app.middleware("http")
    async def observe(request: Request, call_next):
        begin = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse({"detail": "Service temporarily unavailable"}, status_code=503)
        duration = round((time.perf_counter() - begin) * 1000, 1)
        route = request.scope.get("route")
        safe_path = getattr(route, "path", "static-or-unmatched")
        event = {
            "at": now(),
            "request_id": request_id,
            "method": request.method[:10],
            "path": safe_path,
            "status": response.status_code,
            "duration_ms": duration,
        }
        counters["requests"] += 1
        counters["errors"] += int(response.status_code >= 500)
        counters["duration_ms"] += duration
        recent_requests.append(event)
        logger.info(json.dumps({"event": "http_request", **event}))
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    @app.get("/health")
    def health():
        try:
            db.check()
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {
            "status": "ok",
            "version": config.app_version,
            "database": "connected",
            "environment": config.environment,
        }

    @app.get("/api/dashboard")
    def dashboard():
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        with db.session() as session:
            checks = list(
                session.scalars(
                    select(Check)
                    .where(Check.checked_at >= cutoff)
                    .order_by(Check.id.desc())
                    .limit(1440)
                )
            )
            pipelines = list(
                session.scalars(select(Pipeline).order_by(Pipeline.started_at.desc()).limit(15))
            )
            releases = list(session.scalars(select(Release).order_by(Release.id.desc()).limit(20)))
            incidents = list(
                session.scalars(select(Incident).order_by(Incident.id.desc()).limit(30))
            )
            sync = session.get(SyncState, "github")
            latest = checks[0] if checks else None
            stale = (
                latest is None
                or (datetime.now(UTC) - datetime.fromisoformat(latest.checked_at)).total_seconds()
                > config.check_interval_seconds * 3
            )
            completed = [p for p in pipelines if p.status in {"success", "failure", "timed_out"}]
            return {
                "generated_at": now(),
                "environment": config.environment,
                "version": config.app_version,
                "repository": config.github_repository,
                "service": {
                    "name": config.monitor_name,
                    "status": "unknown"
                    if stale or latest is None
                    else ("healthy" if latest.healthy else "down"),
                    "last_checked": latest.checked_at if latest else None,
                    "latency_ms": latest.latency_ms if latest else None,
                    "sample_success_percent": round(
                        100 * sum(c.healthy for c in checks) / len(checks), 1
                    )
                    if checks
                    else None,
                    "samples": len(checks),
                    "interval_seconds": config.check_interval_seconds,
                },
                "checks": [row_dict(c) for c in reversed(checks[:60])],
                "pipelines": [row_dict(p) for p in pipelines],
                "releases": [row_dict(r) for r in releases],
                "incidents": [row_dict(i) for i in incidents],
                "pipeline_success_percent": round(
                    100 * sum(p.status == "success" for p in completed) / len(completed), 1
                )
                if completed
                else None,
                "github": row_dict(sync) if sync else None,
                "observability": {
                    **counters,
                    "uptime_seconds": round(time.monotonic() - started),
                    "logs": list(reversed(recent_requests))[:15],
                },
            }

    @app.post("/api/releases", status_code=201)
    async def release(request: Request):
        token = config.admin_token.get_secret_value()
        supplied = request.headers.get("authorization", "")
        if len(token) < 32 or not hmac.compare_digest(supplied, "Bearer " + token):
            raise HTTPException(401, "Pipeline authentication required")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 4096:
                raise HTTPException(413, "Request too large")
            body.extend(chunk)
        try:
            payload = ReleaseInput.model_validate_json(body)
        except ValueError:
            raise HTTPException(422, "Invalid release payload") from None
        if payload.commit_sha != config.app_version:
            raise HTTPException(409, "Release does not match the running version")
        with db.session() as session:
            previous = session.scalar(
                select(Release).where(Release.commit_sha == payload.commit_sha)
            )
            if previous:
                return {"id": previous.id, "recorded": True}
            saved = Release(**payload.model_dump())
            session.add(saved)
            session.flush()
            return {"id": saved.id, "recorded": True}

    @app.get("/metrics")
    def metrics():
        lines = [
            "# TYPE deploylens_http_requests_total counter",
            f"deploylens_http_requests_total {counters['requests']}",
            "# TYPE deploylens_http_errors_total counter",
            f"deploylens_http_errors_total {counters['errors']}",
            "# TYPE deploylens_uptime_seconds gauge",
            f"deploylens_uptime_seconds {time.monotonic() - started:.1f}",
        ]
        with db.session() as session:
            opened = session.scalar(
                select(func.count()).select_from(Incident).where(Incident.resolved_at.is_(None))
            )
        lines.extend(
            ["# TYPE deploylens_open_incidents gauge", f"deploylens_open_incidents {opened}"]
        )
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @app.get("/robots.txt")
    def robots():
        return PlainTextResponse("User-agent: *\nDisallow: /\n")

    @app.get("/")
    def index():
        if STATIC.exists():
            return FileResponse(STATIC / "index.html")
        return JSONResponse({"detail": "Build the frontend with npm run build"}, status_code=503)

    if (STATIC / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
    hosts = [h.strip() for h in config.allowed_hosts.split(",") if h.strip()]
    if config.render_external_hostname:
        hosts.append(config.render_external_hostname)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    return app


app = create_app()
