"""Client-facing route set and OpenAPI snapshot (NAT-003).

A native client may call the routes in ``CLIENT_ROUTES``. They are tagged
``client`` after the app finishes mounting. Admin routes are not in the set.
``scripts/export-openapi.sh`` writes the filtered snapshot; CI fails when the
mounted client routes drift from ``docs/api/openapi.json``.

Production leaves ``PROJECTIONIST_EXPOSE_OPENAPI`` unset, so ``/openapi.json``
stays dark. The snapshot is a file, not a live document.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from fastapi.routing import APIRoute

from projectionist.web.capabilities import API_CONTRACT

CLIENT_TAG = "client"
SNAPSHOT_PATH = "docs/api/openapi.json"

# Paths are the templates FastAPI stores on the route (including ``{path:path}``).
# Claim, revoke, and throw stay off this list: a signed-in web member uses them.
# The device reads ``GET /api/devices/me/intent``.
CLIENT_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/features"),
        ("POST", "/api/devices/pair/issue"),
        ("POST", "/api/devices/pair/rotate"),
        ("GET", "/api/devices/pair/pending/{pending_id}"),
        ("GET", "/api/auth/me"),
        ("PATCH", "/api/auth/me"),
        ("GET", "/api/devices/me/intent"),
        ("GET", "/api/library/feeds/hub"),
        ("GET", "/api/library/feeds/tonight-table"),
        ("GET", "/api/library/query"),
        ("GET", "/api/title/{media_type}/{item_id}"),
        ("GET", "/api/library/art/{media_type}/{item_id}"),
        ("POST", "/api/library/playback/start"),
        ("POST", "/api/library/playback/{session_id}/seek"),
        ("POST", "/api/library/playback/{session_id}/progress"),
        ("POST", "/api/library/playback/{session_id}/stop"),
        ("POST", "/api/library/playback/{session_id}/subtitles"),
        ("GET", "/api/library/playback/{session_id}/index.m3u8"),
        ("GET", "/api/library/playback/{session_id}/master.m3u8"),
        ("GET", "/api/library/playback/{session_id}/{path:path}"),
        ("GET", "/api/live-channels/on-now"),
        ("GET", "/api/live-channels/guide"),
        ("POST", "/api/live-channels/tune"),
        ("GET", "/api/live/weather"),
        ("GET", "/api/live/weather/audio/{name}"),
        ("GET", "/api/live/weather/image/{image_id}"),
    }
)


def iter_api_routes(router: Any) -> Iterable[APIRoute]:
    """Yield mounted API routes, including routers FastAPI has not flattened."""
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            yield route
            continue
        nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from iter_api_routes(nested)
            continue
        if hasattr(route, "routes"):
            yield from iter_api_routes(route)


def _methods(route: APIRoute) -> set[str]:
    return {method for method in (route.methods or set()) if method != "HEAD"}


def tag_client_routes(app: Any) -> None:
    """Mark ``CLIENT_ROUTES`` with the ``client`` tag. Raises if one is missing."""
    found: set[tuple[str, str]] = set()
    for route in iter_api_routes(app):
        for method in _methods(route):
            key = (method, route.path)
            if key not in CLIENT_ROUTES:
                continue
            tags = list(route.tags or [])
            if CLIENT_TAG not in tags:
                tags.append(CLIENT_TAG)
                route.tags = tags
            found.add(key)
    missing = CLIENT_ROUTES - found
    if missing:
        listed = ", ".join(f"{method} {path}" for method, path in sorted(missing))
        raise RuntimeError(f"Client routes are not mounted: {listed}")
    app.openapi_schema = None


def tagged_client_routes(app: Any) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in iter_api_routes(app):
        if CLIENT_TAG not in (route.tags or []):
            continue
        for method in _methods(route):
            found.add((method, route.path))
    return found


def _collect_refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            found.add(ref)
        for value in node.values():
            _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def _lookup_ref(schema: dict[str, Any], ref: str) -> Any:
    node: Any = schema
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(ref)
        node = node[part]
    return node


def _sort_tags(node: Any) -> None:
    if isinstance(node, dict):
        tags = node.get("tags")
        if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
            node["tags"] = sorted(tags)
        for value in node.values():
            _sort_tags(value)
    elif isinstance(node, list):
        for item in node:
            _sort_tags(item)


def client_openapi_document(app: Any) -> dict[str, Any]:
    """OpenAPI document limited to client-tagged operations and the schemas they use."""
    tag_client_routes(app)
    app.openapi_schema = None
    schema = app.openapi()
    paths: dict[str, Any] = {}
    for path, operations in schema.get("paths", {}).items():
        if not isinstance(operations, dict):
            continue
        kept = {
            method: operation
            for method, operation in operations.items()
            if isinstance(operation, dict) and CLIENT_TAG in (operation.get("tags") or [])
        }
        if kept:
            paths[path] = kept
    _sort_tags(paths)
    needed: set[str] = set()
    _collect_refs(paths, needed)
    components: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    while needed - seen:
        for ref in sorted(needed - seen):
            seen.add(ref)
            target = _lookup_ref(schema, ref)
            _collect_refs(target, needed)
            parts = ref.lstrip("#/").split("/")
            if len(parts) < 3 or parts[0] != "components":
                continue
            components.setdefault(parts[1], {})[parts[2]] = target
    document: dict[str, Any] = {
        "openapi": schema.get("openapi", "3.1.0"),
        "info": {
            "title": "Projectionist client API",
            "version": str(API_CONTRACT),
            "description": (
                "Routes a native client may call. Admin routes are not included. "
                "Regenerate with scripts/export-openapi.sh. "
                "PROJECTIONIST_EXPOSE_OPENAPI stays unset in production."
            ),
        },
        "paths": paths,
    }
    if components:
        document["components"] = components
    return document


def render_client_openapi(app: Any) -> str:
    return json.dumps(client_openapi_document(app), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    from projectionist.web.app import app

    rendered = render_client_openapi(app)
    path = Path(SNAPSHOT_PATH)
    if check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != rendered:
            sys.stderr.write(
                "docs/api/openapi.json does not match the client routes.\n"
                "Regenerate it with scripts/export-openapi.sh\n"
            )
            return 1
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
