"""HTTP 路由：人物 / 周报 / 审核 / 周报生成。

前端审核台与主页走这些接口；后端离线时前端自动降级到演示数据。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.face_registry import FaceRegistry
from src.db.report_store import ReportStore

router = APIRouter(prefix="/api")


@router.get("/persons")
def list_persons():
    """人物列表（供审核台左侧档案）。"""
    reg = FaceRegistry("./data/faces")
    out = []
    for p in reg.list_persons():
        try:
            templates = reg.load_templates(p.id)
            n = int(templates.shape[0]) if hasattr(templates, "shape") else 0
        except Exception:
            n = 0
        out.append({
            "id": p.id, "name": p.name, "nickname": p.nickname,
            "template_count": n, "clip_count": 0,
        })
    return out


@router.get("/reports/id/{report_id}")
def get_report(report_id: str):
    store = ReportStore()
    r = store.get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="周报不存在")
    return r


@router.get("/reports/{person}")
def get_reports(person: str):
    """某人物的周报列表（前端审核台按人物名取）。"""
    store = ReportStore()
    reports = store.list(person=person)
    # 库空时注入演示种子，让审核台首次打开就有内容
    if not reports:
        store.seed_demo(person=person)
        reports = store.list(person=person)
    return reports


class ApproveBody(BaseModel):
    summary: Optional[str] = None


@router.post("/reports/{report_id}/approve")
def approve_report(report_id: str, body: Optional[ApproveBody] = None):
    """审核通过；可带编辑后的文案。"""
    store = ReportStore()
    r = store.get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="周报不存在")
    if body and body.summary:
        r["summary"] = body.summary
        store.save(r)
    result = store.approve(report_id)
    # 同步到 LangGraph 状态（若线程存活），失败不影响审核主流程
    return result


class ReportRequest(BaseModel):
    person: str
    video: str
    person_id: str = ""
    similarity: float = 0.5


@router.post("/reports/generate")
def generate_report(req: ReportRequest):
    """启动周报生成工作流，跑到人工审核中断点，返回草稿。"""
    from src.workflow.weekly_report import start_report

    try:
        result = start_report(
            person=req.person, video=req.video,
            person_id=req.person_id, similarity=req.similarity,
            thread_id=f"api-{req.person}",
        )
        return {"status": "draft", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"周报生成失败：{e}")


@router.get("/health")
def api_health():
    return {"status": "ok"}
