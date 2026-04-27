import pytest
from fastapi.testclient import TestClient
from app.main import app
import uuid

SUPER_ADMIN_EMAIL = "bgh.huybui@gmail.com"
SUPER_ADMIN_PASSWORD = "Huy13062"
ADMIN_EMAIL = "bgh1506@gmail.com"
ADMIN_PASSWORD = "Huy13062"
REP_EMAIL = "minh.tran@example.com"
REP_PASSWORD = "Minh2026!"


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def super_admin_token(client):
    response = client.post("/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Super admin login failed: {response.json()}"
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client):
    response = client.post("/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.json()}"
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def rep_token(client):
    response = client.post("/api/auth/login", json={
        "email": REP_EMAIL, "password": REP_PASSWORD
    })
    assert response.status_code == 200, f"Rep login failed: {response.json()}"
    return response.json()["access_token"]


@pytest.fixture
def super_admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def rep_headers(rep_token):
    return {"Authorization": f"Bearer {rep_token}"}


def unique_id(prefix: str = "TEST") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
