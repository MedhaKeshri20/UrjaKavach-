"""Auth: register (public + official), login, /me, and token behaviour."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.db as db
from backend.app import create_app
from backend.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from backend.config import Settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False}, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", SessionLocal)
    app = create_app(Settings(database_url=db_url, seed_on_startup=False))
    with TestClient(app) as c:
        yield c


def test_password_hash_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_verify_rejects_malformed_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_long_password_does_not_crash():
    # >72 bytes must not raise (bcrypt's limit) — it truncates consistently.
    long_pw = "a" * 200
    h = hash_password(long_pw)
    assert verify_password(long_pw, h) is True


def test_long_password_registers_and_logs_in(client):
    long_pw = "z" * 100
    r = client.post(
        "/auth/register",
        json={"email": "long@x.com", "password": long_pw, "role": "official"},
    )
    assert r.status_code == 201  # not a 500
    login = client.post("/auth/login", json={"email": "long@x.com", "password": long_pw})
    assert login.status_code == 200


@pytest.mark.parametrize("role", ["citizen", "official"])
def test_register_both_roles(client, role):
    r = client.post(
        "/auth/register",
        json={"email": f"{role}@x.com", "password": "secret123", "role": role},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == role
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # dashboard hint drives the post-signup redirect
    assert body["dashboard"] == ("/official" if role == "official" else "/citizen")


def test_register_defaults_to_citizen(client):
    r = client.post(
        "/auth/register", json={"email": "nodrole@x.com", "password": "secret123"}
    )
    assert r.status_code == 201
    assert r.json()["role"] == "citizen"


def test_register_rejects_bad_role(client):
    r = client.post(
        "/auth/register",
        json={"email": "b@x.com", "password": "secret123", "role": "admin"},
    )
    assert r.status_code == 422  # Literal["public","official"] only


def test_register_rejects_short_password(client):
    r = client.post(
        "/auth/register", json={"email": "b@x.com", "password": "123", "role": "public"}
    )
    assert r.status_code == 422


def test_duplicate_email_conflict(client):
    payload = {"email": "dup@x.com", "password": "secret123", "role": "citizen"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_login_and_me(client):
    client.post(
        "/auth/register",
        json={"email": "o@x.com", "password": "secret123", "role": "official"},
    )
    r = client.post("/auth/login", json={"email": "o@x.com", "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "o@x.com"
    assert me.json()["role"] == "official"


def test_login_wrong_password(client):
    client.post(
        "/auth/register",
        json={"email": "o2@x.com", "password": "secret123", "role": "citizen"},
    )
    r = client.post("/auth/login", json={"email": "o2@x.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_token_for_unknown_user_rejected(client):
    # a validly-signed token whose subject isn't in the DB must 401
    token = create_access_token(subject="ghost@x.com", role="official")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
