"""Sprint 3 Task 3.4 — machine issues endpoint tests."""

import pytest
from conftest import unique_id

pytestmark = [pytest.mark.sprint3, pytest.mark.sprint3_4]


class TestMachineIssues:
    def _create_machine(self, client, admin_headers):
        """Helper: create an available machine"""
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        return client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        }).json()

    def test_create_issue(self, client, rep_headers, admin_headers):
        """Any user can report an issue"""
        machine = self._create_machine(client, admin_headers)
        response = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Water leak from bottom",
            "description": "Customer reports water pooling under machine",
            "priority": "high"
        })
        assert response.status_code == 201, f"Create issue failed: {response.json()}"
        data = response.json()
        assert data["status"] == "open"
        assert data["priority"] == "high"

    def test_create_issue_default_priority(self, client, rep_headers, admin_headers):
        """Issue defaults to medium priority"""
        machine = self._create_machine(client, admin_headers)
        response = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Minor cosmetic scratch"
        })
        assert response.status_code == 201, f"Failed: {response.json()}"
        assert response.json()["priority"] == "medium"

    def test_create_issue_invalid_priority(self, client, rep_headers, admin_headers):
        """Invalid priority is rejected"""
        machine = self._create_machine(client, admin_headers)
        response = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Test",
            "priority": "critical"
        })
        assert response.status_code in [400, 422], (
            f"Expected 400/422: {response.status_code} {response.json()}"
        )

    def test_create_issue_requires_title(self, client, rep_headers, admin_headers):
        """Issue without title fails"""
        machine = self._create_machine(client, admin_headers)
        response = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"]
        })
        assert response.status_code in [400, 422], (
            f"Expected 400/422: {response.status_code} {response.json()}"
        )

    def test_get_issues_list(self, client, admin_headers):
        """GET /api/issues returns list"""
        response = client.get("/api/issues", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_filter_by_status(self, client, rep_headers, admin_headers):
        """Filter issues by status"""
        machine = self._create_machine(client, admin_headers)
        client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Filter test issue"
        })
        response = client.get("/api/issues?status=open", headers=admin_headers)
        assert response.status_code == 200
        for issue in response.json():
            assert issue["status"] == "open"

    def test_filter_by_priority(self, client, rep_headers, admin_headers):
        """Filter issues by priority"""
        machine = self._create_machine(client, admin_headers)
        client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Urgent test",
            "priority": "urgent"
        })
        response = client.get("/api/issues?priority=urgent", headers=admin_headers)
        assert response.status_code == 200
        for issue in response.json():
            assert issue["priority"] == "urgent"

    def test_get_issues_by_machine(self, client, rep_headers, admin_headers):
        """Get all issues for a specific machine"""
        machine = self._create_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/issues", headers=rep_headers, json={
            "machine_id": serial, "title": "Issue 1"
        })
        client.post("/api/issues", headers=rep_headers, json={
            "machine_id": serial, "title": "Issue 2"
        })
        response = client.get(f"/api/issues/machine/{serial}", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert len(response.json()) >= 2

    def test_issue_summary(self, client, admin_headers):
        """Summary returns counts by status and priority"""
        response = client.get("/api/issues/summary", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "open" in data
        assert "by_priority" in data
        assert "urgent" in data["by_priority"]

    def test_admin_change_status_to_in_progress(
        self, client, rep_headers, admin_headers
    ):
        """Admin can move issue to in_progress"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Status test"
        }).json()
        response = client.put(
            f"/api/issues/{created['id']}/status",
            headers=admin_headers,
            json={"status": "in_progress"},
        )
        assert response.status_code == 200, f"Status change failed: {response.json()}"
        assert response.json()["status"] == "in_progress"

    def test_resolve_requires_notes(self, client, rep_headers, admin_headers):
        """Resolving without notes fails"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Resolve test"
        }).json()
        response = client.put(
            f"/api/issues/{created['id']}/status",
            headers=admin_headers,
            json={"status": "resolved"},
        )
        assert response.status_code == 400, f"Expected 400: {response.json()}"

    def test_resolve_with_notes(self, client, rep_headers, admin_headers):
        """Resolving with notes succeeds"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Resolve with notes test"
        }).json()
        response = client.put(
            f"/api/issues/{created['id']}/status",
            headers=admin_headers,
            json={"status": "resolved", "resolution_notes": "Replaced faulty valve"},
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert data["status"] == "resolved"
        assert data["resolution_notes"] == "Replaced faulty valve"

    def test_edit_open_issue(self, client, rep_headers, admin_headers):
        """Can edit an open issue"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Original title",
            "priority": "low"
        }).json()
        response = client.put(
            f"/api/issues/{created['id']}",
            headers=rep_headers,
            json={"title": "Updated title", "priority": "high"},
        )
        assert response.status_code == 200, f"Edit failed: {response.json()}"
        assert response.json()["title"] == "Updated title"
        assert response.json()["priority"] == "high"

    def test_cannot_edit_resolved_issue(self, client, rep_headers, admin_headers):
        """Cannot edit a resolved issue"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Will be resolved"
        }).json()
        client.put(
            f"/api/issues/{created['id']}/status",
            headers=admin_headers,
            json={"status": "resolved", "resolution_notes": "Fixed"},
        )
        response = client.put(
            f"/api/issues/{created['id']}",
            headers=rep_headers,
            json={"title": "Try to change"},
        )
        assert response.status_code == 400, f"Expected 400: {response.json()}"

    def test_delete_open_issue(self, client, rep_headers, admin_headers):
        """Admin can delete an open issue"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Delete me"
        }).json()
        response = client.delete(
            f"/api/issues/{created['id']}", headers=admin_headers
        )
        assert response.status_code == 200, f"Delete failed: {response.json()}"

    def test_rep_cannot_change_status(self, client, rep_headers, admin_headers):
        """Rep cannot change issue status"""
        machine = self._create_machine(client, admin_headers)
        created = client.post("/api/issues", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "title": "Rep status test"
        }).json()
        response = client.put(
            f"/api/issues/{created['id']}/status",
            headers=rep_headers,
            json={"status": "resolved", "resolution_notes": "Fixed"},
        )
        assert response.status_code == 403

    def test_rep_can_view_all_issues(self, client, rep_headers):
        """Rep can view issues (transparency)"""
        response = client.get("/api/issues", headers=rep_headers)
        assert response.status_code == 200

    # ─── Sprint 4 — Issues page filters ─────────────────────────────────

    @pytest.mark.sprint4
    def test_issues_list_with_filters(self, client, admin_headers):
        """GET /api/issues with status filter works"""
        response = client.get("/api/issues?status=open", headers=admin_headers)
        assert response.status_code == 200
        for issue in response.json():
            assert issue["status"] == "open"

    @pytest.mark.sprint4
    def test_issues_list_with_priority_filter(self, client, admin_headers):
        """GET /api/issues with priority filter works"""
        response = client.get("/api/issues?priority=high", headers=admin_headers)
        assert response.status_code == 200
        for issue in response.json():
            assert issue["priority"] == "high"
