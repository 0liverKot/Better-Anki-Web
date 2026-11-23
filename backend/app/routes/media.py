from __future__ import annotations

import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..auth import get_auth, require_user
from ..collection import CollectionManager
from ..deps import get_cm

router = APIRouter()

# Media is served to the card iframe, which is sandboxed (opaque origin) and so can't
# send the session cookie. URLs carry a secret token instead. The CSP sandbox stops a
# malicious HTML/SVG file from running scripts on this origin if opened directly.
MEDIA_HEADERS = {
    "Content-Security-Policy": "sandbox",
    "Cache-Control": "private, max-age=86400",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/media/{token}/{filename}")
def get_media(
    token: str, filename: str, request: Request, cm: CollectionManager = Depends(get_cm)
) -> FileResponse:
    if not get_auth(request).check_media_token(token):
        raise HTTPException(404)
    if (
        not filename
        or filename in (".", "..")
        or any(c in filename for c in ("/", "\\", "\x00"))
    ):
        raise HTTPException(404)
    media_dir = cm.media_dir.resolve()
    path = (media_dir / filename).resolve()
    if path.parent != media_dir or not path.is_file():
        raise HTTPException(404)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers=MEDIA_HEADERS)


@router.post("/api/media", dependencies=[Depends(require_user)])
def upload_media(
    file: UploadFile, request: Request, cm: CollectionManager = Depends(get_cm)
) -> dict:
    limit = request.app.state.settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "File is too large.")
    if not data:
        raise HTTPException(400, "File is empty.")
    name = os.path.basename(file.filename or "") or "pasted.png"
    with cm.use() as col:
        stored = col.media.write_data(name, data)
    cm.mark_modified()
    return {"filename": stored}
