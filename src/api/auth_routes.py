"""登录 / 会话 / 家长账号管理，以及供其它路由复用的鉴权依赖。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from src.core.users import UserStore

router = APIRouter(prefix="/api/auth")
COOKIE = "kidlens_session"
_store = UserStore()


# ---------- 鉴权依赖（其它路由 import 这两个） ----------
def current_user(request: Request) -> Optional[dict]:
    return _store.user_by_token(request.cookies.get(COOKIE))


def require_login(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_teacher(request: Request) -> dict:
    user = require_login(request)
    if user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="仅教师可执行此操作")
    return user


# ---------- 登录 / 登出 ----------
class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, response: Response):
    user = _store.authenticate(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = _store.login(user["username"])
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/")
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    _store.logout(request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {"user": current_user(request)}


# ---------- 家长账号管理（教师用） ----------
class ParentBody(BaseModel):
    username: str
    password: str
    name: str = ""
    children: list[str] = []


class ChildrenBody(BaseModel):
    children: list[str]


@router.get("/parents")
def list_parents(user: dict = Depends(require_teacher)):
    return _store.list_parents()


@router.post("/parents")
def add_parent(body: ParentBody, user: dict = Depends(require_teacher)):
    try:
        return _store.add_parent(body.username, body.password, body.name, body.children)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/parents/{username}/children")
def set_children(username: str, body: ChildrenBody, user: dict = Depends(require_teacher)):
    updated = _store.set_children(username, body.children)
    if not updated:
        raise HTTPException(status_code=404, detail="家长账号不存在")
    return updated


@router.delete("/parents/{username}")
def delete_parent(username: str, user: dict = Depends(require_teacher)):
    if not _store.delete_parent(username):
        raise HTTPException(status_code=404, detail="家长账号不存在")
    return {"ok": True}


@router.get("/children")
def all_children(user: dict = Depends(require_teacher)):
    """所有已建档的孩子名字，供家长绑定时勾选。"""
    from src.core.face_registry import FaceRegistry
    from src.core.gallery import GalleryStore

    names = {p.name for p in FaceRegistry("./data/faces").list_persons()}
    names.update(p["name"] for p in GalleryStore("./data").persons())
    return sorted(names)
