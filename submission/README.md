# Module 5 submission

Project: **DeployLens — Release observability dashboard**

Requirements are implemented in `.github/workflows/ci.yml` (build, tests, Docker,
deployment and verification), `.github/workflows/monitor.yml` (scheduled monitoring),
`Dockerfile`, `compose.yaml`, and `docs/ARCHITECTURE.md` (architecture diagram).

Live dashboard: https://deploylens.onrender.com

Repository: https://github.com/Gauravwakle96/deploylens

Successful CI/CD run: https://github.com/Gauravwakle96/deploylens/actions/runs/42661628180

External monitor verified: https://github.com/Gauravwakle96/deploylens/actions/runs/42660920319

Verified on 9 November 2026:

- 24 tests passed in GitHub Actions, including real PostgreSQL integration. Locally,
  23 tests passed and the PostgreSQL integration was skipped without a test database URL.
- React production build, TypeScript, Ruff lint/format, and mypy passed.
- Python dependency audit reported no known vulnerabilities; npm audit reported zero findings.
- Docker image built, container HTTP smoke checks passed, and Compose app/database are healthy.
- Saved observations survived app container replacement. Pausing PostgreSQL caused HTTP 503;
  unpausing restored HTTP 200. See `docker-evidence.json`.
- CI automatically deployed the validated commit, verified its live version and saved a release.
- The authenticated reporting workflow imported actual GitHub job results into the dashboard.
- All four views checked at 1440, 768 and 390 px with no horizontal overflow or axe WCAG A/AA
  findings. Loading, empty, error, partial, success and unauthorized write states were exercised.
- Gitleaks source scan passed. Production database uses TLS and a restricted role/schema.

`pipeline-evidence.json`, `browser-evidence.json` and `docker-evidence.json` record actual checks.
`deploylens-linkedin.png` is the one photo to upload; `post.txt` is the short caption.
Other screenshots show desktop/tablet/mobile QA. Test fixtures were used only for error/empty UI
states and were never inserted into production history.

Known limits: Render Free may sleep; monitoring has gaps while asleep. GitHub schedules may
be delayed. Process counters reset on restart. One third-party Starlette TestClient deprecation
warning remains. This is an internship-scale single-worker application, not an uptime SLA service.
