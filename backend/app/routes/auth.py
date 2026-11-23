from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from ..auth import get_auth, require_csrf

router = APIRouter(prefix="/api/auth", dependencies=[Depends(require_csrf)])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    client = request.client.host if request.client else "unknown"
    get_auth(request).login(body.password, client, response)
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    get_auth(request).logout(response)
    return {"authenticated": False}


@router.get("/me")
def me(request: Request) -> dict:
    return {"authenticated": get_auth(request).is_authenticated(request)}
