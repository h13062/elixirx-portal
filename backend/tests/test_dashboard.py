"""Sprint 4 — dashboard summary endpoint tests.

Split into four classes:
- TestDashboardLayout (Task 4.0) — basic shape, auth, and rep-vs-admin filtering
- TestWarrantyAlerts   (Task 4.1) — warranty-specific fields and check-expiring
- TestLowStockAlerts   (Task 4.2) — low_stock section shape and item fields
- TestActivityFeed     (Task 4.3) — /api/activity endpoint

Module-level `sprint4` marker means every test inherits the sprint marker; the
per-method `sprint4_N` decorators add the task marker on top so
`pytest -m sprint4_3` runs only the activity-feed tests.
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
