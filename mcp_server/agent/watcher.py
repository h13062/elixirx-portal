"""Watch Mode — monitors project files and runs tests on changes.

Resolution order for a changed backend `.py` file:

  1. **Filename match** in `FILE_TO_MARKER` → run `pytest -m <marker>`.
     Task-level markers (e.g. `sprint3_2`) give the fastest feedback;
     sprint-level markers (`sprint1`) are used where no per-task split
     exists yet.
  2. **Path-segment fallback** (`PATH_FALLBACK_MARKERS`) — catches feature
     files that live outside `routers/` (services, models, repositories).
  3. **Sibling test file** — `warranty.py` → `tests/test_warranty.py`,
     run that file directly with no marker filter.
  4. Otherwise: skip with a quiet log line.

Saving a test file (`tests/test_X.py`) runs *only that file* — never a
whole sprint — so iterating on tests stays tight.

Frontend `.ts` / `.tsx` saves run `npx tsc --noEmit`.

Failures land in `mcp_server/agent/last_failure.json` for the Fix Mode
MCP tools to pick up.

Run as a module so relative imports work:

    python -m mcp_server.agent.watcher
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

# Relative import when run with `-m`; absolute fallback for direct script run.
try:
    from .config import (
        BACKEND_DIR,
        DEBOUNCE_SECONDS,
        FILE_TO_MARKER,
        FRONTEND_DIR,
        IGNORE_PATTERNS,
        LAST_FAILURE_PATH,
        PATH_FALLBACK_MARKERS,
        TESTS_DIR,
    )
except ImportError:  # pragma: no cover — script-mode fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.config import (  # type: ignore[no-redef]
        BACKEND_DIR,
        DEBOUNCE_SECONDS,
        FILE_TO_MARKER,
        FRONTEND_DIR,
        IGNORE_PATTERNS,
        LAST_FAILURE_PATH,
        PATH_FALLBACK_MARKERS,
        TESTS_DIR,
    )

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError as exc:
    sys.stderr.write(
        "The watchdog package is required. Run:\n"
        "    pip install watchdog\n"
        f"({exc})\n"
    )
    sys.exit(1)


# ─── ANSI colors (no external deps; cmd.exe handles them in modern Win) ────

class C:
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _print_header(file_changed: str, label: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print()
    print(f"{C.BLUE}── {ts}  {C.RESET}{file_changed}  {C.DIM}→  {label}{C.RESET}")


# ─── Resolution ──────────────────────────────────────────────────────────

ResolutionKind = Literal["marker", "file", "skip"]


@dataclass(frozen=True)
class Resolution:
    """How the watcher will exercise tests for a given changed file."""
    kind: ResolutionKind
    target: Optional[str]   # marker name or test file path (relative to BACKEND_DIR)
    level: str              # "task-level" / "sprint-level" / "file-level" / "skipped"


_TASK_MARKER_RE = re.compile(r"^sprint\d+_\d+$")


def _marker_level(marker: str) -> str:
    return "task-level" if _TASK_MARKER_RE.match(marker) else "sprint-level"


def _sibling_test_for(stem: str) -> Optional[str]:
    """Find `tests/test_<stem>.py` (and a couple of common variants)."""
    candidates = [
        f"test_{stem}.py",
        f"test_{stem.removesuffix('_router')}.py",
        f"test_{stem.removesuffix('_service')}.py",
    ]
    for cand in candidates:
        path = os.path.join(TESTS_DIR, cand)
        if os.path.isfile(path):
            return os.path.relpath(path, BACKEND_DIR).replace("\\", "/")
    return None


def resolve(path: str) -> Resolution:
    """Pick the right pytest invocation for a changed file path.

    Resolution priority is the order documented in the module docstring.
    """
    norm = path.replace("\\", "/")
    basename = os.path.basename(norm)
    stem = Path(norm).stem.lower()

    # 0. Test files run only themselves — never a whole sprint.
    if basename.startswith("test_") and basename.endswith(".py"):
        rel = os.path.relpath(path, BACKEND_DIR).replace("\\", "/")
        return Resolution("file", rel, "file-level")

    # 1. Direct filename match — fastest path, most specific.
    if basename in FILE_TO_MARKER:
        marker = FILE_TO_MARKER[basename]
        return Resolution("marker", marker, _marker_level(marker))

    # 2. Path-segment fallback for files outside the routers/ layer.
    lower = norm.lower()
    for needle, marker in PATH_FALLBACK_MARKERS.items():
        if needle in lower:
            return Resolution("marker", marker, _marker_level(marker))

    # 3. Sibling test file — run that single file with no marker filter.
    sibling = _sibling_test_for(stem)
    if sibling:
        return Resolution("file", sibling, "file-level")

    # 4. Nothing matched — skip.
    return Resolution("skip", None, "skipped")


# Back-compat shim: callers used to import `detect_sprint(path) -> str | None`.
def detect_sprint(path: str) -> Optional[str]:
    """Return the sprint name for the given file, or None.

    Collapses any task-level marker (`sprint3_2`) to its sprint root
    (`sprint3`) for compatibility with the old API.
    """
    r = resolve(path)
    if r.kind != "marker" or r.target is None:
        return None
    return r.target.split("_", 1)[0]


# ─── Pytest runner ───────────────────────────────────────────────────────

def _record_failure(file_changed: str, marker: str, failed: list[str], output: str) -> None:
    payload = {
        "timestamp": _now_iso(),
        "file_changed": str(file_changed),
        "sprint": marker,  # kept under the legacy key so fixer.py doesn't care
        "failed_tests": failed,
        "error_output": output,
        "status": "unresolved",
    }
    try:
        os.makedirs(os.path.dirname(LAST_FAILURE_PATH), exist_ok=True)
        with open(LAST_FAILURE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError as e:  # pragma: no cover
        print(f"{C.YELLOW}⚠ could not save last_failure.json: {e}{C.RESET}")


_TEST_NAME_RE = re.compile(
    r"^FAILED\s+([\w./\\:-]+::[\w:.\-\[\] ]+)", re.MULTILINE
)


def _extract_failed_test_names(output: str) -> list[str]:
    return list(dict.fromkeys(_TEST_NAME_RE.findall(output)))


def _run_pytest(args: list[str], file_changed: str, target_label: str) -> None:
    """Shared pytest runner used by both marker- and file-mode dispatch."""
    cmd = [sys.executable, "-m", "pytest", *args, "--tb=short", "-q", "--color=no"]
    print(f"{C.DIM}Running pytest {' '.join(args)} …{C.RESET}")
    try:
        completed = subprocess.run(
            cmd, cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        print(f"{C.RED}❌ pytest timed out after 300s{C.RESET}")
        _record_failure(file_changed, target_label, [], "timeout")
        return
    except FileNotFoundError as e:  # pragma: no cover
        print(f"{C.RED}❌ failed to launch pytest: {e}{C.RESET}")
        return

    out = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 0:
        summary = next(
            (ln for ln in reversed(out.splitlines()) if ln.strip()), ""
        )
        print(f"{C.GREEN}✅ {target_label}: {summary}{C.RESET}")
        return

    failed = _extract_failed_test_names(out)
    print(f"{C.RED}❌ {target_label}: {len(failed)} test(s) failed{C.RESET}")
    for name in failed[:10]:
        print(f"{C.RED}   · {name}{C.RESET}")
    if len(failed) > 10:
        print(f"{C.DIM}   … and {len(failed) - 10} more{C.RESET}")
    _record_failure(file_changed, target_label, failed, out)
    print(
        f"{C.DIM}   Saved failure to {LAST_FAILURE_PATH}{C.RESET}\n"
        f"{C.DIM}   In Claude Code: 'Use elixirx-dev to diagnose the last test failure'{C.RESET}"
    )


def run_for_resolution(file_changed: str, res: Resolution) -> None:
    """Dispatch on the Resolution kind."""
    if res.kind == "marker" and res.target:
        _run_pytest(["tests/", "-m", res.target], file_changed, res.target)
    elif res.kind == "file" and res.target:
        _run_pytest([res.target], file_changed, res.target)
    # "skip" handled by the caller before we get here.


def run_typecheck(file_changed: str) -> None:
    npx = "npx.cmd" if os.name == "nt" else "npx"
    print(f"{C.DIM}Running {npx} tsc --noEmit …{C.RESET}")
    try:
        completed = subprocess.run(
            [npx, "tsc", "--noEmit"],
            cwd=FRONTEND_DIR, capture_output=True, text=True, timeout=180,
            shell=False,
        )
    except FileNotFoundError:
        print(
            f"{C.YELLOW}⚠ npx not found — install Node.js to enable frontend type checks{C.RESET}"
        )
        return
    except subprocess.TimeoutExpired:
        print(f"{C.RED}❌ tsc timed out{C.RESET}")
        return

    if completed.returncode == 0:
        print(f"{C.GREEN}✅ frontend types OK{C.RESET}")
        return

    out = (completed.stdout or "") + (completed.stderr or "")
    err_lines = [ln for ln in out.splitlines() if ln.strip()]
    print(f"{C.RED}❌ frontend type errors:{C.RESET}")
    for ln in err_lines[:15]:
        print(f"{C.RED}   {ln}{C.RESET}")
    if len(err_lines) > 15:
        print(f"{C.DIM}   … and {len(err_lines) - 15} more lines{C.RESET}")


# ─── Watchdog wiring ──────────────────────────────────────────────────────

def _is_ignored(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(pat in norm for pat in IGNORE_PATTERNS)


class DebouncedHandler(FileSystemEventHandler):
    """Coalesce rapid file-system events into a single trigger per file.

    Editor saves often fire `modified`+`created` (atomic-rename) in quick
    succession. We wait DEBOUNCE_SECONDS after the last change to a given
    path before acting.
    """

    def __init__(self) -> None:
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.dest_path or event.src_path)

    def _schedule(self, path: str) -> None:
        if _is_ignored(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".py", ".ts", ".tsx"):
            return
        with self._lock:
            t = self._timers.get(path)
            if t is not None:
                t.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self._fire, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        ext = os.path.splitext(path)[1].lower()
        rel = os.path.relpath(path, os.path.dirname(BACKEND_DIR))

        if ext == ".py":
            res = resolve(path)
            if res.kind == "skip":
                _print_header(rel, f"{C.DIM}python (no test match — skipped){C.RESET}")
                return
            level_color = C.GREEN if res.level == "task-level" else C.YELLOW
            _print_header(
                rel,
                f"{C.RESET}{res.target}  {level_color}({res.level}){C.RESET}",
            )
            run_for_resolution(rel, res)
        else:  # .ts / .tsx
            _print_header(rel, "typescript")
            run_typecheck(rel)


def _print_banner() -> None:
    print(f"{C.BLUE}ElixirX Watch Mode{C.RESET}")
    print(f"  backend src:    {os.path.join(BACKEND_DIR, 'app')}")
    print(f"  backend tests:  {TESTS_DIR}")
    print(f"  frontend src:   {os.path.join(FRONTEND_DIR, 'src')}")
    print(f"  debounce:       {DEBOUNCE_SECONDS}s")
    print(
        f"{C.DIM}Save a .py file (under backend/app or backend/tests) or a "
        f".ts/.tsx (under frontend/src)."
    )
    print(f"Ctrl+C to stop.{C.RESET}\n")


def main() -> None:
    if not os.path.isdir(BACKEND_DIR):
        print(f"{C.RED}backend/ not found at {BACKEND_DIR}{C.RESET}")
        sys.exit(1)

    handler = DebouncedHandler()
    observer = Observer()
    backend_src = os.path.join(BACKEND_DIR, "app")
    frontend_src = os.path.join(FRONTEND_DIR, "src")
    if os.path.isdir(backend_src):
        observer.schedule(handler, backend_src, recursive=True)
    if os.path.isdir(TESTS_DIR):
        # Editing a test file should rerun *that file*, not the whole sprint.
        observer.schedule(handler, TESTS_DIR, recursive=True)
    if os.path.isdir(frontend_src):
        observer.schedule(handler, frontend_src, recursive=True)

    _print_banner()
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{C.DIM}stopping…{C.RESET}")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
