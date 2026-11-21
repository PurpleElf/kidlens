"""本地文件存储：MD5 去重 + 归档 + 取回。

展示项目用本地目录替代 MinIO，零依赖、零额外内存。
未来若要换回 MinIO，只要保持同名方法（md5 / archive / get / exists）即可无缝替换。
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class LocalStorage:
    """基于本地目录的对象存储。

    目录约定（根目录由 data_dir 指定，默认 ./data）：
        data/inbox/     原始素材（拖入区）
        data/archive/   去重归档（按 MD5 命名）
        data/output/    切片 / 集锦 / 周报产物
    """

    def __init__(self, data_dir: str | Path = "./data"):
        self.root = Path(data_dir).resolve()
        self.inbox_dir = self.root / "inbox"
        self.archive_dir = self.root / "archive"
        self.output_dir = self.root / "output"
        for d in (self.inbox_dir, self.archive_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def md5(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
        """计算文件 MD5（分块读取，支持大视频）。"""
        digest = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def archive(self, src: str | Path) -> tuple[str, bool]:
        """归档单个文件，返回 (目标路径, 是否新归档)。

        相同 MD5 的文件只保留一份：已存在则跳过复制并复用原文件。
        这是演示时可以讲的"工程细节"——去重逻辑不依赖任何外部服务。
        """
        src = Path(src)
        digest = self.md5(src)
        ext = src.suffix.lower()
        target = self.archive_dir / f"{digest}{ext}"
        if target.exists():
            return str(target), False
        shutil.copy2(src, target)
        return str(target), True

    def archivelist(self) -> list[Path]:
        """列出所有已归档文件。"""
        return sorted(p for p in self.archive_dir.iterdir() if p.is_file())

    def get(self, name: str) -> Path:
        """按文件名从归档区取回（返回绝对路径）。"""
        path = self.archive_dir / name
        if not path.exists():
            raise FileNotFoundError(f"归档中不存在: {name}")
        return path

    def scan_inbox(self) -> list[Path]:
        """扫描拖入区里的素材文件。"""
        exts = {".mp4", ".mov", ".jpg", ".png"}
        return sorted(
            p for p in self.inbox_dir.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )

    def exists(self, digest: str, ext: str = "") -> bool:
        """判断某 MD5 是否已归档（ext 可进一步限定扩展名）。"""
        pattern = f"{digest}{ext}" if ext else digest
        return any(p.name.startswith(pattern) for p in self.archive_dir.iterdir())
