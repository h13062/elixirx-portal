"""Database tools for the ElixirX MCP server.

Wraps the Supabase service-role client to expose read-oriented helpers over
MCP. Mirrors project conventions from CLAUDE.md:
  - never use .single() — always .execute() and check result.data
  - the service-role key is required for backend-style table access
"""

from __future__ import annotations

import json
import os
from typing import Any

from supabase import Client, create_client


def _get_supabase() -> Client:
    """Build a Supabase admin client from env. Raises if env is missing."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in the "
            "environment (loaded from backend/.env)."
        )
    return create_client(url, key)


def _parse_filters(filters: str) -> dict[str, Any]:
    """Parse a JSON filter string. Empty string → no filters."""
    if not filters or not filters.strip():
        return {}
    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise ValueError(f"filters must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("filters JSON must be an object")
    return parsed


def _apply_filters(query: Any, parsed: dict[str, Any]) -> Any:
    """Apply each (column, value) pair as an .eq() match."""
    for column, value in parsed.items():
        query = query.eq(column, value)
    return query


def register_database_tools(server: Any) -> None:
    """Register Supabase query tools on the MCP server."""

    @server.tool()
    async def query_table(
        table_name: str,
        columns: str = "*",
        filters: str = "",
        limit: int = 20,
        order_by: str = "",
    ) -> str:
        """Query rows from a Supabase table.

        Args:
            table_name: target table.
            columns: PostgREST column selector, e.g. "id,name" or "*".
            filters: JSON object mapping column → equality value.
            limit: max rows returned (default 20).
            order_by: column name to sort by; prefix with '-' for desc.
        """
        try:
            supabase = _get_supabase()
            parsed = _parse_filters(filters)

            query = supabase.table(table_name).select(columns)
            query = _apply_filters(query, parsed)

            if order_by:
                desc = order_by.startswith("-")
                column = order_by[1:] if desc else order_by
                query = query.order(column, desc=desc)

            if limit and limit > 0:
                query = query.limit(limit)

            result = query.execute()
            rows = result.data or []
            return json.dumps(
                {"table": table_name, "count": len(rows), "rows": rows},
                default=str,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "table": table_name})

    @server.tool()
    async def list_tables() -> str:
        """List all tables in the public schema with column metadata."""
        try:
            supabase = _get_supabase()
            sql = (
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position;"
            )
            try:
                result = supabase.rpc("exec_sql", {"query": sql}).execute()
                rows = result.data or []
            except Exception:
                # exec_sql RPC may not exist — fall back to a curated list.
                tables = [
                    "profiles", "invitations", "admin_codes", "admin_log",
                    "system_config", "products", "machines",
                    "consumable_stock", "supplement_flavors",
                    "consumable_batches", "machine_status_log", "warranty",
                    "reservations", "notifications", "machine_issues",
                ]
                summary: dict[str, dict[str, Any]] = {}
                for table in tables:
                    try:
                        head = (
                            supabase.table(table)
                            .select("*", count="exact")
                            .limit(1)
                            .execute()
                        )
                        summary[table] = {
                            "row_count": head.count,
                            "sample_columns": (
                                list(head.data[0].keys()) if head.data else []
                            ),
                        }
                    except Exception as exc:  # noqa: BLE001
                        summary[table] = {"error": str(exc)}
                return json.dumps(
                    {"source": "fallback_probe", "tables": summary},
                    default=str,
                    indent=2,
                )

            grouped: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                table = row["table_name"]
                grouped.setdefault(table, []).append(
                    {
                        "column": row["column_name"],
                        "type": row["data_type"],
                    }
                )
            return json.dumps(
                {"source": "information_schema", "tables": grouped},
                default=str,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    @server.tool()
    async def check_table_exists(table_name: str) -> str:
        """Check if a table exists; report column names and row count."""
        try:
            supabase = _get_supabase()
            result = (
                supabase.table(table_name)
                .select("*", count="exact")
                .limit(1)
                .execute()
            )
            columns = list(result.data[0].keys()) if result.data else []
            return json.dumps(
                {
                    "table": table_name,
                    "exists": True,
                    "row_count": result.count,
                    "columns": columns,
                },
                default=str,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"table": table_name, "exists": False, "error": str(exc)}
            )

    @server.tool()
    async def count_rows(table_name: str, filters: str = "") -> str:
        """Count rows in a table, optionally filtered by JSON equality dict."""
        try:
            supabase = _get_supabase()
            parsed = _parse_filters(filters)
            query = supabase.table(table_name).select("*", count="exact")
            query = _apply_filters(query, parsed)
            result = query.limit(1).execute()
            return json.dumps(
                {
                    "table": table_name,
                    "filters": parsed,
                    "count": result.count,
                },
                default=str,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"table": table_name, "error": str(exc)})

    @server.tool()
    async def run_sql(query: str) -> str:
        """Run a read-only SELECT against the database.

        Blocks any statement containing INSERT/UPDATE/DELETE/DROP/ALTER/
        TRUNCATE/CREATE/GRANT/REVOKE keywords. Requires an `exec_sql` RPC
        on the database — many Supabase projects do not expose one, in
        which case this returns a guidance error.
        """
        if not query or not query.strip():
            return json.dumps({"error": "query is empty"})
        upper = query.upper()
        forbidden = (
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "CREATE", "GRANT", "REVOKE",
        )
        for keyword in forbidden:
            if keyword in upper:
                return json.dumps(
                    {
                        "error": f"keyword '{keyword}' is not allowed",
                        "allowed": "SELECT only",
                    }
                )
        if "SELECT" not in upper:
            return json.dumps({"error": "only SELECT queries are allowed"})

        try:
            supabase = _get_supabase()
            result = supabase.rpc("exec_sql", {"query": query}).execute()
            rows = result.data or []
            return json.dumps(
                {"rows": rows, "count": len(rows)},
                default=str,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {
                    "error": str(exc),
                    "hint": (
                        "Raw SQL requires an exec_sql RPC on the database. "
                        "Use query_table for read access if exec_sql is "
                        "not available."
                    ),
                }
            )
