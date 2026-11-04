"""docs/PRIVACY.md (rendered at /privacy) may only claim what the code does (PRIV-024).

Each claim below is pinned to the regression tests that prove it, or to a check
in this file. Adding a "We do not" bullet without a backing test fails here;
deleting or renaming a backing test fails here; and sentences the code cannot
keep are rejected outright.
"""

from __future__ import annotations

import ast
import re
import unittest
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "PRIVACY.md"

# Each "We do not" bullet -> tests that fail if the promise breaks.
WE_DO_NOT: Dict[str, List[str]] = {
    "Sell household data, or train a Projectionist-hosted model on your chats": [
        "tests/test_privacy_contract.py::NoPhoneHomeTests::test_outbound_hosts_are_third_party_services",
    ],
    "Require a Projectionist cloud account, or send analytics anywhere": [
        "tests/test_privacy_contract.py::NoPhoneHomeTests::test_outbound_hosts_are_third_party_services",
    ],
    "Expose live `X-Plex-Token` media URLs through privacy MCP or member library views": [
        "tests/test_mcp_privacy.py::PrivacySchemaTests::test_public_drops_infra_and_adds_watch_state",
        "tests/test_mcp_privacy.py::PrivacySchemaTests::test_internal_keeps_rating_key_strips_token",
    ],
    "Let a privacy MCP key, or a mode flag, unlock full MCP": [
        "tests/test_mcp_privacy.py::McpHttpKeyModeTests::test_privacy_key_maps_to_privacy",
        "tests/test_mcp_privacy.py::McpHttpKeyModeTests::test_equal_keys_refuse_full",
        "tests/test_mcp_full_mode.py::FullModeAuthTests::test_wrong_key_does_not_escalate",
    ],
    "Hand MCP clients the Plex server token, AI provider key, or `settings.json`": [
        "tests/test_mcp_full_mode.py::FullSchemaTests::test_full_allows_rating_key_never_token",
        "tests/test_privacy_contract.py::McpSecretsTests::test_mcp_package_never_reads_provider_or_session_secrets",
    ],
    "Store raw microphone audio": [
        "tests/test_privacy_contract.py::NoAudioUploadTests::test_only_file_upload_is_the_avatar",
    ],
    "Let members add Apprise destinations, or confirm Radarr/Sonarr adds unless the owner turned on **Without my confirm** for that adult member (each such add is in the security log with the member and title, never their chat or memory)": [
        "tests/test_trust_phase1.py::AppriseOwnerOnlyTests::test_member_cannot_set_or_test_apprise_urls",
        "tests/test_trust_phase1.py::AcquisitionRouteTests::test_member_and_youth_cannot_confirm_their_own_add_token",
        "tests/test_member_autoconfirm_adds.py::AutoconfirmAddRouteTests::test_flag_off_member_still_cannot_add",
        "tests/test_member_autoconfirm_adds.py::AutoconfirmAddRouteTests::test_autoconfirm_member_add_runs_and_writes_audit_without_memory",
        "tests/test_member_autoconfirm_adds.py::AutoconfirmToggleRouteTests::test_youth_and_owner_accounts_cannot_carry_autoconfirm",
    ],
    'Use someone else\'s viewing to write your "You watched" lines': [
        "tests/test_trust_phase1.py::OwnEvidenceTests::test_member_only_sees_own_seed",
        "tests/test_trust_phase1.py::OwnEvidenceTests::test_member_without_history_gets_no_seeds",
    ],
    "Pretend a Plex list publish worked when Plex refused it": [
        "tests/test_curated_lists.py::CuratedListsDbTests::test_plex_lists_publish_is_deferred",
    ],
    "Bring back a removed account, or data a member deleted, when the owner restores a backup": [
        "tests/test_privacy_registry.py::RestoreAfterErasureTests::test_restore_does_not_bring_back_a_removed_account",
        "tests/test_privacy_registry.py::RestoreAfterErasureTests::test_restore_reapplies_delete_my_data_to_older_snapshots_only",
    ],
}

# Other claims on the page -> what proves them.
CLAIMS: Dict[str, List[str]] = {
    r"It never shows who did what": [
        "tests/test_runtime_pulse.py::HouseholdPulseTests::test_pulse_has_no_member_breakdown",
    ],
    r"records that an owner looked, with the account id and nothing else": [
        "tests/test_runtime_pulse.py::HouseholdPulseTests::test_pulse_view_is_recorded_with_user_id_only",
    ],
    r"Owners read them at `GET /api/admin/runtime`": [
        "tests/test_runtime_pulse.py::RuntimeRouteTests::test_owner_sees_queue_depth_and_latency",
        "tests/test_runtime_pulse.py::RuntimeRouteTests::test_member_gets_403",
    ],
    r"\*\*Settings → My data\*\*": [
        "tests/test_privacy_contract.py::MyDataPageTests::test_settings_has_a_my_data_route",
    ],
    r"Download my data\.\*\* One file with everything": [
        "tests/test_privacy_registry.py::ExportScopeTests::test_export_has_every_export_store_and_no_other_member",
    ],
    r"A readable version includes your chat messages": [
        "tests/test_privacy_registry.py::MyDataApiTests::test_markdown_export_includes_message_text",
    ],
    r"Delete my data\.\*\* Removes all of that except your account": [
        "tests/test_privacy_registry.py::AccountDeletionTests::test_delete_my_data_keeps_the_account_and_clears_the_rest",
        "tests/test_privacy_registry.py::MyDataApiTests::test_delete_my_data_needs_the_phrase_and_spares_others",
    ],
    r"A deleted note is gone, not hidden": [
        "tests/test_privacy_registry.py::MyDataApiTests::test_note_delete_is_scoped_to_the_caller",
    ],
    r"you can't reach anyone else's": [
        "tests/test_privacy_registry.py::MyDataApiTests::test_member_export_is_their_own_only",
    ],
    r"Account removal runs as one database transaction": [
        "tests/test_privacy_registry.py::AccountDeletionTests::test_delete_user_is_one_transaction",
    ],
    r"deleted chat text isn't left readable in the database files": [
        "tests/test_privacy_registry.py::AccountDeletionTests::test_deleted_chat_text_is_not_left_on_disk",
    ],
    r"The uploaded profile picture is deleted from disk": [
        "tests/test_privacy_registry.py::MyDataApiTests::test_owner_removal_clears_the_avatar_file",
    ],
    r"If that file can't be read, restore refuses": [
        "tests/test_privacy_registry.py::RestoreAfterErasureTests::test_restore_refuses_when_the_ledger_is_unreadable",
    ],
    r"A test fails when a new column that looks like an account link": [
        "tests/test_privacy_registry.py::SchemaContractTests::test_every_person_linked_column_is_registered",
        "tests/test_privacy_registry.py::SchemaContractTests::test_privacy_doc_table_is_generated_from_the_registry",
    ],
    r"Projectionist does not phone home": [
        "tests/test_privacy_contract.py::NoPhoneHomeTests::test_outbound_hosts_are_third_party_services",
    ],
}

# Sentences the code cannot keep. Each needs a code change and a CLAIMS entry first.
FORBIDDEN = [
    r"full copy of its own data",
    r"nothing (is )?left behind",
    r"leave anything behind",
    r"permanently delete",
    r"removes? (it|them|your data) from (every|all) backups?",
    r"no Download my data",
    r"verified in `projectionist",
]

# Hosts the code may contact or link to. All are services the owner configures,
# public artwork/metadata sources, or documentation links. None is run by Projectionist.
ALLOWED_HOSTS = {
    "api.openai.com", "api.anthropic.com", "openrouter.ai", "generativelanguage.googleapis.com",
    "api.together.xyz", "api.mistral.ai", "api.groq.com", "api.deepseek.com",
    "plex.tv", "app.plex.tv", "discover.provider.plex.tv",
    "api.themoviedb.org", "image.tmdb.org", "api4.thetvdb.com", "artworks.thetvdb.com",
    "webservice.fanart.tv", "assets.fanart.tv", "www.omdbapi.com", "en.wikipedia.org",
    "api.open-meteo.com", "geocoding-api.open-meteo.com", "api.resend.com", "api.opensubtitles.com",
    "www.youtube.com", "www.youtube-nocookie.com", "www.w3.org",
    # Links and User-Agent strings only; nothing is fetched from these.
    "github.com", "hub.docker.com",
}
FORBIDDEN_HOST_HINTS = ("projectionist", "automat", "telemetry", "analytics", "segment", "sentry", "posthog")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _we_do_not_bullets() -> List[str]:
    doc = _doc()
    section = doc[doc.index("## We do not") :]
    section = section[: section.index("\n---")]
    return [line[2:].strip() for line in section.splitlines() if line.startswith("- ")]


@lru_cache(maxsize=None)
def _test_names(path: str) -> Set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    names.add(f"{node.name}::{item.name}")
                    names.add(f"*::{item.name}")
    return names


def _assert_test_exists(case: unittest.TestCase, node_id: str) -> None:
    path, _, rest = node_id.partition("::")
    case.assertTrue((ROOT / path).is_file(), node_id)
    case.assertIn(rest, _test_names(path), f"Backing test is gone: {node_id}")


class PrivacyContractTests(unittest.TestCase):
    def test_every_we_do_not_bullet_is_backed_by_a_test(self) -> None:
        bullets = _we_do_not_bullets()
        self.assertTrue(bullets)
        unbacked = [b for b in bullets if b not in WE_DO_NOT]
        self.assertEqual(unbacked, [], "Add each new bullet to WE_DO_NOT with the test that proves it")
        for bullet in bullets:
            for node_id in WE_DO_NOT[bullet]:
                _assert_test_exists(self, node_id)

    def test_every_pinned_claim_is_on_the_page_and_backed(self) -> None:
        doc = _doc()
        for pattern, node_ids in CLAIMS.items():
            self.assertRegex(doc, pattern, f"Claim is pinned but no longer on the page: {pattern}")
            for node_id in node_ids:
                _assert_test_exists(self, node_id)

    def test_page_has_no_sentence_the_code_cannot_keep(self) -> None:
        doc = _doc()
        for pattern in FORBIDDEN:
            self.assertNotRegex(doc, re.compile(pattern, re.IGNORECASE))

    def test_faq_repeats_no_retired_promise(self) -> None:
        faq = (ROOT / "docs" / "FAQ.md").read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            self.assertNotRegex(faq, re.compile(pattern, re.IGNORECASE))

    def test_backups_are_disclosed_alongside_deletion(self) -> None:
        doc = _doc()
        self.assertRegex(doc, r"daily backups made before you left still hold your data")
        self.assertRegex(doc, r"Backups the owner downloaded and keeps somewhere else are out of Projectionist's reach")


class NoPhoneHomeTests(unittest.TestCase):
    def test_outbound_hosts_are_third_party_services(self) -> None:
        host_re = re.compile(r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
        found: Dict[str, str] = {}
        paths = list((ROOT / "projectionist").rglob("*.py"))
        for ext in ("ts", "tsx", "js", "jsx"):
            paths += [
                p for p in (ROOT / "frontend" / "src").rglob(f"*.{ext}") if ".test." not in p.name
            ]
        for path in paths:
            for host in host_re.findall(path.read_text(encoding="utf-8", errors="ignore")):
                found.setdefault(host.lower(), str(path.relative_to(ROOT)))
        unexpected = {h: p for h, p in found.items() if h not in ALLOWED_HOSTS}
        self.assertEqual(unexpected, {}, "New outbound host: add it to PRIVACY.md and ALLOWED_HOSTS")
        for host in found:
            self.assertFalse(any(hint in host for hint in FORBIDDEN_HOST_HINTS), host)


class McpSecretsTests(unittest.TestCase):
    def test_mcp_package_never_reads_provider_or_session_secrets(self) -> None:
        for path in (ROOT / "projectionist" / "mcp").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in ("llm_api_key", "session_secret", "webhook_secret"):
                self.assertNotIn(name, text, f"{path.name} reads {name}")
            self.assertNotRegex(text, r"[\"']settings\.json[\"']", f"{path.name} opens settings.json")


class NoAudioUploadTests(unittest.TestCase):
    def test_only_file_upload_is_the_avatar(self) -> None:
        uploads = []
        for path in (ROOT / "projectionist").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            uploads += [f"{path.name}:{m}" for m in re.findall(r"(\w+): UploadFile", text)]
        self.assertEqual(uploads, ["auth_routes.py:file"])
        routes = (ROOT / "projectionist" / "web" / "auth_routes.py").read_text(encoding="utf-8")
        self.assertRegex(routes, r'@router\.(post|put)\("/api/auth/me/avatar"\)')


class MyDataPageTests(unittest.TestCase):
    def test_settings_has_a_my_data_route(self) -> None:
        routes = (ROOT / "frontend" / "src" / "AppRoutes.tsx").read_text(encoding="utf-8")
        self.assertRegex(routes, r'<Route path="privacy" element=\{<MyDataPage />\}')
        page = (ROOT / "frontend" / "src" / "pages" / "settings" / "MyDataPage.tsx").read_text(encoding="utf-8")
        for call in ("exportMyData", "deleteMyMemoryNote", "eraseMyData", "listMyMemoryNotes"):
            self.assertIn(call, page)
        self.assertNotIn("/users/", page, "My data acts on the signed-in account, not by user id")


if __name__ == "__main__":
    unittest.main()
