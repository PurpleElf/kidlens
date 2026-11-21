"""人物档案与动态人脸特征库。

存储方案（纯本地，零服务）：
    data/faces/registry.json   人物元数据（姓名/昵称/基准照路径）
    data/faces/<id>/templates.npy   多模板向量矩阵 (N, 512)

多模板是核心体验：基准照是初始模板，主动学习确认的抓拍会继续追加，
持续提升复杂光线/角度下的召回率。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np

from src.models.schemas import Person

EMBED_DIM = 512


class FaceRegistry:
    def __init__(self, faces_dir: str | Path = "./data/faces"):
        self.root = Path(faces_dir).resolve()
        self.index_path = self.root / "registry.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._index: dict = self._load_index()

    # ---------- 索引读写 ----------
    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"persons": {}}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"persons": {}}

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _person_dir(self, person_id: str) -> Path:
        d = self.root / person_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _template_path(self, person_id: str) -> Path:
        return self._person_dir(person_id) / "templates.npy"

    # ---------- 档案 CRUD ----------
    def create_person(
        self,
        name: str,
        nickname: str = "",
        birthdate: str = "",
        note: str = "",
        base_images: list[str] | None = None,
    ) -> Person:
        """创建人物档案，返回带 id 的 Person。"""
        person_id = uuid.uuid4().hex[:8]
        person = Person(
            id=person_id,
            name=name,
            nickname=nickname,
            birthdate=birthdate,
            note=note,
            base_images=list(base_images or []),
        )
        self._index["persons"][person_id] = {
            "id": person_id,
            "name": name,
            "nickname": nickname,
            "birthdate": birthdate,
            "note": note,
            "base_images": person.base_images,
        }
        self._save_index()
        np.save(self._template_path(person_id), np.empty((0, EMBED_DIM), dtype=np.float32))
        return person

    def get_person(self, person_id: str) -> Person | None:
        raw = self._index["persons"].get(person_id)
        if not raw:
            return None
        templates = self.load_templates(person_id)
        return Person(
            id=raw["id"],
            name=raw["name"],
            nickname=raw.get("nickname", ""),
            birthdate=raw.get("birthdate", ""),
            note=raw.get("note", ""),
            base_images=raw.get("base_images", []),
            templates=templates.tolist(),
        )

    def find_by_name(self, name: str) -> Person | None:
        for pid, raw in self._index["persons"].items():
            if raw["name"] == name or raw.get("nickname") == name:
                return self.get_person(pid)
        return None

    def list_persons(self) -> list[Person]:
        return [self.get_person(pid) for pid in self._index["persons"]]

    def delete_person(self, person_id: str) -> bool:
        if person_id not in self._index["persons"]:
            return False
        del self._index["persons"][person_id]
        self._save_index()
        import shutil
        shutil.rmtree(self._person_dir(person_id), ignore_errors=True)
        return True

    # ---------- 特征模板 ----------
    def load_templates(self, person_id: str) -> np.ndarray:
        """加载某人的全部模板，shape (N, 512)；无模板返回 (0, 512)。"""
        path = self._template_path(person_id)
        if not path.exists():
            return np.empty((0, EMBED_DIM), dtype=np.float32)
        arr = np.load(path)
        return arr if arr.ndim == 2 else arr.reshape(-1, EMBED_DIM)

    def add_templates(self, person_id: str, embeddings: list[np.ndarray]) -> int:
        """追加模板向量，返回当前模板总数。"""
        if not embeddings:
            return self.load_templates(person_id).shape[0]
        cur = self.load_templates(person_id)
        new = np.vstack([np.asarray(e, dtype=np.float32).reshape(1, -1) for e in embeddings])
        merged = np.vstack([cur, new]) if cur.size else new
        np.save(self._template_path(person_id), merged.astype(np.float32))
        return merged.shape[0]

    def add_template(self, person_id: str, embedding: np.ndarray) -> int:
        """追加单个模板（主动学习确认后调用）。"""
        return self.add_templates(person_id, [embedding])

    def template_map(self) -> dict[str, np.ndarray]:
        """返回 {person_id: (N,512)模板矩阵}，供批量比对使用。"""
        return {
            pid: self.load_templates(pid)
            for pid in self._index["persons"]
            if self.load_templates(pid).size
        }
