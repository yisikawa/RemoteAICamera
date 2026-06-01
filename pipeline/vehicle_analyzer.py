"""
Step 2-6: 車両色抽出・車種分類・既知車両照合
ナンバープレートなしで色+車種+サムネイルで車両を管理する
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from loguru import logger


# HSV 色名マッピング (日本語)
# (H範囲, S閾値, V閾値) → 色名
_COLOR_MAP = [
    # 無彩色を先に判定
    {"name": "白",        "v_min": 0.75, "s_max": 0.25},
    {"name": "黒",        "v_max": 0.25},
    {"name": "シルバー",  "v_min": 0.25, "v_max": 0.75, "s_max": 0.25},
    # 有彩色 (H=0〜180 in OpenCV)
    {"name": "赤",        "h_min": 0,   "h_max": 12,  "s_min": 0.3},
    {"name": "橙",        "h_min": 12,  "h_max": 22,  "s_min": 0.3},
    {"name": "黄",        "h_min": 22,  "h_max": 38,  "s_min": 0.3},
    {"name": "黄緑",      "h_min": 38,  "h_max": 55,  "s_min": 0.3},
    {"name": "緑",        "h_min": 55,  "h_max": 85,  "s_min": 0.3},
    {"name": "水色",      "h_min": 85,  "h_max": 100, "s_min": 0.3},
    {"name": "青",        "h_min": 100, "h_max": 130, "s_min": 0.3},
    {"name": "紺",        "h_min": 100, "h_max": 130, "s_min": 0.3, "v_max": 0.35},
    {"name": "紫",        "h_min": 130, "h_max": 155, "s_min": 0.3},
    {"name": "ピンク",    "h_min": 155, "h_max": 175, "s_min": 0.3},
    {"name": "赤",        "h_min": 175, "h_max": 180, "s_min": 0.3},  # 赤の折り返し
]

VEHICLE_TYPE_JP = {
    "bicycle":    "自転車",
    "car":        "乗用車",
    "motorcycle": "バイク",
    "bus":        "バス",
    "truck":      "トラック",
}


@dataclass
class VehicleAnalysis:
    vehicle_type: str          # car / motorcycle / bus / truck
    vehicle_type_jp: str       # 乗用車 / バイク 等
    color_name: str            # 黒 / 白 / シルバー 等
    color_hsv: tuple[float, float, float]  # (H, S, V) 正規化値
    bbox: tuple[int, int, int, int]
    confidence: float = 0.0


@dataclass
class VehicleMatch:
    label: str
    display_name: str
    owner_label: str
    color_name: str
    vehicle_type: str
    score: float               # 色類似度 (0〜1)


class VehicleAnalyzer:
    """
    YOLOv8 検出済み車両 bbox から色・車種を抽出し、
    登録済み車両との照合を行う。
    """

    COLOR_SIMILARITY_THRESHOLD = 0.75   # 色照合スコア閾値

    def analyze(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        vehicle_class: str,
    ) -> VehicleAnalysis:
        import cv2
        x1, y1, x2, y2 = bbox
        crop = frame[y1:y2, x1:x2]

        color_name, hsv = self._extract_dominant_color(crop)

        return VehicleAnalysis(
            vehicle_type=vehicle_class,
            vehicle_type_jp=VEHICLE_TYPE_JP.get(vehicle_class, vehicle_class),
            color_name=color_name,
            color_hsv=hsv,
            bbox=bbox,
        )

    def _extract_dominant_color(
        self, crop: np.ndarray
    ) -> tuple[str, tuple[float, float, float]]:
        import cv2
        if crop is None or crop.size == 0:
            return "不明", (0.0, 0.0, 0.0)

        # 上部20%はボンネット・ルーフが多いので使用しない
        h = crop.shape[0]
        roi = crop[int(h * 0.1): int(h * 0.85)]
        if roi.size == 0:
            roi = crop

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # k-means で支配色を求める (k=3)
        pixels = hsv.reshape(-1, 3).astype(np.float32)
        if len(pixels) < 10:
            return "不明", (0.0, 0.0, 0.0)

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        k = min(3, len(pixels))
        _, labels, centers = cv2.kmeans(
            pixels, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS
        )

        # 最多ピクセル数のクラスタを支配色とする
        counts = np.bincount(labels.flatten())
        dominant = centers[np.argmax(counts)]
        h_val = float(dominant[0]) / 180.0
        s_val = float(dominant[1]) / 255.0
        v_val = float(dominant[2]) / 255.0

        color_name = self._hsv_to_name(h_val * 180, s_val, v_val)
        return color_name, (round(h_val, 3), round(s_val, 3), round(v_val, 3))

    @staticmethod
    def _hsv_to_name(h: float, s: float, v: float) -> str:
        """OpenCV HSV値 (H:0-180, S:0-1, V:0-1) → 色名"""
        # 無彩色判定
        if v > 0.75 and s < 0.25:
            return "白"
        if v < 0.25:
            return "黒"
        if v >= 0.25 and s < 0.25:
            if v > 0.55:
                return "シルバー"
            return "グレー"
        # 紺は青より先に判定
        if 100 <= h <= 130 and v < 0.35 and s >= 0.3:
            return "紺"
        # 有彩色
        for entry in _COLOR_MAP:
            if "h_min" not in entry:
                continue
            if not (entry["h_min"] <= h < entry["h_max"]):
                continue
            if s < entry.get("s_min", 0):
                continue
            if v > entry.get("v_max", 999):
                continue
            return entry["name"]
        return "その他"

    # ------------------------------------------------------------------ #
    # 既知車両照合                                                          #
    # ------------------------------------------------------------------ #

    def match(
        self,
        analysis: VehicleAnalysis,
        known_vehicles: list,   # KnownVehicle ORM オブジェクトのリスト
    ) -> Optional[VehicleMatch]:
        """色+車種で既知車両と照合し、最もスコアの高いものを返す"""
        best = None
        best_score = 0.0

        for kv in known_vehicles:
            if not kv.is_active:
                continue
            # 車種が違えばスキップ
            if kv.vehicle_type and kv.vehicle_type != analysis.vehicle_type:
                continue
            # 色名が完全一致なら高スコア、近似色なら部分スコア
            score = self._color_score(
                analysis.color_name, analysis.color_hsv,
                kv.vehicle_color, kv.vehicle_color_hsv,
            )
            if score > best_score:
                best_score = score
                best = VehicleMatch(
                    label=kv.label,
                    display_name=kv.display_name or kv.label,
                    owner_label=kv.owner_label or "",
                    color_name=kv.vehicle_color or "",
                    vehicle_type=kv.vehicle_type or "",
                    score=score,
                )

        if best and best_score >= self.COLOR_SIMILARITY_THRESHOLD:
            return best
        return None

    @staticmethod
    def _color_score(
        name_a: str, hsv_a: tuple,
        name_b: str, hsv_b_str: Optional[str],
    ) -> float:
        # 色名完全一致 → 0.9
        if name_a == name_b:
            base = 0.9
        # 類似色グループ (黒系・白系・シルバー系)
        elif {name_a, name_b} <= {"黒", "グレー"} or \
             {name_a, name_b} <= {"白", "シルバー"}:
            base = 0.6
        else:
            base = 0.0

        # HSV 数値でさらに微調整
        if hsv_b_str and base > 0:
            try:
                hsv_b = tuple(float(x) for x in hsv_b_str.split(","))
                h_diff = abs(hsv_a[0] - hsv_b[0])
                v_diff = abs(hsv_a[2] - hsv_b[2])
                base += max(0.0, 0.1 - h_diff * 0.5 - v_diff * 0.3)
            except Exception:
                pass

        return min(base, 1.0)


def hsv_to_str(hsv: tuple[float, float, float]) -> str:
    return f"{hsv[0]:.3f},{hsv[1]:.3f},{hsv[2]:.3f}"
