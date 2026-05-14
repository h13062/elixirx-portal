"""Agent tools — expose Fix Mode and Review Mode through MCP.

`mcp_server/server.py` adds `mcp_server/` to sys.path (the script's own
directory), so `agent.*` resolves as a top-level package the same way
`tools.*` does. Imports are kept lazy (inside each tool function) so a
missing watchdog install during a fresh `pip install` doesn't break the
server boot — only the watcher needs that package.
"""

from __future__ import annotations

import json
from typing import Any


def register_agent_tools(server: Any) -> None:
    """Register Fix Mode / Review Mode tools on the MCP server."""

    @server.tool()
    async def diagnose_failure() -> str:
        """Read the last test failure and diagnose the problem.

        Returns a markdown analysis with the matched error patterns and a
        short list of files to investigate. Reads
        `mcp_server/agent/last_failure.json` — produced by Watch Mode
        whenever a save makes the affected sprint's tests fail.
        """
        from agent.fixer import analyze_failure, format_diagnosis, get_last_failure

        failure = get_last_failure()
        if not failure:
            return (
                "No recent test failures found. "
                "Start Watch Mode (`.\\mcp_server\\agent\\watch.ps1`) and save a "
                "file in backend/app or frontend/src, or run pytest manually."
            )
        diagnosis = analyze_failure(failure)
        return format_diagnosis(diagnosis)

    @server.tool()
    async def auto_fix(task_description: str = "") -> str:
        """Analyze failing tests and generate a fix plan.

        Args:
            task_description: Optional description of what to fix
                (e.g. "fix the warranty 404 error"). Appended as additional
                context if the watcher hasn't captured a failure yet.
        """
        from agent.fixer import analyze_failure, get_last_failure

        failure = get_last_failure()
        if not failure and not task_description:
            return (
                "No failures to fix and no task description provided. "
                "Either run the watcher or pass `task_description`."
            )

        lines = ["## Auto-Fix Plan", ""]

        if failure:
            diagnosis = analyze_failure(failure)
            lines.append(
                f"**Last failure in:** `{diagnosis.get('file_changed', 'unknown')}` "
                f"({diagnosis.get('sprint', 'unknown')})"
            )
            failed = diagnosis.get("failed_tests", []) or []
            if failed:
                lines.append(f"**Failed tests:** {', '.join(f'`{t}`' for t in failed[:8])}")
                if len(failed) > 8:
                    lines[-1] += f", … +{len(failed) - 8} more"

            patterns = diagnosis.get("error_patterns", []) or []
            if patterns:
                lines += ["", "### Steps to fix"]
                for i, p in enumerate(patterns, 1):
                    head = p["type"]
                    if p.get("table"):
                        head += f" (table: `{p['table']}`)"
                    lines.append(f"{i}. **{head}** — {p['fix']}")
            else:
                lines += [
                    "",
                    "_No known error pattern matched. Inspect "
                    "`mcp_server/agent/last_failure.json` for the raw pytest "
                    "output and follow the bug-log conventions._",
                ]

            suggested = diagnosis.get("suggested_files_to_check", []) or []
            if suggested:
                lines += ["", "### Check these files"]
                for f in suggested:
                    lines.append(f"  - `{f}`")

        if task_description:
            lines += ["", f"### Additional context\n{task_description}"]

        lines += [
            "",
            "### Recommended action",
            "1. Read the suggested files via the `read_file` tool above.",
            "2. Apply edits via Claude Code's Edit tool, following CLAUDE.md conventions.",
            f"3. Re-run the affected suite: `run_tests(marker=\"{(failure or {}).get('sprint', 'sprint4')}\")`.",
            "4. Once green, run `pre_push_review` before pushing.",
        ]
        return "\n".join(lines)

    @server.tool()
    async def pre_push_review() -> str:
        """Run the pre-push review: full pytest, debug-artifact scan, secret
        scan, .env exposure check, and router/test-coverage diff.

        Returns the same report that `python -m mcp_server.agent.reviewer`
        prints, in markdown form. Takes a few minutes — the full pytest run
        is the slow step.
        """
        from agent.reviewer import build_report

        report = build_report()
        t = report["tests"]
        ok = report["recommendation"].startswith("SAFE")
        icon = "✅" if ok else "❌"

        lines = [
            "## Pre-Push Review",
            "",
            f"_{report['timestamp']}_",
            "",
            f"- **Tests:** {t['passed']} passed · {t['failed']} failed  "
            f"_({t['summary']})_",
            f"- **Debug artifacts:** {len(report['debug_artifacts'])}",
            f"- **Env safety:** {'safe' if report['env_exposure'] == 'safe' else 'ISSUES'}",
            f"- **Hardcoded secrets:** {len(report['hardcoded_secrets'])}",
            f"- **Coverage gaps:** {len(report['coverage_gaps'])}",
            "",
        ]

        for label, items in (
            ("Debug artifacts", report["debug_artifacts"]),
            ("Hardcoded secrets", report["hardcoded_secrets"]),
            ("Coverage gaps", report["coverage_gaps"]),
        ):
            if items:
                lines.append(f"### {label}")
                for it in items[:15]:
                    lines.append(f"  - {it}")
                if len(items) > 15:
                    lines.append(f"  - … and {len(items) - 15} more")
                lines.append("")

        if report["env_exposure"] != "safe":
            env = report["env_exposure"]
            lines.append("### .env exposure")
            if env.get("missing_from_gitignore"):
                lines.append(f"  - Missing from .gitignore: `{env['missing_from_gitignore']}`")
            if env.get("staged_env_files"):
                lines.append(f"  - Staged .env files: `{env['staged_env_files']}`")
            lines.append("")

        lines.append(f"### {icon} {report['recommendation']}")
        return "\n".join(lines)

    @server.tool()
    async def get_last_failure_raw() -> str:
        """Return the raw `last_failure.json` blob as a code-fenced string.

        Useful when `diagnose_failure` doesn't match a known pattern and you
        want to read the pytest output directly.
        """
        from agent.fixer import get_last_failure

        failure = get_last_failure()
        if not failure:
            return "No `last_failure.json` on disk."
        return "```json\n" + json.dumps(failure, indent=2) + "\n```"
