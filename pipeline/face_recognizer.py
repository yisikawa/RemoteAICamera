"""
InsightFace による顔検出・顔埋め込み抽出。
Step 2-1: 顔検出のみ (照合は Step 2-3 で追加)
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]   # x1, y1, x2, y2
    confidence: float
    embedding: Optional[np.ndarray] = None   # 512次元 (buffalo_l)
    landmarks: Optional[np.ndarray] = None   # 5点ランドマーク

    def crop(self, frame: np.ndarray, margin: float = 0.2) -> np.ndarray:
        """マージン付きで顔領域を切り出す"""
        x1, y1, x2, y2 = self.bbox
        h, w = frame.shape[:2]
        mw = int((x2 - x1) * margin)
        mh = int((y2 - y1) * margin)
        x1 = max(0, x1 - mw)
        y1 = max(0, y1 - mh)
        x2 = min(w, x2 + mw)
        y2 = min(h, y2 + mh)
        return frame[y1:y2, x1:x2].copy()

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)

    @property
    def largest_side(self) -> int:
        x1, y1, x2, y2 = self.bbox
        return max(x2 - x1, y2 - y1)


@dataclass
class FaceDetectionResult:
    frame_id: int
    timestamp: float
    faces: list[FaceDetection]
    inference_ms: float

    @property
    def has_faces(self) -> bool:
        return len(self.faces) > 0

    @property
    def largest_face(self) -> Optional[FaceDetection]:
        return max(self.faces, key=lambda f: f.area) if self.faces else None


class FaceRecognizer:
    """
    InsightFace buffalo_l モデルによる顔検出・埋め込み抽出ラッパー。
    初回 load() 時にモデルを自動ダウンロードする (~200MB)。
    """

    MIN_FACE_SIZE = 40        # これより小さい顔は無視 (px)
    SIMILARITY_THRESHOLD = 0.45  # 顔照合の類似度閾値 (Step 2-3 で使用)

    def __init__(
        self,
        model_pack: str = "buffalo_l",
        device: str = "cuda",
        det_size: tuple[int, int] = (640, 640),
        models_dir: str = "data/models",
    ):
        self.model_pack = model_pack
        self.device = device
        self.det_size = det_size
        self.models_dir = Path(models_dir)
        self._app = None

    def load(self):
        # Windows: PyTorch が持つ CUDA/cuDNN DLL を onnxruntime に認識させる
        # (onnxruntime_providers_cuda.dll は cudart/cublas/cudnn を動的ロードするため)
        self._add_torch_dll_directory()

        try:
            from insightface.app import FaceAnalysis

            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if self.device == "cuda"
                else ["CPUExecutionProvider"]
            )
            ctx_id = 0 if self.device == "cuda" else -1
            self._app = FaceAnalysis(
                name=self.model_pack,
                root=str(self.models_dir),
                providers=providers,
            )
            self._app.prepare(ctx_id=ctx_id, det_size=self.det_size)

            # 実際に使われた provider を確認
            used = self._app.models.get("detection", None)
            logger.info(f"FaceRecognizer loaded: {self.model_pack} on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load FaceRecognizer: {e}")
            raise

    @staticmethod
    def _add_torch_dll_directory():
        """Windows 専用: PyTorch の lib フォルダを DLL 検索パスに追加する"""
        import os
        if os.name != "nt":
            return
        try:
            import torch
            lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
            if os.path.isdir(lib_path):
                os.add_dll_directory(lib_path)
                logger.debug(f"Added DLL directory: {lib_path}")
        except Exception as e:
            logger.warning(f"Could not add torch DLL directory: {e}")

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> FaceDetectionResult:
        if self._app is None:
            raise RuntimeError("FaceRecognizer not loaded. Call load() first.")

        t0 = time.perf_counter()
        raw_faces = self._app.get(frame)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        faces = []
        for f in raw_faces:
            x1, y1, x2, y2 = map(int, f.bbox)
            size = max(x2 - x1, y2 - y1)
            if size < self.MIN_FACE_SIZE:
                continue
            faces.append(FaceDetection(
                bbox=(x1, y1, x2, y2),
                confidence=float(f.det_score),
                embedding=f.embedding.copy() if f.embedding is not None else None,
                landmarks=f.kps.copy() if f.kps is not None else None,
            ))

        return FaceDetectionResult(
            frame_id=frame_id,
            timestamp=time.time(),
            faces=faces,
            inference_ms=elapsed_ms,
        )

    def draw(self, frame: np.ndarray, result: FaceDetectionResult) -> np.ndarray:
        """検出結果をフレームに描画して返す"""
        import cv2
        COLOR = (255, 80, 80)
        out = frame.copy()
        for face in result.faces:
            x1, y1, x2, y2 = face.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), COLOR, 2)
            label = f"face {face.confidence:.2f}"
            cv2.putText(out, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR, 1)
            if face.landmarks is not None:
                for pt in face.landmarks:
                    cv2.circle(out, (int(pt[0]), int(pt[1])), 2, (0, 255, 255), -1)
        return out

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
