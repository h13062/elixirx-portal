"""Project file tooling for the ElixirX MCP server."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
MAX_FILE_CHARS = 10000
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}


def _resolve_safe(path: str) -> Path:
    """Resolve a path relative to PROJECT_ROOT and ensure it stays inside."""
    candidate = (PROJECT_ROOT / path).resolve() if path else PROJECT_ROOT
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise PermissionError(
            f"path '{path}' resolves outside PROJECT_ROOT"
        ) from exc
    return candidate


def _walk_files(root: Path, pattern: str) -> list[Path]:
    matches: list[Path] = []
    for current_dir, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if fnmatch.fnmatch(filename, pattern):
                matches.append(Path(current_dir) / filename)
    return matches


def register_project_tools(server: Any) -> None:
    """Register project-file inspection tools."""

    @server.tool()
    async def read_file(file_path: str) -> str:
        """Read a file relative to project root. Truncates at 10k chars."""
        try:
            resolved = _resolve_safe(file_path)
            if not resolved.is_file():
                return json.dumps(
                    {"error": f"not a file: {file_path}", "path": str(resolved)}
                )
            content = resolved.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > MAX_FILE_CHARS
            if truncated:
                content = content[:MAX_FILE_CHARS]
            return json.dumps(
                {
                    "path": str(resolved.relative_to(PROJECT_ROOT)),
                    "truncated": truncated,
                    "char_count": len(content),
                    "content": content,
                },
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "file_path": file_path})

    @server.tool()
    async def list_project_files(directory: str = "", pattern: str = "*.py") -> str:
        """List files under a directory, skipping noisy dirs."""
        try:
            base = _resolve_safe(directory)
            if not base.exists():
                return json.dumps({"error": f"path does not exist: {directory}"})
            if base.is_file():
                return json.dumps(
                    {"files": [str(base.relative_to(PROJECT_ROOT))], "count": 1}
                )
            files = _walk_files(base, pattern)
            relative = [str(f.relative_to(PROJECT_ROOT)) for f in files]
            return json.dumps(
                {
                    "directory": str(base.relative_to(PROJECT_ROOT)) or ".",
                    "pattern": pattern,
                    "count": len(relative),
                    "files": relative[:500],
                    "limited": len(relative) > 500,
                },
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @server.tool()
    async def search_code(
        search_text: str, file_pattern: str = "*.py", directory: str = ""
    ) -> str:
        """Case-insensitive substring search; reports file:line for matches."""
        if not search_text:
            return json.dumps({"error": "search_text is required"})
        try:
            base = _resolve_safe(directory)
            if not base.exists():
                return json.dumps({"error": f"path does not exist: {directory}"})
            needle = search_text.lower()
            files = _walk_files(base, file_pattern) if base.is_dir() else [base]
            hits: list[dict[str, Any]] = []
            for file_path in files:
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if needle in line.lower():
                        hits.append(
                            {
                                "file": str(file_path.relative_to(PROJECT_ROOT)),
                                "line": line_no,
                                "text": line.strip()[:300],
                            }
                        )
                        if len(hits) >= 200:
                            break
                if len(hits) >= 200:
                    break
            return json.dumps(
                {
                    "search_text": search_text,
                    "pattern": file_pattern,
                    "match_count": len(hits),
                    "matches": hits,
                },
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @server.tool()
    async def get_project_status() -> str:
        """Summarize project state: sprint info from CLAUDE.md plus file counts."""
        try:
            claude_md = PROJECT_ROOT / "CLAUDE.md"
            sprint_lines: list[str] = []
            if claude_md.exists():
                content = claude_md.read_text(encoding="utf-8", errors="replace")
                in_sprint_section = False
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("## Sprint Order"):
                        in_sprint_section = True
                        sprint_lines.append(stripped)
                        continue
                    if in_sprint_section:
                        if stripped.startswith("## ") and "Sprint Order" not in stripped:
                            break
                        if stripped:
                            sprint_lines.append(stripped)

            backend = PROJECT_ROOT / "backend"
            frontend = PROJECT_ROOT / "frontend"
            test_files = (
                _walk_files(backend / "tests", "test_*.py")
                if (backend / "tests").exists()
                else []
            )
            routers = (
                _walk_files(backend / "app" / "routers", "*.py")
                if (backend / "app" / "routers").exists()
                else []
            )
            pages = (
                _walk_files(frontend / "src" / "pages", "*.tsx")
                if (frontend / "src" / "pages").exists()
                else []
            )

            return json.dumps(
                {
                    "project_root": str(PROJECT_ROOT),
                    "sprint_section": sprint_lines[:40],
                    "counts": {
                        "test_files": len(test_files),
                        "routers": len(routers),
                        "frontend_pages": len(pages),
                    },
                },
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
