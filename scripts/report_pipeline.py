"""Import actual GitHub results with the ephemeral Actions token, then send a report."""

import json
import os
import urllib.error
import urllib.request


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["SOURCE_RUN_ID"])
    base = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    headers = {
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "User-Agent": "DeployLens-CI",
    }
    with urllib.request.urlopen(urllib.request.Request(base, headers=headers), timeout=20) as r:
        run = json.load(r)
    with urllib.request.urlopen(
        urllib.request.Request(base + "/jobs?per_page=30", headers=headers), timeout=20
    ) as r:
        jobs = json.load(r)["jobs"]
    payload = {
        "id": run["id"],
        "title": run["display_title"][:240],
        "status": run["conclusion"] or run["status"],
        "commit_sha": run["head_sha"],
        "branch": run["head_branch"] or "unknown",
        "started_at": run["created_at"],
        "updated_at": run["updated_at"],
        "jobs": [
            {
                "name": j["name"],
                "status": j["conclusion"] or j["status"],
                "started_at": j["started_at"],
                "completed_at": j["completed_at"],
            }
            for j in jobs
        ],
    }
    request = urllib.request.Request(
        os.environ["DEPLOYLENS_URL"].rstrip("/") + "/api/pipelines",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ["DEPLOYLENS_ADMIN_TOKEN"],
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 201:
            raise RuntimeError("Pipeline report was not accepted")
    print(f"Recorded GitHub run {run_id}: {payload['status']}")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, ValueError, KeyError):
        raise RuntimeError(
            "Could not import pipeline results; check job and service configuration"
        ) from None
