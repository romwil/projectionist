"""Investigate Apply stays off until the owner opts in and the library is writable."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.library.episode_investigate.rename_gate import (
    LIBRARY_READONLY,
    RENAMES_OFF,
    file_rename_refusal,
    file_rename_status,
)


class FileRenameGateTests(unittest.TestCase):
    def test_default_is_off(self) -> None:
        reason = file_rename_refusal(Settings(), roots=[])
        self.assertEqual(reason, RENAMES_OFF)
        self.assertFalse(file_rename_status(Settings(), roots=[])["allowed"])

    def test_flag_without_a_folder_refuses(self) -> None:
        settings = Settings()
        settings.features.allow_file_renames = True
        self.assertIn("not mounted", file_rename_refusal(settings, roots=[]) or "")

    def test_read_only_folder_refuses(self) -> None:
        settings = Settings()
        settings.features.allow_file_renames = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "projectionist.library.episode_investigate.rename_gate.os.access",
                return_value=False,
            ):
                self.assertEqual(file_rename_refusal(settings, roots=[root]), LIBRARY_READONLY)

    def test_writable_folder_and_flag_allow(self) -> None:
        settings = Settings()
        settings.features.allow_file_renames = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(os.access(root, os.W_OK))
            self.assertIsNone(file_rename_refusal(settings, roots=[root]))
            self.assertTrue(file_rename_status(settings, roots=[root])["allowed"])
