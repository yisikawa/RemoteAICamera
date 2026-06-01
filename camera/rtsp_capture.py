"""RTSP ストリームキャプチャ + フレームバッファ管理"""
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np
from loguru import logger


@dataclass
class Frame:
    data: np.ndarray
    timestamp: float
    frame_id: int


class RTSPCapture:
    """
    別スレッドで RTSP を常時受信し、最新フレームをバッファに保持する。
    カメラ切断時は reconnect_interval 秒後に自動再接続する。
    """

    def __init__(
        self,
        rtsp_url: str,
        buffer_seconds: int = 10,
        fps_hint: int = 15,
        reconnect_interval: int = 5,
    ):
        self.rtsp_url = rtsp_url
        self.reconnect_interval = reconnect_interval
        buffer_size = buffer_seconds * fps_hint
        self._buffer: deque[Frame] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_id = 0
        self._fps = 0.0
        self._connected = False

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"RTSPCapture started: {self.rtsp_url}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("RTSPCapture stopped")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def fps(self) -> float:
        return self._fps

    def latest_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_recent_frames(self, seconds: float) -> list[Frame]:
        """直近 N 秒分のフレームを返す"""
        cutoff = time.time() - seconds
        with self._lock:
            return [f for f in self._buffer if f.timestamp >= cutoff]

    def snapshot(self) -> Optional[np.ndarray]:
        frame = self.latest_frame()
        return frame.data.copy() if frame else None

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _capture_loop(self):
        while not self._stop_event.is_set():
            cap = self._open_capture()
            if cap is None:
                time.sleep(self.reconnect_interval)
                continue

            self._connected = True
            logger.info("RTSP stream opened")
            fps_counter = _FPSCounter()

            while not self._stop_event.is_set():
                ret, img = cap.read()
                if not ret:
                    logger.warning("Frame read failed — reconnecting")
                    break
                ts = time.time()
                self._frame_id += 1
                frame = Frame(data=img, timestamp=ts, frame_id=self._frame_id)
                with self._lock:
                    self._buffer.append(frame)
                self._fps = fps_counter.tick()

            cap.release()
            self._connected = False
            if not self._stop_event.is_set():
                logger.info(f"Reconnecting in {self.reconnect_interval}s…")
                time.sleep(self.reconnect_interval)

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            logger.warning(f"Cannot open RTSP: {self.rtsp_url}")
            return None
        return cap


class _FPSCounter:
    def __init__(self, window: int = 30):
        self._times: deque[float] = deque(maxlen=window)

    def tick(self) -> float:
        self._times.append(time.time())
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0
