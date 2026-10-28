"""Freeze the agent tool registry count after the domain-package split."""

from __future__ import annotations

import unittest

from projectionist.agent.tools import TOOL_DEFINITIONS, ToolRegistry, build_tool_definitions
from projectionist.config_store import FeatureFlags, Settings


# Frozen on the P1-B carve — bump only when adding/removing a real tool.
FROZEN_TOOL_COUNT = 65


class AgentToolRegistryCarveTests(unittest.TestCase):
    def test_tool_definition_count_is_frozen(self) -> None:
        names = [str((tool.get("function") or {}).get("name") or "") for tool in TOOL_DEFINITIONS]
        self.assertEqual(len(TOOL_DEFINITIONS), FROZEN_TOOL_COUNT)
        self.assertEqual(len(set(names)), FROZEN_TOOL_COUNT)
        self.assertNotIn("", names)

    def test_registry_handlers_match_definitions(self) -> None:
        defined = {str((tool.get("function") or {}).get("name") or "") for tool in TOOL_DEFINITIONS}
        handlers = {
            name[len("_tool_") :]
            for name in dir(ToolRegistry)
            if name.startswith("_tool_")
        }
        self.assertEqual(handlers, defined)

    def test_public_patch_surface_is_preserved(self) -> None:
        import projectionist.agent.tools as tools

        for name in (
            "TMDBClient",
            "RadarrClient",
            "SonarrClient",
            "SeerrClient",
            "search_library",
            "plex_collections_configuration_error",
            "_enrich_show_external_ids",
            "_dt",
        ):
            self.assertTrue(hasattr(tools, name), name)

    def test_build_tool_definitions_does_not_invent_tools(self) -> None:
        names = {
            str((tool.get("function") or {}).get("name") or "")
            for tool in build_tool_definitions(
                Settings(
                    features=FeatureFlags(
                        seerr_enabled=True,
                        plex_collections_enabled=True,
                    )
                )
            )
        }
        self.assertEqual(len(names), FROZEN_TOOL_COUNT)
        self.assertTrue(names <= {tool["function"]["name"] for tool in TOOL_DEFINITIONS})


if __name__ == "__main__":
    unittest.main()
