"""成长周报存储层（JSON 落盘，零外部服务）。

周报是 LangGraph 工作流产物，状态机：
    draft(待审核) -> approved(已通过)

字段与前端审核台对齐：
    id, person, person_id, week, title, summary, tags, photos, status, updated_at
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()


class ReportStore:
    def __init__(self, data_dir: str | Path = "./data"):
        self.root = Path(data_dir)
        self.dir = self.root / "reports"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.face_dir = self.root / "faces"
        self.path = self.dir / "reports.json"
        self._index = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        with _LOCK:
            self.path.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ---- 增删改查 ----
    def save(self, report: dict) -> dict:
        """新建或覆盖一条周报（以 id 为键）。"""
        rid = report["id"]
        report.setdefault("status", "draft")
        report.setdefault("photos", [])
        report.setdefault("tags", [])
        report["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._index[rid] = report
        self._save()
        return report

    def get(self, report_id: str) -> dict | None:
        return self._index.get(report_id)

    def list(self, person: str | None = None) -> list[dict]:
        items = list(self._index.values())
        if person:
            items = [r for r in items if r.get("person") == person]
        return sorted(items, key=lambda r: r.get("updated_at", ""), reverse=True)

    def approve(self, report_id: str) -> dict | None:
        r = self._index.get(report_id)
        if not r:
            return None
        r["status"] = "approved"
        r["approved_at"] = datetime.now().isoformat(timespec="seconds")
        self._save()
        return r

    def exists(self, report_id: str) -> bool:
        return report_id in self._index

    # ---- 展示用种子数据（后端审核台首次打开时可见）----
    @staticmethod
    def _avatar_path() -> str:
        # 从 data/faces 找第一张基准照，供前端缩略图用
        for p in Path("./data/faces").glob("*"):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                return "../data/faces/" + p.name
        return ""

    def seed_demo(self, person: str = "小宝") -> int:
        """写入两条演示周报（待审核 + 已通过），仅当库为空时。"""
        if self._index:
            return 0
        avatar = self._avatar_path()
        self.save({
            "id": "r-2026-w46", "person": person, "week": "2026 · 第 46 周",
            "title": "游乐园的开心一天", "status": "draft",
            "summary": "这一周，小宝去了游乐园。戴上新发夹的样子格外精神，笑声几乎没停过。孩子长大的痕迹，藏在每一个不经意的瞬间里。",
            "tags": ["大笑", "户外", "活力满满"],
            "photos": [avatar] * 3,
        })
        self.save({
            "id": "r-2026-w45", "person": person, "week": "2026 · 第 45 周",
            "title": "别着发夹的小可爱", "status": "approved",
            "summary": "换发型的一周。从最初的不太适应，到后来对着镜头做鬼脸，小宝又解锁了新的一面。",
            "tags": ["特写", "新造型"],
            "photos": [avatar] * 2,
        })
        self.approve("r-2026-w45")
        return 2
