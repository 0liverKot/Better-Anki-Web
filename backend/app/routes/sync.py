from __future__ import annotations

from typing import Literal

from anki.errors import SyncError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_user
from ..deps import get_sync
from ..sync import NotLoggedIn, SyncManager

router = APIRouter(prefix="/api/sync", dependencies=[Depends(require_user)])


class SyncLoginBody(BaseModel):
    username: str
    password: str
    # Blank means AnkiWeb (or BAW_SYNC_ENDPOINT if set).
    endpoint: str | None = None


class FullSyncBody(BaseModel):
    direction: Literal["upload", "download"]


@router.get("/status")
def status(sync: SyncManager = Depends(get_sync)) -> dict:
    return sync.status()


@router.post("/login")
def login(body: SyncLoginBody, sync: SyncManager = Depends(get_sync)) -> dict:
    try:
        sync.login(body.username.strip(), body.password, body.endpoint)
    except SyncError as err:
        raise HTTPException(400, str(err)) from err
    sync.start_sync("logged in")
    return sync.status()


@router.post("/logout")
def logout(sync: SyncManager = Depends(get_sync)) -> dict:
    sync.logout()
    return sync.status()


@router.post("")
def sync_now(
    wait: bool = False,
    max_age: float | None = None,
    sync: SyncManager = Depends(get_sync),
) -> dict:
    """Start a sync. Returns at once unless wait=true; poll /status for progress.
    With max_age, skips the sync if one finished within that many seconds."""
    try:
        if wait:
            return sync.sync("manual")
        if max_age is not None:
            sync.sync_if_stale(max_age)
        else:
            sync.start_sync("manual")
    except NotLoggedIn as err:
        raise HTTPException(400, str(err)) from err
    return sync.status()


@router.post("/soon")
def sync_soon(sync: SyncManager = Depends(get_sync)) -> dict:
    """Called when the tab is hidden or closed, so reviews reach AnkiWeb promptly."""
    if sync.logged_in:
        sync.request_sync(delay=3)
    return {"ok": True}


@router.post("/full")
def full_sync(body: FullSyncBody, sync: SyncManager = Depends(get_sync)) -> dict:
    try:
        return sync.full_sync(body.direction)
    except NotLoggedIn as err:
        raise HTTPException(400, str(err)) from err
