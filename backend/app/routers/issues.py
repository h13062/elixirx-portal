"""Machine Issues router (Sprint 3 Task 3.4).

Direct supabase_admin queries — no service/repository per spec.

Authorization summary:
- POST /api/issues, GET /api/issues, GET /api/issues/...   any logged-in user
- PUT /api/issues/{id}                                     admin OR original reporter (only on open/in_progress)
- PUT /api/issues/{id}/status, DELETE /api/issues/{id}     admin only

Notifications writes are best-effort (try/except) so schema variance doesn't
break the main flow.

Route ordering: static segments (`/issues/summary`, `/issues/machine/...`)
MUST be declared before `/issues/{issue_id}` so FastAPI doesn't capture
literals as the dynamic param.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_admin
from app.core.helpers import lookup_machine
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    IssueCreate,
    IssueResponse,
    IssueStatusUpdate,
    IssueSummary,
    IssueSummaryByPriority,
    IssueUpdate,
    RecentUrgentIssue,
)

router = APIRouter(prefix="/api", tags=["Machine Issues"])

VALID_PRIORITIES = ("low", "medium", "high", "urgent")
VALID_STATUSES = ("open", "in_progress", "resolved", "closed")
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
EDITABLE_STATUSES = ("open", "in_progress")


_ISSUE_SELECT = (
    "*, machines(serial_number, products(name)), "
    "reporter:profiles!reported_by(full_name), "
    "resolver:profiles!resolved_by(full_name)"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_admin(profile: dict) -> bool:
    return profile.get("role") in ("admin", "super_admin")


def _fetch_issue_by_id(issue_id: str) -> dict | None:
    r = (
        supabase_admin.table("machine_issues")
        .select(_ISSUE_SELECT)
        .eq("id", issue_id)
        .execute()
    )
    return r.data[0] if r.data else None


def _build_issue_response(row: dict) -> IssueResponse:
    machine_join = row.get("machines") or {}
    serial = (
        machine_join.get("serial_number") if isinstance(machine_join, dict) else None
    )
    product_join = (
        machine_join.get("products") if isinstance(machine_join, dict) else None
    )
    product_name = (
        product_join.get("name") if isinstance(product_join, dict) else None
    )

    reporter = row.get("reporter") or {}
    reported_by_name = (
        reporter.get("full_name") if isinstance(reporter, dict) else None
    )

    resolver = row.get("resolver") or {}
    resolved_by_name = (
        resolver.get("full_name") if isinstance(resolver, dict) else None
    )

    return IssueResponse(
        id=row["id"],
        machine_id=row["machine_id"],
        serial_number=serial,
        product_name=product_name,
        reported_by=row.get("reported_by"),
        reported_by_name=reported_by_name,
        title=row["title"],
        description=row.get("description"),
        priority=row["priority"],
        status=row["status"],
        resolved_by=row.get("resolved_by"),
        resolved_by_name=resolved_by_name,
        resolution_notes=row.get("resolution_notes"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _sort_by_priority_then_recent(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            PRIORITY_RANK.get(r.get("priority", "low"), 99),
            -datetime.fromisoformat(
                str(r["created_at"]).replace("Z", "+00:00")
            ).timestamp(),
        ),
    )


def _notify(payload: dict) -> None:
    """Best-effort notification insert. Schema may vary; failures are swallowed."""
    try:
        supabase_admin.table("notifications").insert({
            "read": False,
            "created_at": _now_iso(),
            **payload,
        }).execute()
    except Exception:
        pass


def _notify_admins(payload: dict) -> None:
    try:
        admins = (
            supabase_admin.table("profiles")
            .select("id")
            .in_("role", ["admin", "super_admin"])
            .execute()
            .data
            or []
        )
        for a in admins:
            _notify({**payload, "user_id": a["id"]})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# POST /api/issues  (any authenticated user)
# ---------------------------------------------------------------------------

@router.post("/issues", response_model=IssueResponse, status_code=201)
def create_issue(
    payload: IssueCreate, current_user: dict = Depends(get_current_user)
):
    try:
        if not payload.title or not payload.title.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="title is required"
            )

        machine = lookup_machine(payload.machine_id)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {payload.machine_id}",
            )

        priority = payload.priority or "medium"
        now_iso = _now_iso()
        created = supabase_admin.table("machine_issues").insert({
            "machine_id": machine["id"],
            "reported_by": current_user["id"],
            "title": payload.title.strip(),
            "description": payload.description,
            "priority": priority,
            "status": "open",
            "created_at": now_iso,
            "updated_at": now_iso,
        }).execute()
        if not created.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create issue",
            )
        issue_id = created.data[0]["id"]

        # Notify all admins
        reporter_name = (
            current_user.get("full_name") or current_user.get("email") or "User"
        )
        _notify_admins({
            "type": "ticket_update",
            "title": "New Machine Issue",
            "message": (
                f"{reporter_name} reported {priority} issue on machine "
                f"{machine['serial_number']}: {payload.title}"
            ),
            "entity_type": "machine_issue",
            "entity_id": issue_id,
            "machine_id": machine["id"],
        })

        full = _fetch_issue_by_id(issue_id)
        if not full:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Issue created but could not be retrieved",
            )
        return _build_issue_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create issue: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/issues
# ---------------------------------------------------------------------------

@router.get("/issues", response_model=list[IssueResponse])
def list_issues(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    machine_id: str | None = Query(default=None),
    reported_by: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        q = supabase_admin.table("machine_issues").select(_ISSUE_SELECT)
        if status_filter:
            q = q.eq("status", status_filter)
        if priority:
            if priority not in VALID_PRIORITIES:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid priority '{priority}'. Allowed: {list(VALID_PRIORITIES)}",
                )
            q = q.eq("priority", priority)
        if reported_by:
            q = q.eq("reported_by", reported_by)
        if machine_id:
            machine = lookup_machine(machine_id)
            if not machine:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Machine not found: {machine_id}",
                )
            q = q.eq("machine_id", machine["id"])

        rows = q.execute().data or []
        sorted_rows = _sort_by_priority_then_recent(rows)
        return [_build_issue_response(r) for r in sorted_rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch issues: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/issues/summary  (static — must come BEFORE /{issue_id})
# ---------------------------------------------------------------------------

@router.get("/issues/summary", response_model=IssueSummary)
def issue_summary(current_user: dict = Depends(get_current_user)):
    try:
        rows = (
            supabase_admin.table("machine_issues")
            .select(_ISSUE_SELECT)
            .execute()
            .data
            or []
        )

        counts = {s: 0 for s in VALID_STATUSES}
        prio_counts = {p: 0 for p in VALID_PRIORITIES}
        for r in rows:
            s = r.get("status")
            p = r.get("priority")
            if s in counts:
                counts[s] += 1
            if p in prio_counts:
                prio_counts[p] += 1

        # Recent urgent/high open issues (top 10 by created_at desc)
        recent = sorted(
            [
                r for r in rows
                if r.get("status") == "open"
                and r.get("priority") in ("urgent", "high")
            ],
            key=lambda r: r["created_at"],
            reverse=True,
        )[:10]

        recent_urgent = []
        for r in recent:
            machine_join = r.get("machines") or {}
            serial = (
                machine_join.get("serial_number")
                if isinstance(machine_join, dict) else None
            )
            recent_urgent.append(RecentUrgentIssue(
                id=r["id"],
                machine_id=r["machine_id"],
                serial_number=serial,
                title=r["title"],
                priority=r["priority"],
                created_at=r["created_at"],
            ))

        return IssueSummary(
            open=counts["open"],
            in_progress=counts["in_progress"],
            resolved=counts["resolved"],
            closed=counts["closed"],
            total=len(rows),
            by_priority=IssueSummaryByPriority(**prio_counts),
            recent_urgent=recent_urgent,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch issue summary: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/issues/machine/{identifier}  (static prefix — before /{issue_id})
# ---------------------------------------------------------------------------

@router.get("/issues/machine/{identifier}", response_model=list[IssueResponse])
def list_issues_for_machine(
    identifier: str, current_user: dict = Depends(get_current_user)
):
    try:
        machine = lookup_machine(identifier)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {identifier}",
            )
        rows = (
            supabase_admin.table("machine_issues")
            .select(_ISSUE_SELECT)
            .eq("machine_id", machine["id"])
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        return [_build_issue_response(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch issues for machine: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/issues/{issue_id}/status  (admin only) — 3-seg, declare BEFORE /{id}
# ---------------------------------------------------------------------------

@router.put("/issues/{issue_id}/status", response_model=IssueResponse)
def change_issue_status(
    issue_id: str,
    payload: IssueStatusUpdate,
    current_user: dict = Depends(require_admin),
):
    try:
        existing = _fetch_issue_by_id(issue_id)
        if not existing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Issue not found"
            )

        new_status = payload.status
        update_data: dict = {
            "status": new_status,
            "updated_at": _now_iso(),
        }

        if new_status in ("resolved", "closed"):
            if not payload.resolution_notes or not payload.resolution_notes.strip():
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="resolution_notes is required when resolving or closing an issue",
                )
            update_data["resolution_notes"] = payload.resolution_notes
            update_data["resolved_by"] = current_user["id"]

        supabase_admin.table("machine_issues").update(update_data).eq(
            "id", issue_id
        ).execute()

        # Notify the reporter
        machine_join = existing.get("machines") or {}
        serial = (
            machine_join.get("serial_number") if isinstance(machine_join, dict) else None
        )
        _notify({
            "user_id": existing.get("reported_by"),
            "type": "ticket_update",
            "title": "Issue Updated",
            "message": (
                f"Your issue '{existing['title']}' on machine "
                f"{serial or existing['machine_id']} has been marked as {new_status}"
            ),
            "entity_type": "machine_issue",
            "entity_id": issue_id,
            "machine_id": existing["machine_id"],
        })

        full = _fetch_issue_by_id(issue_id)
        return _build_issue_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change issue status: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/issues/{issue_id}  (admin or original reporter; only when open/in_progress)
# ---------------------------------------------------------------------------

@router.put("/issues/{issue_id}", response_model=IssueResponse)
def edit_issue(
    issue_id: str,
    payload: IssueUpdate,
    current_user: dict = Depends(get_current_user),
):
    try:
        existing = _fetch_issue_by_id(issue_id)
        if not existing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Issue not found"
            )

        # Authorization
        if existing["reported_by"] != current_user["id"] and not _is_admin(current_user):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Only the reporter or an admin can edit this issue",
            )

        # Edit window
        if existing["status"] not in EDITABLE_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit resolved/closed issues",
            )

        update_data = {
            k: v for k, v in payload.model_dump().items() if v is not None
        }
        if not update_data:
            return _build_issue_response(existing)

        if "priority" in update_data and update_data["priority"] not in VALID_PRIORITIES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority. Allowed: {list(VALID_PRIORITIES)}",
            )

        update_data["updated_at"] = _now_iso()
        supabase_admin.table("machine_issues").update(update_data).eq(
            "id", issue_id
        ).execute()

        full = _fetch_issue_by_id(issue_id)
        return _build_issue_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit issue: {e}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/issues/{issue_id}  (admin only; only when open)
# ---------------------------------------------------------------------------

@router.delete("/issues/{issue_id}")
def delete_issue(issue_id: str, current_user: dict = Depends(require_admin)):
    try:
        existing = _fetch_issue_by_id(issue_id)
        if not existing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Issue not found"
            )
        if existing["status"] != "open":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete issues that are in progress or resolved",
            )

        supabase_admin.table("machine_issues").delete().eq("id", issue_id).execute()
        return {"success": True, "message": "Issue deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete issue: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/issues/{issue_id}  (dynamic — must come AFTER static peers)
# ---------------------------------------------------------------------------

@router.get("/issues/{issue_id}", response_model=IssueResponse)
def get_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    try:
        row = _fetch_issue_by_id(issue_id)
        if not row:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Issue not found"
            )
        return _build_issue_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch issue: {e}",
        )
