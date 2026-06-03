"""
ONVIF イベント駆動型クリップ分析
15秒クリップから最高confidence フレームを抽出
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from loguru import logger

from pipeline.detector import YOLODetector, Detection, CATEGORY_MAP

# detection_type の優先順位（複数検出時にどのカテゴリを代表とするか）
_CATEGORY_PRIORITY: dict[str, int] = {
    "person":     5,
    "pet":        4,
    "motorcycle": 3,
    "bicycle":    2,
    "car":        1,
    "other":      0,
}


def _dominant_category(detections: list[Detection]) -> str:
    """検出リストの中で最も優先度の高いカテゴリを返す"""
    if not detections:
        return "other"
    return max(
        (CATEGORY_MAP.get(d.class_id, "other") for d in detections),
        key=lambda c: _CATEGORY_PRIORITY.get(c, 0),
    )


@dataclass
class ClipAnalysisResult:
    """クリップ分析結果"""
    event_id: str
    detection_type: str          # person / car / motorcycle / bicycle / pet / other
    best_frame: np.ndarray       # 最高confidence フレーム
    best_frame_time: float
    best_confidence: float
    best_detections: list[Detection] = field(default_factory=list)  # ベストフレームの全検出
    frame_count: int = 0
    started_at: float = 0.0
    ended_at: float = 0.0


class ClipAnalyzer:
    """
    15秒クリップ内で every 5th frame に YOLOv8 推論を実行。
    最高confidence フレームとその全検出結果を返す。
    """

    def __init__(self, detector: YOLODetector):
        self.detector = detector

    def analyze(
        self,
        frames: list[tuple[np.ndarray, float]],
        event_id: str,
        frame_interval: int = 5,
    ) -> Optional[ClipAnalysisResult]:
        if not frames:
            logger.warning(f"[{event_id}] no frames to analyze")
            return None

        best_frame = None
        best_frame_time = 0.0
        best_confidence = 0.0
        best_detections: list[Detection] = []

        started_at = frames[0][1]
        ended_at = frames[-1][1]

        for i in range(0, len(frames), frame_interval):
            img, ts = frames[i]
            result = self.detector.detect(img)

            if result and result.has_detections:
                frame_top_conf = max(d.confidence for d in result.detections)
                if frame_top_conf > best_confidence:
                    best_confidence = frame_top_conf
                    best_frame = img.copy()
                    best_frame_time = ts
                    best_detections = list(result.detections)

        if best_frame is None:
            best_frame = frames[0][0].copy()
            best_frame_time = frames[0][1]
            best_confidence = 0.0
            best_detections = []

        detection_type = _dominant_category(best_detections) if best_detections else "other"

        return ClipAnalysisResult(
            event_id=event_id,
            detection_type=detection_type,
            best_frame=best_frame,
            best_frame_time=best_frame_time,
            best_confidence=best_confidence,
            best_detections=best_detections,
            frame_count=len(frames),
            started_at=started_at,
            ended_at=ended_at,
        )
