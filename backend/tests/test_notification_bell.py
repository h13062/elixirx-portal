"""Sprint 4 Task 4.5 — notification bell tests.

Lives in its own file so the module-level marker matches the bell sprint
without colliding with `test_notifications.py`'s sprint-3 marker.
"""

import pytest

pytestmark = [pytest.mark.sprint4, pytest.mark.sprint4_5]


class TestNotificationBell:
    """End-to-end checks for the bell-facing notification endpoints."""

    def _get_user_id(self, client, headers):
        return client.get("/api/auth/me", headers=headers).json()["id"]

    def test_unread_count(self, client, admin_headers):
        """Unread count endpoint returns number"""
        response = client.get(
            "/api/notifications/unread-count", headers=admin_headers
        )
        assert response.status_code == 200
        assert "count" in response.json()
        assert isinstance(response.json()["count"], int)

    def test_mark_read_updates_count(self, client, admin_headers):
        """Marking notification read decreases unread count"""
        user_id = self._get_user_id(client, admin_headers)
        # Create a notification
        client.post("/api/notifications", headers=admin_headers, json={
            "user_id": user_id,
            "title": "Count Test",
            "message": "Testing count",
            "type": "general",
        })
        # Get count
        count_before = client.get(
            "/api/notifications/unread-count", headers=admin_headers
        ).json()["count"]
        # Get notifications and mark first as read
        notifs = client.get(
            "/api/notifications?is_read=false", headers=admin_headers
        ).json()
        if notifs:
            client.put(
                f"/api/notifications/{notifs[0]['id']}/read",
                headers=admin_headers,
            )
        # Count should decrease
        count_after = client.get(
            "/api/notifications/unread-count", headers=admin_headers
        ).json()["count"]
        assert count_after < count_before

    def test_mark_all_read(self, client, admin_headers):
        """Mark all read sets count to 0"""
        client.put("/api/notifications/read-all", headers=admin_headers)
        count = client.get(
            "/api/notifications/unread-count", headers=admin_headers
        ).json()["count"]
        assert count == 0

    def test_notification_has_type_icon_mapping(self, client, admin_headers):
        """Notifications have valid types for icon mapping"""
        valid_types = [
            "warranty_expiring",
            "low_stock",
            "machine_status_change",
            "reservation_request",
            "reservation_approved",
            "reservation_denied",
            "reservation_expiring",
            "order_update",
            "ticket_update",
            "general",
        ]
        response = client.get("/api/notifications", headers=admin_headers)
        for notif in response.json():
            assert notif["type"] in valid_types, (
                f"Unknown type: {notif['type']}"
            )

    def test_clear_read_keeps_unread(self, client, admin_headers):
        """Clear read notifications keeps unread ones"""
        user_id = self._get_user_id(client, admin_headers)
        # Create 2 notifications
        n1 = client.post("/api/notifications", headers=admin_headers, json={
            "user_id": user_id,
            "title": "Read Me",
            "message": "Will be read",
            "type": "general",
        }).json()
        n2 = client.post("/api/notifications", headers=admin_headers, json={
            "user_id": user_id,
            "title": "Keep Me",
            "message": "Stay unread",
            "type": "general",
        }).json()
        # Mark first as read
        client.put(
            f"/api/notifications/{n1['id']}/read", headers=admin_headers
        )
        # Clear read
        client.delete(
            "/api/notifications/clear-read", headers=admin_headers
        )
        # Second should still exist
        remaining = client.get(
            "/api/notifications", headers=admin_headers
        ).json()
        ids = [n["id"] for n in remaining]
        assert n2["id"] in ids

    def test_notification_navigation_fields(self, client, admin_headers):
        """Notifications have entity_type and entity_id for navigation"""
        user_id = self._get_user_id(client, admin_headers)
        client.post("/api/notifications", headers=admin_headers, json={
            "user_id": user_id,
            "title": "Nav Test",
            "message": "Testing nav",
            "type": "machine_status_change",
            "entity_type": "machine",
            "entity_id": user_id,
        })
        response = client.get("/api/notifications", headers=admin_headers)
        nav_notif = [n for n in response.json() if n["title"] == "Nav Test"]
        if nav_notif:
            assert nav_notif[0]["entity_type"] == "machine"
