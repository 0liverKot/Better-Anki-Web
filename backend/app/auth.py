"""Single-user login: one password, a signed session cookie, and a CSRF header check."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import Settings

log = logging.getLogger(__name__)

COOKIE_NAME = "baw_session"
# Every state-changing request must carry this header. Browsers won't let another site
# set custom headers on a cross-origin request without a CORS preflight we never allow.
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "baw"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

BCRYPT_RE = re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}")

MAX_FAILURES = 10
FAILURE_WINDOW_SECONDS = 15 * 60


class Auth:
    def __init__(self, settings: Settings) -> None:
        if not settings.password_hash and not settings.password:
            raise RuntimeError(
                "Set BAW_PASSWORD_HASH (recommended; generate with "
                "`python -m app.hash_password`) or BAW_PASSWORD."
            )
        if settings.password_hash and not BCRYPT_RE.fullmatch(settings.password_hash):
            raise RuntimeError(
                "BAW_PASSWORD_HASH isn't a bcrypt hash (expected 60 characters starting "
                "with $2b$). Generate one with `python -m app.hash_password`, or use "
                "BAW_PASSWORD for a plain password."
            )
        if settings.password_hash and settings.password:
            log.warning("Both BAW_PASSWORD_HASH and BAW_PASSWORD are set; using BAW_PASSWORD_HASH.")
        self.settings = settings
        self.secret = settings.resolved_secret_key()
        self._serializer = URLSafeTimedSerializer(self.secret, salt="baw-session")
        # Changing the password invalidates existing sessions.
        credential = settings.password_hash or settings.password or ""
        self._fingerprint = hashlib.sha256(credential.encode()).hexdigest()[:16]
        self.media_token = hmac.new(self.secret.encode(), b"baw-media-v1", "sha256").hexdigest()[:32]
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._failures_lock = threading.Lock()

    # Password
    ##########################################################################

    def check_password(self, password: str) -> bool:
        if self.settings.password_hash:
            try:
                return bcrypt.checkpw(password.encode(), self.settings.password_hash.encode())
            except ValueError:
                return False
        return hmac.compare_digest(password.encode(), (self.settings.password or "").encode())

    def _recent_failures(self, client: str) -> deque[float]:
        attempts = self._failures[client]
        cutoff = time.time() - FAILURE_WINDOW_SECONDS
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts

    def login(self, password: str, client: str, response: Response) -> None:
        with self._failures_lock:
            if len(self._recent_failures(client)) >= MAX_FAILURES:
                raise HTTPException(429, "Too many failed attempts. Try again later.")
        if not self.check_password(password):
            with self._failures_lock:
                self._recent_failures(client).append(time.time())
            raise HTTPException(401, "Wrong password.")
        with self._failures_lock:
            self._failures.pop(client, None)
        response.set_cookie(
            COOKIE_NAME,
            self._serializer.dumps({"f": self._fingerprint}),
            max_age=self.settings.session_days * 86400,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            path="/",
        )

    def logout(self, response: Response) -> None:
        response.delete_cookie(COOKIE_NAME, path="/")

    # Sessions
    ##########################################################################

    def is_authenticated(self, request: Request) -> bool:
        cookie = request.cookies.get(COOKIE_NAME)
        if not cookie:
            return False
        try:
            data = self._serializer.loads(cookie, max_age=self.settings.session_days * 86400)
        except BadSignature:
            return False
        return isinstance(data, dict) and data.get("f") == self._fingerprint

    def check_media_token(self, token: str) -> bool:
        return hmac.compare_digest(token, self.media_token)


def get_auth(request: Request) -> Auth:
    return request.app.state.auth


def require_csrf(request: Request) -> None:
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing CSRF header.")


def require_user(request: Request) -> None:
    require_csrf(request)
    if not get_auth(request).is_authenticated(request):
        raise HTTPException(401, "Not logged in.")
