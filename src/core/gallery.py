"""按孩子 + 日期归档的照片/视频相册。

设计（单机、量少、不上线）：
    data/gallery/index.json              唯一数据源：素材 ↔ 孩子 ↔ 日期
    data/gallery/{孩子}/{YYYY-MM-DD}/    网页按孩子/日期翻看的实体目录

两条已确认的决策：
    ①a 多人合影：每个孩子的日期目录各放一份，用硬链接指向同一原文件，不重复占空间。
    ②a 日期：优先 EXIF 拍摄时间 → 回退文件修改时间 → 允许导入页手动覆盖。

原文件本体存 data/archive/（MD5 去重），gallery 里只放硬链接，改归属/改日期只动链接。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.core.storage import LocalStorage

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


def safe_name(name: str) -> str:
    """把孩子名/文件名清成安全路径片段。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip()
    return name or "unnamed"


class GalleryStore:
    def __init__(self, data_dir: str | Path = "./data"):
        self.root = Path(data_dir).resolve()
        self.gallery_dir = self.root / "gallery"
        self.index_path = self.gallery_dir / "index.json"
        self.gallery_dir.mkdir(parents=True, exist_ok=True)
        self.storage = LocalStorage(self.root)
        self._index: dict = self._load_index()

    # ---------- 索引 ----------
    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"items": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data.get("items"), dict) else {"items": {}}
        except (json.JSONDecodeError, OSError):
            return {"items": {}}

    def save(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def items(self) -> list[dict]:
        return list(self._index["items"].values())

    def get(self, item_id: str) -> dict | None:
        return self._index["items"].get(item_id)

    # ---------- 日期 ----------
    @staticmethod
    def extract_date(path: str | Path, override: str = "") -> tuple[str, str]:
        """返回 (YYYY-MM-DD, 来源)。override 优先；其次 EXIF；最后 mtime。"""
        if override:
            try:
                d = datetime.strptime(override[:10], "%Y-%m-%d").date()
                return d.isoformat(), "manual"
            except ValueError:
                pass
        path = Path(path)
        # EXIF：PIL 已装则读 DateTimeOriginal
        try:
            from PIL import Image
            with Image.open(path) as img:
                exif = img.getexif()
                # 36867 = DateTimeOriginal, 306 = DateTime
                tag = exif.get(36867) or exif.get(306)
                if tag:
                    m = re.match(r"(\d{4}):(\d{2}):(\d{2})", str(tag))
                    if m:
                        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "exif"
        except Exception:
            pass
        # 回退文件修改时间
        try:
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime).date().isoformat(), "mtime"
        except OSError:
            return datetime.now().date().isoformat(), "mtime"

    # ---------- 链接 ----------
    def _link_file(self, src: str | Path, dst: Path) -> None:
        """优先硬链接（同盘不占额外空间），跨设备或不支持时回退复制。"""
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            return
        try:
            os.link(src, dst)
        except (OSError, NotImplementedError):
            shutil.copy2(src, dst)

    def _unlink_file(self, person: str, date: str, filename: str) -> None:
        p = self.gallery_dir / safe_name(person) / date / filename
        try:
            p.unlink()
        except OSError:
            pass
        # 空日期目录、空人物目录顺手清掉（只清到 gallery 根为止）
        for d in (p.parent, p.parent.parent):
            try:
                if d != self.gallery_dir and d.exists() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass

    # ---------- 归档 ----------
    def archive(
        self,
        src: str | Path,
        person_names: list[str],
        date_override: str = "",
        kind: str = "",
        similarity: float = 0.0,
        status: str = "confirmed",
    ) -> dict:
        """归档一个素材：原文件 MD5 去重入库，再为每个孩子建硬链接。

        person_names 为空时只入库不建链接（用于待确认池素材先留档）。
        """
        src = Path(src)
        digest = self.storage.md5(src)
        ext = src.suffix.lower()
        if not kind:
            kind = "video" if ext in VIDEO_EXTS else "photo"
        date, date_source = self.extract_date(src, date_override)

        # 原文件去重归档
        canonical, _ = self.storage.archive(src)
        canonical_path = Path(canonical)

        # 复用已有条目（同一素材再次导入）
        existing = next((it for it in self.items() if it["md5"] == digest and it["date"] == date), None)
        if existing:
            item = existing
        else:
            item_id = uuid.uuid4().hex[:10]
            item = {
                "id": item_id,
                "src": canonical,
                "md5": digest,
                "filename": src.name,
                "kind": kind,
                "date": date,
                "date_source": date_source,
                "persons": [],
                "status": status,
                "similarity": round(float(similarity), 4),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._index["items"][item_id] = item

        # 为每个孩子建链接（①a 多人合影各一份）
        for name in person_names:
            safe = safe_name(name)
            link_name = f"{digest[:8]}_{safe_name(src.name)}"
            self._link_file(canonical_path, self.gallery_dir / safe / date / link_name)
            if safe not in item["persons"]:
                item["persons"].append(safe)

        item["status"] = status
        self.save()
        return dict(item)

    # ---------- 查询 ----------
    def list(self, person: str = "", date: str = "", status: str = "") -> list[dict]:
        out = []
        for it in self.items():
            if person and safe_name(person) not in it["persons"]:
                continue
            if date and it["date"] != date:
                continue
            if status and it["status"] != status:
                continue
            out.append(it)
        out.sort(key=lambda x: (x["date"], x["created_at"]), reverse=True)
        return out

    def dates_for(self, person: str) -> list[str]:
        """某人有素材的所有日期，倒序。"""
        return sorted({it["date"] for it in self.list(person=person)}, reverse=True)

    def persons(self) -> list[dict]:
        """相册里出现过的人物 + 素材数，按素材数倒序。"""
        counts: dict[str, int] = {}
        for it in self.items():
            if it["status"] != "confirmed":
                continue
            for p in it["persons"]:
                counts[p] = counts.get(p, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    # ---------- 修改 ----------
    def set_date(self, item_id: str, new_date: str) -> dict | None:
        """②a 手动改日期：重建所有链接到新日期目录。"""
        item = self.get(item_id)
        if not item:
            return None
        old_date = item["date"]
        canonical = Path(item["src"])
        for person in item["persons"]:
            link_name = f"{item['md5'][:8]}_{safe_name(item['filename'])}"
            self._unlink_file(person, old_date, link_name)
            self._link_file(canonical, self.gallery_dir / person / new_date / link_name)
        item["date"] = new_date
        item["date_source"] = "manual"
        self.save()
        return item

    def assign(self, item_id: str, person_name: str) -> dict | None:
        """纠错：把某素材归给一个孩子（建链接 + 更新 persons + 转 confirmed）。"""
        item = self.get(item_id)
        if not item:
            return None
        safe = safe_name(person_name)
        link_name = f"{item['md5'][:8]}_{safe_name(item['filename'])}"
        self._link_file(Path(item["src"]), self.gallery_dir / safe / item["date"] / link_name)
        if safe not in item["persons"]:
            item["persons"].append(safe)
        item["status"] = "confirmed"
        self.save()
        return item

    def unassign(self, item_id: str, person_name: str) -> dict | None:
        """纠错：把某素材从某孩子移走（删链接 + 更新 persons）。"""
        item = self.get(item_id)
        if not item:
            return None
        safe = safe_name(person_name)
        link_name = f"{item['md5'][:8]}_{safe_name(item['filename'])}"
        self._unlink_file(safe, item["date"], link_name)
        item["persons"] = [p for p in item["persons"] if p != safe]
        if not item["persons"]:
            item["status"] = "pending"
        self.save()
        return item

    def delete(self, item_id: str) -> bool:
        """删索引与所有链接，原文件保留在 archive（避免误删不可恢复）。"""
        item = self.get(item_id)
        if not item:
            return False
        for person in item["persons"]:
            link_name = f"{item['md5'][:8]}_{safe_name(item['filename'])}"
            self._unlink_file(person, item["date"], link_name)
        del self._index["items"][item_id]
        self.save()
        return True

    def thumb_url(self, item: dict) -> str:
        """给前端的相对路径（从 web/ 视角）。视频返回空，由前端用 <video>。"""
        if item["kind"] == "video":
            return ""
        if not item["persons"]:
            return ""
        return f"/data/gallery/{item['persons'][0]}/{item['date']}/{item['md5'][:8]}_{item['filename']}"

    def media_url(self, item: dict, person: str = "") -> str:
        """素材的真实访问路径（取第一个或指定孩子的链接）。"""
        p = safe_name(person) if person else (item["persons"][0] if item["persons"] else "")
        link_name = f"{item['md5'][:8]}_{safe_name(item['filename'])}"
        return f"/data/gallery/{p}/{item['date']}/{link_name}"
