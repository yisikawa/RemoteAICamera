"""
RTSP 音声ストリームから騒音レベル (dB) を継続的に計測するモジュール。
Tapo C520W: pcm_alaw 8000Hz モノラル
"""
from __future__ import annotations
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class NoiseLevel:
    timestamp: float
    db: float
    peak_db: float
    duration_sec: float = 0.5


class AudioMonitor:
    """
    RTSP 音声を別スレッドで受信し、RMS → dB 変換してバッファに保持する。
    alert_db 以上が連続したときにコールバックを呼ぶ。
    """

    REFERENCE = 32768.0   # 16bit PCM の最大値 (0 dBFS 基準)

    def __init__(
        self,
        rtsp_url: str,
        camera_name: str = "cam",
        window_sec: float = 0.5,      # dB 計算ウィンドウ (秒)
        alert_db: float = 70.0,       # この dB を超えたら騒音イベント
        alert_duration: float = 1.0,  # 連続してこの秒数超えたら発火
        history_sec: int = 60,        # 保持する履歴の長さ (秒)
    ):
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.window_sec = window_sec
        self.alert_db = alert_db
        self.alert_duration = alert_duration

        self._history: deque[NoiseLevel] = deque(
            maxlen=int(history_sec / window_sec)
        )
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_db: float = 0.0
        self._alert_since: Optional[float] = None
        self._on_alert = None   # コールバック: (NoiseLevel) -> None

    def start(self, on_alert=None):
        self._on_alert = on_alert
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"audio-{self.camera_name}"
        )
        self._thread.start()
        logger.info(f"AudioMonitor started: {self.camera_name}")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def current_db(self) -> float:
        return self._current_db

    def latest(self, n: int = 10) -> list[NoiseLevel]:
        with self._lock:
            return list(self._history)[-n:]

    def average_db(self, last_sec: float = 10.0) -> float:
        cutoff = time.time() - last_sec
        with self._lock:
            vals = [n.db for n in self._history if n.timestamp >= cutoff]
        return float(np.mean(vals)) if vals else 0.0

    # ------------------------------------------------------------------ #
    # 内部処理                                                              #
    # ------------------------------------------------------------------ #

    def _run(self):
        import av
        while not self._stop.is_set():
            try:
                self._capture_loop()
            except Exception as e:
                logger.warning(f"AudioMonitor {self.camera_name} error: {e}")
                if not self._stop.is_set():
                    time.sleep(3)

    def _capture_loop(self):
        import av
        options = {"rtsp_transport": "tcp", "stimeout": "5000000"}
        container = av.open(self.rtsp_url, options=options, timeout=10)

        audio_stream = next(
            (s for s in container.streams if s.type == "audio"), None
        )
        if audio_stream is None:
            logger.warning(f"No audio stream: {self.camera_name}")
            container.close()
            return

        sample_rate = audio_stream.codec_context.sample_rate
        samples_per_window = int(sample_rate * self.window_sec)
        buf = np.array([], dtype=np.float32)

        for packet in container.demux(audio_stream):
            if self._stop.is_set():
                break
            for frame in packet.decode():
                pcm = frame.to_ndarray().astype(np.float32).flatten()
                buf = np.concatenate([buf, pcm])

                while len(buf) >= samples_per_window:
                    window = buf[:samples_per_window]
                    buf = buf[samples_per_window:]
                    self._process_window(window)

        container.close()

    def _process_window(self, samples: np.ndarray):
        rms = np.sqrt(np.mean(samples ** 2))
        db = 20 * np.log10(rms / self.REFERENCE + 1e-9)
        peak = 20 * np.log10(np.max(np.abs(samples)) / self.REFERENCE + 1e-9)

        now = time.time()
        level = NoiseLevel(timestamp=now, db=round(db, 1), peak_db=round(peak, 1))
        self._current_db = db

        with self._lock:
            self._history.append(level)

        # 騒音アラート判定
        if db >= self.alert_db:
            if self._alert_since is None:
                self._alert_since = now
            elif now - self._alert_since >= self.alert_duration:
                if self._on_alert:
                    self._on_alert(level)
                self._alert_since = now   # 連続発火を防ぐ
        else:
            self._alert_since = None
