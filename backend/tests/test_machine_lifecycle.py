"""Sprint 3 — machine lifecycle tests.

Endpoint contract (see backend/app/routers/machine_lifecycle.py):
- GET  /api/machines/status-summary           → MachineStatusSummary
- POST /api/machines/bulk-status              → BulkStatusResult
- PUT  /api/machines/{identifier}/status      → MachineStatusUpdateResponse
                                                 = { machine: MachineResponse,
                                                     warranty_setup_required: bool }
- GET  /api/machines/{identifier}/status-history → list[MachineStatusLogEntry]
                                                 = [{ id, from_status, to_status,
                                                      changed_by, changed_by_name,
                                                      reason, created_at }]
- GET  /api/machines/{identifier}/full-detail → MachineFullDetail
                                                 = { machine, product, status_history,
                                                     warranty, active_reservation,
                                                     open_issues }

Identifier may be a UUID OR serial_number.
"""

import pytest

from conftest import unique_id


def _new_machine(client, admin_headers):
    """Module-level helper: register a fresh available machine and return its row."""
    products = client.get("/api/products", headers=admin_headers).json()
    rx = next(p for p in products if p["name"] == "RX Machine")
    serial = unique_id("RX")
    result = client.post("/api/machines", headers=admin_headers, json={
        "serial_number": serial, "product_id": rx["id"],
        "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
    })
    assert result.status_code == 201, f"Failed to create test machine: {result.json()}"
    return result.json()


def _force_to(client, admin_headers, serial, target_status, reason="Test setup"):
    """Forcibly move a machine to a target status (used to set up tests)."""
    response = client.put(
        f"/api/machines/{serial}/status",
        headers=admin_headers,
        json={"new_status": target_status, "reason": reason, "force": True},
    )
    assert response.status_code == 200, (
        f"Setup move to {target_status} failed: {response.json()}"
    )
    return response.json()


class TestMachineLifecycle:
    def _create_test_machine(self, client, admin_headers):
        return _new_machine(client, admin_headers)

    def test_status_summary(self, client, admin_headers):
        """GET /api/machines/status-summary returns counts"""
        response = client.get("/api/machines/status-summary", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.json()}"
        data = response.json()
        assert "available" in data
        assert "reserved" in data
        assert "ordered" in data
        assert "sold" in data
        assert "delivered" in data
        assert "returned" in data
        assert "total" in data
        # Total must equal sum of buckets
        bucket_sum = (
            data["available"] + data["reserved"] + data["ordered"]
            + data["sold"] + data["delivered"] + data["returned"]
        )
        assert data["total"] == bucket_sum, f"Total mismatch: {data}"

    def test_valid_transition(self, client, admin_headers):
        """Valid status transition (available → reserved) succeeds"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "Customer interested"}
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        body = response.json()
        assert body["machine"]["status"] == "reserved"
        assert body["warranty_setup_required"] is False

    def test_invalid_transition(self, client, admin_headers):
        """Invalid transition (available → delivered) returns 400"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Skip ahead"}
        )
        assert response.status_code == 400, (
            f"Expected 400, got {response.status_code}: {response.json()}"
        )

    def test_force_override(self, client, admin_headers):
        """Force flag bypasses transition validation"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Testing", "force": True}
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "delivered"

    def test_force_override_logs_with_forced_prefix(self, client, admin_headers):
        """Forced transitions are logged with FORCED: prefix in reason"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "sold", "reason": "Bypass for test", "force": True},
        )
        history = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        ).json()
        assert history, "Expected at least one log entry"
        assert history[0]["reason"].startswith("FORCED:"), (
            f"Expected FORCED: prefix, got: {history[0]['reason']}"
        )

    def test_delivery_triggers_warranty_flag(self, client, admin_headers):
        """Transition to 'delivered' returns warranty_setup_required: true"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "delivered", "reason": "Test warranty", "force": True}
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json().get("warranty_setup_required") is True

    def test_non_delivery_does_not_set_warranty_flag(self, client, admin_headers):
        """Non-delivery transitions return warranty_setup_required: false"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "Customer interested"}
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json().get("warranty_setup_required") is False

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
            assert response.status_code == 200, (
                f"Failed {new_status}: {response.json()}"
            )
            assert response.json()["machine"]["status"] == new_status

    def test_status_history(self, client, admin_headers):
        """Status history shows all transitions, newest first"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "reserved", "reason": "Test 1"})
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "available", "reason": "Test 2"})
        response = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        history = response.json()
        assert len(history) >= 2
        # Newest first
        assert history[0]["to_status"] == "available"
        assert history[0]["from_status"] == "reserved"
        assert history[1]["to_status"] == "reserved"
        assert history[1]["from_status"] == "available"

    def test_full_detail(self, client, admin_headers):
        """Full detail endpoint returns machine + product + history (and best-effort fields)"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.put(f"/api/machines/{serial}/status", headers=admin_headers,
                   json={"new_status": "reserved", "reason": "Detail test"})
        response = client.get(
            f"/api/machines/{serial}/full-detail", headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        body = response.json()
        assert body["machine"]["serial_number"] == serial
        assert body["product"] is not None
        assert body["product"]["name"] == "RX Machine"
        assert isinstance(body["status_history"], list)
        assert len(body["status_history"]) >= 1
        assert isinstance(body["open_issues"], list)
        # warranty + active_reservation are best-effort; just assert keys present
        assert "warranty" in body
        assert "active_reservation" in body

    def test_rep_cannot_change_status(self, client, rep_headers, admin_headers):
        """Rep cannot change machine status"""
        machine = self._create_test_machine(client, admin_headers)
        response = client.put(
            f"/api/machines/{machine['serial_number']}/status",
            headers=rep_headers,
            json={"new_status": "reserved", "reason": "test"}
        )
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}: {response.json()}"
        )

    def test_bulk_status_change(self, client, admin_headers):
        """Bulk status change updates multiple machines"""
        m1 = self._create_test_machine(client, admin_headers)
        m2 = self._create_test_machine(client, admin_headers)
        response = client.post(
            "/api/machines/bulk-status",
            headers=admin_headers,
            json={
                "machine_ids": [m1["serial_number"], m2["serial_number"]],
                "new_status": "reserved",
                "reason": "Bulk test",
            },
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        body = response.json()
        assert body["updated"] == 2, f"Expected 2 updated, got: {body}"
        assert body["failed"] == 0
        assert body["errors"] == []

    def test_bulk_status_collects_per_id_errors(self, client, admin_headers):
        """Bulk update returns per-id errors instead of failing the whole batch"""
        m1 = self._create_test_machine(client, admin_headers)
        bogus = "DOES-NOT-EXIST-XYZ"
        response = client.post(
            "/api/machines/bulk-status",
            headers=admin_headers,
            json={
                "machine_ids": [m1["serial_number"], bogus],
                "new_status": "reserved",
                "reason": "Mixed batch",
            },
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        body = response.json()
        assert body["updated"] == 1
        assert body["failed"] == 1
        assert any(bogus in err for err in body["errors"]), (
            f"Expected bogus id in errors, got: {body['errors']}"
        )

    def test_machine_not_found_for_status_change(self, client, admin_headers):
        """Status change on nonexistent machine returns 404"""
        response = client.put(
            "/api/machines/NONEXISTENT-999/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "test"},
        )
        assert response.status_code == 404, (
            f"Expected 404, got {response.status_code}: {response.json()}"
        )


class TestMachineStatusLog:
    def _create_test_machine(self, client, admin_headers):
        return _new_machine(client, admin_headers)

    def test_status_change_creates_log(self, client, admin_headers):
        """Every status change creates an entry in machine_status_log"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]

        before = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        ).json()
        assert before == [], (
            f"Expected empty history for fresh machine, got: {before}"
        )

        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "Logged test"},
        )

        after = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        ).json()
        assert len(after) == 1, f"Expected 1 entry, got: {after}"
        assert after[0]["from_status"] == "available"
        assert after[0]["to_status"] == "reserved"

    def test_log_includes_reason(self, client, admin_headers):
        """Status log captures the reason provided"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        reason = f"Reason-{unique_id()}"
        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": reason},
        )
        history = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        ).json()
        assert history[0]["reason"] == reason, (
            f"Expected reason '{reason}', got: {history[0]['reason']}"
        )

    def test_log_includes_who_changed(self, client, admin_headers):
        """Status log shows who made the change (changed_by id, with changed_by_name when joinable)"""
        # Get the admin's id from /me so we can compare against changed_by
        me = client.get("/api/auth/me", headers=admin_headers).json()
        admin_id = me["id"]

        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={"new_status": "reserved", "reason": "Who-changed test"},
        )
        history = client.get(
            f"/api/machines/{serial}/status-history", headers=admin_headers
        ).json()
        entry = history[0]
        assert entry["changed_by"] == admin_id, (
            f"Expected changed_by {admin_id}, got: {entry.get('changed_by')}"
        )
        # changed_by_name is best-effort (depends on profiles join); allow None
        assert "changed_by_name" in entry


class TestStatusValidation:
    def _create_test_machine(self, client, admin_headers):
        return _new_machine(client, admin_headers)

    def _put_status(self, client, admin_headers, serial, new_status, force=False):
        return client.put(
            f"/api/machines/{serial}/status",
            headers=admin_headers,
            json={
                "new_status": new_status,
                "reason": f"Validation test → {new_status}",
                "force": force,
            },
        )

    def test_available_to_reserved_valid(self, client, admin_headers):
        """available → reserved is valid"""
        machine = self._create_test_machine(client, admin_headers)
        response = self._put_status(
            client, admin_headers, machine["serial_number"], "reserved"
        )
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "reserved"

    def test_available_to_ordered_invalid(self, client, admin_headers):
        """available → ordered is invalid (must go through reserved first)"""
        machine = self._create_test_machine(client, admin_headers)
        response = self._put_status(
            client, admin_headers, machine["serial_number"], "ordered"
        )
        assert response.status_code == 400, (
            f"Expected 400, got {response.status_code}: {response.json()}"
        )

    def test_reserved_to_available_valid(self, client, admin_headers):
        """reserved → available is valid (cancellation)"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        self._put_status(client, admin_headers, serial, "reserved")
        response = self._put_status(client, admin_headers, serial, "available")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "available"

    def test_reserved_to_ordered_valid(self, client, admin_headers):
        """reserved → ordered is valid"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        self._put_status(client, admin_headers, serial, "reserved")
        response = self._put_status(client, admin_headers, serial, "ordered")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "ordered"

    def test_ordered_to_sold_valid(self, client, admin_headers):
        """ordered → sold is valid"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        self._put_status(client, admin_headers, serial, "reserved")
        self._put_status(client, admin_headers, serial, "ordered")
        response = self._put_status(client, admin_headers, serial, "sold")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "sold"

    def test_sold_to_delivered_valid(self, client, admin_headers):
        """sold → delivered is valid"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        self._put_status(client, admin_headers, serial, "reserved")
        self._put_status(client, admin_headers, serial, "ordered")
        self._put_status(client, admin_headers, serial, "sold")
        response = self._put_status(client, admin_headers, serial, "delivered")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "delivered"
        assert response.json().get("warranty_setup_required") is True

    def test_delivered_to_returned_valid(self, client, admin_headers):
        """delivered → returned is valid"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        _force_to(client, admin_headers, serial, "delivered")
        response = self._put_status(client, admin_headers, serial, "returned")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "returned"

    def test_returned_to_available_valid(self, client, admin_headers):
        """returned → available is valid (restocking)"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        _force_to(client, admin_headers, serial, "returned")
        response = self._put_status(client, admin_headers, serial, "available")
        assert response.status_code == 200, f"Failed: {response.json()}"
        assert response.json()["machine"]["status"] == "available"

    def test_delivered_to_available_invalid(self, client, admin_headers):
        """delivered → available is invalid (must go through returned)"""
        machine = self._create_test_machine(client, admin_headers)
        serial = machine["serial_number"]
        _force_to(client, admin_headers, serial, "delivered")
        response = self._put_status(client, admin_headers, serial, "available")
        assert response.status_code == 400, (
            f"Expected 400, got {response.status_code}: {response.json()}"
        )
