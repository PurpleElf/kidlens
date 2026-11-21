"""片段剪辑与集锦合成。

双路径设计：
    有系统 ffmpeg -> 用 ffmpeg-python 裁剪（快、精确、可控转场）
    无系统 ffmpeg -> 用 opencv 重新编码写出（慢一点，但零外部依赖，开箱能跑）

pip 装的 ffmpeg-python 只是个命令行包装，不含 ffmpeg 二进制；
所以这里先探测系统 PATH，缺失时自动降级到 opencv，不让演示卡住。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from src.models.schemas import ClipSegment

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def ffmpeg_available() -> bool:
    return _HAS_FFMPEG


def cut_segment(video: str | Path, segment: ClipSegment, out_path: str | Path) -> Path:
    """裁剪出单个片段，返回输出文件路径。"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_FFMPEG:
        return _cut_with_ffmpeg(video, segment, out)
    return _cut_with_opencv(video, segment, out)


def _cut_with_ffmpeg(video, segment: ClipSegment, out: Path) -> Path:
    import ffmpeg

    duration = segment.duration
    (
        ffmpeg.input(str(video), ss=segment.start, t=duration)
        .output(str(out), vcodec="libx264", acodec="aac", movflags="+faststart")
        .overwrite_output()
        .run(quiet=True)
    )
    return out


def _cut_with_opencv(video, segment: ClipSegment, out: Path) -> Path:
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, fps, (width, height))
    start_frame = int(segment.start * fps)
    end_frame = int(segment.end * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    frame = start_frame
    while frame < end_frame:
        ok, img = cap.read()
        if not ok:
            break
        writer.write(img)
        frame += 1

    writer.release()
    cap.release()
    return out


def concat_segments(parts: list[Path], out_path: str | Path) -> Path:
    """把多个片段按顺序拼成一个集锦。

    ffmpeg 路径用 concat demuxer；opencv 路径逐帧写入同一文件。
    """
    if not parts:
        raise ValueError("没有可拼接的片段")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_FFMPEG and len(parts) > 1:
        return _concat_with_ffmpeg(parts, out)
    return _concat_with_opencv(parts, out)


def _concat_with_ffmpeg(parts: list[Path], out: Path) -> Path:
    import ffmpeg

    list_file = out.parent / "_concat_list.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8"
    )
    try:
        (
            ffmpeg.input(str(list_file), format="concat", safe=0)
            .output(str(out), vcodec="libx264", acodec="aac")
            .overwrite_output()
            .run(quiet=True)
        )
    finally:
        list_file.unlink(missing_ok=True)
    return out


def _concat_with_opencv(parts: list[Path], out: Path) -> Path:
    import cv2

    writer = None
    for part in parts:
        cap = cv2.VideoCapture(str(part))
        if not cap.isOpened():
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if writer is None:
            writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        while True:
            ok, img = cap.read()
            if not ok:
                break
            writer.write(img)
        cap.release()
    if writer is None:
        raise RuntimeError("所有片段都无法读取，无法合成")
    writer.release()
    return out


def build_highlight(
    video: str | Path,
    segments: list[ClipSegment],
    out_path: str | Path,
    temp_dir: str | Path | None = None,
) -> Path:
    """一步到位：裁剪所有片段 -> 拼接 -> 输出单人高光集锦。

    只有 1 个片段时直接裁剪（无需拼接）。
    """
    segments = sorted(segments, key=lambda s: s.start)
    if not segments:
        raise ValueError("没有可用片段")
    tmp = Path(temp_dir or Path(out_path).parent / "_parts")
    tmp.mkdir(parents=True, exist_ok=True)

    parts = []
    for i, seg in enumerate(segments):
        part = tmp / f"part_{i:03d}.mp4"
        cut_segment(video, seg, part)
        parts.append(part)

    if len(parts) == 1:
        result = Path(out_path)
        result.parent.mkdir(parents=True, exist_ok=True)
        parts[0].replace(result)
        return result
    return concat_segments(parts, out_path)
