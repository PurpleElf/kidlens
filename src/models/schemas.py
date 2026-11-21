"""核心数据模型。

用 dataclass 而非 ORM，展示项目轻量够用；字段与 PRD 对齐。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Person:
    """人物档案。"""
    id: str
    name: str
    nickname: str = ""
    birthdate: str = ""
    note: str = ""
    base_images: list[str] = field(default_factory=list)
    templates: list[list[float]] = field(default_factory=list)  # 多模板：基准照 + 主动学习追加


@dataclass
class FaceHit:
    """一次人脸命中记录。"""
    frame_id: int
    timestamp: float          # 秒
    person_id: Optional[str]  # None = 未匹配到任何人
    similarity: float
    is_pending: bool = False  # 落在模糊区间，进待确认池


@dataclass
class ClipSegment:
    """一个单人片段区间。"""
    start: float              # 秒
    end: float                # 秒
    person_id: str
    hit_count: int = 0

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class WeeklyReport:
    """成长周报草稿。"""
    person_id: str
    week: str
    highlights: str = ""
    observation: str = ""
    wish: str = ""
    frame_paths: list[str] = field(default_factory=list)
    approved: bool = False
