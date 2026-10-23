from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


def test_http_credential_api_never_returns_secret_data(client: TestClient, monkeypatch):
    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr("app.services.credential_service._get_fernet", lambda: fernet)
    email = "http-credential-api@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    secret = "test-api-key-that-must-not-return"

    created = client.post(
        "/api/v1/credentials",
        json={
            "name": "Integration API key",
            "type": "api_key",
            "data": {"api_key": secret},
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert "data" not in created.json()
    assert secret not in created.text

    listed = client.get("/api/v1/credentials", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "data" not in listed.json()[0]
    assert secret not in listed.text
