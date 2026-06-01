"""
ONVIF イベント駆動型クリップ分析
15秒クリップから最高confidence フレームを抽出
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
from loguru import logger

from pipeline.detector import YOLODetector, Detection


@dataclass
class ClipAnalysisResult:
    """クリップ分析結果"""
    event_id: str
    detection_type: str          # "person" / "vehicle" / "motion"
    best_frame: np.ndarray       # 最高confidence フレーム
    best_frame_time: float       # ベストフレームのタイムスタンプ
    best_confidence: float
    frame_count: int
    started_at: float
    ended_at: float


class ClipAnalyzer:
    """
    15秒クリップ内で every 5th frame に YOLOv8 推論を実行。
    最高confidence フレームを抽出して返す。
    """

    def __init__(self, detector: YOLODetector):
        self.detector = detector

    def analyze(
        self,
        frames: list[tuple[np.ndarray, float]],
        event_id: str,
        frame_interval: int = 5,
    ) -> Optional[ClipAnalysisResult]:
        """
        frames: [(画像, タイムスタンプ), ...]
        frame_interval: 何フレーム毎に推論するか (デフォルト: 5)

        戻り値: ClipAnalysisResult または None (フレームなし)
        """
        if not frames:
            logger.warning(f"[{event_id}] no frames to analyze")
            return None

        best_frame = None
        best_frame_time = 0.0
        best_confidence = 0.0
        best_detection_type = "motion"

        started_at = frames[0][1]
        ended_at = frames[-1][1]

        # every frame_interval フレーム目に推論
        for i in range(0, len(frames), frame_interval):
            img, ts = frames[i]
            result = self.detector.detect(img)

            if result and result.has_detections:
                # 各フレームで最高confidence を取得
                for det in result.detections:
                    if det.confidence > best_confidence:
                        best_confidence = det.confidence
                        best_frame = img.copy()
                        best_frame_time = ts
                        # detection_type を更新（末尾の検出で上書き）
                        if det.class_id == 0:  # person
                            best_detection_type = "person"
                        elif det.class_id in [2, 3, 5, 7]:  # car/motorcycle/bus/truck
                            best_detection_type = "vehicle"

        # ベストフレームがない場合は最初のフレームを使用
        if best_frame is None:
            best_frame = frames[0][0].copy()
            best_frame_time = frames[0][1]
            best_confidence = 0.0
            best_detection_type = "motion"

        return ClipAnalysisResult(
            event_id=event_id,
            detection_type=best_detection_type,
            best_frame=best_frame,
            best_frame_time=best_frame_time,
            best_confidence=best_confidence,
            frame_count=len(frames),
            started_at=started_at,
            ended_at=ended_at,
        )
