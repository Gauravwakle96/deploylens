"""Probe the real HTTP application; retries allow container startup/cold starts."""

import json
import os
import time
import urllib.error
import urllib.request


def main():
    base = os.environ.get("SMOKE_URL", "http://127.0.0.1:8015").rstrip("/")
    expected = os.environ.get("EXPECTED_VERSION")
    for _ in range(20):
        try:
            with urllib.request.urlopen(base + "/health", timeout=15) as response:
                health = json.load(response)
            if health.get("status") != "ok":
                raise ValueError("Unhealthy application")
            if expected and health.get("version") != expected:
                raise ValueError("Unexpected deployed version")
            for path in ("/", "/api/dashboard", "/metrics"):
                with urllib.request.urlopen(base + path, timeout=15) as response:
                    if response.status != 200:
                        raise ValueError("Endpoint did not return HTTP 200")
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "version": health["version"],
                        "checks": ["health", "dashboard", "website", "metrics"],
                    }
                )
            )
            return
        except (urllib.error.URLError, ValueError, ConnectionError, TimeoutError):
            time.sleep(5)
    raise RuntimeError("Application smoke checks failed")


if __name__ == "__main__":
    main()
