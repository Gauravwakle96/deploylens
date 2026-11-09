# Operations

## Troubleshooting

- `docker compose ps` lists local service health; the migration container exits successfully.
- `docker compose logs --tail 50 app` shows structured requests and health probes.
- `/health` returns 503 when database access fails; provider health checks use this path.
- In the dashboard, `unknown` means no recent probe, not a successful check.
- GitHub 403/rate limits retain cached pipeline results and show a sync warning.
- Free hosting cold starts can cause a target failure followed by recovery; inspect timestamps.
- Check GitHub Actions for build/test failures and Render logs for deployment failures.

## Rollback

Use Render's deployment history to redeploy a known good commit, then verify `/health`
reports that commit. For a tracked pipeline rollback, revert the faulty code in Git and
push a new commit: the complete CI/CD workflow must pass again. No automatic database
rollback is performed. Keep migrations backward compatible and back up production data.

## Secrets and access

Production uses environment-scoped GitHub secrets. The API key can control other services
in the Render account, so never expose it to browser code or pull-request jobs. Rotate it
in Render and GitHub if compromised. ADMIN_TOKEN only authenticates release callbacks.
The public UI cannot modify targets or invoke deployment APIs. Configure targets in the
hosting environment only; redirects are disabled on health probes.

The Supabase `deploylens` schema is not exposed through the public data API. The app's
database role has schema usage and table/sequence DML rights, no schema creation or access
to the earlier feedback table. Database setup uses the separate migration/admin role.

## Limits

This is an internship-scale, single-instance deployment. Process metrics are not aggregated
across instances. Alerts use failed GitHub workflow notifications according to the owner's
notification settings; no email or messaging integration is configured by this project.
An hourly external probe does not provide a continuous uptime guarantee.
