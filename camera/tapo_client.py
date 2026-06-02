"""ONVIF による Tapo C520W カメラ接続・イベント取得"""
import time
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from onvif import ONVIFCamera
from zeep.transports import Transport


@dataclass
class MotionEvent:
    timestamp: float
    detection_type: str   # "person" / "vehicle" / "motion"
    raw: dict = field(default_factory=dict)


class TapoClient:
    def __init__(
        self,
        host: str,
        api_username: str = "admin",
        api_password: str = "",
        onvif_port: int = 2020,
    ):
        self.host = host
        self.api_username = api_username
        self.api_password = api_password
        self.onvif_port = onvif_port
        self._cam: Optional[ONVIFCamera] = None
        self._events_service = None
        self._pullpoint_service = None
        self._subscription_ref = None
        self._connected = False

    def connect(self) -> bool:
        """
        ONVIF (ポート 2020) 接続を試みる。
        失敗しても RTSP は独立して動作する。
        """
        try:
            transport = Transport(timeout=5, operation_timeout=5)
            self._cam = ONVIFCamera(
                host=self.host,
                port=self.onvif_port,
                user=self.api_username,
                passwd=self.api_password,
                transport=transport,
            )

            # デバイス情報で疎通確認
            device_service = self._cam.create_devicemgmt_service()
            device_info = device_service.GetDeviceInformation()
            model = getattr(device_info, "Model", "unknown")

            # イベントサービス準備
            self._events_service = self._cam.create_events_service()

            # CreatePullPointSubscription でサブスクリプション作成
            sub_resp = self._events_service.CreatePullPointSubscription(
                {"InitialTerminationTime": "PT10M"}
            )
            self._subscription_ref = sub_resp.SubscriptionReference

            # PullPoint service 取得
            self._pullpoint_service = self._cam.create_pullpoint_service()

            logger.info(
                f"ONVIF connected: {self.host}:{self.onvif_port} (model={model})"
            )
            self._connected = True
            return True
        except Exception as e:
            logger.error(
                f"ONVIF connection failed ({self.host}:{self.onvif_port}): "
                f"{type(e).__name__}: {e}"
            )
            self._connected = False
            return False

    def disconnect(self):
        self._cam = None
        self._events_service = None
        self._pullpoint_service = None
        self._subscription_ref = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._cam is not None

    def get_device_info(self) -> dict:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        device_service = self._cam.create_devicemgmt_service()
        return device_service.GetDeviceInformation()

    def poll_events(self) -> list[MotionEvent]:
        """
        PullPoint Subscription で ONVIF イベント取得。
        最大 1 秒待機、最大 10 件までの最新イベントを返す。
        """
        if not self.is_connected or not self._pullpoint_service:
            return []

        events = []
        try:
            # PullMessages: Timeout='PT1S' (1秒), MessageLimit=10
            msgs = self._pullpoint_service.PullMessages(
                {"MessageLimit": 10, "Timeout": "PT1S"}
            )

            if not msgs or not hasattr(msgs, "NotificationMessage"):
                return events

            for msg in msgs.NotificationMessage:
                detection_type = self._classify_message(msg)
                events.append(
                    MotionEvent(
                        timestamp=time.time(),
                        detection_type=detection_type,
                        raw={"message": str(msg)},
                    )
                )
        except Exception as e:
            logger.debug(f"ONVIF poll error ({self.host}): {e}")

        return events

    def _classify_message(self, message) -> str:
        """ONVIF メッセージから検出種別を判定"""
        msg_str = str(message).lower()

        if "person" in msg_str or "human" in msg_str:
            return "person"
        if "vehicle" in msg_str or "car" in msg_str:
            return "vehicle"

        return "motion"
