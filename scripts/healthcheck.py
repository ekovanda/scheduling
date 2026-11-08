"""Container healthcheck probing FastAPI (/api/v1/health) and Streamlit (/_stcore/health).

Used in Dockerfile HEALTHCHECK without requiring external utilities like curl (Finding E4).
"""

import os
import sys
import urllib.request


def check_health() -> int:
    """Return 0 if either health endpoint responds with HTTP 200, else 1."""
    port = os.environ.get("PORT", "8080")
    for path in ("/api/v1/health", "/_stcore/health"):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"User-Agent": "HealthCheck/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return 0
        except Exception:
            continue
    return 1


if __name__ == "__main__":
    sys.exit(check_health())
