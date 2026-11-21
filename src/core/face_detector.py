"""人脸检测与特征比对（InsightFace / ArcFace 512 维向量）。

首次运行会自动下载 buffalo_l 模型到 ~/.insightface（约 300MB）。
比对用余弦相似度（向量已 L2 归一化，点积即余弦）：
    相似度 >= high   -> 确认归属
    low <= 相似度 < high -> 进待确认池（主动学习）
    相似度 < low     -> 不匹配
"""
from __future__ import annotations

import numpy as np

from src.models.schemas import FaceHit

DEFAULT_MODEL = "buffalo_l"


class FaceDetector:
    def __init__(self, model_name: str = DEFAULT_MODEL, det_size: tuple[int, int] = (640, 640)):
        self.model_name = model_name
        self.det_size = det_size
        self._app = None  # 延迟加载，避免 import 时就触发下载

    def _get_app(self):
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis
            except ImportError as e:
                raise RuntimeError("缺少 insightface，请先 pip install insightface onnxruntime") from e
            print(f"[face] 加载模型 {self.model_name}（首次会自动下载约 300MB，请稍候）...")
            try:
                app = FaceAnalysis(name=self.model_name)
                app.prepare(ctx_id=-1, det_size=self.det_size)  # ctx_id=-1 走 CPU/NPU，M 系列够用
            except Exception as e:
                raise RuntimeError(
                    f"人脸模型 {self.model_name} 加载失败（通常是首次下载中断）：{e}\n"
                    "  处理方式二选一：\n"
                    "  1) 手动下载：访问 https://github.com/deepinsight/insightface/releases/download/v0.7/"
                    f"{self.model_name}.zip ，解压到 ~/.insightface/models/{self.model_name}/ ；\n"
                    "  2) 若系统代理不稳定，可在 shell 里执行 unset http_proxy https_proxy 后重试。\n"
                    "  模型文件约 275MB，建议用支持断点续传的工具下载。"
                ) from e
            self._app = app
        return self._app

    def detect(self, frame: np.ndarray) -> list:
        """检测单帧，返回 insightface 的 Face 对象列表（含 embedding）。"""
        return self._get_app().get(frame)

    @staticmethod
    def normalize(vec: np.ndarray) -> np.ndarray:
        v = np.asarray(vec, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    def compare(
        self,
        embedding: np.ndarray,
        template_map: dict[str, np.ndarray],
        threshold_high: float = 0.40,
        threshold_low: float = 0.25,
    ) -> tuple[str | None, float, bool]:
        """把一个 embedding 与全部人物模板比对。

        返回 (person_id, 最高相似度, 是否待确认)。
        多模板取该人所有模板中的最大相似度，胜出者再按阈值判定。
        """
        e = self.normalize(embedding)
        best_id, best_sim = None, -1.0
        for pid, matrix in template_map.items():
            if matrix.size == 0:
                continue
            mats = matrix.astype(np.float32)
            norms = np.linalg.norm(mats, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            sims = (mats / norms) @ e          # (N,) 余弦相似度
            top = float(sims.max())
            if top > best_sim:
                best_sim, best_id = top, pid

        if best_id is None or best_sim < threshold_low:
            return None, round(max(best_sim, 0.0), 4), False
        pending = threshold_low <= best_sim < threshold_high
        return (None if pending else best_id), round(best_sim, 4), pending

    def embedding_from_image(self, image_path: str | bytes) -> list[np.ndarray]:
        """从一张基准照中提所有检测到的人脸向量（通常取最大那张脸）。"""
        import cv2
        img = cv2.imread(str(image_path)) if isinstance(image_path, str) else image_path
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        faces = self.detect(img)
        return [self.normalize(f.embedding) for f in faces]
