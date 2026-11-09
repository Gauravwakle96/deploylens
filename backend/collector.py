import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select

from .config import Settings
from .database import Check, Database, Incident, Pipeline, SyncState, now

logger = logging.getLogger("deploylens")


def record_check(
    db: Database, service: str, healthy: bool, latency: float, status: int | None, detail: str
) -> None:
    with db.session() as session:
        session.add(
            Check(
                service=service,
                healthy=healthy,
                latency_ms=round(latency, 1),
                status_code=status,
                detail=detail,
            )
        )
        opened = session.scalar(
            select(Incident).where(Incident.service == service, Incident.resolved_at.is_(None))
        )
        if not healthy and opened is None:
            session.add(Incident(service=service, detail=detail))
        elif healthy and opened is not None:
            opened.resolved_at = now()
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        session.execute(delete(Check).where(Check.checked_at < cutoff))
        history_cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        session.execute(delete(Incident).where(Incident.resolved_at < history_cutoff))
        session.execute(delete(Pipeline).where(Pipeline.updated_at < history_cutoff))


def sync_state(db: Database, success: bool, detail: str):
    with db.session() as session:
        session.merge(SyncState(key="github", checked_at=now(), success=success, detail=detail))


async def check_service(config: Settings, db: Database, client: httpx.AsyncClient):
    started = time.perf_counter()
    status = None
    try:
        # Only the operator-configured target is fetched. Redirects are disabled.
        response = await client.get(config.monitor_url, timeout=12, follow_redirects=False)
        status = response.status_code
        healthy = status == 200 and response.json().get("status") == "ok"
        detail = "Health check passed" if healthy else f"Unhealthy response (HTTP {status})"
    except (httpx.HTTPError, ValueError, AttributeError):
        healthy = False
        detail = "Health endpoint unreachable or returned invalid JSON"
    latency = (time.perf_counter() - started) * 1000
    await asyncio.to_thread(record_check, db, config.monitor_name, healthy, latency, status, detail)
    logger.info(
        "health_check service=%s healthy=%s latency_ms=%.1f", config.monitor_name, healthy, latency
    )


async def sync_github(config: Settings, db: Database, client: httpx.AsyncClient):
    base = f"https://api.github.com/repos/{config.github_repository}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        response = await client.get(
            base + "/actions/workflows/ci.yml/runs?per_page=10", headers=headers, timeout=15
        )
        response.raise_for_status()
        runs = response.json()["workflow_runs"]
        for run in runs:
            with db.session() as session:
                previous = session.get(Pipeline, run["id"])
                if previous and previous.updated_at == run["updated_at"] and previous.jobs:
                    continue
            jobs_response = await client.get(
                base + f"/actions/runs/{run['id']}/jobs?per_page=30", headers=headers, timeout=15
            )
            jobs_response.raise_for_status()
            jobs = [
                {
                    "name": job["name"],
                    "status": job["conclusion"] or job["status"],
                    "started_at": job["started_at"],
                    "completed_at": job["completed_at"],
                }
                for job in jobs_response.json()["jobs"]
            ]
            with db.session() as session:
                session.merge(
                    Pipeline(
                        id=run["id"],
                        title=run["display_title"][:240],
                        status=run["conclusion"] or run["status"],
                        commit_sha=run["head_sha"],
                        branch=(run["head_branch"] or "unknown")[:160],
                        started_at=run["created_at"],
                        updated_at=run["updated_at"],
                        url=f"https://github.com/{config.github_repository}/actions/runs/{run['id']}",
                        jobs=jobs,
                    )
                )
        sync_state(db, True, "Connected to GitHub Actions")
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        sync_state(db, False, "GitHub unavailable or rate limited; saved results are retained")


async def collect(config: Settings, db: Database):
    next_github = 0.0
    async with httpx.AsyncClient(headers={"User-Agent": "DeployLens/1.0"}) as client:
        while True:
            try:
                await check_service(config, db, client)
                if config.github_poll_enabled and time.monotonic() >= next_github:
                    await sync_github(config, db, client)
                    next_github = time.monotonic() + config.github_interval_seconds
            except Exception:
                # Never log database URLs or exception text containing credentials.
                logger.error("collector_cycle_failed")
            await asyncio.sleep(config.check_interval_seconds)
