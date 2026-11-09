# DeployLens · Module 5

Release history, GitHub pipeline results, service health and incident timelines in one
React + FastAPI dashboard. Uses real GitHub Actions and HTTP health data.

**GitHub → Build → Test → Docker → Deploy → Monitor**

## Run locally

Install Docker Desktop with Linux containers and Python 3.13+.

```powershell
python scripts/setup_local.py
docker compose up -d --build --wait
```

Open http://localhost:8015. PostgreSQL runs on a private Docker network with a persistent
volume. The `.env` file contains generated local credentials and is ignored by Git.
`docker compose down` stops the app while preserving history.

## CI/CD

`.github/workflows/ci.yml` runs on pushes and pull requests:

1. Build React, check Python style/types, run tests including PostgreSQL integration,
   and audit production dependencies.
2. Build the Docker image and run HTTP smoke tests against the actual container.
3. On `main`, deploy the **validated commit** to Render using its API.
4. Wait for Render to report `live`, verify `/health` reports the expected commit,
   probe the website/API/metrics, and record the release using an authenticated callback.

Render rebuilds that commit's Dockerfile. The pipeline does not claim to promote the
same CI image digest. Automatic Render deploys are disabled so pushes cannot bypass CI.
GitHub Actions are pinned to upstream commit SHAs. Pull requests have no deployment secrets.

The GitHub `production` environment holds `RENDER_API_KEY` and `DEPLOYLENS_ADMIN_TOKEN`.
Repository variables: `DEPLOYLENS_URL` and `RENDER_SERVICE_ID`. The Render key is a sensitive
account-level credential; use a dedicated operator key when configuring another account.
The deploy job is skipped until a deployment URL has been configured.

## Monitoring and environment management

- Health probes run every 60 seconds while the service is awake. Target: Feedback Board.
- GitHub workflow/job results refresh every five minutes. Failed syncs retain saved history.
- First failed probe opens an incident; recovery resolves it. Stale observations show unknown.
- `/metrics` exposes request/error counters, process uptime and open incident count.
- JSON stdout logs include request ID, route, status and duration, without headers or bodies.
- An hourly GitHub workflow probes DeployLens independently and fails visibly on an outage.
- Local: Docker + PostgreSQL. CI: disposable PostgreSQL and container smoke database.
  Production: Render Free + Supabase PostgreSQL with TLS and a dedicated restricted role/schema.

The free Render service can sleep and cold starts can delay requests. Monitoring inside a
sleeping service pauses; scheduled GitHub runs can be delayed. The dashboard reports
**sample success**, not uninterrupted uptime. Health samples are retained for seven days;
resolved incidents and pipeline snapshots for 90 days. Request logs/counters are in memory
and reset on restart. This first version is single-worker and public read-only.

## Development and verification

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uvx pip-audit -r requirements.txt
cd frontend
npm ci
npm run build
npm audit --audit-level=high
```

Set `TEST_POSTGRES_URL` to a **disposable test database** to run the PostgreSQL integration
test; it deletes test records in its own tables. It must never point at production.

Configuration is documented in `.env.example`. Cloud tables are initialized using
`python -m scripts.migrate` under the migration role, then the app uses only DML privileges.
Schema changes must be additive/backward compatible. No application login is needed for
this public dashboard; the write endpoint requires a pipeline bearer token.

See [architecture and design contract](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md),
and [submission evidence](submission/README.md).

MIT licensed. React, FastAPI, Vite, SQLAlchemy and Lucide retain their respective licenses.
System fonts are used; no external image assets or paid integrations are required.
