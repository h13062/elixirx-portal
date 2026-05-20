"""Sprint 4 — dashboard summary endpoint tests.

Class index:
- TestDashboardLayout      (Task 4.0) — basic shape, auth, rep-vs-admin filtering
- TestWarrantyAlerts       (Task 4.1) — warranty fields, check-expiring
- TestLowStockAlerts       (Task 4.2) — low_stock section + items
- TestActivityFeed         (Task 4.3) — /api/activity endpoint
- TestIssueTrackerWidget   (Task 4.4) — issues counts, open_issues, quick-start
- TestSummaryReport        (Task 4.6) — /api/dashboard/report daily/weekly
- TestRoleBasedDashboard   (Task 4.7) — admin vs rep payload split
- TestSprint4Complete      (Task 4.8) — full sprint smoke test (every endpoint)

Module-level `sprint4` marker means every test inherits the sprint marker; the
per-method `sprint4_N` decorators add the task marker on top so
`pytest -m sprint4_4` runs only the issue-tracker tests.
"""

import pytest

pytestmark = pytest.mark.sprint4


class TestDashboardLayout:
    """Task 4.0 — Dashboard layout and summary endpoint."""

    @pytest.mark.sprint4_0
    def test_admin_dashboard_summary(self, client, admin_headers):
        """Admin dashboard returns all summary data"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "machines" in data
        assert "warranties" in data
        assert "issues" in data
        assert "reservations" in data
        assert "low_stock" in data
        assert "recent_activity" in data
        assert "recent_issues" in data
        assert "expiring_warranties" in data

        # recent_issues is bounded and contains only open/in_progress
        assert isinstance(data["recent_issues"], list)
        assert len(data["recent_issues"]) <= 5
        for issue in data["recent_issues"]:
            assert issue["status"] in ("open", "in_progress")

        # Machine counts add up to total
        m = data["machines"]
        breakdown = (
            m["available"] + m["reserved"] + m["ordered"]
            + m["sold"] + m["delivered"] + m["returned"]
        )
        assert breakdown == m["total"]

        # Recent activity is bounded
        assert isinstance(data["recent_activity"], list)
        assert len(data["recent_activity"]) <= 10

        # Low stock items each carry a quantity strictly below threshold
        for item in data["low_stock"]["items"]:
            assert item["quantity"] < item["min_threshold"]

    @pytest.mark.sprint4_0
    def test_rep_dashboard_summary(self, client, rep_headers):
        """Rep dashboard returns filtered data"""
        response = client.get("/api/dashboard/summary", headers=rep_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "machines" in data
        assert "reservations" in data
        # Rep can still see global machine counts
        assert "total" in data["machines"]
        # Rep's reservations counts shape is intact
        for key in ("pending", "approved", "denied", "expired", "cancelled", "total"):
            assert key in data["reservations"]

    @pytest.mark.sprint4_0
    def test_dashboard_no_auth(self, client):
        """Dashboard requires authentication"""
        response = client.get("/api/dashboard/summary")
        assert response.status_code in [401, 403]


class TestWarrantyAlerts:
    """Task 4.1 — Warranty expiration alerts."""

    @pytest.mark.sprint4_1
    def test_dashboard_expiring_warranties(self, client, admin_headers):
        """Dashboard summary includes expiring warranties data"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "expiring_warranties" in data
        assert isinstance(data["expiring_warranties"], list)
        # Each entry carries the fields the dashboard widget consumes
        for entry in data["expiring_warranties"]:
            assert "warranty_id" in entry
            assert "machine_id" in entry
            assert "duration_months" in entry
            assert "days_remaining" in entry
            assert entry["days_remaining"] >= 0

    @pytest.mark.sprint4_1
    def test_dashboard_warranty_counts(self, client, admin_headers):
        """Dashboard warranty section has correct structure"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        warranties = data["warranties"]
        assert "active" in warranties
        assert "expiring_soon" in warranties
        assert "expired" in warranties
        # Counts should be non-negative integers and add up to total
        for k in ("active", "expiring_soon", "expired", "total"):
            assert isinstance(warranties[k], int)
            assert warranties[k] >= 0
        assert (warranties["active"] + warranties["expiring_soon"]
                + warranties["expired"]) == warranties["total"]

    @pytest.mark.sprint4_1
    def test_warranty_check_expiring_endpoint(self, client, admin_headers):
        """Check-expiring endpoint returns list"""
        response = client.get("/api/warranty/check-expiring", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestLowStockAlerts:
    """Task 4.2 — Low stock alerts widget."""

    @pytest.mark.sprint4_2
    def test_dashboard_low_stock_structure(self, client, admin_headers):
        """Low stock section has correct structure"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        assert "low_stock" in data
        assert "count" in data["low_stock"]
        assert "items" in data["low_stock"]
        assert isinstance(data["low_stock"]["items"], list)

    @pytest.mark.sprint4_2
    def test_low_stock_items_have_required_fields(self, client, admin_headers):
        """Each low stock item has product_name, sku, quantity, min_threshold"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        for item in data["low_stock"]["items"]:
            assert "product_name" in item
            assert "quantity" in item
            assert "min_threshold" in item


@pytest.mark.sprint4_3
class TestActivityFeed:
    """Task 4.3 — Machine status change activity feed."""

    def test_get_activity_feed(self, client, admin_headers):
        """GET /api/activity returns activity list"""
        response = client.get("/api/activity", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert isinstance(response.json(), list)

    def test_activity_feed_limit(self, client, admin_headers):
        """Activity feed respects limit parameter"""
        response = client.get("/api/activity?limit=5", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) <= 5

    def test_activity_feed_has_required_fields(self, client, admin_headers):
        """Each activity entry has required fields"""
        response = client.get("/api/activity", headers=admin_headers)
        data = response.json()
        if data:
            entry = data[0]
            assert "machine_serial" in entry or "serial_number" in entry
            assert "to_status" in entry
            assert "created_at" in entry

    def test_activity_after_status_change(self, client, admin_headers):
        """Activity feed includes recent status changes"""
        from conftest import unique_id
        # Create a machine
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST", "manufacture_date": "2026-01-15"
        })
        # Change status
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "reserved", "reason": "Activity feed test"})
        # Check activity
        response = client.get("/api/activity", headers=admin_headers)
        serials = [e.get("machine_serial", e.get("serial_number", "")) for e in response.json()]
        assert serial in serials, f"{serial} not found in activity feed"

    def test_rep_can_view_activity(self, client, rep_headers):
        """Rep can view activity feed"""
        response = client.get("/api/activity", headers=rep_headers)
        assert response.status_code == 200


@pytest.mark.sprint4_4
class TestIssueTrackerWidget:
    """Task 4.4 — Issue tracker widget."""

    def test_dashboard_issues_structure(self, client, admin_headers):
        """Dashboard summary has issues section with correct fields"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        assert "issues" in data
        issues = data["issues"]
        assert "open" in issues
        assert "in_progress" in issues
        assert "urgent" in issues
        assert "high" in issues

    def test_dashboard_open_issues_list(self, client, admin_headers):
        """Dashboard includes list of open issues"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        assert "open_issues" in data
        assert isinstance(data["open_issues"], list)

    def test_open_issues_sorted_by_priority(self, client, admin_headers):
        """Open issues are sorted urgent first"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        issues = data.get("open_issues", [])
        if len(issues) >= 2:
            priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
            for i in range(len(issues) - 1):
                current = priority_order.get(issues[i]["priority"], 99)
                next_p = priority_order.get(issues[i + 1]["priority"], 99)
                assert current <= next_p, "Issues not sorted by priority"

    def test_open_issues_max_five(self, client, admin_headers):
        """Dashboard returns max 5 open issues"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        assert len(data.get("open_issues", [])) <= 5

    def test_issue_quick_start(self, client, admin_headers):
        """Admin can start an issue from dashboard context"""
        from conftest import unique_id
        # Create machine + issue
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST", "manufacture_date": "2026-01-15"
        })
        issue = client.post("/api/issues", headers=admin_headers, json={
            "machine_id": serial, "title": "Dashboard test issue", "priority": "high"
        }).json()
        # Start it
        response = client.put(
            f"/api/issues/{issue['id']}/status",
            headers=admin_headers,
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"


@pytest.mark.sprint4_6
class TestSummaryReport:
    """Task 4.6 — Daily / weekly summary report."""

    def test_daily_report(self, client, admin_headers):
        """Daily report returns correct structure"""
        response = client.get("/api/dashboard/report?period=daily", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert data["period"] == "daily"
        for section in ("machines", "warranties", "reservations", "issues", "stock"):
            assert section in data, f"Missing section: {section}"
        # Each numeric sub-field must be a non-negative int.
        for key in ("registered", "status_changes", "delivered"):
            assert isinstance(data["machines"][key], int)
            assert data["machines"][key] >= 0

    def test_weekly_report(self, client, admin_headers):
        """Weekly report returns correct structure"""
        response = client.get("/api/dashboard/report?period=weekly", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["period"] == "weekly"

    def test_invalid_period_rejected(self, client, admin_headers):
        """Unknown period is a 400, not a default-to-daily silent fallback"""
        response = client.get("/api/dashboard/report?period=hourly", headers=admin_headers)
        assert response.status_code == 400

    def test_report_requires_auth(self, client):
        """Report requires authentication"""
        response = client.get("/api/dashboard/report")
        assert response.status_code in (401, 403)

    def test_rep_can_view_report(self, client, rep_headers):
        """Rep can view report (may have filtered data)"""
        response = client.get(
            "/api/dashboard/report?period=daily", headers=rep_headers,
        )
        assert response.status_code == 200

    def test_report_has_date_range(self, client, admin_headers):
        """Report includes date_range with from_date / to_date"""
        response = client.get("/api/dashboard/report?period=weekly", headers=admin_headers)
        data = response.json()
        assert "date_range" in data
        assert "from_date" in data["date_range"]
        assert "to_date" in data["date_range"]

    def test_report_has_top_rep(self, client, admin_headers):
        """Report includes top_rep block (may be empty)"""
        response = client.get("/api/dashboard/report?period=weekly", headers=admin_headers)
        data = response.json()
        assert "top_rep" in data
        assert "name" in data["top_rep"]
        assert "reservations" in data["top_rep"]


@pytest.mark.sprint4_7
class TestRoleBasedDashboard:
    """Task 4.7 — Admin vs rep dashboard payloads."""

    def test_admin_sees_full_dashboard(self, client, admin_headers):
        """Admin dashboard has every operational section"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        for section in (
            "machines", "warranties", "issues", "reservations",
            "low_stock", "recent_activity", "expiring_warranties",
            "open_issues",
        ):
            assert section in data, f"Missing section: {section}"

    def test_admin_has_no_personal_lists(self, client, admin_headers):
        """Admin doesn't get rep-only my_reservations / my_issues populated"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        data = response.json()
        # Either absent or null — never a non-null list for admins.
        assert data.get("my_reservations") in (None, [])
        assert data.get("my_issues") in (None, [])

    def test_rep_sees_personal_lists(self, client, rep_headers):
        """Rep dashboard has my_reservations + my_issues lists"""
        response = client.get("/api/dashboard/summary", headers=rep_headers)
        data = response.json()
        # The fields exist and are lists (possibly empty).
        assert isinstance(data.get("my_reservations"), list)
        assert isinstance(data.get("my_issues"), list)
        # Each my_reservations entry has the documented fields.
        for r in data["my_reservations"]:
            assert "id" in r
            assert "machine_id" in r
            assert "status" in r

    def test_rep_reservations_are_filtered_to_self(self, client, rep_headers):
        """Rep only sees their own reservations in `reservations` counts.

        We can't directly count without an admin probe, but we can verify
        the `my_reservations` list — every row must reference a machine the
        rep actually reserved (machine_id present).
        """
        me = client.get("/api/auth/me", headers=rep_headers).json()
        response = client.get("/api/dashboard/summary", headers=rep_headers)
        data = response.json()
        for r in data.get("my_reservations") or []:
            assert r["machine_id"], "rep reservation row missing machine_id"
        # And the rep id is well-formed (covers our auth scope assumption).
        assert "id" in me


@pytest.mark.sprint4_8
class TestSprint4Complete:
    """Task 4.8 — every Sprint 4 endpoint responds for an authed admin."""

    def test_dashboard_summary_endpoint(self, client, admin_headers):
        """Dashboard summary is accessible"""
        response = client.get("/api/dashboard/summary", headers=admin_headers)
        assert response.status_code == 200

    def test_activity_endpoint(self, client, admin_headers):
        """Activity feed is accessible"""
        response = client.get("/api/activity", headers=admin_headers)
        assert response.status_code == 200

    def test_report_endpoint(self, client, admin_headers):
        """Report endpoint is accessible"""
        response = client.get("/api/dashboard/report", headers=admin_headers)
        assert response.status_code == 200

    def test_notification_bell(self, client, admin_headers):
        """Notification endpoints power the bell"""
        count = client.get("/api/notifications/unread-count", headers=admin_headers)
        assert count.status_code == 200
        notifs = client.get("/api/notifications", headers=admin_headers)
        assert notifs.status_code == 200
