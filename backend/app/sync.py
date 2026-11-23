"""Keeps the server's collection in sync with AnkiWeb (or a self-hosted sync server).

The server acts as one more Anki client, exactly like desktop or AnkiDroid: it holds its
own copy of the collection and exchanges changes with the sync server.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Literal

from anki.errors import BackendError, SyncError, SyncErrorKind
from anki.sync_pb2 import SyncAuth, SyncCollectionResponse, SyncStatusResponse

from .collection import CollectionManager
from .config import Settings

log = logging.getLogger(__name__)

Required = SyncCollectionResponse.ChangesRequired
State = Literal["logged_out", "idle", "syncing", "error", "full_sync_required", "auth_required"]

TICK_SECONDS = 5
RETRY_AFTER_ERROR_SECONDS = 120


class NotLoggedIn(Exception):
    pass


class SyncManager:
    def __init__(self, cm: CollectionManager, settings: Settings) -> None:
        self.cm = cm
        self.settings = settings
        self.auth_file = settings.data_dir / "sync_auth.json"
        self._auth: dict[str, Any] | None = self._load_auth()

        self._state_lock = threading.Lock()
        self._run_lock = threading.Lock()  # one sync (normal or full) at a time
        self.state: State = "idle" if self.logged_in else "logged_out"
        self.last_sync_at: float | None = None
        self.last_error: str | None = None
        self.server_message: str | None = None
        # Set when a one-way full sync is needed and the user has to pick a direction.
        # suggested is "upload" when the server copy has content and the sync server is
        # empty, otherwise None (both sides changed incompatibly).
        self.full_sync_info: dict[str, Any] | None = None
        self._server_media_usn: int | None = None

        self._requested_at: float | None = None
        self._next_retry_at = 0.0
        self._last_poll_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # Credentials
    ##########################################################################

    def _load_auth(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.auth_file.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            log.exception("Could not read %s", self.auth_file)
            return None

    def _save_auth(self, data: dict[str, Any] | None) -> None:
        self._auth = data
        if data is None:
            self.auth_file.unlink(missing_ok=True)
            return
        self.auth_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.auth_file.with_suffix(".tmp")
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.auth_file)

    @property
    def logged_in(self) -> bool:
        return bool(self._auth and self._auth.get("hkey"))

    def _sync_auth(self) -> SyncAuth:
        if not self.logged_in:
            raise NotLoggedIn("Not logged in to a sync server.")
        assert self._auth
        endpoint = self._auth.get("endpoint") or None
        return SyncAuth(hkey=self._auth["hkey"], endpoint=endpoint)

    def login(self, username: str, password: str, endpoint: str | None) -> None:
        endpoint = (endpoint or self.settings.sync_endpoint or "").strip() or None
        with self.cm.use() as col:
            auth = col.sync_login(username=username, password=password, endpoint=endpoint)
        self._save_auth(
            {
                "username": username,
                "hkey": auth.hkey,
                "endpoint": auth.endpoint if auth.HasField("endpoint") else endpoint,
            }
        )
        self._set(state="idle", last_error=None, full_sync_info=None, server_message=None)
        self.last_sync_at = None
        self._next_retry_at = 0.0

    def logout(self) -> None:
        self._save_auth(None)
        self._set(state="logged_out", last_error=None, full_sync_info=None, server_message=None)

    # Status
    ##########################################################################

    def _set(self, **fields: Any) -> None:
        with self._state_lock:
            for key, value in fields.items():
                setattr(self, key, value)

    def status(self) -> dict[str, Any]:
        media_syncing, media_error = self._media_status()
        auth = self._auth or {}
        with self._state_lock:
            return {
                "logged_in": self.logged_in,
                "username": auth.get("username"),
                "endpoint": auth.get("endpoint") or None,
                "state": self.state,
                "last_sync_at": self.last_sync_at,
                "last_error": self.last_error,
                "server_message": self.server_message,
                "full_sync": self.full_sync_info,
                "media_syncing": media_syncing,
                "media_error": media_error,
                "local_changes": self.cm.last_mutation > (self.last_sync_at or 0.0),
            }

    def _media_status(self) -> tuple[bool, str | None]:
        # Don't wait behind a long sync just to report media progress.
        if not self.cm.lock.acquire(timeout=0.2):
            return False, None
        try:
            with self.cm.use() as col:
                return col.media_sync_status().active, None
        except BackendError as err:
            return False, str(err)
        except Exception:
            return False, None
        finally:
            self.cm.lock.release()

    # Syncing
    ##########################################################################

    def start_sync(self, reason: str = "manual") -> None:
        """Sync in a background thread, so long full downloads don't hold a request open."""
        if not self.logged_in:
            raise NotLoggedIn("Not logged in to a sync server.")
        if self._run_lock.locked():
            return
        self._set(state="syncing")
        threading.Thread(target=self.sync, args=(reason,), daemon=True).start()

    def request_sync(self, delay: float = 5.0) -> None:
        """Ask the background loop to sync soon (e.g. when the user leaves the page)."""
        self._requested_at = time.time() + delay

    def sync(self, reason: str = "manual") -> dict[str, Any]:
        """Run a normal sync now, blocking. Performs a full download automatically when
        this server's copy is empty; any other full sync waits for the user to choose."""
        auth = self._sync_auth()
        if not self._run_lock.acquire(blocking=False):
            # Another sync is running: wait for it rather than starting a second one.
            with self._run_lock:
                pass
            return self.status()
        try:
            log.info("Syncing (%s)", reason)
            self._set(state="syncing")
            with self.cm.use() as col:
                out = col.sync_collection(auth=auth, sync_media=True)
                if out.HasField("new_endpoint") and self._auth:
                    self._save_auth({**self._auth, "endpoint": out.new_endpoint})
                    auth = self._sync_auth()
                self._server_media_usn = out.server_media_usn
                message = out.server_message or None

                if out.required in (Required.NO_CHANGES, Required.NORMAL_SYNC):
                    self._finished(message)
                elif out.required == Required.FULL_DOWNLOAD:
                    # Only returned when this server's copy is empty, so nothing is lost.
                    self._full_sync_locked(col, auth, upload=False)
                    self._finished(message)
                else:
                    suggested = "upload" if out.required == Required.FULL_UPLOAD else None
                    self._set(
                        state="full_sync_required",
                        full_sync_info={"suggested": suggested},
                        server_message=message,
                        last_error=None,
                    )
        except SyncError as err:
            self._failed(err)
        except NotLoggedIn:
            raise
        except Exception as err:  # network errors, server errors, closed collection
            self._failed(err)
        finally:
            self._run_lock.release()
        return self.status()

    def full_sync(self, direction: Literal["upload", "download"]) -> dict[str, Any]:
        """One-way sync chosen by the user. Upload replaces the sync server's copy with
        this server's; download replaces this server's copy with the sync server's."""
        auth = self._sync_auth()
        with self._run_lock:
            try:
                self._set(state="syncing")
                with self.cm.use() as col:
                    self._full_sync_locked(col, auth, upload=direction == "upload")
                self._finished(None)
            except Exception as err:
                self._failed(err)
                if self.state == "error":
                    # Still unresolved: keep asking for a direction.
                    self._set(state="full_sync_required", full_sync_info=self.full_sync_info or {"suggested": None})
        return self.status()

    def _full_sync_locked(self, col: Any, auth: SyncAuth, upload: bool) -> None:
        log.info("Full sync: %s", "upload" if upload else "download")
        col.close_for_full_sync()
        try:
            col.full_upload_or_download(
                auth=auth, server_usn=self._server_media_usn, upload=upload
            )
        finally:
            # The backend reopens the collection whether or not the transfer succeeded.
            col.reopen(after_full_sync=True)

    def _finished(self, message: str | None) -> None:
        self._set(
            state="idle",
            last_sync_at=time.time(),
            last_error=None,
            server_message=message,
            full_sync_info=None,
        )
        self._next_retry_at = 0.0

    def _failed(self, err: Exception) -> None:
        if isinstance(err, SyncError) and err.kind == SyncErrorKind.AUTH:
            # Token rejected (password changed, or logged out elsewhere). Keep the
            # username so the login form can be prefilled.
            if self._auth:
                self._save_auth({**self._auth, "hkey": None})
            self._set(state="auth_required", last_error=str(err))
            log.warning("Sync auth rejected: %s", err)
            return
        log.warning("Sync failed: %s", err)
        self._set(state="error", last_error=str(err) or type(err).__name__)
        self._next_retry_at = time.time() + RETRY_AFTER_ERROR_SECONDS

    # Background loop
    ##########################################################################

    def start(self) -> None:
        if not self.settings.autosync or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="autosync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            try:
                self._tick()
            except Exception:
                log.exception("Autosync tick failed")

    def _tick(self) -> None:
        if not self.logged_in or self.state in ("full_sync_required", "auth_required"):
            return
        if self._run_lock.locked():
            return
        now = time.time()
        requested = self._requested_at is not None and now >= self._requested_at
        if now < self._next_retry_at and not requested:
            return

        last = self.last_sync_at or 0.0
        idle = now - self.cm.last_mutation
        if requested:
            reason = "requested"
        elif self.cm.last_mutation > last and idle >= self.settings.autosync_idle_seconds:
            reason = "local changes"
        elif now - max(last, self._last_poll_at) >= self.settings.autosync_poll_seconds:
            self._last_poll_at = now
            # Cheap check: only does a full sync round-trip if either side changed.
            with self.cm.use() as col:
                status = col.sync_status(self._sync_auth())
            if status.required == SyncStatusResponse.NO_CHANGES:
                return
            reason = "remote changes"
        else:
            return

        self._requested_at = None
        self.sync(reason)

    def sync_if_stale(self, max_age: float) -> None:
        """Start a sync unless one finished within max_age seconds."""
        if not self.logged_in or self.state in ("full_sync_required", "auth_required"):
            return
        if self.last_sync_at and time.time() - self.last_sync_at < max_age:
            return
        self.start_sync("app opened")
