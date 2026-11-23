from __future__ import annotations

from tests.conftest import PASSWORD, Client


def test_api_requires_login(anon: Client) -> None:
    assert anon.get("/api/auth/me").json() == {"authenticated": False}
    assert anon.get("/api/decks").status_code == 401


def test_wrong_password_rejected(anon: Client) -> None:
    response = anon.post("/api/auth/login", json={"password": "nope"})
    assert response.status_code == 401
    assert anon.get("/api/decks").status_code == 401


def test_login_and_logout(anon: Client) -> None:
    assert anon.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert anon.get("/api/auth/me").json() == {"authenticated": True}
    assert anon.get("/api/decks").status_code == 200
    anon.post("/api/auth/logout")
    assert anon.get("/api/decks").status_code == 401


def test_csrf_header_required_for_writes(client: Client) -> None:
    response = client.post("/api/sync/soon", headers={"X-Requested-With": ""})
    assert response.status_code == 403


def test_forged_cookie_rejected(anon: Client) -> None:
    anon.cookies.set("baw_session", "eyJmIjoiYWJjIn0.forged.signature")
    assert anon.get("/api/decks").status_code == 401


def test_login_rate_limited(anon: Client) -> None:
    for _ in range(10):
        anon.post("/api/auth/login", json={"password": "wrong"})
    response = anon.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 429


def test_bcrypt_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import bcrypt

    from app.main import create_app
    from tests.conftest import make_settings

    hashed = bcrypt.hashpw(b"hunter22", bcrypt.gensalt()).decode()
    settings = make_settings(tmp_path / "d", password=None, password_hash=hashed)
    with Client(create_app(settings)) as client:
        assert client.post("/api/auth/login", json={"password": "hunter2"}).status_code == 401
        assert client.post("/api/auth/login", json={"password": "hunter22"}).status_code == 200
