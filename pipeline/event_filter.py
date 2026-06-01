"""連続検出をデバウンスしてイベント単位にまとめるフィルター"""
import time
from dataclasses import dataclass, field
from typing import Optional
from .detector import DetectionResult, Detection


@dataclass
class DetectionEvent:
    """1回の「通過イベント」を表す"""
    event_id: str
    started_at: float
    ended_at: float
    detection_type: str          # "person" / "vehicle" / "person+vehicle"
    best_detections: list[Detection]
    frame_count: int
    trigger_frame_id: int

    @property
    def duration_sec(self) -> float:
        return self.ended_at - self.started_at


class EventFilter:
    """
    連続フレームの検出結果を受け取り、
    - クールダウン内の重複をまとめる
    - 一定フレーム数以上続いた場合のみ発火する
    """

    def __init__(
        self,
        min_frames: int = 3,
        cooldown_sec: float = 5.0,
        event_timeout_sec: float = 10.0,
    ):
        self.min_frames = min_frames
        self.cooldown_sec = cooldown_sec
        self.event_timeout_sec = event_timeout_sec

        self._active: Optional[_ActiveEvent] = None
        self._last_event_time: float = 0.0
        self._event_counter = 0

    def process(self, result: DetectionResult) -> Optional[DetectionEvent]:
        """
        フレーム結果を渡す。イベント完了時のみ DetectionEvent を返す。
        """
        if not result.has_detections:
            return self._maybe_close()

        # クールダウン中は無視
        if time.time() - self._last_event_time < self.cooldown_sec:
            return None

        if self._active is None:
            self._active = _ActiveEvent(trigger_frame_id=result.frame_id)

        self._active.add(result)

        # タイムアウト超過 → 強制クローズ
        if time.time() - self._active.started_at > self.event_timeout_sec:
            return self._close_event()

        return None

    def _maybe_close(self) -> Optional[DetectionEvent]:
        if self._active and self._active.frame_count >= self.min_frames:
            return self._close_event()
        self._active = None
        return None

    def _close_event(self) -> Optional[DetectionEvent]:
        active = self._active
        self._active = None
        if active is None or active.frame_count < self.min_frames:
            return None

        self._last_event_time = time.time()
        self._event_counter += 1
        event_id = f"evt_{int(active.started_at)}_{self._event_counter:04d}"

        detection_type = active.detection_type()
        return DetectionEvent(
            event_id=event_id,
            started_at=active.started_at,
            ended_at=time.time(),
            detection_type=detection_type,
            best_detections=active.best_detections(),
            frame_count=active.frame_count,
            trigger_frame_id=active.trigger_frame_id,
        )


class _ActiveEvent:
    def __init__(self, trigger_frame_id: int):
        self.started_at = time.time()
        self.trigger_frame_id = trigger_frame_id
        self.frame_count = 0
        self._all_detections: list[Detection] = []

    def add(self, result: DetectionResult):
        self.frame_count += 1
        self._all_detections.extend(result.detections)

    def detection_type(self) -> str:
        has_person = any(d.is_person for d in self._all_detections)
        has_vehicle = any(d.is_vehicle for d in self._all_detections)
        if has_person and has_vehicle:
            return "person+vehicle"
        if has_person:
            return "person"
        if has_vehicle:
            return "vehicle"
        return "motion"

    def best_detections(self) -> list[Detection]:
        """信頼度が最も高いフレームの検出結果を返す"""
        if not self._all_detections:
            return []
        # 信頼度上位5件
        return sorted(self._all_detections, key=lambda d: d.confidence, reverse=True)[:5]
