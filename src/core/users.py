"""本地用户与会话（单机软隔离，不上线）。

设计取舍：
    - 用户存 data/users.json：教师 1 个 + 家长 N 个，家长绑定孩子名单。
    - 密码只做 sha256（本地演示强度足够，别拿真实密码）。
    - 会话是内存 token + HttpOnly cookie，服务重启后需重新登录（单机可接受）。
    - 教师可见全部数据；家长只能看自己绑定的孩子，写操作一律禁止。
"""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Optional

DEFAULT_USERS = {
    "users": {
        "teacher": {
            "role": "teacher",
            "name": "教师",
            "password_sha256": hashlib.sha256(b"admin123").hexdigest(),
            "children": [],
        },
        "parent": {
            "role": "parent",
            "name": "家长（示例）",
            "password_sha256": hashlib.sha256(b"123456").hexdigest(),
            "children": ["小宝"],
        },
    }
}


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class UserStore:
    def __init__(self, path: str | Path = "./data/users.json"):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()
        self._sessions: dict[str, str] = {}  # token -> username

    # ---------- 存储 ----------
    def _load(self) -> dict:
        if not self.path.exists():
            data = json.loads(json.dumps(DEFAULT_USERS))
            self._save(data)
            return data
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data.get("users"), dict) else json.loads(json.dumps(DEFAULT_USERS))
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(DEFAULT_USERS))

    def _save(self, data: Optional[dict] = None) -> None:
        self.path.write_text(
            json.dumps(data if data is not None else self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- 查询 ----------
    def get(self, username: str) -> Optional[dict]:
        raw = self._data["users"].get(username)
        if not raw:
            return None
        return {"username": username, **{k: v for k, v in raw.items() if k != "password_sha256"}}

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        raw = self._data["users"].get(username)
        if not raw or raw.get("password_sha256") != _hash(password):
            return None
        return self.get(username)

    def list_parents(self) -> list[dict]:
        out = [self.get(u) for u, raw in self._data["users"].items() if raw.get("role") == "parent"]
        return [u for u in out if u]

    # ---------- 会话 ----------
    def login(self, username: str) -> str:
        token = secrets.token_hex(16)
        self._sessions[token] = username
        return token

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def user_by_token(self, token: Optional[str]) -> Optional[dict]:
        if not token:
            return None
        return self.get(self._sessions.get(token, ""))

    # ---------- 家长管理（教师用） ----------
    def add_parent(self, username: str, password: str, name: str = "", children: Optional[list[str]] = None) -> dict:
        username = username.strip()
        if not username or not password:
            raise ValueError("账号和密码不能为空")
        if username in self._data["users"]:
            raise ValueError("账号已存在")
        self._data["users"][username] = {
            "role": "parent",
            "name": name or username,
            "password_sha256": _hash(password),
            "children": list(children or []),
        }
        self._save()
        return self.get(username)

    def delete_parent(self, username: str) -> bool:
        raw = self._data["users"].get(username)
        if not raw or raw.get("role") != "parent":
            return False
        del self._data["users"][username]
        for token, u in list(self._sessions.items()):
            if u == username:
                self._sessions.pop(token, None)
        self._save()
        return True

    def set_children(self, username: str, children: list[str]) -> Optional[dict]:
        raw = self._data["users"].get(username)
        if not raw or raw.get("role") != "parent":
            return None
        raw["children"] = list(children)
        self._save()
        return self.get(username)

    # ---------- 可见范围 ----------
    @staticmethod
    def visible_children(user: dict) -> Optional[list[str]]:
        """教师返回 None（不限制）；家长返回允许的孩子名单。"""
        return None if user.get("role") == "teacher" else list(user.get("children") or [])

    @staticmethod
    def can_view(user: dict, person: str) -> bool:
        allowed = UserStore.visible_children(user)
        return allowed is None or person in allowed
