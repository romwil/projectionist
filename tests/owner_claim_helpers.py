"""Give a test client the one-time owner claim (SEC-008).

Tests that start ownerless and expect their first Plex/OIDC sign-in to become
owner must hold the claim, the same as the browser that turned sign-in on.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from projectionist.web.owner_claim import OWNER_CLAIM_COOKIE, issue_owner_claim


def grant_owner_claim(client: TestClient, db=None) -> str:
    if db is None:
        import projectionist.web.jobs as jobs

        db = jobs.get_job_manager().db
    raw = issue_owner_claim(db)
    for cookie in list(client.cookies.jar):
        if cookie.name == OWNER_CLAIM_COOKIE:
            client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    client.cookies.set(OWNER_CLAIM_COOKIE, raw)
    return raw
