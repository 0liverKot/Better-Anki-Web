"""End-to-end sync against a real Anki sync server.

A second Collection stands in for "Anki on your phone/desktop" syncing to the same
account, so these tests check that work done on the web reaches other devices and back.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from anki.collection import Collection
from anki.sync_pb2 import SyncCollectionResponse, SyncStatusResponse

from tests.conftest import SYNC_USER, Client, add_basic

Required = SyncCollectionResponse.ChangesRequired


class OtherDevice:
    def __init__(self, path: Path, endpoint: str) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.col = Collection(str(path / "collection.anki2"))
        self.auth = self.col.sync_login(SYNC_USER[0], SYNC_USER[1], endpoint)

    def sync(self) -> int:
        out = self.col.sync_collection(self.auth, sync_media=False)
        if out.required in (Required.FULL_UPLOAD, Required.FULL_DOWNLOAD, Required.FULL_SYNC):
            upload = out.required != Required.FULL_DOWNLOAD
            self.col.close_for_full_sync()
            self.col.full_upload_or_download(auth=self.auth, server_usn=None, upload=upload)
            self.col.reopen(after_full_sync=True)
        return out.required

    def add(self, front: str) -> None:
        note = self.col.new_note(self.col.models.by_name("Basic"))
        note["Front"] = front
        note["Back"] = "back"
        self.col.add_note(note, self.col.decks.id("Default"))


def _wait_idle(client: Client, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get("/api/sync/status").json()
        if status["state"] != "syncing":
            return status
        time.sleep(0.2)
    raise AssertionError("sync did not finish")


def _login(client: Client, endpoint: str) -> dict:
    response = client.post(
        "/api/sync/login",
        json={"username": SYNC_USER[0], "password": SYNC_USER[1], "endpoint": endpoint},
    )
    assert response.status_code == 200, response.text
    return _wait_idle(client)


def test_bad_credentials(client: Client, sync_server: str) -> None:
    response = client.post(
        "/api/sync/login", json={"username": SYNC_USER[0], "password": "wrong", "endpoint": sync_server}
    )
    assert response.status_code == 400
    assert client.get("/api/sync/status").json()["logged_in"] is False


def test_first_login_downloads_existing_collection(
    client: Client, sync_server: str, tmp_path: Path
) -> None:
    phone = OtherDevice(tmp_path / "phone", sync_server)
    phone.add("made on phone")
    assert phone.sync() == Required.FULL_UPLOAD

    status = _login(client, sync_server)
    assert status["state"] == "idle", status
    assert status["last_sync_at"]

    # The server's empty copy was replaced by the account's collection automatically.
    deck_id = client.get("/api/add/defaults").json()["deck_id"]
    card = client.get(f"/api/review/{deck_id}/next").json()["card"]
    assert "made on phone" in card["question"]

    # Review on the web, add a card on the web, sync, and the phone sees both.
    client.post(
        "/api/review/answer",
        json={"deck_id": deck_id, "card_id": card["id"], "rating": 3, "time_taken_ms": 2000},
    )
    add_basic(client, "made on web")
    assert client.get("/api/sync/status").json()["local_changes"] is True
    status = client.post("/api/sync?wait=true").json()
    assert status["state"] == "idle", status
    assert status["local_changes"] is False

    phone.sync()
    assert phone.col.db.scalar("select count() from revlog") == 1
    assert phone.col.find_notes('"front:made on web"')

    # And changes from the phone come back to the web.
    phone.add("second from phone")
    phone.sync()
    client.post("/api/sync?wait=true")
    decks = client.get("/api/decks").json()["decks"]
    assert sum(d["new"] for d in decks) == 2  # "made on web" + "second from phone"
    phone.col.close()


def test_conflict_requires_choice(client: Client, sync_server: str, tmp_path: Path) -> None:
    phone = OtherDevice(tmp_path / "phone", sync_server)
    phone.add("phone card")
    phone.sync()

    # Content on the server that was never synced: neither side may silently win.
    add_basic(client, "web-only card")
    status = _login(client, sync_server)
    assert status["state"] == "full_sync_required"
    assert status["full_sync"] == {"suggested": None}

    status = client.post("/api/sync/full", json={"direction": "download"}).json()
    assert status["state"] == "idle", status
    deck_id = client.get("/api/add/defaults").json()["deck_id"]
    card = client.get(f"/api/review/{deck_id}/next").json()["card"]
    assert "phone card" in card["question"]
    phone.col.close()


def test_logout(client: Client, sync_server: str) -> None:
    _login(client, sync_server)
    status = client.post("/api/sync/logout").json()
    assert status["logged_in"] is False
    assert status["state"] == "logged_out"
    assert client.post("/api/sync").status_code == 400


def test_background_sync_pushes_and_pulls(
    client: Client, sync_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = OtherDevice(tmp_path / "phone", sync_server)
    phone.add("first")
    phone.sync()
    _login(client, sync_server)

    manager = client.app.state.sync  # type: ignore[attr-defined]
    settings = client.app.state.settings  # type: ignore[attr-defined]
    settings.autosync_idle_seconds = 0
    settings.autosync_poll_seconds = 0

    # The periodic check asks the server whether anything changed. Anki caches that
    # answer for a few minutes (fine with the 10 minute default), so stub it here.
    col = manager.cm._col
    real_status = col.sync_status
    monkeypatch.setattr(col, "sync_status", lambda auth: SyncStatusResponse(required=SyncStatusResponse.NO_CHANGES))
    last = manager.last_sync_at
    manager._tick()
    assert manager.last_sync_at == last  # nothing changed: no sync

    # A card added on the phone is pulled in once the check reports changes.
    phone.add("from phone later")
    phone.sync()
    monkeypatch.setattr(col, "sync_status", lambda auth: SyncStatusResponse(required=SyncStatusResponse.NORMAL_SYNC))
    manager._tick()
    monkeypatch.setattr(col, "sync_status", real_status)
    assert manager.last_sync_at != last
    decks = client.get("/api/decks").json()["decks"]
    assert sum(d["new"] for d in decks) == 2

    # A card added on the web is pushed once the server is idle.
    add_basic(client, "from web later")
    manager._tick()
    assert client.get("/api/sync/status").json()["local_changes"] is False
    phone.sync()
    assert phone.col.find_notes('"front:from web later"')
    phone.col.close()
