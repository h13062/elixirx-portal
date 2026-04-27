"""Sprint 3 Task 3.2 — warranty endpoint tests."""

import pytest
from conftest import unique_id

pytestmark = pytest.mark.sprint3


class TestWarranty:
    def _create_delivered_machine(self, client, admin_headers):
        """Helper: create a machine and force it to delivered status"""
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        machine = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        }).json()
        # Force to delivered
        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Test delivery", "force": True},
        )
        return machine

    def test_create_warranty(self, client, admin_headers):
        """Admin can create warranty for a delivered machine"""
        machine = self._create_delivered_machine(client, admin_headers)
        response = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": machine["serial_number"],
            "duration_months": 12,
            "customer_name": "Test Customer",
            "customer_contact": "test@example.com"
        })
        assert response.status_code == 201, f"Create warranty failed: {response.json()}"
        data = response.json()
        assert data["duration_months"] == 12
        assert data["status"] == "active"

    def test_duplicate_warranty_fails(self, client, admin_headers):
        """Cannot create two warranties for same machine"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        })
        response = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        })
        assert response.status_code == 400, f"Expected 400: {response.json()}"

    def test_get_warranty_list(self, client, admin_headers):
        """GET /api/warranty returns list of warranties"""
        response = client.get("/api/warranty", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_warranty_by_machine(self, client, admin_headers):
        """Get warranty by machine serial number"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        })
        response = client.get(
            f"/api/warranty/machine/{serial}", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"

    def test_warranty_dashboard(self, client, admin_headers):
        """Dashboard returns warranty summary counts"""
        response = client.get("/api/warranty/dashboard", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "active" in data
        assert "expiring_soon" in data
        assert "expired" in data
        assert "total" in data

    def test_extend_warranty(self, client, admin_headers):
        """Admin can extend warranty"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        created = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        }).json()
        response = client.put(
            f"/api/warranty/{created['id']}/extend",
            headers=admin_headers,
            json={"additional_months": 6, "reason": "Customer loyalty"}
        )
        assert response.status_code == 200, f"Extend failed: {response.json()}"
        data = response.json()
        assert data["extended"] is True
        assert (
            data["duration_months"] == 18
            or data["extension_reason"] == "Customer loyalty"
        )

    def test_extend_requires_reason(self, client, admin_headers):
        """Extension without reason fails"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        created = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        }).json()
        response = client.put(
            f"/api/warranty/{created['id']}/extend",
            headers=admin_headers,
            json={"additional_months": 6}
        )
        assert response.status_code in [400, 422], (
            f"Expected 400/422: {response.status_code} {response.json()}"
        )

    def test_check_expiring(self, client, admin_headers):
        """Check expiring endpoint returns list"""
        response = client.get("/api/warranty/check-expiring", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert isinstance(response.json(), list)

    def test_warranty_certificate_pdf(self, client, admin_headers):
        """Certificate endpoint returns PDF"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12,
            "customer_name": "PDF Test Customer"
        })
        response = client.get(
            f"/api/warranty/certificate/{serial}", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.text[:200]}"
        ctype = response.headers.get("content-type", "")
        assert "pdf" in ctype.lower(), f"Expected PDF content-type, got: {ctype}"
        # Sanity-check the body starts with the PDF magic bytes
        assert response.content.startswith(b"%PDF-"), (
            f"Body does not look like a PDF: {response.content[:20]!r}"
        )

    def test_rep_cannot_create_warranty(self, client, rep_headers, admin_headers):
        """Rep cannot create warranty"""
        machine = self._create_delivered_machine(client, admin_headers)
        response = client.post("/api/warranty", headers=rep_headers, json={
            "machine_id": machine["serial_number"], "duration_months": 12
        })
        assert response.status_code == 403

    def test_rep_can_view_warranty(self, client, rep_headers, admin_headers):
        """Rep can view warranty list (transparency)"""
        response = client.get("/api/warranty", headers=rep_headers)
        assert response.status_code == 200

    def test_create_warranty_for_non_delivered_machine_requires_force(
        self, client, admin_headers
    ):
        """Cannot create warranty for non-delivered machine without force=true"""
        # Register a fresh machine — leaves it in 'available'
        products = client.get("/api/products", headers=admin_headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        serial = unique_id("RX")
        client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": rx["id"],
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        })
        response = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        })
        assert response.status_code == 400, (
            f"Expected 400: {response.status_code} {response.json()}"
        )

    def test_extend_warranty_preserves_original_end_date(
        self, client, admin_headers
    ):
        """First extension stores original_end_date; second extension does not overwrite it"""
        machine = self._create_delivered_machine(client, admin_headers)
        serial = machine["serial_number"]
        created = client.post("/api/warranty", headers=admin_headers, json={
            "machine_id": serial, "duration_months": 12
        }).json()
        original_end = created["end_date"]

        # First extension — original_end_date should be saved
        first = client.put(
            f"/api/warranty/{created['id']}/extend",
            headers=admin_headers,
            json={"additional_months": 6, "reason": "First extension"}
        ).json()
        assert first["original_end_date"] == original_end, (
            f"Expected original_end_date={original_end}, got {first.get('original_end_date')}"
        )

        # Second extension — original_end_date should still match the FIRST original
        second = client.put(
            f"/api/warranty/{created['id']}/extend",
            headers=admin_headers,
            json={"additional_months": 3, "reason": "Second extension"}
        ).json()
        assert second["original_end_date"] == original_end, (
            f"original_end_date should not change on subsequent extensions"
        )
