"""Database migration tooling for the ElixirX MCP server.

PostgREST does not execute DDL, so these helpers focus on:
  - formatting SQL for paste-into-Supabase-SQL-editor flows
  - generating CREATE TABLE statements from JSON column definitions
  - probing which expected tables exist for the current sprint plan
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from supabase import Client, create_client


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))


SPRINT_TABLES: dict[str, list[str]] = {
    "sprint0": ["system_config"],
    "sprint1": ["profiles", "invitations", "admin_codes", "admin_log"],
    "sprint2": [
        "products",
        "machines",
        "consumable_stock",
        "supplement_flavors",
        "consumable_batches",
    ],
    "sprint3": [
        "machine_status_log",
        "warranty",
        "reservations",
        "notifications",
        "machine_issues",
    ],
}


def _get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set "
            "(loaded from backend/.env)."
        )
    return create_client(url, key)


def _table_exists(supabase: Client, table_name: str) -> bool:
    try:
        supabase.table(table_name).select("*", count="exact").limit(1).execute()
        return True
    except Exception:  # noqa: BLE001
        return False


def register_migration_tools(server: Any) -> None:
    """Register migration helpers."""

    @server.tool()
    async def run_migration(sql: str, description: str = "") -> str:
        """Format a migration for manual execution in the Supabase SQL editor.

        Cannot execute DDL through PostgREST. Refuses statements that drop
        a database or schema.
        """
        if not sql or not sql.strip():
            return json.dumps({"error": "sql is empty"})
        upper = sql.upper()
        if "DROP DATABASE" in upper or "DROP SCHEMA" in upper:
            return json.dumps(
                {"error": "DROP DATABASE / DROP SCHEMA statements are blocked"}
            )

        return json.dumps(
            {
                "description": description or "(unnamed migration)",
                "instructions": (
                    "PostgREST cannot run DDL. Open Supabase Studio → "
                    "SQL Editor → paste the SQL below → Run."
                ),
                "sql": sql.strip(),
            },
            indent=2,
        )

    @server.tool()
    async def generate_migration(
        table_name: str,
        columns: str,
        add_timestamps: bool = True,
        disable_rls: bool = True,
    ) -> str:
        """Generate a CREATE TABLE statement from JSON column definitions.

        Args:
            table_name: name of the new table.
            columns: JSON list of objects with keys ``name``, ``type``, and
                optional ``constraints`` (string). Example:
                [{"name":"id","type":"uuid","constraints":"primary key default gen_random_uuid()"}]
            add_timestamps: append created_at / updated_at columns.
            disable_rls: append ``ALTER TABLE ... DISABLE ROW LEVEL SECURITY``
                (project-wide convention from CLAUDE.md).
        """
        if not table_name.replace("_", "").isalnum():
            return json.dumps(
                {"error": f"invalid table name: {table_name!r}"}
            )
        try:
            parsed = json.loads(columns) if columns else []
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"columns must be valid JSON: {exc}"})
        if not isinstance(parsed, list) or not parsed:
            return json.dumps(
                {"error": "columns must be a non-empty JSON list of objects"}
            )

        column_lines: list[str] = []
        for entry in parsed:
            if not isinstance(entry, dict) or "name" not in entry or "type" not in entry:
                return json.dumps(
                    {"error": "each column needs 'name' and 'type'", "entry": entry}
                )
            piece = f"    {entry['name']} {entry['type']}"
            if entry.get("constraints"):
                piece += f" {entry['constraints']}"
            column_lines.append(piece)

        if add_timestamps:
            column_lines.append("    created_at timestamptz not null default now()")
            column_lines.append("    updated_at timestamptz not null default now()")

        sql_parts = [
            f"CREATE TABLE IF NOT EXISTS public.{table_name} (",
            ",\n".join(column_lines),
            ");",
        ]
        if disable_rls:
            sql_parts.append(
                f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY;"
            )

        return json.dumps(
            {
                "table": table_name,
                "sql": "\n".join(sql_parts),
                "instructions": (
                    "Run this in Supabase SQL Editor; PostgREST cannot "
                    "execute DDL."
                ),
            },
            indent=2,
        )

    @server.tool()
    async def check_migration_status() -> str:
        """Check which expected sprint tables exist or are missing."""
        try:
            supabase = _get_supabase()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

        report: dict[str, Any] = {}
        for sprint, tables in SPRINT_TABLES.items():
            existing: list[str] = []
            missing: list[str] = []
            for table in tables:
                if _table_exists(supabase, table):
                    existing.append(table)
                else:
                    missing.append(table)
            report[sprint] = {
                "expected": tables,
                "existing": existing,
                "missing": missing,
                "status": "complete" if not missing else "incomplete",
            }
        return json.dumps(report, indent=2)
