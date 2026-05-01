"""Sprint 4 Task 4.0 — dashboard summary endpoint tests."""

import pytest

pytestmark = pytest.mark.sprint4


class TestDashboard:
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

    def test_dashboard_no_auth(self, client):
        """Dashboard requires authentication"""
        response = client.get("/api/dashboard/summary")
        assert response.status_code in [401, 403]
