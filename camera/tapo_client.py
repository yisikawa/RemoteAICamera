"""ONVIF による Tapo C520WS カメラ接続・イベント取得"""
import time
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from onvif import ONVIFCamera
from zeep.transports import Transport

_ONVIF_NS      = "http://www.onvif.org/ver10/schema"
_PULLPOINT_NS  = "http://www.onvif.org/ver10/events/wsdl/PullPointSubscription"
_SUB_LIFETIME  = "PT9M"   # サブスクリプション有効期間
_SUB_RENEW_SEC = 8 * 60   # 8分経過で能動的に再作成


@dataclass
class MotionEvent:
    timestamp: float
    detection_type: str   # "person" / "vehicle" / "motion"
    raw: dict = field(default_factory=dict)


class TapoClient:
    def __init__(
        self,
        host: str,
        stream_username: str = "admin",
        stream_password: str = "",
        onvif_port: int = 2020,
    ):
        self.host = host
        self.stream_username = stream_username
        self.stream_password = stream_password
        self.onvif_port = onvif_port
        self._cam: Optional[ONVIFCamera] = None
        self._events_service = None
        self._pullpoint_service = None
        self._sub_created_at: float = 0.0
        self._connected = False

    def connect(self) -> bool:
        try:
            transport = Transport(timeout=5, operation_timeout=5)
            self._cam = ONVIFCamera(
                host=self.host,
                port=self.onvif_port,
                user=self.stream_username,
                passwd=self.stream_password,
                transport=transport,
            )
            device_service = self._cam.create_devicemgmt_service()
            device_info = device_service.GetDeviceInformation()
            model = getattr(device_info, "Model", "unknown")

            self._events_service = self._cam.create_events_service()

            if not self._renew_subscription():
                raise RuntimeError("PullPoint subscription creation failed")

            logger.info(f"ONVIF connected: {self.host}:{self.onvif_port} (model={model})")
            self._connected = True
            return True
        except Exception as e:
            logger.error(
                f"ONVIF connection failed ({self.host}:{self.onvif_port}): "
                f"{type(e).__name__}: {e}"
            )
            self._connected = False
            return False

    def _renew_subscription(self) -> bool:
        try:
            sub = self._events_service.CreatePullPointSubscription(
                {"InitialTerminationTime": _SUB_LIFETIME}
            )
            url = sub.SubscriptionReference.Address._value_1
            self._cam.xaddrs[_PULLPOINT_NS] = url
            self._pullpoint_service = self._cam.create_pullpoint_service()
            self._sub_created_at = time.time()
            logger.debug(f"ONVIF subscription (re)created: {self.host} → {url}")
            return True
        except Exception as e:
            logger.warning(f"ONVIF subscription renewal failed ({self.host}): {e}")
            return False

    def disconnect(self):
        self._cam = None
        self._events_service = None
        self._pullpoint_service = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._cam is not None

    def poll_events(self) -> list[MotionEvent]:
        """
        PullPoint で ONVIF イベント取得（最大1秒ブロック）。
        IsPerson / IsVehicle / IsMotion = true のイベントを返す。
        Tapo C520WS は PropertyOperation="Initialized" を継続送信するため
        Initialized / Changed どちらも検知対象とする。
        """
        if not self.is_connected or self._pullpoint_service is None:
            return []

        if time.time() - self._sub_created_at >= _SUB_RENEW_SEC:
            self._renew_subscription()

        events = []
        try:
            msgs = self._pullpoint_service.PullMessages(
                {"MessageLimit": 10, "Timeout": "PT1S"}
            )
            for msg in list(getattr(msgs, "NotificationMessage", None) or []):
                det = self._classify_message(msg)
                if det:
                    events.append(MotionEvent(
                        timestamp=time.time(),
                        detection_type=det,
                        raw={"message": str(msg)},
                    ))
        except Exception as e:
            err = str(e)
            if any(kw in err for kw in ("SubscriptionNotFound", "Expired", "404", "UnknownToken")):
                logger.info(f"ONVIF subscription expired, renewing: {self.host}")
                self._renew_subscription()
            elif "Timeout" not in err:
                logger.debug(f"ONVIF poll error ({self.host}): {e}")

        return events

    def _classify_message(self, message) -> Optional[str]:
        try:
            element = message.Message._value_1
            if element is None:
                return None
            ns = {"tt": _ONVIF_NS}
            for item in element.findall(".//tt:SimpleItem", ns):
                name  = item.get("Name", "")
                value = str(item.get("Value", "")).lower()
                if value not in ("true", "1"):
                    continue
                if name == "IsPerson":
                    return "person"
                if name == "IsVehicle":
                    return "vehicle"
                if name == "IsMotion":
                    return "motion"
            return None
        except Exception as e:
            logger.debug(f"classify_message error: {e}")
            return None
