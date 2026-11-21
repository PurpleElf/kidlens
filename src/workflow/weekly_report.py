"""LangGraph 成长周报工作流。

流程：collect -> label -> draft -> [interrupt 人工审核] -> publish

人工审核（HITL）用 LangGraph 新版 interrupt() + MemorySaver checkpoint：
    - invoke() 第一次在 review 节点中断，返回草稿（含 __interrupt__）
    - Command(resume={"decision": "approve"|"reject", "edited": "..."}) 恢复
    - approve -> publish 落盘为已通过；reject -> 回到 draft 重新生成

展示项目务实处理：草稿与审核结果同时写入 report_store（JSON），
这样审核台（另一个 HTTP 请求）也能读到，不依赖内存 thread 存活。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.core.vlm import label_frames, summarize_labels
from src.db.report_store import ReportStore


class GraphState(TypedDict, total=False):
    person: str
    person_id: str
    video: str
    week: str
    frame_paths: list[str]
    times: list[float]
    similarity: float
    labels: list[dict]
    summary: str
    title: str
    tags: list[str]
    photos: list[str]
    report_id: str
    decision: str
    edited: str
    status: str


def _week_tag() -> str:
    d = datetime.now()
    return f"{d.year} · 第 {d.isocalendar()[1]} 周"


def _collect_frames(state: GraphState) -> dict:
    """从视频按步长抽关键帧，存到 data/reports/frames/<人>/。

    真正的生产做法应复用 slicer 命中区间抽帧；展示项目按固定步长抽，
    保证没有 clip 也能演示工作流。
    """
    import cv2

    video = state.get("video", "")
    person = state.get("person", "unknown")
    out_dir = Path("data/reports/frames") / person
    out_dir.mkdir(parents=True, exist_ok=True)
    if not video or not Path(video).exists():
        return {"frame_paths": [], "times": []}

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    step = 2.0  # 抽帧步长，与 config 一致即可；周报帧上限由调用方截取
    paths, times = [], []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        p = out_dir / f"frame_{int(t):04d}.jpg"
        cv2.imwrite(str(p), frame)
        paths.append(str(p))
        times.append(t)
        t += step
    cap.release()
    # 控制送 VLM 的帧数（config: weekly_frame_limit=12）
    return {"frame_paths": paths[:12], "times": times[:12]}


def _label(state: GraphState) -> dict:
    """VLM 打标签（云/本地/模板三路），失败自动降级。"""
    labels = label_frames(
        state.get("frame_paths", []),
        state.get("times"),
        state.get("similarity", 0.5),
    )
    return {"labels": labels}


def _draft(state: GraphState) -> dict:
    """把标签聚合成周报文案。"""
    labels = state.get("labels", [])
    feat = summarize_labels(labels)
    scene = "、".join(feat["scenes"]) or "日常活动"
    action = "、".join(feat["actions"]) or "开心地玩耍"
    emotion = "、".join(feat["emotions"]) or "愉悦"
    tags = feat["tags"] or ["可爱瞬间"]
    person = state.get("person", "孩子")
    week = state.get("week") or _week_tag()

    summary = (
        f"这一周，{person}在{scene}里{action}，看起来格外{emotion}。"
        f"孩子长大的痕迹，藏在每一个不经意的瞬间里。"
    )
    title = f"{feat['actions'][0] if feat['actions'] else '成长'}的{week.split('·')[-1].strip()}"
    report_id = f"r-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 落盘为草稿，供审核台读取
    store = ReportStore()
    store.save({
        "id": report_id,
        "person": person,
        "person_id": state.get("person_id", ""),
        "week": week,
        "title": title,
        "summary": summary,
        "tags": tags,
        "photos": state.get("frame_paths", [])[:3],
        "status": "draft",
    })
    return {
        "summary": summary, "title": title, "tags": tags,
        "report_id": report_id, "week": week,
        "photos": state.get("frame_paths", [])[:3],
    }


def _review(state: GraphState) -> dict:
    """人工审核中断点：把草稿交给人类决定 approve / reject。"""
    payload = {
        "report_id": state.get("report_id"),
        "title": state.get("title"),
        "summary": state.get("summary"),
        "tags": state.get("tags"),
        "photos": state.get("photos"),
    }
    answer = interrupt({"type": "review_report", "draft": payload})
    decision = answer.get("decision", "approve") if isinstance(answer, dict) else str(answer)
    edited = answer.get("edited", "") if isinstance(answer, dict) else ""
    result = {"decision": decision}
    if edited:
        result["summary"] = edited  # 人类改过的文案进入最终稿
    return result


def _publish(state: GraphState) -> dict:
    """审核通过：把最终稿落盘为 approved。"""
    store = ReportStore()
    report_id = state.get("report_id", "")
    summary = state.get("summary", "")
    if report_id and store.get(report_id):
        r = store.get(report_id)
        r["summary"] = summary
        store.save(r)
        store.approve(report_id)
    return {"status": "approved"}


def _revise(state: GraphState) -> dict:
    """审核打回：标记状态，等待重新生成。"""
    store = ReportStore()
    rid = state.get("report_id", "")
    r = store.get(rid) if rid else None
    if r:
        r["status"] = "rejected"
        store.save(r)
    return {"status": "rejected"}


def route_after_review(state: GraphState) -> str:
    return "publish" if state.get("decision") == "approve" else "revise"


def build_graph():
    """构建并编译周报工作流（带内存 checkpoint，支持 interrupt 恢复）。"""
    g = StateGraph(GraphState)
    g.add_node("collect", _collect_frames)
    g.add_node("label", _label)
    g.add_node("draft", _draft)
    g.add_node("review", _review)
    g.add_node("publish", _publish)
    g.add_node("revise", _revise)

    g.add_edge(START, "collect")
    g.add_edge("collect", "label")
    g.add_edge("label", "draft")
    g.add_edge("draft", "review")
    g.add_conditional_edges("review", route_after_review, {
        "publish": "publish",
        "revise": "revise",
    })
    g.add_edge("publish", END)
    g.add_edge("revise", END)

    return g.compile(checkpointer=MemorySaver())


# 模块级单例（演示足够；生产应换持久化 checkpointer）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def start_report(person: str, video: str, person_id: str = "", week: str = "",
                 similarity: float = 0.5, thread_id: str = "demo") -> dict:
    """启动周报生成，跑到人工审核中断点返回草稿。"""
    app = get_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    state = {
        "person": person, "person_id": person_id, "video": video,
        "week": week, "similarity": similarity,
    }
    result = app.invoke(state, cfg)
    result.pop("__interrupt__", None)  # 内部对象不序列化给前端
    return result


def resume_report(decision: str, edited: str = "", thread_id: str = "demo") -> dict:
    """人工审核后恢复工作流。decision: approve | reject。"""
    app = get_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    answer = {"decision": decision}
    if edited:
        answer["edited"] = edited
    result = app.invoke(Command(resume=answer), cfg)
    result.pop("__interrupt__", None)
    return result
