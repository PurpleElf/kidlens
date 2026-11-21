"""时空切片：抽帧检测 -> 命中时间戳合并 -> 前后扩边输出片段区间。

核心算法与 I/O 解耦：extract_hits 做检测（慢），merge_intervals 是纯函数（可单测）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.models.schemas import ClipSegment, FaceHit
from src.core.face_detector import FaceDetector


def extract_hits(
    video_path: str | Path,
    detector: FaceDetector,
    template_map: dict[str, np.ndarray],
    step_seconds: float = 2.0,
    threshold_high: float = 0.40,
    threshold_low: float = 0.25,
    progress_every: int = 50,
) -> list[FaceHit]:
    """按固定步长抽帧检测人脸，返回命中记录列表。

    每 step_seconds 抽一帧；一帧里可能有多个人脸，逐个与模板库比对。
    """
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps if fps else 0.0
    step_frames = max(1, int(round(step_seconds * fps)))

    hits: list[FaceHit] = []
    frame_id = 0
    sampled = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = cap.read()
        if not ok:
            break
        timestamp = round(frame_id / fps, 3)
        for face in detector.detect(frame):
            person_id, sim, pending = detector.compare(
                face.embedding, template_map, threshold_high, threshold_low
            )
            hits.append(
                FaceHit(
                    frame_id=frame_id,
                    timestamp=timestamp,
                    person_id=person_id,
                    similarity=sim,
                    is_pending=pending,
                )
            )
        sampled += 1
        if progress_every and sampled % progress_every == 0:
            print(f"[slicer] 已抽 {sampled} 帧 / {duration:.1f}s，命中 {len(hits)} 次")
        frame_id += step_frames
        if frame_id >= total:
            break

    cap.release()
    return hits


def merge_intervals(
    hits: list[FaceHit],
    person_id: str,
    gap_seconds: float = 4.0,
    padding_seconds: float = 2.0,
    min_duration: float = 3.0,
) -> list[ClipSegment]:
    """把某人的离散命中时间合并成连续区间，并前后扩边。

    - 相邻命中间隔 <= gap_seconds 视为同一段（容忍短暂遮挡）
    - 每段前后各扩 padding_seconds 秒，保留动作上下文
    - 短于 min_duration 的片段丢弃，避免碎片
    """
    times = sorted(h.timestamp for h in hits if h.person_id == person_id)
    if not times:
        return []

    groups: list[list[float]] = [[times[0]]]
    for t in times[1:]:
        if t - groups[-1][-1] <= gap_seconds:
            groups[-1].append(t)
        else:
            groups.append([t])

    segments: list[ClipSegment] = []
    for group in groups:
        start = max(0.0, group[0] - padding_seconds)
        end = group[-1] + padding_seconds
        if end - start < min_duration:
            continue
        segments.append(
            ClipSegment(
                start=round(start, 3),
                end=round(end, 3),
                person_id=person_id,
                hit_count=len(group),
            )
        )
    return segments
