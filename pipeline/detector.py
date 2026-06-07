"""YOLOv8 による人体・車両検出"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import numpy as np
from loguru import logger


# COCO 80クラス全名称
COCO_CLASSES: dict[int, str] = {i: name for i, name in enumerate([
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
])}

# COCO class_id → detection_type カテゴリマッピング
CATEGORY_MAP: dict[int, str] = {
    0:  "person",      # person
    1:  "bicycle",     # bicycle
    2:  "car",         # car
    3:  "motorcycle",  # motorcycle
    5:  "car",         # bus
    7:  "car",         # truck
    14: "pet",         # bird
    15: "pet",         # cat
    16: "pet",         # dog
}
# 上記以外は "other"


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]   # x1, y1, x2, y2
    timestamp: float = field(default_factory=time.time)

    @property
    def category(self) -> str:
        return CATEGORY_MAP.get(self.class_id, "other")

    @property
    def is_person(self) -> bool:
        return self.class_id == 0

    @property
    def is_vehicle(self) -> bool:
        return self.class_id in (2, 3, 5, 7)

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = self.bbox
        return frame[y1:y2, x1:x2].copy()


@dataclass
class DetectionResult:
    frame_id: int
    timestamp: float
    detections: list[Detection]
    inference_ms: float

    @property
    def persons(self) -> list[Detection]:
        return [d for d in self.detections if d.is_person]

    @property
    def vehicles(self) -> list[Detection]:
        return [d for d in self.detections if d.is_vehicle]

    @property
    def has_detections(self) -> bool:
        return len(self.detections) > 0


class YOLODetector:
    """
    YOLOv8 推論ラッパー。
    初回呼び出し時にモデルをダウンロード/ロードする。
    """

    def __init__(
        self,
        model_name: str = "yolov8s.pt",
        confidence: float = 0.5,
        target_classes: Optional[list[int]] = None,
        device: str = "cuda",
        models_dir: str = "data/models",
    ):
        self.model_name = model_name
        self.confidence = confidence
        self.target_classes = target_classes or list(COCO_CLASSES.keys())
        self.device = device
        self.models_dir = Path(models_dir)
        self._model = None

    def load(self):
        try:
            from ultralytics import YOLO
            model_path = self.models_dir / self.model_name
            self._model = YOLO(str(model_path) if model_path.exists() else self.model_name)
            # 初回推論でモデルを GPU に転送
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self._model.predict(dummy, device=self.device, verbose=False)
            logger.info(f"YOLOv8 loaded: {self.model_name} on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> DetectionResult:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        t0 = time.perf_counter()
        results = self._model.predict(
            frame,
            device=self.device,
            conf=self.confidence,
            classes=self.target_classes if self.target_classes else None,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append(Detection(
                    class_id=cls_id,
                    class_name=COCO_CLASSES.get(cls_id, str(cls_id)),
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                ))

        return DetectionResult(
            frame_id=frame_id,
            timestamp=time.time(),
            detections=detections,
            inference_ms=elapsed_ms,
        )

    def draw(self, frame: np.ndarray, result: DetectionResult) -> np.ndarray:
        """検出結果をフレームに描画して返す"""
        import cv2
        COLOR_PERSON = (0, 255, 0)
        COLOR_VEHICLE = (0, 128, 255)
        out = frame.copy()
        for d in result.detections:
            color = COLOR_PERSON if d.is_person else COLOR_VEHICLE
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{d.class_name} {d.confidence:.2f}"
            cv2.putText(out, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        fps_text = f"{1000/result.inference_ms:.1f}fps ({result.inference_ms:.0f}ms)"
        cv2.putText(out, fps_text, (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        return out
