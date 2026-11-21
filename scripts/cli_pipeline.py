"""Phase 1 命令行闭环入口。

三个子命令：
    enroll  从基准照建档（提 512 维向量入模板库）
    scan    扫描视频，输出人脸命中与切片区间（不剪片，便宜 fast）
    run     完整闭环：命中 -> 切片 -> 单人高光集锦 mp4

用法示例：
    python scripts/cli_pipeline.py enroll --name 小宝 --images data/faces/xb1.jpg data/faces/xb2.jpg
    python scripts/cli_pipeline.py scan --input data/inbox/班级视频.mp4
    python scripts/cli_pipeline.py run --input data/inbox/班级视频.mp4 --person 小宝
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings, get_yaml_config
from src.core.face_detector import FaceDetector
from src.core.face_registry import FaceRegistry
from src.core.highlight import build_highlight, ffmpeg_available
from src.core.slicer import extract_hits, merge_intervals


def _thresholds(cfg: dict) -> tuple[float, float]:
    face = cfg.get("face", {})
    return face.get("threshold_high", 0.40), face.get("threshold_low", 0.25)


def cmd_enroll(args, cfg: dict) -> None:
    registry = FaceRegistry(ROOT / "data" / "faces")
    detector = FaceDetector()

    embeddings = []
    for img in args.images:
        if not Path(img).exists():
            print(f"[warn] 图片不存在，跳过: {img}")
            continue
        faces = detector.embedding_from_image(img)
        if not faces:
            print(f"[warn] 未检测到人脸: {img}")
            continue
        # 一张基准照取最大那张脸（通常面积最大者是主角）
        embeddings.append(faces[0])
        print(f"[enroll] 已从 {Path(img).name} 提取特征")

    if not embeddings:
        print("[error] 没有可用的人脸特征，建档失败")
        return

    existing = registry.find_by_name(args.name)
    if existing:
        person = existing
        print(f"[enroll] 人物 {args.name} 已存在，追加 {len(embeddings)} 个模板")
    else:
        person = registry.create_person(
            name=args.name,
            nickname=args.nickname,
            birthdate=args.birthdate,
            note=args.note,
            base_images=[str(i) for i in args.images],
        )
        print(f"[enroll] 新建人物 {args.name} (id={person.id})")

    total = registry.add_templates(person.id, embeddings)
    print(f"[enroll] 完成：{args.name} 现有 {total} 个模板")


def cmd_scan(args, cfg: dict) -> None:
    registry = FaceRegistry(ROOT / "data" / "faces")
    template_map = registry.template_map()
    if not template_map:
        print("[error] 模板库为空，请先 enroll 建档")
        return

    detector = FaceDetector()
    high, low = _thresholds(cfg)
    face_cfg = cfg.get("face", {})
    hits = extract_hits(
        args.input,
        detector,
        template_map,
        step_seconds=face_cfg.get("sample_step_seconds", 2.0),
        threshold_high=high,
        threshold_low=low,
    )

    names = {p.id: p.name for p in registry.list_persons()}
    print(f"\n[scan] 共 {len(hits)} 次人脸检测，明细：")
    for h in hits[:40]:
        who = names.get(h.person_id, "待确认" if h.is_pending else "陌生人")
        print(f"  {h.timestamp:7.2f}s  {who:6s}  sim={h.similarity:.3f}")
    if len(hits) > 40:
        print(f"  ... 另有 {len(hits) - 40} 条")

    print("\n[scan] 切片汇总：")
    clip_cfg = cfg.get("clip", {})
    for pid in template_map:
        segs = merge_intervals(
            hits, pid,
            gap_seconds=face_cfg.get("merge_gap_seconds", 4.0),
            padding_seconds=clip_cfg.get("padding_seconds", 2.0),
            min_duration=clip_cfg.get("min_duration_seconds", 3.0),
        )
        print(f"  {names.get(pid, pid)}: {len(segs)} 段 " +
              ", ".join(f"{s.start}-{s.end}s" for s in segs))


def cmd_run(args, cfg: dict) -> None:
    registry = FaceRegistry(ROOT / "data" / "faces")
    person = registry.find_by_name(args.person)
    if not person:
        print(f"[error] 找不到人物 {args.person}，请先 enroll 建档")
        return
    templates = registry.load_templates(person.id).reshape(1, -1)
    if templates.size == 0:
        print(f"[error] {args.person} 还没有模板，请先 enroll")
        return

    detector = FaceDetector()
    high, low = _thresholds(cfg)
    face_cfg = cfg.get("face", {})
    clip_cfg = cfg.get("clip", {})
    hits = extract_hits(
        args.input, detector, {person.id: templates},
        step_seconds=face_cfg.get("sample_step_seconds", 2.0),
        threshold_high=high, threshold_low=low,
    )
    segs = merge_intervals(
        hits, person.id,
        gap_seconds=face_cfg.get("merge_gap_seconds", 4.0),
        padding_seconds=clip_cfg.get("padding_seconds", 2.0),
        min_duration=clip_cfg.get("min_duration_seconds", 3.0),
    )
    if not segs:
        print(f"[run] 没有找到 {args.person} 的有效片段")
        return

    print(f"[run] {args.person}: {len(segs)} 段，总时长 "
          f"{sum(s.duration for s in segs):.1f}s")
    print(f"[run] 剪辑后端: {'ffmpeg' if ffmpeg_available() else 'opencv（建议装 ffmpeg 以获得更好质量）'}")

    out_dir = Path(args.output)
    out_file = out_dir / f"{args.person}_高光集锦.mp4"
    build_highlight(args.input, segs, out_file, temp_dir=out_dir / "_parts")
    print(f"[run] 完成 -> {out_file}")


def cmd_report(args, cfg: dict) -> None:
    """生成成长周报（LangGraph 工作流，含人工审核中断）。"""
    from src.workflow.weekly_report import start_report, resume_report

    if args.decision:
        # 审核模式：直接操作落盘的 report_store（跨进程可靠，不依赖内存 checkpoint）
        from src.db.report_store import ReportStore
        store = ReportStore()
        drafts = [r for r in store.list() if r.get("status") == "draft"]
        if not drafts:
            print("[warn] 没有待审核的草稿")
            return
        target = drafts[0]
        if args.decision == "approve":
            if args.edit:
                target["summary"] = args.edit
                store.save(target)
            store.approve(target["id"])
            print(f"[report] 已通过: {target['id']}")
            print(f"[report] 最终文案: {store.get(target['id'])['summary']}")
        else:
            target["status"] = "rejected"
            store.save(target)
            print(f"[report] 已打回: {target['id']}")
        return

    registry = FaceRegistry(ROOT / "data" / "faces")
    person = registry.find_by_name(args.person)
    if not person:
        print(f"[error] 找不到人物 {args.person}，请先 enroll 建档")
        return

    print(f"[report] 启动周报生成（人物={args.person}, 视频={args.input}）...")
    draft = start_report(
        person=args.person, video=args.input, person_id=person.id,
        similarity=args.similarity, thread_id=args.thread,
    )
    print("\n--- 周报草稿（待审核）---")
    print(f"  ID   : {draft.get('report_id')}")
    print(f"  标题 : {draft.get('title')}")
    print(f"  文案 : {draft.get('summary')}")
    print(f"  标签 : {', '.join(draft.get('tags', []))}")
    print(f"  关键帧: {len(draft.get('frame_paths', []))} 张")
    print("\n[report] 草稿已落盘，等待人工审核。审核通过请执行：")
    print("  .venv/bin/python scripts/cli_pipeline.py report --decision approve")
    print("  如需改文案：追加 --edit '改后的文案'")


def main() -> None:
    parser = argparse.ArgumentParser(description="KidLens Phase 1 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_enroll = sub.add_parser("enroll", help="从基准照建立人物档案")
    p_enroll.add_argument("--name", required=True, help="人物姓名")
    p_enroll.add_argument("--images", nargs="+", required=True, help="基准照路径（1~5 张）")
    p_enroll.add_argument("--nickname", default="")
    p_enroll.add_argument("--birthdate", default="")
    p_enroll.add_argument("--note", default="")

    p_scan = sub.add_parser("scan", help="扫描视频，输出命中与切片（不剪片）")
    p_scan.add_argument("--input", required=True, help="输入视频路径")

    p_run = sub.add_parser("run", help="完整闭环：命中 -> 切片 -> 集锦 mp4")
    p_run.add_argument("--input", required=True, help="输入视频路径")
    p_run.add_argument("--person", required=True, help="目标人物名")
    p_run.add_argument("--output", default="./data/output", help="输出目录")

    p_report = sub.add_parser("report", help="生成成长周报（LangGraph + 人工审核）")
    p_report.add_argument("--input", default="data/inbox/视频.MP4", help="输入视频路径")
    p_report.add_argument("--person", default="小宝", help="目标人物名")
    p_report.add_argument("--similarity", type=float, default=0.5, help="平均相似度（模板文案用）")
    p_report.add_argument("--thread", default="demo", help="工作流线程 ID（审核恢复要用同一个）")
    p_report.add_argument("--decision", choices=["approve", "reject"], help="审核决定（恢复工作流）")
    p_report.add_argument("--edit", default="", help="审核时编辑后的文案")

    args = parser.parse_args()
    cfg = get_yaml_config()
    {"enroll": cmd_enroll, "scan": cmd_scan, "run": cmd_run, "report": cmd_report}[args.command](args, cfg)


if __name__ == "__main__":
    main()
