"""Sprint 3 Task 3.5 — notification endpoint tests."""

import pytest
from conftest import unique_id

pytestmark = [pytest.mark.sprint3, pytest.mark.sprint3_5]


class TestNotifications:
    def _create_notification(self, client, admin_headers, user_id):
        """Helper: admin creates a notification for a user"""
        return client.post("/api/notifications", headers=admin_headers, json={
            "user_id": user_id,
            "title": "Test Notification",
            "message": "This is a test notification",
            "type": "general"
        })

    def _get_current_user_id(self, client, headers):
        """Helper: get current user's id"""
        response = client.get("/api/auth/me", headers=headers)
        return response.json()["id"]

    def test_get_notifications_empty(self, client, rep_headers):
        """New user may have empty or existing notifications"""
        response = client.get("/api/notifications", headers=rep_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_admin_create_notification(self, client, admin_headers, rep_headers):
        """Admin can create notification for a user"""
        rep_id = self._get_current_user_id(client, rep_headers)
        response = self._create_notification(client, admin_headers, rep_id)
        assert response.status_code == 201, f"Create failed: {response.json()}"

    def test_user_sees_own_notifications(self, client, admin_headers, rep_headers):
        """User only sees their own notifications"""
        rep_id = self._get_current_user_id(client, rep_headers)
        self._create_notification(client, admin_headers, rep_id)
        response = client.get("/api/notifications", headers=rep_headers)
        assert response.status_code == 200
        for notif in response.json():
            assert notif["user_id"] == rep_id

    def test_unread_count(self, client, admin_headers, rep_headers):
        """Unread count returns correct number"""
        rep_id = self._get_current_user_id(client, rep_headers)
        self._create_notification(client, admin_headers, rep_id)
        response = client.get(
            "/api/notifications/unread-count", headers=rep_headers
        )
        assert response.status_code == 200
        assert "count" in response.json()
        assert response.json()["count"] >= 1

    def test_mark_as_read(self, client, admin_headers, rep_headers):
        """User can mark notification as read"""
        rep_id = self._get_current_user_id(client, rep_headers)
        created = self._create_notification(
            client, admin_headers, rep_id
        ).json()
        response = client.put(
            f"/api/notifications/{created['id']}/read", headers=rep_headers
        )
        assert response.status_code == 200, f"Mark-read failed: {response.json()}"
        assert response.json()["is_read"] is True

    def test_mark_all_read(self, client, admin_headers, rep_headers):
        """User can mark all notifications as read"""
        rep_id = self._get_current_user_id(client, rep_headers)
        self._create_notification(client, admin_headers, rep_id)
        self._create_notification(client, admin_headers, rep_id)
        response = client.put("/api/notifications/read-all", headers=rep_headers)
        assert response.status_code == 200
        assert response.json()["updated"] >= 0
        # Verify unread count is now 0
        count = client.get(
            "/api/notifications/unread-count", headers=rep_headers
        ).json()
        assert count["count"] == 0

    def test_delete_notification(self, client, admin_headers, rep_headers):
        """User can delete their own notification"""
        rep_id = self._get_current_user_id(client, rep_headers)
        created = self._create_notification(
            client, admin_headers, rep_id
        ).json()
        response = client.delete(
            f"/api/notifications/{created['id']}", headers=rep_headers
        )
        assert response.status_code == 200, f"Delete failed: {response.json()}"

    def test_cannot_read_others_notification(
        self, client, admin_headers, rep_headers
    ):
        """User cannot access another user's notification"""
        admin_id = self._get_current_user_id(client, admin_headers)
        created = self._create_notification(
            client, admin_headers, admin_id
        ).json()
        # Rep tries to read admin's notification
        response = client.get(
            f"/api/notifications/{created['id']}", headers=rep_headers
        )
        assert response.status_code == 403

    def test_cannot_delete_others_notification(
        self, client, admin_headers, rep_headers
    ):
        """User cannot delete another user's notification"""
        admin_id = self._get_current_user_id(client, admin_headers)
        created = self._create_notification(
            client, admin_headers, admin_id
        ).json()
        response = client.delete(
            f"/api/notifications/{created['id']}", headers=rep_headers
        )
        assert response.status_code == 403

    def test_clear_read_notifications(
        self, client, admin_headers, rep_headers
    ):
        """Clear all read notifications keeps unread ones"""
        rep_id = self._get_current_user_id(client, rep_headers)
        # Create 2 notifications
        n1 = self._create_notification(client, admin_headers, rep_id).json()
        n2 = self._create_notification(client, admin_headers, rep_id).json()
        # Mark first as read
        client.put(f"/api/notifications/{n1['id']}/read", headers=rep_headers)
        # Clear read
        response = client.delete(
            "/api/notifications/clear-read", headers=rep_headers
        )
        assert response.status_code == 200
        assert response.json()["deleted"] >= 1
        # Second notification should still exist (unread)
        remaining = client.get(
            "/api/notifications?is_read=false", headers=rep_headers
        ).json()
        ids = [n["id"] for n in remaining]
        assert n2["id"] in ids

    def test_broadcast_to_all(self, client, admin_headers):
        """Admin can broadcast notification to all users"""
        response = client.post(
            "/api/notifications/broadcast",
            headers=admin_headers,
            json={
                "title": "System Maintenance",
                "message": "Portal will be down for maintenance tonight at 10 PM",
                "type": "general",
                "role_filter": "all",
            },
        )
        assert response.status_code == 200, f"Broadcast failed: {response.json()}"
        assert response.json()["sent_to"] >= 1

    def test_broadcast_to_reps_only(self, client, admin_headers):
        """Admin can broadcast to reps only"""
        response = client.post(
            "/api/notifications/broadcast",
            headers=admin_headers,
            json={
                "title": "New Commission Rates",
                "message": "Commission rates updated for next month",
                "type": "general",
                "role_filter": "rep",
            },
        )
        assert response.status_code == 200

    def test_rep_cannot_create_notification(
        self, client, rep_headers, admin_headers
    ):
        """Rep cannot create notifications for others"""
        admin_id = self._get_current_user_id(client, admin_headers)
        response = client.post("/api/notifications", headers=rep_headers, json={
            "user_id": admin_id,
            "title": "Should fail",
            "message": "Reps cannot send",
            "type": "general"
        })
        assert response.status_code == 403

    def test_rep_cannot_broadcast(self, client, rep_headers):
        """Rep cannot broadcast"""
        response = client.post(
            "/api/notifications/broadcast",
            headers=rep_headers,
            json={
                "title": "Should fail",
                "message": "Reps cannot broadcast",
                "type": "general",
            },
        )
        assert response.status_code == 403

    def test_filter_by_type(self, client, admin_headers, rep_headers):
        """Can filter notifications by type"""
        rep_id = self._get_current_user_id(client, rep_headers)
        client.post("/api/notifications", headers=admin_headers, json={
            "user_id": rep_id,
            "title": "Stock Alert",
            "message": "Low stock",
            "type": "low_stock"
        })
        response = client.get(
            "/api/notifications?type=low_stock", headers=rep_headers
        )
        assert response.status_code == 200
        for notif in response.json():
            assert notif["type"] == "low_stock"

    def test_pagination(self, client, admin_headers, rep_headers):
        """Pagination with limit and offset works"""
        response = client.get(
            "/api/notifications?limit=5&offset=0", headers=rep_headers
        )
        assert response.status_code == 200
        assert len(response.json()) <= 5
