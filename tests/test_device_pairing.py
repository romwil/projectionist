"""Apple TV sign-in codes, device bearer, revoke, and throw."""

from __future__ import annotations

import importlib
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.devices.pairing import (
    CLAIM_EXPIRED_DETAIL,
    CLAIM_INVALID_DETAIL,
    CLAIM_USED_DETAIL,
    CODE_ALPHABET,
    DEVICE_REVOKED_DETAIL,
    ISSUE_AGAIN_DETAIL,
    THROW_REVOKED_DETAIL,
    THROW_UNPAIRED_DETAIL,
    YOUTH_TITLE_DETAIL,
)
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache
from tests.owner_claim_helpers import grant_owner_claim

_CODE = re.compile(rf"^[{CODE_ALPHABET}]{{4}}-[{CODE_ALPHABET}]{{4}}$")


class DevicePairingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-device-pair-session-secret"
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        grant_owner_claim(self.client)
        self._enable_multi_user()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_ALLOW_OPEN_JOIN",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True, "open_auto_provision": True},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
        }
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing.update(payload)
            existing["features"] = {**existing.get("features", {}), **payload["features"]}
            payload = existing
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _plex_login(self, plex_id: int, title: str) -> dict:
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": plex_id, "title": title},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"token-{plex_id}"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["user"]

    def _issue(self) -> dict:
        resp = self.client.post("/api/devices/pair/issue", json={})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertNotIn("credential", body)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["expires_in_minutes"], 5)
        self.assertRegex(body["code"], _CODE)
        self.assertTrue(body["pending_id"])
        return body

    def _insert_title(self, rating_key: str, content_rating: str) -> None:
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
        now = time.time()

        def _write() -> None:
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO library_items (
                        rating_key, media_type, title, content_rating, updated_at
                    ) VALUES (?, 'movie', ?, ?, ?)
                    """,
                    (rating_key, rating_key, content_rating, now),
                )

        db.run_write(_write, label="test_insert_title")

    def test_single_use_claim_and_one_time_credential(self) -> None:
        self.client.cookies.delete(SESSION_COOKIE_NAME)
        unsigned = self.client.post("/api/devices/pair/claim", json={"code": "ABCD-EFGH"})
        self.assertEqual(unsigned.status_code, 401, unsigned.text)

        owner = self._plex_login(1, "Owner")
        self.assertEqual(owner["role"], "owner")
        member = self._plex_login(2, "Member")
        self.assertEqual(member["role"], "member")

        issued = self._issue()
        waiting = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
        self.assertEqual(waiting.status_code, 200, waiting.text)
        self.assertEqual(waiting.json()["status"], "pending")
        self.assertNotIn("credential", waiting.json())

        claimed = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        body = claimed.json()
        self.assertEqual(body["status"], "claimed")
        self.assertNotIn("credential", body)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        again = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["detail"], CLAIM_USED_DETAIL)

        self.client.cookies.clear()
        first = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
        self.assertEqual(first.status_code, 200, first.text)
        delivered = first.json()
        self.assertEqual(delivered["status"], "claimed")
        self.assertTrue(str(delivered["credential"]).startswith("cxd_"))
        self.assertEqual(delivered["member"]["id"], member["id"])
        self.assertEqual(delivered["member"]["role"], "member")
        self.assertFalse(delivered["member"]["is_youth"])

        second = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
        self.assertEqual(second.status_code, 410, second.text)
        self.assertEqual(second.json()["status"], "issue_again")
        self.assertEqual(second.json()["detail"], ISSUE_AGAIN_DETAIL)
        self.assertNotIn("credential", second.json())

    def test_rotate_kills_the_previous_code(self) -> None:
        self._plex_login(1, "Owner")
        issued = self._issue()
        rotated = self.client.post(
            "/api/devices/pair/rotate",
            json={"pending_id": issued["pending_id"]},
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        body = rotated.json()
        self.assertEqual(body["pending_id"], issued["pending_id"])
        self.assertNotEqual(body["code"], issued["code"])
        self.assertNotIn("credential", body)
        self.assertRegex(body["code"], _CODE)

        stale = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
        self.assertEqual(stale.status_code, 400, stale.text)
        self.assertEqual(stale.json()["detail"], CLAIM_INVALID_DETAIL)

        fresh = self.client.post("/api/devices/pair/claim", json={"code": body["code"]})
        self.assertEqual(fresh.status_code, 200, fresh.text)

    def test_expired_code_is_refused_and_rotate_mints_another(self) -> None:
        self._plex_login(1, "Owner")
        base = 1_800_000_000
        with patch("projectionist.devices.pairing._now", return_value=base):
            issued = self._issue()
        with patch(
            "projectionist.devices.pairing._now",
            return_value=base + 5 * 60 + 1,
        ):
            expired = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
            self.assertEqual(expired.status_code, 400, expired.text)
            self.assertEqual(expired.json()["detail"], CLAIM_EXPIRED_DETAIL)
            poll = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
            self.assertEqual(poll.status_code, 410, poll.text)
            self.assertEqual(poll.json()["status"], "issue_again")
            rotated = self.client.post(
                "/api/devices/pair/rotate",
                json={"pending_id": issued["pending_id"]},
            )
            self.assertEqual(rotated.status_code, 200, rotated.text)
            claimed = self.client.post(
                "/api/devices/pair/claim",
                json={"code": rotated.json()["code"]},
            )
            self.assertEqual(claimed.status_code, 200, claimed.text)

    def test_bearer_is_the_claiming_member_until_revoke(self) -> None:
        self._plex_login(1, "Owner")
        member = self._plex_login(2, "Living Room")
        issued = self._issue()
        claimed = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        device_id = claimed.json()["device_id"]
        self.client.cookies.clear()
        delivered = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
        credential = delivered.json()["credential"]
        headers = {"Authorization": f"Bearer {credential}"}

        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["id"], member["id"])
        self.assertEqual(me.json()["user"]["role"], "member")
        self.assertEqual(me.json()["user"]["display_name"], "Living Room")

        segment = self.client.get(
            "/api/library/playback/notasess1/index.m3u8",
            headers=headers,
        )
        self.assertNotEqual(segment.status_code, 401, segment.text)
        self.assertNotIn(
            segment.json().get("detail"), {DEVICE_REVOKED_DETAIL, "Authentication required"}
        )

        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        owner = self._plex_login(1, "Owner")
        self.assertEqual(owner["role"], "owner")
        station = self.client.post(
            f"/api/devices/{device_id}/throw",
            json={"kind": "station", "station_id": "4"},
        )
        self.assertEqual(station.status_code, 200, station.text)
        station_intent = self.client.get("/api/devices/me/intent", headers=headers)
        self.assertEqual(station_intent.status_code, 200, station_intent.text)
        self.assertEqual(
            station_intent.json()["intent"],
            {"id": station.json()["intent_id"], "kind": "station", "station_id": "4"},
        )

        revoked = self.client.post(f"/api/devices/{device_id}/revoke")
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["status"], "revoked")

        after = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(after.status_code, 401, after.text)
        self.assertEqual(after.json()["detail"], DEVICE_REVOKED_DETAIL)
        segment_after = self.client.get(
            "/api/library/playback/notasess1/index.m3u8",
            headers=headers,
        )
        self.assertEqual(segment_after.status_code, 401, segment_after.text)
        self.assertEqual(segment_after.json()["detail"], DEVICE_REVOKED_DETAIL)

        thrown = self.client.post(
            f"/api/devices/{device_id}/throw",
            json={
                "kind": "title",
                "media_type": "movie",
                "item_id": "does-not-matter",
                "id_type": "rating_key",
            },
        )
        self.assertEqual(thrown.status_code, 409, thrown.text)
        self.assertEqual(thrown.json()["detail"], THROW_REVOKED_DETAIL)

        missing = self.client.post(
            "/api/devices/00000000-0000-0000-0000-000000000000/throw",
            json={"kind": "station", "station_id": "4"},
        )
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["detail"], THROW_UNPAIRED_DETAIL)

        still = self.client.get("/api/auth/me")
        self.assertEqual(still.status_code, 200, still.text)
        self.assertEqual(still.json()["user"]["id"], owner["id"])

    def test_throw_title_or_station_and_youth_ceiling(self) -> None:
        self._plex_login(1, "Owner")
        member = self._plex_login(2, "Youth")
        issued = self._issue()
        claimed = self.client.post("/api/devices/pair/claim", json={"code": issued["code"]})
        device_id = claimed.json()["device_id"]
        self.client.cookies.clear()
        delivered = self.client.get(f"/api/devices/pair/pending/{issued['pending_id']}")
        credential = delivered.json()["credential"]
        headers = {"Authorization": f"Bearer {credential}"}

        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.set_user_youth(member["id"], True)
        youth = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(youth.status_code, 200, youth.text)
        self.assertTrue(youth.json()["user"]["is_youth"])
        self.assertEqual(youth.json()["user"]["id"], member["id"])

        self._insert_title("rk-pg", "PG")
        self._insert_title("rk-r", "R")
        self._plex_login(1, "Owner")

        blocked = self.client.post(
            f"/api/devices/{device_id}/throw",
            json={
                "kind": "title",
                "media_type": "movie",
                "item_id": "rk-r",
                "id_type": "rating_key",
            },
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"], YOUTH_TITLE_DETAIL)

        queued = self.client.post(
            f"/api/devices/{device_id}/throw",
            json={
                "kind": "title",
                "media_type": "movie",
                "item_id": "rk-pg",
                "id_type": "rating_key",
            },
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["status"], "queued")

        intent = self.client.get("/api/devices/me/intent", headers=headers)
        self.assertEqual(intent.status_code, 200, intent.text)
        self.assertEqual(
            intent.json()["intent"],
            {
                "id": queued.json()["intent_id"],
                "kind": "title",
                "media_type": "movie",
                "item_id": "rk-pg",
                "id_type": "rating_key",
            },
        )
        empty = self.client.get("/api/devices/me/intent", headers=headers)
        self.assertEqual(empty.json()["intent"], None)
