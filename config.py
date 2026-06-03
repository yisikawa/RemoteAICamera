"""設定ファイル (config.yaml) 読み込みユーティリティ"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class CameraConfig:
    host: str
    name: str = "cam"

    # Tapo API 認証 (pytapo, KLAP protocol 用)
    api_username: str = "admin"
    api_password: str = ""           # TP-Link ID のパスワード

    # RTSP/ONVIF 認証 (ローカルカメラアカウント用)
    stream_username: str = "admin"
    stream_password: str = ""

    rtsp_stream: int = 1
    onvif_port: int = 2020            # ONVIF ポート (Tapo C520WS: 2020)
    reconnect_interval: int = 5
    motion_poll_interval: int = 2

    # 旧形式との後方互換性
    username: str = ""               # 廃止予定: stream_username を使用
    password: str = ""               # 廃止予定: stream_password を使用
    cloud_password: str = ""         # 廃止予定: api_password を使用

    def __post_init__(self):
        """旧形式 (username/password/cloud_password) から新形式に自動変換"""
        if self.username and not self.stream_username:
            self.stream_username = self.username
        if self.password and not self.stream_password:
            self.stream_password = self.password
        if self.cloud_password and not self.api_password:
            self.api_password = self.cloud_password

    @property
    def rtsp_password(self) -> str:
        return self.stream_password if self.stream_password else ""


@dataclass
class DetectionConfig:
    yolo_model: str = "yolov8s.pt"
    confidence: float = 0.5
    target_classes: list[int] = field(default_factory=list)  # 空 = 全クラス検出
    device: str = "cuda"
    frame_skip: int = 2


@dataclass
class StorageConfig:
    base_dir: str = "data"
    snapshots_dir: str = "data/snapshots"
    clips_dir: str = "data/clips"
    faces_dir: str = "data/faces"
    db_path: str = "data/events.db"
    snapshot_quality: int = 90
    clip_pre_seconds: float = 3.0
    clip_post_seconds: float = 12.0     # ONVIF駆動: 3+12=15秒クリップ
    clip_duration_sec: float = 15.0     # 総クリップ長 (pre + post)
    max_storage_gb: float = 50.0


@dataclass
class LMStudioConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen2.5-vl-7b-instruct-q4_k_m"   # ビジョン+チャット兼用
    timeout: int = 30


@dataclass
class ApiServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:5173",
        "http://localhost:3000",
    ])


@dataclass
class AppConfig:
    cameras: list[CameraConfig]
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    api_server: ApiServerConfig = field(default_factory=ApiServerConfig)


def load_config(path: str = "config.yaml") -> AppConfig:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"config.yaml not found: {cfg_path.resolve()}")
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # cameras: リスト形式、または旧形式 camera: 単体を両対応
    cam_raw = raw.get("cameras") or [raw.get("camera", {})]
    cameras = [CameraConfig(**c) for c in cam_raw]

    det = raw.get("detection", {})
    sto = raw.get("storage", {})
    lms_raw = raw.get("lm_studio", {})
    # 旧キー (vision_model/chat_model) との後方互換
    lms = {k: v for k, v in lms_raw.items() if k not in ("vision_model", "chat_model")}
    if "vision_model" in lms_raw and "model" not in lms:
        lms["model"] = lms_raw["vision_model"]

    api_raw = raw.get("api_server", {})

    return AppConfig(
        cameras=cameras,
        detection=DetectionConfig(**det),
        storage=StorageConfig(**sto),
        lm_studio=LMStudioConfig(**lms) if lms else LMStudioConfig(),
        api_server=ApiServerConfig(**api_raw) if api_raw else ApiServerConfig(),
    )
