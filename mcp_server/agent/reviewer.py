"""Review Mode — pre-push checks.

Six checks, each best-effort and reported independently so a failure in one
doesn't hide the others:

  1. Run the full pytest suite.
  2. Scan backend/app for debug artifacts (print, breakpoint, pdb, ...).
  3. Verify .env files are properly gitignored and not staged.
  4. Scan backend/app for hardcoded secrets.
  5. Compare router files to test files and report coverage gaps.
  6. Aggregate into a JSON report + a coloured summary.

Run:

    python -m mcp_server.agent.reviewer
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .config import BACKEND_DIR, FRONTEND_DIR, PROJECT_ROOT, TESTS_DIR
except ImportError:  # pragma: no cover — direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.config import (  # type: ignore[no-redef]
        BACKEND_DIR,
        FRONTEND_DIR,
        PROJECT_ROOT,
        TESTS_DIR,
    )


class C:
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    DIM = "\033[2m"
    RESET = "\033[0m"


# ─── Helpers ──────────────────────────────────────────────────────────────

def _walk_py(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune noisy / vendor dirs.
        dirnames[:] = [
            d for d in dirnames
            if d not in {"__pycache__", "node_modules", ".git", "venv", "dist"}
        ]
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def _is_test_file(path: str) -> bool:
    base = os.path.basename(path).lower()
    return base.startswith("test_") or base == "conftest.py" or "/tests/" in path.replace("\\", "/")


_PYTEST_SUMMARY = re.compile(
    r"(?P<passed>\d+) passed|(?P<failed>\d+) failed|(?P<errors>\d+) errors?",
)


# 1. ─── Run tests ────────────────────────────────────────────────────────

def run_tests() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short",
             "--color=no"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 0, "summary": "TIMEOUT", "ok": False}
    except FileNotFoundError as e:
        return {"total": 0, "passed": 0, "failed": 0, "summary": f"ERROR: {e}", "ok": False}

    out = (completed.stdout or "") + (completed.stderr or "")
    last_lines = [ln for ln in out.splitlines() if ln.strip()]
    summary = last_lines[-1] if last_lines else "(empty output)"

    passed = sum(int(m.group(1)) for m in re.finditer(r"(\d+) passed", out))
    failed = sum(int(m.group(1)) for m in re.finditer(r"(\d+) failed", out))
    errors = sum(int(m.group(1)) for m in re.finditer(r"(\d+) errors?", out))

    return {
        "total": passed + failed + errors,
        "passed": passed,
        "failed": failed + errors,
        "summary": summary,
        "ok": completed.returncode == 0,
    }


# 2. ─── Debug artifacts ──────────────────────────────────────────────────

_DEBUG_NEEDLES = [
    "print(",
    "console.log",
    "debugger",
    "import pdb",
    "pdb.set_trace",
    "breakpoint()",
]


def find_debug_artifacts() -> list[str]:
    hits: list[str] = []
    app_dir = os.path.join(BACKEND_DIR, "app")
    if not os.path.isdir(app_dir):
        return hits
    for path in _walk_py(app_dir):
        if _is_test_file(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if "# noqa" in line or "# review-ok" in line:
                        continue
                    for needle in _DEBUG_NEEDLES:
                        if needle in line:
                            rel = os.path.relpath(path, PROJECT_ROOT)
                            hits.append(f"{rel}:{i}: {line.strip()[:100]}")
                            break
        except OSError:
            continue
    return hits


# 3. ─── .env exposure ────────────────────────────────────────────────────

def check_env_exposure() -> dict[str, Any]:
    """Verify .env paths are gitignored and not currently staged."""
    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    required = ["backend/.env", "frontend/.env"]
    missing_from_gitignore: list[str] = []

    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        for entry in required:
            # A simple "is the string present" check; more rigorous parsing isn't
            # worth it for this guardrail.
            if entry not in content and entry.split("/")[-1] not in content:
                missing_from_gitignore.append(entry)
    else:
        missing_from_gitignore = list(required)

    staged_env: list[str] = []
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in out.stdout.splitlines():
            ln = line.strip()
            if ln.endswith(".env") or ".env." in ln:
                staged_env.append(ln)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    safe = not missing_from_gitignore and not staged_env
    return {
        "safe": safe,
        "missing_from_gitignore": missing_from_gitignore,
        "staged_env_files": staged_env,
    }


# 4. ─── Hardcoded secrets ────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r'password\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
    re.compile(r'api[_-]?key\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
    re.compile(r'secret\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
    re.compile(r'token\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
]

# Allowlist: anything pointing at env vars or known placeholders.
_ALLOW_NEEDLES = (
    "os.environ",
    "os.getenv",
    "getenv(",
    "<",  # things like password="<your password>"
    "...",
    "settings.",
    "self.",  # method args / model assignments
)


def find_hardcoded_secrets() -> list[str]:
    hits: list[str] = []
    for root in (os.path.join(BACKEND_DIR, "app"),):
        if not os.path.isdir(root):
            continue
        for path in _walk_py(root):
            if _is_test_file(path) or path.endswith(".env.example"):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        if any(a in stripped for a in _ALLOW_NEEDLES):
                            continue
                        for pat in _SECRET_PATTERNS:
                            if pat.search(line):
                                rel = os.path.relpath(path, PROJECT_ROOT)
                                hits.append(f"{rel}:{i}: {stripped[:100]}")
                                break
            except OSError:
                continue
    return hits


# 5. ─── Coverage gaps ────────────────────────────────────────────────────

def find_coverage_gaps() -> list[str]:
    routers_dir = os.path.join(BACKEND_DIR, "app", "routers")
    if not os.path.isdir(routers_dir) or not os.path.isdir(TESTS_DIR):
        return []

    routers = [
        f for f in os.listdir(routers_dir)
        if f.endswith(".py") and f != "__init__.py"
    ]
    test_files = {f for f in os.listdir(TESTS_DIR) if f.endswith(".py")}

    # Tolerant mapping: warranty.py → test_warranty.py; inventory_router.py → test_inventory.py.
    gaps: list[str] = []
    for r in routers:
        stem = Path(r).stem
        stem_no_suffix = re.sub(r"_router$", "", stem)
        candidates = {
            f"test_{stem}.py",
            f"test_{stem_no_suffix}.py",
        }
        if not (candidates & test_files):
            gaps.append(f"backend/app/routers/{r}  (expected one of: {', '.join(sorted(candidates))})")
    return gaps


# ─── Report assembly + main ──────────────────────────────────────────────

def build_report() -> dict[str, Any]:
    tests = run_tests()
    debug_hits = find_debug_artifacts()
    env_info = check_env_exposure()
    secret_hits = find_hardcoded_secrets()
    gaps = find_coverage_gaps()

    issues: list[str] = []
    if not tests["ok"]:
        issues.append(f"{tests['failed']} test(s) failing")
    if debug_hits:
        issues.append(f"{len(debug_hits)} debug artifact(s)")
    if not env_info["safe"]:
        if env_info["missing_from_gitignore"]:
            issues.append("env path missing from .gitignore")
        if env_info["staged_env_files"]:
            issues.append(".env file staged for commit")
    if secret_hits:
        issues.append(f"{len(secret_hits)} potential secret(s)")

    recommendation = "SAFE TO PUSH" if not issues else f"FIX ISSUES BEFORE PUSHING: {', '.join(issues)}"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tests": {
            "total": tests["total"],
            "passed": tests["passed"],
            "failed": tests["failed"],
            "summary": tests["summary"],
        },
        "debug_artifacts": debug_hits,
        "env_exposure": "safe" if env_info["safe"] else env_info,
        "hardcoded_secrets": secret_hits,
        "coverage_gaps": gaps,
        "recommendation": recommendation,
    }


def _print_summary(report: dict[str, Any]) -> None:
    t = report["tests"]
    ok = report["recommendation"].startswith("SAFE")

    print()
    print(f"{C.BLUE}── ElixirX Pre-Push Review ──{C.RESET}")
    print(f"  timestamp: {report['timestamp']}")
    print()
    print(f"  Tests:       {t['passed']} passed, {t['failed']} failed  "
          f"{C.DIM}({t['summary']}){C.RESET}")
    print(f"  Debug:       {len(report['debug_artifacts'])} artifact(s)")
    print(f"  Env safety:  {'safe' if report['env_exposure'] == 'safe' else 'ISSUES'}")
    print(f"  Secrets:     {len(report['hardcoded_secrets'])} suspect(s)")
    print(f"  Coverage:    {len(report['coverage_gaps'])} gap(s)")
    print()

    for label, items in (
        ("Debug artifacts", report["debug_artifacts"]),
        ("Hardcoded secrets", report["hardcoded_secrets"]),
        ("Coverage gaps", report["coverage_gaps"]),
    ):
        if items:
            print(f"{C.YELLOW}  {label}:{C.RESET}")
            for it in items[:15]:
                print(f"    · {it}")
            if len(items) > 15:
                print(f"    {C.DIM}… and {len(items) - 15} more{C.RESET}")
            print()

    if report["env_exposure"] != "safe":
        env = report["env_exposure"]
        print(f"{C.YELLOW}  .env exposure:{C.RESET}")
        if env.get("missing_from_gitignore"):
            print(f"    missing from .gitignore: {env['missing_from_gitignore']}")
        if env.get("staged_env_files"):
            print(f"    staged .env files: {env['staged_env_files']}")
        print()

    color = C.GREEN if ok else C.RED
    icon = "✅" if ok else "❌"
    print(f"{color}  {icon} {report['recommendation']}{C.RESET}\n")


def main() -> int:
    report = build_report()
    _print_summary(report)

    # Persist alongside the failure cache so other tools can grep it.
    out_path = os.path.join(os.path.dirname(__file__), "last_review.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    except OSError:
        pass

    return 0 if report["recommendation"].startswith("SAFE") else 1


if __name__ == "__main__":
    sys.exit(main())
