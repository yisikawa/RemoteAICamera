"""静止画・動画クリップのローカル保存管理"""
from __future__ import annotations
import os
import shutil
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
from loguru import logger


class FileStore:
    def __init__(
        self,
        snapshots_dir: str = "data/snapshots",
        clips_dir: str = "data/clips",
        snapshot_quality: int = 90,
        clip_pre_seconds: float = 3.0,
        clip_post_seconds: float = 5.0,
        max_storage_gb: float = 50.0,
    ):
        self.snapshots_dir = Path(snapshots_dir)
        self.clips_dir = Path(clips_dir)
        self.snapshot_quality = snapshot_quality
        self.clip_pre_seconds = clip_pre_seconds
        self.clip_post_seconds = clip_post_seconds
        self.max_storage_bytes = int(max_storage_gb * 1024 ** 3)

        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 静止画保存                                                            #
    # ------------------------------------------------------------------ #

    def save_snapshot(
        self,
        frame: np.ndarray,
        event_id: Optional[str] = None,
        prefix: str = "snap",
    ) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S_%f")[:13]
        day_dir = self.snapshots_dir / date_str
        day_dir.mkdir(exist_ok=True)

        name = f"{prefix}_{time_str}"
        if event_id:
            name = f"{event_id}_{time_str}"
        path = day_dir / f"{name}.jpg"

        cv2.imwrite(
            str(path),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.snapshot_quality],
        )
        logger.debug(f"Snapshot saved: {path}")
        return str(path)

    # ------------------------------------------------------------------ #
    # 動画クリップ保存                                                      #
    # ------------------------------------------------------------------ #

    def save_clip(
        self,
        frames: list[tuple[np.ndarray, float]],  # (image, timestamp) リスト
        event_id: str,
        fps: float = 15.0,
    ) -> Optional[str]:
        if not frames:
            return None

        date_str = datetime.fromtimestamp(frames[0][1]).strftime("%Y-%m-%d")
        time_str = datetime.fromtimestamp(frames[0][1]).strftime("%H%M%S")
        day_dir = self.clips_dir / date_str
        day_dir.mkdir(exist_ok=True)

        path = day_dir / f"{event_id}_{time_str}.mp4"
        h, w = frames[0][0].shape[:2]

        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (w, h),
        )
        for img, _ in frames:
            writer.write(img)
        writer.release()

        size_kb = path.stat().st_size // 1024
        logger.info(f"Clip saved: {path} ({size_kb}KB, {len(frames)} frames)")
        return str(path)

    # ------------------------------------------------------------------ #
    # ストレージ容量管理                                                    #
    # ------------------------------------------------------------------ #

    def check_storage(self) -> dict:
        snap_size = self._dir_size(self.snapshots_dir)
        clip_size = self._dir_size(self.clips_dir)
        total = snap_size + clip_size
        return {
            "snapshots_gb": round(snap_size / 1024 ** 3, 2),
            "clips_gb": round(clip_size / 1024 ** 3, 2),
            "total_gb": round(total / 1024 ** 3, 2),
            "limit_gb": round(self.max_storage_bytes / 1024 ** 3, 2),
            "usage_pct": round(total / self.max_storage_bytes * 100, 1),
        }

    def cleanup_old_files(self, keep_days: int = 30):
        """keep_days より古いファイルを削除"""
        cutoff = time.time() - keep_days * 86400
        removed = 0
        for directory in [self.snapshots_dir, self.clips_dir]:
            for f in directory.rglob("*"):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
        if removed:
            logger.info(f"Cleanup: removed {removed} files older than {keep_days} days")
        return removed

    @staticmethod
    def _dir_size(path: Path) -> int:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


class FrameRingBuffer:
    """
    RTSPCapture のフレームを受け取り、一定秒数分を循環バッファで保持する。
    イベント発火時に pre_seconds 分の過去フレームを取り出せる。
    """

    def __init__(self, pre_seconds: float = 5.0, fps_hint: int = 15):
        self._buf: deque[tuple[np.ndarray, float]] = deque(
            maxlen=int(pre_seconds * fps_hint)
        )

    def push(self, frame: np.ndarray, timestamp: float):
        self._buf.append((frame.copy(), timestamp))

    def get_pre_frames(self, since: float) -> list[tuple[np.ndarray, float]]:
        """since 以降のフレームを返す"""
        return [(img, ts) for img, ts in self._buf if ts >= since]

    def all_frames(self) -> list[tuple[np.ndarray, float]]:
        return list(self._buf)
