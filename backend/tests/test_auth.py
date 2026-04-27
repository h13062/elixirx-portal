"""Sprint 1 — auth endpoint tests."""

from conftest import unique_id


class TestHealthCheck:
    def test_health_endpoint(self, client):
        """API health check returns ok"""
        response = client.get("/api/health")
        assert response.status_code == 200, f"Health check failed: {response.json()}"
        assert response.json()["status"] == "ok"


class TestLogin:
    def test_login_super_admin(self, client):
        """Super admin can login and gets correct role"""
        response = client.post("/api/auth/login", json={
            "email": "bgh.huybui@gmail.com", "password": "Huy13062"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "super_admin"

    def test_login_admin(self, client):
        """Admin can login"""
        response = client.post("/api/auth/login", json={
            "email": "bgh1506@gmail.com", "password": "Huy13062"
        })
        assert response.status_code == 200
        assert response.json()["user"]["role"] in ["admin", "super_admin"]

    def test_login_rep(self, client):
        """Rep can login and gets correct role and tier"""
        response = client.post("/api/auth/login", json={
            "email": "minh.tran@example.com", "password": "Minh2026!"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["role"] == "rep"
        assert data["user"]["tier"] is not None

    def test_login_wrong_password(self, client):
        """Wrong password returns 401"""
        response = client.post("/api/auth/login", json={
            "email": "bgh.huybui@gmail.com", "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_login_nonexistent_email(self, client):
        """Nonexistent email returns 401"""
        response = client.post("/api/auth/login", json={
            "email": "nobody@nowhere.com", "password": "test123"
        })
        assert response.status_code == 401


class TestAdminSetup:
    def test_wrong_admin_code(self, client):
        """Wrong admin code returns 403"""
        response = client.post("/api/auth/admin-setup", json={
            "email": "test@test.com", "password": "test12345",
            "full_name": "Test", "admin_code": "WRONGCODE"
        })
        assert response.status_code == 403


class TestProtectedRoutes:
    def test_no_token_rejected(self, client):
        """Requests without auth token are rejected"""
        response = client.get("/api/machines")
        assert response.status_code in [401, 403, 422], (
            f"Expected auth error, got {response.status_code}"
        )

    def test_invalid_token_rejected(self, client):
        """Requests with invalid token are rejected"""
        response = client.get(
            "/api/machines",
            headers={"Authorization": "Bearer fake_token_123"},
        )
        assert response.status_code in [401, 403]


class TestGetMe:
    def test_get_me_super_admin(self, client, super_admin_headers):
        """GET /api/auth/me returns current user profile"""
        response = client.get("/api/auth/me", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "bgh.huybui@gmail.com"
        assert data["role"] == "super_admin"


class TestInviteRep:
    def test_invite_as_admin(self, client, super_admin_headers):
        """Admin can invite a new rep with auto-generated password"""
        test_email = f"test-{unique_id()}@example.com"
        response = client.post("/api/auth/invite", headers=super_admin_headers, json={
            "email": test_email, "full_name": "Test Rep", "tier": "distributor"
        })
        assert response.status_code == 201, f"Invite failed: {response.json()}"
        data = response.json()
        assert (
            "temporary_password" in data
            or "temp_password" in data
            or "password" in data
        )
        # Clean up: delete the test user
        from app.core.supabase_client import supabase_admin
        users = supabase_admin.auth.admin.list_users()
        for u in users:
            if u.email == test_email:
                supabase_admin.auth.admin.delete_user(str(u.id))
                break

    def test_invite_as_rep_forbidden(self, client, rep_headers):
        """Rep cannot invite other reps"""
        response = client.post("/api/auth/invite", headers=rep_headers, json={
            "email": "should-fail@example.com",
            "full_name": "Fail",
            "tier": "distributor",
        })
        assert response.status_code == 403
