from __future__ import annotations

from fastapi import Request

from .collection import CollectionManager
from .sync import SyncManager


def get_cm(request: Request) -> CollectionManager:
    return request.app.state.cm


def get_sync(request: Request) -> SyncManager:
    return request.app.state.sync


def media_base(request: Request) -> str:
    """Path the card iframe uses as <base href> for media files."""
    return f"/media/{request.app.state.auth.media_token}/"
