from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PASSWORD = "correct horse battery"
SYNC_USER = ("tester", "sync-pass")


def make_settings(data_dir: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "data_dir": data_dir,
        "password": PASSWORD,
        "secret_key": "test-secret",
        "autosync": False,
        "frontend_dist": data_dir / "no-frontend",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


class Client(TestClient):
    """TestClient that sends the CSRF header like the real frontend does."""

    def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def, override]
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("X-Requested-With", "baw")
        return super().request(method, url, headers=headers, **kwargs)


@pytest.fixture
def anon(tmp_path: Path) -> Iterator[Client]:
    with Client(create_app(make_settings(tmp_path / "data"))) as client:
        yield client


@pytest.fixture
def client(anon: Client) -> Client:
    response = anon.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return anon


def add_basic(client: Client, front: str, back: str = "back", **extra: object) -> dict:
    defaults = client.get("/api/add/defaults").json()
    types = {t["name"]: t for t in client.get("/api/notetypes").json()}
    body = {
        "notetype_id": types[extra.pop("notetype", "Basic")]["id"],  # type: ignore[index]
        "deck_id": defaults["deck_id"],
        "fields": extra.pop("fields", [front, back]),
        **extra,
    }
    return client.post("/api/notes", json=body).json()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sync_server(tmp_path: Path) -> Iterator[str]:
    """A real Anki sync server (bundled with the anki package) on a local port."""
    port = _free_port()
    env = {
        **os.environ,
        "SYNC_USER1": f"{SYNC_USER[0]}:{SYNC_USER[1]}",
        "SYNC_BASE": str(tmp_path / "syncserver"),
        "SYNC_HOST": "127.0.0.1",
        "SYNC_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "anki.syncserver"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("Anki sync server did not start")
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
