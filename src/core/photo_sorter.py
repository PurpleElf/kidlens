"""照片/视频人脸分拣：一张素材里有哪些孩子？

轻量设计（单机、量少）：
    逐张检测所有人脸 → 每个 embedding 与档案库比对 → 命中的孩子去重收集。
    多人合影返回多个孩子（①a：归档时每个孩子各放一份硬链接）。
    一张脸都没认出 → needs_review=True，进待确认池，人工兜底。

视频用稀疏抽帧复用同一套比对（不切片、不出集锦——那是旧演示链路的事）。
模型延迟加载：import 本模块不会触发人脸模型下载。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.config import get_yaml_config

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


class PhotoSorter:
    def __init__(self, registry=None, detector=None):
        self.registry = registry
        self._detector = detector
        cfg = get_yaml_config()["face"]
        self.threshold_high = float(cfg["threshold_high"])
        self.threshold_low = float(cfg["threshold_low"])

    @property
    def detector(self):
        if self._detector is None:
            from src.core.face_detector import FaceDetector
            self._detector = FaceDetector()
        return self._detector

    @property
    def registry_obj(self):
        if self.registry is None:
            from src.core.face_registry import FaceRegistry
            self.registry = FaceRegistry("./data/faces")
        return self.registry

    def _id_to_name(self) -> dict[str, str]:
        return {p.id: p.name for p in self.registry_obj.list_persons()}

    def _match_embedding(self, emb, template_map, id2name) -> dict:
        """单个 embedding 比对，返回 {name, similarity, pending}。"""
        pid, sim, pending = self.detector.compare(
            emb, template_map, self.threshold_high, self.threshold_low
        )
        return {
            "name": id2name.get(pid, "") if pid else "",
            "person_id": pid or "",
            "similarity": sim,
            "pending": bool(pending),
        }

    def sort_image(self, path: str | Path) -> dict:
        """分拣单张照片，返回结构化结果。"""
        import cv2
        path = Path(path)
        img = cv2.imread(str(path))
        if img is None:
            return self._empty(path, error="无法读取图片")

        faces = self.detector.detect(img)
        template_map = self.registry_obj.template_map()
        id2name = self._id_to_name()

        matched: dict[str, float] = {}   # name -> 最高相似度
        details = []
        has_pending = False
        for face in faces:
            emb = self.detector.normalize(face.embedding)
            r = self._match_embedding(emb, template_map, id2name)
            details.append(r)
            if r["pending"]:
                has_pending = True
            if r["name"]:
                matched[r["name"]] = max(matched.get(r["name"], 0.0), r["similarity"])

        persons = list(matched.keys())
        return {
            "path": str(path),
            "kind": "photo",
            "persons": persons,
            "similarities": matched,
            "face_count": len(faces),
            "details": details,
            "needs_review": len(persons) == 0,
            "has_pending": has_pending,
            "embedding": self._largest_face(faces),  # 供纠错回填人脸库
            "error": "",
        }

    def sort_video(self, path: str | Path, max_frames: int = 8) -> dict:
        """视频稀疏抽帧分拣：聚合所有帧里认出的孩子。"""
        import cv2
        path = Path(path)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return self._empty(path, error="无法打开视频", kind="video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total / fps if fps else 0
        # 均匀取 max_frames 个采样点
        step = max(duration / (max_frames + 1), 0.5)
        template_map = self.registry_obj.template_map()
        id2name = self._id_to_name()

        matched: dict[str, float] = {}
        details = []
        face_count = 0
        largest = None
        for i in range(1, max_frames + 1):
            t = min(step * i, max(duration - 0.1, 0))
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            faces = self.detector.detect(frame)
            face_count += len(faces)
            if faces and largest is None:
                largest = self.detector.normalize(faces[0].embedding)
            for face in faces:
                emb = self.detector.normalize(face.embedding)
                r = self._match_embedding(emb, template_map, id2name)
                details.append(r)
                if r["name"]:
                    matched[r["name"]] = max(matched.get(r["name"], 0.0), r["similarity"])
        cap.release()

        persons = list(matched.keys())
        return {
            "path": str(path),
            "kind": "video",
            "persons": persons,
            "similarities": matched,
            "face_count": face_count,
            "details": details,
            "needs_review": len(persons) == 0,
            "has_pending": any(d["pending"] for d in details),
            "embedding": largest,
            "error": "",
        }

    def sort(self, path: str | Path) -> dict:
        """自动按扩展名分流。"""
        ext = Path(path).suffix.lower()
        if ext in VIDEO_EXTS:
            return self.sort_video(path)
        if ext in IMAGE_EXTS:
            return self.sort_image(path)
        return self._empty(path, error=f"不支持的文件类型: {ext}")

    def _largest_face(self, faces) -> np.ndarray | None:
        """返回画面里最大那张脸的 embedding（纠错回填用）。"""
        if not faces:
            return None
        biggest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return self.detector.normalize(biggest.embedding)

    @staticmethod
    def _empty(path, error: str, kind: str = "photo") -> dict:
        return {
            "path": str(path), "kind": kind, "persons": [], "similarities": {},
            "face_count": 0, "details": [], "needs_review": True,
            "has_pending": False, "embedding": None, "error": error,
        }
