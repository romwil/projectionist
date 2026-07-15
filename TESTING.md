# Testing Guide

## Why Value-Based Tests

Shape-only tests (e.g., `assertIn("hidden_gems", result)`) verify that a key exists but never check the **value** behind it. This creates a dangerous blind spot: bugs that produce wrong numbers, wrong orderings, or wrong filter logic all pass as long as the response structure looks right.

### Real examples from this codebase

**hidden_gems bug:** The `get_library_snapshot` tool counted hidden gems with a SQL query that compared `vote_average >= 7.0`, but items with `vote_average = NULL` were silently included in the count. A shape-only test checking `assertIn("hidden_gems", result)` would pass — the key is present. A value-based test seeding 2 gems (unwatched + high-rated), 1 watched, 1 low-rated, and 1 NULL-rated, then asserting `assertEqual(result["hidden_gems"], 2)` catches the bug.

**keywords bug:** The `find_collection_gaps` tool accepted a `keywords` parameter, but text keywords were passed directly to the TMDB discover API without resolving them to keyword IDs first. Shape tests checking `assertIn("items", result)` would pass (the items key exists), but the returned films wouldn't match the keyword filter. A value-based test that mocks `search_keywords` and asserts `assertEqual(call_kwargs.get("with_keywords"), "9715")` catches the resolution bug.

### The principle

> If your test would still pass when the function returns the wrong answer, it's not testing anything useful.

## How to Write a Value-Based Test

### Step-by-step

1. **Create an ephemeral database** — each test gets a fresh SQLite file in a temp directory.
2. **Seed with explicit known data** — specify all nullable fields so there are no surprises from defaults.
3. **Call the function under test** — using the real database, not mocks (except for external APIs).
4. **Assert exact values** — use `assertEqual`, not `assertIn`. Check counts, orderings, specific field values.
5. **Test boundaries, NULLs, empty sets** — the bugs live at the edges.

### Code example

```python
import json
import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import DEFAULT_LENS_ID, Database


class TestLibraryCountsValues(unittest.TestCase):
    """Verify library_counts returns exact counts matching seeded data."""

    def test_exact_counts_by_media_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")

            # Step 2: Seed with explicit known data
            for rk, mt, title in [
                ("m1", "movie", "Movie A"),
                ("m2", "movie", "Movie B"),
                ("s1", "show", "Show A"),
            ]:
                db.upsert_library_item({
                    "rating_key": rk,
                    "media_type": mt,
                    "title": title,
                    "year": 2020,        # nullable field — specify it
                    "view_count": 0,     # nullable field — specify it
                    "vote_average": None, # explicitly test NULL handling
                })

            # Step 3: Call the function under test
            counts = db.library_counts()

            # Step 4: Assert exact values
            self.assertEqual(counts["movies"], 2)
            self.assertEqual(counts["shows"], 1)
            self.assertEqual(counts["items"], 3)

    def test_empty_library_returns_zeros(self):
        """Step 5: Test the empty/boundary case."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            counts = db.library_counts()
            self.assertEqual(counts["movies"], 0)
            self.assertEqual(counts["shows"], 0)
            self.assertEqual(counts["items"], 0)
```

## Test File Organization

| File | Purpose |
|------|---------|
| `tests/test_agent_tools_validation.py` | Value-based tests for agent tool methods (gaps, anniversaries, picks, patterns) |
| `tests/test_db_query_validation.py` | Value-based tests for Database query methods (telemetry, chat threads, preferences, embeddings, arr queue) |
| Other `tests/test_*.py` files | Feature-specific unit and integration tests |

## Running Tests

Run all tests:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=curatorx --cov-report=term-missing
```

Run a specific test file:

```bash
pytest tests/test_db_query_validation.py -v
```

Run a specific test class or method:

```bash
pytest tests/test_db_query_validation.py::TestTelemetrySummary -v
pytest tests/test_db_query_validation.py::TestTelemetrySummary::test_counts_grouped_by_event_class -v
```

Coverage is configured in `pyproject.toml` and runs automatically with `pytest`. The threshold is set to 10% (`--cov-fail-under=10`), which gives room to grow as tests are added.

## Adding Tests for New Tools

Every new `_tool_*` method in `curatorx/agent/tools.py` must have a corresponding value-based test before merging:

1. **Create a test class** named `Test<ToolName>Values` in the appropriate test file.
2. **Seed known data** — don't rely on fixtures that hide what's in the database.
3. **Assert exact return values** — verify counts, specific titles, field values, orderings.
4. **Cover at minimum:**
   - The happy path with known inputs/outputs
   - Empty/no-match case
   - Boundary values (exact limits, NULL fields, zero counts)
   - Filter parameters (genre, runtime, media type)
5. **Mock only external APIs** (TMDB, Radarr, Sonarr) — use a real SQLite database.
