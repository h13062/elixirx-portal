"""Sprint 3 Task 3.3 — reservation endpoint tests."""

import pytest
from conftest import unique_id

pytestmark = pytest.mark.sprint3


class TestReservations:
    def _create_available_machine(self, client, admin_headers):
        """Helper: create an available machine"""
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        machine = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        }).json()
        return machine

    def test_create_reservation(self, client, rep_headers, admin_headers):
        """Rep can request a reservation"""
        machine = self._create_available_machine(client, admin_headers)
        response = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": machine["serial_number"],
            "reserved_for": "Heights Nail Spa"
        })
        assert response.status_code == 201, f"Create reservation failed: {response.json()}"
        data = response.json()
        assert data["status"] == "pending"

    def test_cannot_reserve_non_available(self, client, rep_headers, admin_headers):
        """Cannot reserve a machine that is not available"""
        machine = self._create_available_machine(client, admin_headers)
        serial = machine["serial_number"]
        # Force to delivered
        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Test", "force": True},
        )
        response = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Test"
        })
        assert response.status_code == 400, f"Expected 400: {response.json()}"

    def test_cannot_double_reserve(self, client, rep_headers, admin_headers):
        """Cannot create second reservation for same machine"""
        machine = self._create_available_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Customer 1"
        })
        response = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Customer 2"
        })
        assert response.status_code == 400, f"Expected 400: {response.json()}"

    def test_approve_reservation(self, client, rep_headers, admin_headers):
        """Admin can approve reservation, machine becomes reserved"""
        machine = self._create_available_machine(client, admin_headers)
        serial = machine["serial_number"]
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Test Customer"
        }).json()
        response = client.put(
            f"/api/reservations/{created['id']}/approve", headers=admin_headers
        )
        assert response.status_code == 200, f"Approve failed: {response.json()}"
        assert response.json()["status"] == "approved"
        assert response.json()["expires_at"] is not None
        # Verify machine is now reserved
        machine_check = client.get(
            f"/api/machines/{serial}", headers=admin_headers
        ).json()
        assert machine_check["status"] == "reserved"

    def test_deny_reservation(self, client, rep_headers, admin_headers):
        """Admin can deny reservation with reason"""
        machine = self._create_available_machine(client, admin_headers)
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": machine["serial_number"], "reserved_for": "Test"
        }).json()
        response = client.put(
            f"/api/reservations/{created['id']}/deny",
            headers=admin_headers,
            json={"reason": "Customer credit check failed"},
        )
        assert response.status_code == 200, f"Deny failed: {response.json()}"
        assert response.json()["status"] == "denied"
        assert response.json()["deny_reason"] == "Customer credit check failed"

    def test_deny_requires_reason(self, client, rep_headers, admin_headers):
        """Denial without reason fails"""
        machine = self._create_available_machine(client, admin_headers)
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": machine["serial_number"], "reserved_for": "Test"
        }).json()
        response = client.put(
            f"/api/reservations/{created['id']}/deny",
            headers=admin_headers,
            json={},
        )
        assert response.status_code in [400, 422], (
            f"Expected 400/422: {response.status_code} {response.json()}"
        )

    def test_cancel_pending_reservation(self, client, rep_headers, admin_headers):
        """Rep can cancel their pending reservation"""
        machine = self._create_available_machine(client, admin_headers)
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": machine["serial_number"], "reserved_for": "Test"
        }).json()
        response = client.put(
            f"/api/reservations/{created['id']}/cancel", headers=rep_headers
        )
        assert response.status_code == 200, f"Cancel failed: {response.json()}"
        assert response.json()["status"] == "cancelled"

    def test_cancel_approved_reservation_restores_machine(
        self, client, rep_headers, admin_headers
    ):
        """Cancelling approved reservation returns machine to available"""
        machine = self._create_available_machine(client, admin_headers)
        serial = machine["serial_number"]
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Test"
        }).json()
        client.put(
            f"/api/reservations/{created['id']}/approve", headers=admin_headers
        )
        # Now cancel
        response = client.put(
            f"/api/reservations/{created['id']}/cancel", headers=admin_headers
        )
        assert response.status_code == 200, f"Cancel failed: {response.json()}"
        # Machine should be available again
        machine_check = client.get(
            f"/api/machines/{serial}", headers=admin_headers
        ).json()
        assert machine_check["status"] == "available"

    def test_get_reservations_list(self, client, admin_headers):
        """GET /api/reservations returns list"""
        response = client.get("/api/reservations", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_reservation_by_machine(self, client, rep_headers, admin_headers):
        """Get active reservation by machine"""
        machine = self._create_available_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": serial, "reserved_for": "Test"
        })
        response = client.get(
            f"/api/reservations/machine/{serial}", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"

    def test_rep_cannot_approve(self, client, rep_headers, admin_headers):
        """Rep cannot approve reservations"""
        machine = self._create_available_machine(client, admin_headers)
        created = client.post("/api/reservations", headers=rep_headers, json={
            "machine_id": machine["serial_number"], "reserved_for": "Test"
        }).json()
        response = client.put(
            f"/api/reservations/{created['id']}/approve", headers=rep_headers
        )
        assert response.status_code == 403

    def test_check_expired(self, client, admin_headers):
        """Check expired endpoint runs without error"""
        response = client.post(
            "/api/reservations/check-expired", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "expired_count" in data

    def test_expiring_soon(self, client, admin_headers):
        """Expiring soon endpoint returns list"""
        response = client.get(
            "/api/reservations/expiring-soon", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert isinstance(response.json(), list)
