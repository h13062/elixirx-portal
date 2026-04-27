"""Sprint 3 — machine lifecycle tests.

All tests are skipped pending Sprint 3 Task 3.1 sign-off. To enable, change
`@pytest.mark.skipif(True, ...)` to `@pytest.mark.skipif(False, ...)` (or
remove the decorator) on each test as the corresponding feature lands.
"""

import pytest

from conftest import unique_id


class TestMachineLifecycle:
    def _create_test_machine(self, client, admin_headers):
        """Helper: register a fresh available machine"""
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        result = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        })
        assert result.status_code == 201, f"Failed to create test machine: {result.json()}"
        return result.json()

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_status_summary(self, client, admin_headers):
        """GET /api/machines/status-summary returns counts"""
        response = client.get("/api/machines/status-summary", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "total" in data

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_valid_transition(self, client, admin_headers):
        """Valid status transition succeeds"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "Customer interested"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reserved"

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_invalid_transition(self, client, admin_headers):
        """Invalid transition returns 400"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Skip ahead"}
        )
        assert response.status_code == 400

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_force_override(self, client, admin_headers):
        """Force flag bypasses transition validation"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Testing", "force": True}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "delivered"

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_delivery_triggers_warranty_flag(self, client, admin_headers):
        """Delivery returns warranty_setup_required flag"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Test warranty", "force": True}
        )
        assert response.status_code == 200
        assert response.json().get("warranty_setup_required") == True

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_full_lifecycle(self, client, admin_headers):
        """Complete lifecycle: available → reserved → ordered → sold → delivered → returned → available"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        transitions = [
            ("reserved", "Customer wants it"),
            ("ordered", "Order approved"),
            ("sold", "Payment received"),
            ("delivered", "Delivered to customer"),
            ("returned", "Defective unit"),
            ("available", "Restocked after repair"),
        ]
        for new_status, reason in transitions:
            response = client.put(
                f"/api/machines/{serial}/status",
                headers=admin_headers,
                json={"new_status": new_status, "reason": reason}
            )
            assert response.status_code == 200, f"Failed {new_status}: {response.json()}"
            assert response.json()["status"] == new_status

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_status_history(self, client, admin_headers):
        """Status history shows all transitions"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "reserved", "reason": "Test 1"})
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "available", "reason": "Test 2"})
        response = client.get(f"/api/machines/{serial}/status-history", headers=admin_headers)
        assert response.status_code == 200
        history = response.json()
        assert len(history) >= 2

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_full_detail(self, client, admin_headers):
        """Full detail endpoint returns machine with history"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.get(
            f"/api/machines/{machine['serial_number']}/full-detail",
            headers=admin_headers
        )
        assert response.status_code == 200

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_rep_cannot_change_status(self, client, rep_headers, admin_headers):
        """Rep cannot change machine status"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=rep_headers,
            json={"new_status": "reserved", "reason": "test"}
        )
        assert response.status_code == 403

    @pytest.mark.skipif(True, reason="Enable after Sprint 3 Task 3.1 is built")
    def test_bulk_status_change(self, client, admin_headers):
        """Bulk status change updates multiple machines"""
        m1 = self._create_test_machine(client, admin_headers)
        m2 = self._create_test_machine(client, admin_headers)
        response = client.post("/api/machines/bulk-status", headers=admin_headers, json={
            "machine_ids": [m1["serial_number"], m2["serial_number"]],
            "new_status": "reserved", "reason": "Bulk test"
        })
        assert response.status_code == 200
        assert response.json()["updated"] == 2
