"""Pytest tooling for the ElixirX MCP server."""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
BACKEND_DIR = PROJECT_ROOT / "backend"
PYTEST_INI = BACKEND_DIR / "pytest.ini"
PYTEST_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 3000


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return "...[truncated]...\n" + text[-MAX_OUTPUT_CHARS:]


def _build_pytest_args(
    marker: str,
    test_file: str,
    test_name: str,
    stop_on_first_failure: bool,
    verbose: bool,
) -> list[str]:
    pytest_invocation = [sys.executable, "-m", "pytest"]
    args = pytest_invocation + ["tests/"]
    if test_file:
        target = test_file if "tests/" in test_file else f"tests/{test_file}"
        if test_name:
            target = f"{target}::{test_name}"
        args = pytest_invocation + [target]
    if marker:
        args.extend(["-m", marker])
    if stop_on_first_failure:
        args.append("-x")
    if verbose:
        args.append("-v")
    args.extend(["--tb=short", "--color=no"])
    return args


def _run_pytest(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
            check=False,
        )
        return {
            "command": " ".join(args),
            "exit_code": completed.returncode,
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(args),
            "error": f"timed out after {PYTEST_TIMEOUT_SECONDS}s",
        }
    except FileNotFoundError as exc:
        return {
            "command": " ".join(args),
            "error": f"pytest executable not found: {exc}",
        }


def register_testing_tools(server: Any) -> None:
    """Register pytest-related tools."""

    @server.tool()
    async def run_tests(
        marker: str = "",
        test_file: str = "",
        test_name: str = "",
        stop_on_first_failure: bool = False,
        verbose: bool = True,
    ) -> str:
        """Run pytest with optional filters.

        Args:
            marker: pytest marker, e.g. "sprint4_1".
            test_file: filename like "test_dashboard.py" or path under tests/.
            test_name: optional "ClassName::method" suffix appended via "::".
            stop_on_first_failure: pass -x.
            verbose: pass -v (default true).
        """
        args = _build_pytest_args(
            marker, test_file, test_name, stop_on_first_failure, verbose
        )
        result = _run_pytest(args)
        return json.dumps(result, indent=2)

    @server.tool()
    async def list_test_markers() -> str:
        """Read pytest.ini and return registered markers."""
        if not PYTEST_INI.exists():
            return json.dumps({"error": f"pytest.ini not found at {PYTEST_INI}"})

        try:
            parser = configparser.ConfigParser(allow_no_value=True)
            parser.read(PYTEST_INI, encoding="utf-8")
            if "pytest" not in parser:
                return json.dumps({"error": "no [pytest] section in pytest.ini"})

            raw = parser["pytest"].get("markers", "") or ""
            markers: list[dict[str, str]] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                if ":" in line:
                    name, _, description = line.partition(":")
                    markers.append(
                        {"name": name.strip(), "description": description.strip()}
                    )
                else:
                    markers.append({"name": line, "description": ""})
            return json.dumps(
                {"file": str(PYTEST_INI), "count": len(markers), "markers": markers},
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @server.tool()
    async def get_test_summary() -> str:
        """Run each sprint marker and report pass/fail counts."""
        sprints = ["sprint1", "sprint2", "sprint3", "sprint4"]
        results: dict[str, Any] = {}
        for marker in sprints:
            args = _build_pytest_args(
                marker=marker,
                test_file="",
                test_name="",
                stop_on_first_failure=False,
                verbose=False,
            )
            run = _run_pytest(args)
            stdout = run.get("stdout", "") or ""
            tail_lines = [line for line in stdout.splitlines() if line.strip()]
            tail = tail_lines[-3:] if tail_lines else []
            results[marker] = {
                "exit_code": run.get("exit_code"),
                "summary_tail": tail,
                "error": run.get("error"),
            }
        return json.dumps(results, indent=2)
