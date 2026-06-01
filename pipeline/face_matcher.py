"""
Step 2-3: 登録済み顔エンコーディングとの照合
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class MatchResult:
    label: str
    similarity: float
    is_known: bool = True


class FaceMatcher:
    """
    data/faces/*.npy を読み込み、検出された顔埋め込みと照合する。
    reload() を呼ぶと登録内容をホットリロードできる。
    """

    def __init__(
        self,
        faces_dir: str = "data/faces",
        threshold: float = 0.45,
    ):
        self.faces_dir = Path(faces_dir)
        self.threshold = threshold
        self._encodings: dict[str, np.ndarray] = {}
        self._loaded_at: float = 0.0

    def load(self):
        """faces_dir から全エンコーディングを読み込む"""
        self._encodings = {}
        for npy in self.faces_dir.glob("*.npy"):
            label = npy.stem
            try:
                self._encodings[label] = np.load(str(npy))
            except Exception as e:
                logger.warning(f"Failed to load encoding {npy}: {e}")
        self._loaded_at = time.time()
        logger.info(f"FaceMatcher loaded {len(self._encodings)} persons: "
                    f"{list(self._encodings.keys())}")

    def reload_if_stale(self, max_age_sec: float = 30.0):
        """一定時間ごとに自動リロード (新規登録をリアルタイム反映)"""
        if time.time() - self._loaded_at > max_age_sec:
            self.load()

    @property
    def known_labels(self) -> list[str]:
        return list(self._encodings.keys())

    def match(self, embedding: np.ndarray) -> Optional[MatchResult]:
        """
        埋め込みベクトルを全登録顔と比較し、最も類似度の高いラベルを返す。
        threshold 未満なら None を返す。
        """
        if not self._encodings or embedding is None:
            return None

        best_label = None
        best_sim = -1.0

        for label, known_emb in self._encodings.items():
            sim = self._cosine_similarity(embedding, known_emb)
            if sim > best_sim:
                best_sim = sim
                best_label = label

        if best_sim >= self.threshold:
            return MatchResult(label=best_label, similarity=best_sim)
        return None

    def match_all(self, embeddings: list[np.ndarray]) -> list[Optional[MatchResult]]:
        """複数の埋め込みをまとめて照合"""
        return [self.match(emb) for emb in embeddings]

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
