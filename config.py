"""設定ファイル (config.yaml) 読み込みユーティリティ"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class CameraConfig:
    host: str
    username: str
    password: str                    # Tapo API (pytapo) 用ローカル管理パスワード
    name: str = "cam"
    stream_password: str = ""        # RTSP ストリーム用パスワード (空なら password を流用)
    cloud_password: str = ""         # Tapo クラウドアカウントパスワード (KLAP認証が必要な場合)
    rtsp_stream: int = 1
    reconnect_interval: int = 5
    motion_poll_interval: int = 2

    @property
    def rtsp_password(self) -> str:
        return self.stream_password if self.stream_password else self.password


@dataclass
class DetectionConfig:
    yolo_model: str = "yolov8s.pt"
    confidence: float = 0.5
    target_classes: list[int] = field(default_factory=lambda: [0, 2, 3, 5, 7])
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
    clip_post_seconds: float = 5.0
    max_storage_gb: float = 50.0


@dataclass
class LMStudioConfig:
    base_url: str = "http://localhost:1234/v1"
    vision_model: str = "qwen2-vl-7b"
    chat_model: str = "qwen2.5-7b"
    timeout: int = 30


@dataclass
class AppConfig:
    cameras: list[CameraConfig]
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)


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
    lms = raw.get("lm_studio", {})

    return AppConfig(
        cameras=cameras,
        detection=DetectionConfig(**det),
        storage=StorageConfig(**sto),
        lm_studio=LMStudioConfig(**lms),
    )
