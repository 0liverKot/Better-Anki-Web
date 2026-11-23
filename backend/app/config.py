from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """All settings come from environment variables prefixed with BAW_, or from a .env
    file: the repo root's (shared with docker-compose) and then backend/.env, which wins.
    Real environment variables override both."""

    model_config = SettingsConfigDict(
        env_prefix="BAW_",
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # Where the collection, media, AnkiWeb token and secret key live. Must be persistent.
    data_dir: Path = Path("data")

    # App login. Prefer a bcrypt hash (generate with `python -m app.hash_password`).
    # A plain password is accepted for local development.
    password_hash: str | None = None
    password: str | None = None

    # Signs session cookies and derives the media URL token. Generated and stored in
    # data_dir if not given.
    secret_key: str | None = None

    # Set true when served over HTTPS (it should be, outside local development).
    cookie_secure: bool = False
    session_days: int = 30

    # Default sync server for new AnkiWeb logins. Empty means AnkiWeb itself; set a URL
    # such as https://sync.example.com/ to use a self-hosted Anki sync server instead.
    sync_endpoint: str | None = None

    # Background sync: push local changes once idle this long, and check the server for
    # changes made on other devices this often. (Anki caches the server's answer to that
    # check for a few minutes, so polling more often than every ~5 minutes doesn't help.
    # Opening the app always syncs if the last sync is over a minute old.)
    autosync: bool = True
    autosync_idle_seconds: int = 60
    autosync_poll_seconds: int = 600

    max_upload_mb: int = 50

    # Built frontend to serve at /. Defaults to ../frontend/dist relative to backend/.
    frontend_dist: Path | None = None

    @field_validator("password_hash", "password", "secret_key", "sync_endpoint", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        # A value pasted with a trailing newline (or a quote on the next line) would
        # otherwise never match.
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @property
    def collection_path(self) -> Path:
        return self.data_dir.resolve() / "collection.anki2"

    def resolved_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        key_file = self.data_dir / "secret_key"
        if key_file.exists():
            return key_file.read_text().strip()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        key_file.write_text(key)
        os.chmod(key_file, 0o600)
        return key

    def resolved_frontend_dist(self) -> Path:
        if self.frontend_dist:
            return self.frontend_dist
        return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
