"""RTSP ストリームキャプチャ（映像・音声を単一接続で同時取得 via PyAV）"""
from __future__ import annotations
import io
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class Frame:
    data: np.ndarray
    timestamp: float
    frame_id: int


class RTSPCapture:
    """
    PyAV で RTSP を常時受信し、映像フレームと音声を単一接続からバッファに保持する。
    カメラ切断時は reconnect_interval 秒後に自動再接続する。
    """

    def __init__(
        self,
        rtsp_url: str,
        buffer_seconds: int = 20,
        fps_hint: int = 15,
        reconnect_interval: int = 5,
        audio_buffer_seconds: int = 30,
    ):
        self.rtsp_url = rtsp_url
        self.reconnect_interval = reconnect_interval
        buffer_size = buffer_seconds * fps_hint
        self._buffer: deque[Frame] = deque(maxlen=buffer_size)
        self._audio_buf: deque[tuple[float, np.ndarray]] = deque()
        self._audio_buffer_seconds = audio_buffer_seconds
        self._lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_id = 0
        self._fps = 0.0
        self._connected = False
        self._sample_rate: int = 8000

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

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

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

    def get_wav_segment(self, start_ts: float, end_ts: float) -> Optional[bytes]:
        """指定時間範囲の音声を WAV バイト列で返す。データがなければ None。"""
        with self._audio_lock:
            segments = [s for ts, s in self._audio_buf if start_ts <= ts <= end_ts]

        if not segments:
            return None

        all_samples = np.concatenate(segments)
        pcm_int16 = (np.clip(all_samples, -1.0, 1.0) * 32767).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm_int16.tobytes())
        return buf.getvalue()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _capture_loop(self):
        while not self._stop_event.is_set():
            try:
                self._run_av()
            except Exception as e:
                logger.warning(f"RTSPCapture error: {e}")
                self._connected = False
                if not self._stop_event.is_set():
                    logger.info(f"Reconnecting in {self.reconnect_interval}s…")
                    time.sleep(self.reconnect_interval)

    def _run_av(self):
        import av
        container = av.open(
            self.rtsp_url,
            options={"rtsp_transport": "tcp", "stimeout": "5000000"},
            timeout=10,
        )
        try:
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            audio_stream = next((s for s in container.streams if s.type == "audio"), None)

            if video_stream is None:
                logger.warning("No video stream in RTSP")
                return

            if audio_stream is not None:
                self._sample_rate = audio_stream.codec_context.sample_rate

            streams_to_decode = [s for s in [video_stream, audio_stream] if s is not None]

            # 音声フォーマット変換: fltp（float32 -1〜1）・モノラルに統一
            resampler = av.AudioResampler(
                format="fltp", layout="mono", rate=self._sample_rate
            ) if audio_stream is not None else None

            # タイムスタンプは time.time() を直接使用する。
            # PTSベース計算（v_wall_start + (pts - first_pts) * time_base）は
            # カメラのPTSクロックドリフトや time_base 不一致で長時間稼働時に
            # 記録時刻がずれる問題があるため採用しない。
            a_chunk_size = int(self._sample_rate * 0.1)  # 100ms 単位
            a_buf = np.array([], dtype=np.float32)
            a_buf_start_ts: Optional[float] = None

            self._connected = True
            logger.info("RTSP stream opened")
            fps_counter = _FPSCounter()

            for packet in container.demux(*streams_to_decode):
                if self._stop_event.is_set():
                    break

                for frame in packet.decode():
                    if frame is None:
                        continue

                    if packet.stream is video_stream:
                        ts = time.time()

                        img = frame.to_ndarray(format="bgr24")
                        self._frame_id += 1
                        f = Frame(data=img, timestamp=ts, frame_id=self._frame_id)
                        with self._lock:
                            self._buffer.append(f)
                        self._fps = fps_counter.tick()

                    elif packet.stream is audio_stream:
                        if frame.pts is None:
                            continue
                        frame_wall_ts = time.time()

                        for resampled in resampler.resample(frame):
                            pcm = resampled.to_ndarray().flatten()
                            if a_buf_start_ts is None:
                                a_buf_start_ts = frame_wall_ts
                            a_buf = np.concatenate([a_buf, pcm])

                        while len(a_buf) >= a_chunk_size:
                            chunk, a_buf = a_buf[:a_chunk_size], a_buf[a_chunk_size:]
                            chunk_ts = a_buf_start_ts
                            a_buf_start_ts += a_chunk_size / self._sample_rate
                            now = time.time()
                            with self._audio_lock:
                                self._audio_buf.append((chunk_ts, chunk))
                                cutoff = now - self._audio_buffer_seconds
                                while self._audio_buf and self._audio_buf[0][0] < cutoff:
                                    self._audio_buf.popleft()
        finally:
            container.close()
            self._connected = False


class _FPSCounter:
    def __init__(self, window: int = 30):
        self._times: deque[float] = deque(maxlen=window)

    def tick(self) -> float:
        self._times.append(time.time())
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0
