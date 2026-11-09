"""Deploy the validated commit through the Render API; never log credentials."""

import json
import os
import time
import urllib.error
import urllib.request


def request_json(url, payload=None, token=None):
    headers = {"User-Agent": "DeployLens-CI", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def deploy():
    sha = os.environ["GITHUB_SHA"]
    base = os.environ["DEPLOYLENS_URL"].rstrip("/")
    service_id = os.environ["RENDER_SERVICE_ID"]
    token = os.environ["RENDER_API_KEY"]
    if not service_id.startswith("srv-") or not service_id.replace("-", "").isalnum():
        raise RuntimeError("Invalid Render service configuration")
    try:
        result = request_json(
            f"https://api.render.com/v1/services/{service_id}/deploys",
            {"commitId": sha, "clearCache": "do_not_clear"},
            token,
        )
    except (urllib.error.URLError, ValueError):
        raise RuntimeError(
            "Render rejected the deployment request; check the service configuration"
        ) from None
    print("Deployment requested for commit " + sha[:7])
    for attempt in range(60):
        try:
            state = request_json(
                f"https://api.render.com/v1/services/{service_id}/deploys/{result['id']}",
                token=token,
            )
            if state.get("status") in {"build_failed", "update_failed", "canceled", "deactivated"}:
                raise RuntimeError("Render deployment failed; inspect the provider build logs")
            health = request_json(base + "/health")
            if (
                state.get("status") == "live"
                and health.get("status") == "ok"
                and health.get("version") == sha
            ):
                print("Live application is healthy and running the validated commit")
                return
        except (urllib.error.URLError, ValueError):
            pass
        if attempt % 5 == 0:
            print("Waiting for the new version to become healthy...")
        time.sleep(15)
    raise RuntimeError("Deployment did not become healthy with the expected commit in time")


def record_release():
    sha = os.environ["GITHUB_SHA"]
    base = os.environ["DEPLOYLENS_URL"].rstrip("/")
    try:
        health = request_json(base + "/health")
        if health.get("status") != "ok" or health.get("version") != sha:
            raise RuntimeError("Live version did not match the validated commit")
        request_json(
            base + "/api/releases",
            {
                "commit_sha": sha,
                "run_id": int(os.environ["GITHUB_RUN_ID"]),
                "version": "release-" + sha[:7],
            },
            os.environ["DEPLOYLENS_ADMIN_TOKEN"],
        )
        print("Release verified and recorded")
    except (urllib.error.URLError, ValueError):
        raise RuntimeError("Release verification or recording failed") from None


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["record"]:
        record_release()
    else:
        deploy()
