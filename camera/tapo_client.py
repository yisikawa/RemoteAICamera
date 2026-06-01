"""Tapo C520W カメラ接続・イベント取得クライアント"""
import time
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from pytapo import Tapo


@dataclass
class MotionEvent:
    timestamp: float
    detection_type: str   # "person" / "vehicle" / "motion"
    raw: dict = field(default_factory=dict)


class TapoClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        cloud_password: str = "",
        rtsp_password: str = "",
    ):
        self.host = host
        self.username = username
        self.password = password
        self.cloud_password = cloud_password
        # RTSP 用パスワード (未指定なら password を流用)
        self._rtsp_password = rtsp_password if rtsp_password else password
        self._tapo: Optional[Tapo] = None
        self._connected = False

    def connect(self) -> bool:
        """
        pytapo 接続を試みる。
        新しい C520W は KLAP 認証を使うため cloudPassword が必要な場合がある。
        失敗しても RTSP は独立して動作する。
        """
        try:
            if self.cloud_password:
                # KLAP 対応: cloudPassword を渡す
                self._tapo = Tapo(
                    self.host, self.username, self.password,
                    cloudPassword=self.cloud_password,
                )
            else:
                self._tapo = Tapo(self.host, self.username, self.password)
            info = self._tapo.getBasicInfo()
            model = (
                info.get("device_info", {})
                    .get("basic_info", {})
                    .get("device_model", "unknown")
            )
            logger.info(f"Tapo connected: {self.host} (model={model})")
            self._connected = True
            return True
        except Exception as e:
            err = str(e)
            if "Invalid authentication" in err:
                logger.warning(
                    f"Tapo API 認証失敗 ({self.host}): "
                    "config.yaml の cloud_password にTapoクラウドパスワードを設定してください"
                )
            else:
                logger.error(f"Tapo connection failed ({self.host}): {e}")
            self._connected = False
            return False

    def disconnect(self):
        self._tapo = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._tapo is not None

    def get_device_info(self) -> dict:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        return self._tapo.getBasicInfo()

    def get_motion_detection_config(self) -> dict:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        try:
            return self._tapo.getMotionDetection()
        except Exception as e:
            logger.warning(f"Failed to get motion detection config: {e}")
            return {}

    def poll_events(self) -> list[MotionEvent]:
        if not self.is_connected:
            return []
        events = []
        try:
            raw = self._tapo.getEvents()
            for item in raw if isinstance(raw, list) else []:
                detection_type = self._classify_event(item)
                events.append(MotionEvent(
                    timestamp=time.time(),
                    detection_type=detection_type,
                    raw=item,
                ))
        except Exception as e:
            logger.debug(f"Event poll error: {e}")
        return events

    def _classify_event(self, event: dict) -> str:
        event_str = str(event).lower()
        if "person" in event_str or "human" in event_str:
            return "person"
        if "vehicle" in event_str or "car" in event_str:
            return "vehicle"
        return "motion"

    def get_rtsp_url(self, stream: int = 1) -> str:
        """RTSP URL を組み立てる (stream=1:高画質, 2:低画質)"""
        return f"rtsp://{self.username}:{self._rtsp_password}@{self.host}:554/stream{stream}"
