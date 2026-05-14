"""Fix Mode — diagnose and fix failing tests.

Called from Claude Code via the `diagnose_failure` and `auto_fix` MCP tools.
Reads the last failure captured by the watcher and pattern-matches the
pytest output against a small library of known failure modes.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Optional

try:
    from .config import LAST_FAILURE_PATH
except ImportError:  # pragma: no cover — direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.config import LAST_FAILURE_PATH  # type: ignore[no-redef]


# ─── Last-failure I/O ─────────────────────────────────────────────────────

def get_last_failure() -> Optional[dict[str, Any]]:
    """Read the last failure saved by the watcher."""
    if not os.path.exists(LAST_FAILURE_PATH):
        return None
    try:
        with open(LAST_FAILURE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ─── Pattern matchers — each returns a dict or None ──────────────────────

_MISSING_TABLE_RE = re.compile(
    r"Could not find the table ['\"]?public\.([\w_]+)['\"]?", re.IGNORECASE
)


def _missing_table(out: str) -> Optional[dict[str, str]]:
    m = _MISSING_TABLE_RE.search(out)
    if not m:
        return None
    return {
        "type": "missing_table",
        "table": m.group(1),
        "fix": (
            f"Create the `{m.group(1)}` table in the Supabase SQL Editor. "
            "Check `docs/bug-log/` for the canonical migration if it's "
            "an existing-but-deleted table."
        ),
    }


def _single_query(out: str) -> Optional[dict[str, str]]:
    if ".single()" in out or "PGRST116" in out:
        return {
            "type": "single_query",
            "fix": (
                "Replace `.single()` with `.execute()` and check "
                "`result.data` (empty list ≠ error). Convention in CLAUDE.md."
            ),
        }
    return None


def _auth_error(out: str) -> Optional[dict[str, str]]:
    if "401" in out or "User not allowed" in out:
        return {
            "type": "auth_error",
            "fix": (
                "Use `supabase_admin` (service-role) for backend writes — never "
                "the user-context `supabase` client (sprint-1 Bug 1.8)."
            ),
        }
    return None


def _permission_error(out: str) -> Optional[dict[str, str]]:
    if "403" in out:
        return {
            "type": "permission_error",
            "fix": (
                "Check role-based access: is the route gated by `require_admin` "
                "but the test using `rep_headers`? Or vice-versa?"
            ),
        }
    return None


def _not_found(out: str) -> Optional[dict[str, str]]:
    if "404" in out:
        return {
            "type": "not_found",
            "fix": (
                "Verify the URL path matches the route registration. Common "
                "trap: a static path was declared after a `{param}` route in "
                "the same router (sprint-2 Bug 2.8, sprint-3 Bug 3.9)."
            ),
        }
    return None


def _validation_error(out: str) -> Optional[dict[str, str]]:
    if "422" in out:
        return {
            "type": "validation_error",
            "fix": (
                "Request body doesn't match the Pydantic model. Compare the "
                "test JSON to the model's required fields and types."
            ),
        }
    return None


def _uuid_error(out: str) -> Optional[dict[str, str]]:
    if "invalid input syntax for type uuid" in out:
        return {
            "type": "friendly_identifier",
            "fix": (
                "Route called `.eq('id', value)` with a non-UUID friendly "
                "identifier (SKU / serial). Use the repository's "
                "`find_by_identifier` instead (sprint-2 Bugs 2.1–2.3)."
            ),
        }
    return None


_MATCHERS = (
    _missing_table,
    _single_query,
    _auth_error,
    _permission_error,
    _not_found,
    _validation_error,
    _uuid_error,
)


_SPRINT_FILE_HINTS: dict[str, list[str]] = {
    "sprint1": [
        "backend/app/routers/auth_router.py",
    ],
    "sprint2": [
        "backend/app/routers/inventory_router.py",
        "backend/app/services/inventory_service.py",
    ],
    "sprint3": [
        "backend/app/routers/machine_lifecycle.py",
        "backend/app/routers/warranty.py",
        "backend/app/routers/reservations.py",
        "backend/app/routers/issues.py",
        "backend/app/routers/notifications.py",
    ],
    "sprint4": [
        "backend/app/routers/dashboard.py",
        "backend/app/routers/notifications.py",
        "frontend/src/pages/Dashboard.tsx",
        "frontend/src/components/NotificationBell.tsx",
    ],
}


# ─── Public API ───────────────────────────────────────────────────────────

def analyze_failure(failure: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Pattern-match a failure into a structured diagnosis."""
    if not failure:
        return {
            "status": "no_failures",
            "message": "No recent test failures found",
        }

    output = failure.get("error_output", "") or ""
    patterns: list[dict[str, str]] = []
    for matcher in _MATCHERS:
        result = matcher(output)
        if result:
            patterns.append(result)

    sprint = failure.get("sprint", "") or ""
    suggested = []
    for key, files in _SPRINT_FILE_HINTS.items():
        if key in sprint:
            suggested = files
            break

    return {
        "status": "diagnosed",
        "file_changed": failure.get("file_changed"),
        "sprint": sprint,
        "failed_tests": failure.get("failed_tests", []) or [],
        "error_patterns": patterns,
        "suggested_files_to_check": suggested,
        "timestamp": failure.get("timestamp"),
    }


def format_diagnosis(diagnosis: dict[str, Any]) -> str:
    """Render a diagnosis as a human-readable markdown block."""
    if diagnosis.get("status") == "no_failures":
        return (
            "## No recent test failures\n\n"
            "Either everything is passing, or the watcher hasn't run yet. "
            "Start it with `.\\mcp_server\\agent\\watch.ps1` and save a "
            "file in `backend/app/` or `frontend/src/`."
        )

    lines: list[str] = ["## Test Failure Diagnosis", ""]
    if diagnosis.get("timestamp"):
        lines.append(f"_Captured: {diagnosis['timestamp']}_")
    lines.append(f"**File changed:** `{diagnosis.get('file_changed') or 'unknown'}`")
    lines.append(f"**Sprint:** `{diagnosis.get('sprint') or 'unknown'}`")

    failed = diagnosis.get("failed_tests") or []
    if failed:
        lines.append("")
        lines.append(f"**Failed tests ({len(failed)}):**")
        for name in failed[:15]:
            lines.append(f"  - `{name}`")
        if len(failed) > 15:
            lines.append(f"  - … and {len(failed) - 15} more")

    patterns = diagnosis.get("error_patterns") or []
    if patterns:
        lines.append("")
        lines.append("### Error patterns matched")
        for p in patterns:
            head = f"**{p['type']}**"
            if p.get("table"):
                head += f" (table: `{p['table']}`)"
            lines.append(f"- {head}: {p['fix']}")
    else:
        lines.append("")
        lines.append("_No known error pattern matched — open `last_failure.json` for the raw output._")

    suggested = diagnosis.get("suggested_files_to_check") or []
    if suggested:
        lines.append("")
        lines.append("### Files to check")
        for f in suggested:
            lines.append(f"  - `{f}`")

    return "\n".join(lines)
