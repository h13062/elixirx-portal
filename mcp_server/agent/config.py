"""Agent configuration."""

import os

PROJECT_ROOT = os.environ.get(
    "PROJECT_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
TESTS_DIR = os.path.join(BACKEND_DIR, "tests")
MCP_DIR = os.path.join(PROJECT_ROOT, "mcp_server")

# Where the watcher writes the last failure so other tools can read it.
LAST_FAILURE_PATH = os.path.join(MCP_DIR, "agent", "last_failure.json")


# Filename → pytest marker. The watcher matches the changed file's basename
# against this map first; if the marker contains `_N` it is treated as a
# task-level marker (faster feedback), otherwise sprint-level.
#
# Add a row whenever a feature warrants its own task marker; the map should
# never contain a marker that isn't declared in `backend/pytest.ini`.
FILE_TO_MARKER: dict[str, str] = {
    # ── Sprint 1 — Auth ───────────────────────────────────────────────
    "auth.py":          "sprint1",
    "auth_router.py":   "sprint1",
    "auth_service.py":  "sprint1",

    # ── Sprint 2 — Inventory ──────────────────────────────────────────
    "inventory.py":          "sprint2",
    "inventory_router.py":   "sprint2",
    "inventory_service.py":  "sprint2",

    # ── Sprint 3 — Machine lifecycle, warranty, …  (task level) ──────
    "machine_lifecycle.py":          "sprint3_1",
    "machine_lifecycle_service.py":  "sprint3_1",
    "warranty.py":                   "sprint3_2",
    "warranty_service.py":           "sprint3_2",
    "reservations.py":               "sprint3_3",
    "reservation_service.py":        "sprint3_3",
    "issues.py":                     "sprint3_4",
    "issue_service.py":              "sprint3_4",
    "notifications.py":              "sprint3_5",
    "notification_helper.py":        "sprint3_5",

    # ── Sprint 4 — Dashboard & widgets  (task level) ─────────────────
    "dashboard.py":          "sprint4_0",
    "dashboard_models.py":   "sprint4_0",
}


# Path-segment fallback used only when FILE_TO_MARKER misses. Keyed by a
# substring of the path (lowercase), value is the marker to run.
PATH_FALLBACK_MARKERS: dict[str, str] = {
    "/auth":              "sprint1",
    "/inventory":         "sprint2",
    "/machine_lifecycle": "sprint3_1",
    "/warranty":          "sprint3_2",
    "/reservations":      "sprint3_3",
    "/issues":            "sprint3_4",
    "/notifications":     "sprint3_5",
    "/dashboard":         "sprint4_0",
}


# Watch settings
DEBOUNCE_SECONDS = 1.5
IGNORE_PATTERNS = ["__pycache__", "node_modules", ".git", "venv", "dist", ".pyc"]


# ── Back-compat shim ──────────────────────────────────────────────────
# The first cut of the watcher exposed `SPRINT_MAP` as a simple
# keyword → sprint mapping. Anything still importing it (e.g. older
# scripts, the reviewer's smoke-tests) gets a synthesized view: every
# task-level marker collapsed to its sprint root.
def _derive_sprint_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for fname, marker in FILE_TO_MARKER.items():
        # Strip _router / _service / .py to get a feature key.
        stem = fname[:-3] if fname.endswith(".py") else fname
        for suffix in ("_router", "_service", "_helper", "_models"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        sprint = marker.split("_", 1)[0]  # "sprint3_2" → "sprint3"
        out.setdefault(stem, sprint)
    return out


SPRINT_MAP: dict[str, str] = _derive_sprint_map()
