"""
Confirms signup/login still work end-to-end now that User/FaceProfile are
schema-qualified under auth.* instead of the default public schema.
"""
from fastapi.testclient import TestClient

from app.database.models import User
from app.main import app

client = TestClient(app)


def test_signup_creates_a_user_in_auth_users(db, unique_suffix):
    username = f"schematest_{unique_suffix}"
    response = client.post(
        "/auth/signup",
        json={
            "full_name": "Schema Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "pending_enrollment"

    user = db.query(User).filter_by(username=username).one()
    assert user.email == f"{username}@example.com"

    db.delete(user)
    db.commit()


def test_login_with_wrong_password_is_rejected(db, unique_suffix):
    username = f"schematest_{unique_suffix}"
    client.post(
        "/auth/signup",
        json={
            "full_name": "Schema Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )

    response = client.post("/auth/login", json={"username": username, "password": "wrong-password"})
    assert response.status_code == 401

    user = db.query(User).filter_by(username=username).one()
    db.delete(user)
    db.commit()
