"""
Integration smoke tests for the auth API endpoints.
Uses FastAPI TestClient with the in-memory SQLite DB.

These tests verify the full request → response cycle without a
real PostgreSQL database.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestAuthEndpoints:
    def test_register_new_user(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "alice@example.com", "password": "password123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert "id" in data
        assert "hashed_password" not in data  # never exposed

    def test_register_duplicate_email(self, client: TestClient):
        payload = {"email": "dup@example.com", "password": "password123"}
        client.post("/api/v1/auth/register", json=payload)
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409

    def test_login_valid_credentials(self, client: TestClient):
        # First register
        client.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "password": "securepass"},
        )
        # Then login
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "securepass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_wrong_password(self, client: TestClient):
        client.post(
            "/api/v1/auth/register",
            json={"email": "carol@example.com", "password": "rightpass"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "carol@example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything"},
        )
        assert resp.status_code == 401

    def test_password_too_short_rejected(self, client: TestClient):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_authenticated_request(self, client: TestClient):
        """Register, login, then call a protected endpoint."""
        client.post(
            "/api/v1/auth/register",
            json={"email": "dave@example.com", "password": "password123"},
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "dave@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # Protected endpoint: list workflows
        resp = client.get(
            "/api/v1/workflows",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_unauthenticated_request_rejected(self, client: TestClient):
        resp = client.get("/api/v1/workflows")
        assert resp.status_code == 403  # HTTPBearer returns 403 when no token


class TestHealthEndpoint:
    def test_health_check(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
