"""相册 API：导入 / 相册浏览 / 待确认纠错 / 建档 / 权限过滤。

单机、量少，写操作后立即落盘 JSON，不需要事务数据库。
权限：教师可读写全部；家长只能读自己绑定的孩子，所有写接口拒绝。
"""
from __future__ import annotations

import io
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.auth_routes import require_teacher, current_user
from src.core.face_detector import FaceDetector
from src.core.face_registry import FaceRegistry
from src.core.gallery import GalleryStore
from src.core.photo_sorter import PhotoSorter
from src.core.users import UserStore

router = APIRouter(prefix="/api")
DATA_DIR = "./data"
FACE_DIR = "./data/faces"
_users = UserStore()


def _store() -> GalleryStore:
    return GalleryStore(DATA_DIR)


def _registry() -> FaceRegistry:
    return FaceRegistry(FACE_DIR)


# ---------- 建档（教师） ----------
@router.post("/enroll")
async def enroll_person(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    nickname: str = Form(""),
    user: dict = Depends(require_teacher),
):
    """网页建档：上传 1~5 张基准照，提人脸特征建档案。"""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写孩子名字")
    reg = _registry()
    detector = FaceDetector()
    base_dir = Path(FACE_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)

    embeddings = []
    saved_paths = []
    for upload in files:
        ext = Path(upload.filename or "").suffix.lower() or ".jpg"
        dest = base_dir / f"{uuid.uuid4().hex[:10]}{ext}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_paths.append(str(dest))
        try:
            embs = detector.embedding_from_image(str(dest))
        except Exception:
            embs = []
        if not embs:
            dest.unlink(missing_ok=True)
            continue
        embeddings.append(embs[0])

    if not embeddings:
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="这些照片里没检测到清晰人脸，请换正面照重试")

    existing = reg.find_by_name(name)
    if existing:
        person = existing
        action = "追加模板"
    else:
        person = reg.create_person(name=name, nickname=nickname, base_images=saved_paths)
        action = "新建档案"
    total = reg.add_templates(person.id, embeddings)
    return {"id": person.id, "name": person.name, "action": action, "templates": total}


# ---------- 导入（教师） ----------
@router.post("/import")
async def import_materials(
    files: list[UploadFile] = File(...),
    date: Optional[str] = Form(None),
    auto_sort: bool = Form(True),
    user: dict = Depends(require_teacher),
):
    """批量上传素材：落 inbox → 人脸分拣 → 按孩子+日期归档。"""
    store = _store()
    inbox = Path(DATA_DIR) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    sorter = None
    if auto_sort:
        try:
            sorter = PhotoSorter(registry=_registry())
        except Exception:
            sorter = None

    results = []
    for upload in files:
        name = Path(upload.filename or "unnamed").name
        saved = inbox / name
        if saved.exists():
            stem, ext = saved.stem, saved.suffix
            i = 1
            while (inbox / f"{stem}_{i}{ext}").exists():
                i += 1
            saved = inbox / f"{stem}_{i}{ext}"
        with open(saved, "wb") as f:
            shutil.copyfileobj(upload.file, f)

        persons: list[str] = []
        similarity = 0.0
        status = "pending"
        detail = {}
        if sorter:
            try:
                detail = sorter.sort(saved)
                persons = detail["persons"]
                similarity = max(detail["similarities"].values(), default=0.0)
                status = "confirmed" if persons else "pending"
            except Exception as e:
                detail = {"error": str(e)}

        item = store.archive(
            saved,
            person_names=persons,
            date_override=date or "",
            similarity=similarity,
            status=status,
        )
        results.append({
            "item_id": item["id"],
            "filename": item["filename"],
            "kind": item["kind"],
            "date": item["date"],
            "date_source": item["date_source"],
            "persons": item["persons"],
            "status": item["status"],
            "similarity": similarity,
            "needs_review": item["status"] == "pending",
            "error": detail.get("error", ""),
        })
    return {"imported": len(results), "results": results}


# ---------- 相册浏览（登录可见，家长按绑定过滤） ----------
@router.get("/gallery")
def gallery_overview(request: Request):
    store = _store()
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    allowed = UserStore.visible_children(user)
    dates_by_person: dict[str, dict[str, int]] = {}
    for it in store.items():
        if it["status"] != "confirmed":
            continue
        for p in it["persons"]:
            if allowed is not None and p not in allowed:
                continue
            dates_by_person.setdefault(p, {})
            dates_by_person[p][it["date"]] = dates_by_person[p].get(it["date"], 0) + 1
    people = [
        {"name": name, "total": sum(dates.values()), "dates": dates}
        for name, dates in sorted(dates_by_person.items(), key=lambda x: -sum(x[1].values()))
    ]
    pending = len(store.list(status="pending")) if allowed is None else 0
    return {"people": people, "pending_count": pending, "total": len(store.items())}


@router.get("/gallery/person/{person}")
def gallery_person(person: str, request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    if not UserStore.can_view(user, person):
        raise HTTPException(status_code=403, detail="无权查看该孩子的相册")
    store = _store()
    items = store.list(person=person, status="confirmed")
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["date"], []).append({
            "id": it["id"],
            "kind": it["kind"],
            "filename": it["filename"],
            "url": store.media_url(it, person),
            "similarity": it["similarity"],
            "date_source": it["date_source"],
        })
    return {
        "person": person,
        "dates": [
            {"date": d, "count": len(g), "items": g}
            for d, g in sorted(groups.items(), reverse=True)
        ],
    }


# ---------- 待确认池（教师） ----------
@router.get("/pending")
def list_pending(user: dict = Depends(require_teacher)):
    store = _store()
    out = []
    for it in store.list(status="pending"):
        out.append({
            "id": it["id"],
            "filename": it["filename"],
            "kind": it["kind"],
            "date": it["date"],
            "url": f"/data/archive/{it['md5']}{Path(it['filename']).suffix.lower()}",
        })
    return out


class AssignBody(BaseModel):
    person: str
    learn: bool = True


@router.post("/pending/{item_id}/assign")
def assign_pending(item_id: str, body: AssignBody, user: dict = Depends(require_teacher)):
    """纠错：把待确认素材归给某孩子；可顺带把脸写进其模板库。"""
    store = _store()
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="素材不存在")

    reg = _registry()
    person = reg.find_by_name(body.person)
    if not person:
        person = reg.create_person(name=body.person)

    learned = False
    if body.learn:
        try:
            import cv2
            detector = FaceDetector()
            img = cv2.imread(str(Path(item["src"])))
            if img is not None:
                faces = detector.detect(img)
                if faces:
                    biggest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                    reg.add_template(person.id, detector.normalize(biggest.embedding))
                    learned = True
        except Exception:
            pass

    updated = store.assign(item_id, person.name)
    return {"item": updated, "person": person.name, "learned": learned}


class DateBody(BaseModel):
    date: str


@router.post("/gallery/{item_id}/date")
def change_date(item_id: str, body: DateBody, user: dict = Depends(require_teacher)):
    store = _store()
    item = store.set_date(item_id, body.date)
    if not item:
        raise HTTPException(status_code=404, detail="素材不存在")
    return item


class UnassignBody(BaseModel):
    person: str


@router.post("/gallery/{item_id}/unassign")
def unassign(item_id: str, body: UnassignBody, user: dict = Depends(require_teacher)):
    store = _store()
    item = store.unassign(item_id, body.person)
    if not item:
        raise HTTPException(status_code=404, detail="素材不存在")
    return item


class PersonCreate(BaseModel):
    name: str
    nickname: Optional[str] = None


@router.post("/persons")
def create_person(body: PersonCreate, user: dict = Depends(require_teacher)):
    reg = _registry()
    existing = reg.find_by_name(body.name)
    if existing:
        return {"id": existing.id, "name": existing.name, "exists": True}
    p = reg.create_person(name=body.name, nickname=body.nickname or "")
    return {"id": p.id, "name": p.name, "exists": False}


# ---------- 我的孩子（前端按角色渲染用） ----------
@router.get("/my-children")
def my_children(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    allowed = UserStore.visible_children(user)
    if allowed is None:
        return {"all": True, "children": [p["name"] for p in _store().persons()]}
    return {"all": False, "children": allowed}


# ---------- 一键备份导出（教师） ----------
# 打包 data 下的核心数据（相册树+原文件+人脸库+账号+周报），排除 inbox 临时副本。
# 这是单机场景唯一的灾备手段：解压回项目根目录即可完整恢复。
BACKUP_DIRS = ("gallery", "archive", "faces", "reports", "output")
BACKUP_FILES = ("users.json",)
RESTORE_NOTE = (
    "KidLens 备份包\n"
    "================\n\n"
    "恢复方法：\n"
    "1. 先停止 KidLens（关掉启动脚本的终端窗口）。\n"
    "2. 把本压缩包里的所有内容，解压覆盖到项目的 data/ 目录。\n"
    "3. 重新启动 KidLens，相册、人脸库、账号就都回来了。\n\n"
    "说明：\n"
    "- gallery/ 是按孩子+日期整理好的相册（照片/视频本体）。\n"
    "- archive/ 是原文件去重库，纠错/改日期会用到，请勿删除。\n"
    "- faces/ 是人脸库，删了就得重新给孩子建档。\n"
    "- users.json 是教师/家长账号。\n"
    "- inbox/ 是临时上传副本，无需备份，已自动排除。\n"
)


@router.get("/backup/export")
def export_backup(user: dict = Depends(require_teacher)):
    """一键备份：把 data 核心数据打成 zip 下载。教师专属。"""
    root = Path(DATA_DIR).resolve()
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for sub in BACKUP_DIRS:
            folder = root / sub
            if not folder.exists():
                continue
            for f in sorted(folder.rglob("*")):
                if f.is_file() and f.name != ".gitkeep":
                    zf.write(f, f.relative_to(root).as_posix())
                    count += 1
        for name in BACKUP_FILES:
            f = root / name
            if f.exists():
                zf.write(f, name)
                count += 1
        zf.writestr("恢复说明.txt", RESTORE_NOTE.encode("utf-8"))
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "kidlens_backup_%s.zip" % stamp
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="%s"' % filename},
    )
