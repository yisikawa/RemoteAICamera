"""
Step 2-4/2-5: ナンバープレート認識
YOLOv8 の車両 bbox を切り出し → EasyOCR で文字認識 → 日本プレート形式で正規化
"""
from __future__ import annotations
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from loguru import logger


# 日本のナンバープレート正規化パターン
# 例: "品川３００あ１２３４" / "品川 300 あ 1234" / "品川300あ1234"
# 一-鿿 : CJK漢字  ぁ-ゖ : ひらがな
_JP_PLATE_RE = re.compile(
    r"([一-鿿㐀-䶿]{1,4})"  # 地名漢字 (1〜4文字)
    r"\s*(\d{1,3})"                           # 分類番号
    r"\s*([ぁ-ゖ])"                   # ひらがな1文字
    r"\s*(\d{1,4}(?:[-・]\d{1,4})?)",    # 一連番号 (中点区切りも対応)
    re.UNICODE,
)

# 全角数字→半角
_FULLWIDTH_TABLE = str.maketrans(
    "０１２３４５６７８９", "0123456789"
)


@dataclass
class PlateResult:
    raw_text: str           # OCR生テキスト
    normalized: str         # 正規化後 "品川 300 あ 1234" 形式
    confidence: float
    bbox: tuple[int, int, int, int]  # 車両 bbox (元フレーム座標)
    vehicle_class: str = "car"

    @property
    def is_valid(self) -> bool:
        return bool(self.normalized)


@dataclass
class PlateDetectionResult:
    frame_id: int
    timestamp: float
    plates: list[PlateResult]
    inference_ms: float

    @property
    def best(self) -> Optional[PlateResult]:
        valid = [p for p in self.plates if p.is_valid]
        return max(valid, key=lambda p: p.confidence) if valid else None


class PlateRecognizer:
    """
    EasyOCR による日本語ナンバープレート認識。
    初回 load() 時にモデルをダウンロードする (~300MB)。
    """

    # 車両 bbox の下部何割を切り出すか (プレートは前後にある)
    CROP_RATIO_BOTTOM = 0.60   # 下60%
    CROP_RATIO_TOP    = 0.35   # 上35% (前面プレート用)
    UPSCALE_FACTOR    = 4      # OCR前に何倍に拡大するか
    MIN_CROP_PX       = 20     # これより小さいクロップは処理しない

    def __init__(
        self,
        device: str = "cuda",
        languages: list[str] = None,
    ):
        self.device = device
        self.languages = languages or ["ja", "en"]
        self._reader = None

    def load(self):
        try:
            import easyocr
            gpu = self.device == "cuda"
            self._reader = easyocr.Reader(
                self.languages,
                gpu=gpu,
                verbose=False,
            )
            logger.info(f"PlateRecognizer loaded (GPU={gpu})")
        except Exception as e:
            logger.error(f"Failed to load PlateRecognizer: {e}")
            raise

    def detect_from_vehicle_crops(
        self,
        frame: np.ndarray,
        vehicle_bboxes: list[tuple[int, int, int, int, str]],  # (x1,y1,x2,y2,class)
        frame_id: int = 0,
    ) -> PlateDetectionResult:
        """
        YOLO で検出した車両 bbox リストを受け取り、
        各車両の切り出し画像で OCR を実行してプレートを返す。
        """
        if self._reader is None:
            raise RuntimeError("PlateRecognizer not loaded. Call load() first.")

        t0 = time.perf_counter()
        results = []

        for x1, y1, x2, y2, vclass in vehicle_bboxes:
            crops = self._make_crops(frame, x1, y1, x2, y2)
            for crop in crops:
                if crop is None or crop.size == 0:
                    continue
                plate = self._ocr_crop(crop, (x1, y1, x2, y2), vclass)
                if plate:
                    results.append(plate)
                    break   # 1台につき最初に見つかったプレートを採用

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return PlateDetectionResult(
            frame_id=frame_id,
            timestamp=time.time(),
            plates=results,
            inference_ms=elapsed_ms,
        )

    def _make_crops(self, frame, x1, y1, x2, y2) -> list[np.ndarray]:
        """前面・後面プレートを想定した複数クロップを返す"""
        h = y2 - y1
        crops = []
        # 下部クロップ (後面プレート)
        cy1 = y1 + int(h * (1 - self.CROP_RATIO_BOTTOM))
        crops.append(frame[max(0, cy1):y2, x1:x2])
        # 上部クロップ (前面プレート)
        cy2 = y1 + int(h * self.CROP_RATIO_TOP)
        crops.append(frame[y1:min(frame.shape[0], cy2), x1:x2])
        return crops

    def _ocr_crop(
        self, crop: np.ndarray,
        vehicle_bbox: tuple[int, int, int, int],
        vehicle_class: str,
    ) -> Optional[PlateResult]:
        import cv2
        if crop.shape[0] < self.MIN_CROP_PX or crop.shape[1] < self.MIN_CROP_PX:
            return None

        # 4倍アップスケール + シャープ処理 (小さなプレートのOCR精度向上)
        h, w = crop.shape[:2]
        enlarged = cv2.resize(
            crop, (w * self.UPSCALE_FACTOR, h * self.UPSCALE_FACTOR),
            interpolation=cv2.INTER_LANCZOS4,
        )
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        enlarged = cv2.filter2D(enlarged, -1, kernel)

        try:
            ocr_results = self._reader.readtext(enlarged, detail=1)
        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return None

        if not ocr_results:
            return None

        full_text = " ".join(r[1] for r in ocr_results)
        conf = float(np.mean([r[2] for r in ocr_results]))
        normalized = normalize_jp_plate(full_text)

        # デバッグ: プレート形式に合わなくても生テキストをログ出力
        if full_text.strip():
            logger.debug(f"OCR raw: '{full_text}'  normalized: '{normalized}'  conf={conf:.2f}")

        # 正規化できなくても生テキストがあれば返す (デバッグ・改善に活用)
        return PlateResult(
            raw_text=full_text,
            normalized=normalized,
            confidence=conf,
            bbox=vehicle_bbox,
            vehicle_class=vehicle_class,
        )

    def draw(self, frame: np.ndarray, result: PlateDetectionResult) -> np.ndarray:
        import cv2
        out = frame.copy()
        for plate in result.plates:
            x1, y1, x2, y2 = plate.bbox
            label = f"{plate.normalized} ({plate.confidence:.2f})"
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 200, 255), 2)
            cv2.putText(out, label, (x1, y2 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        return out


def normalize_jp_plate(text: str) -> str:
    """
    OCR テキストから日本のナンバープレート形式を抽出して正規化する。
    認識できない場合は空文字を返す。

    例: "品川３００あ１２３４" → "品川 300 あ 1234"
    """
    if not text:
        return ""

    # 全角数字を半角に変換
    text = text.translate(_FULLWIDTH_TABLE)
    # 全角英数・記号を半角に
    text = unicodedata.normalize("NFKC", text)
    # 不要スペース除去
    text = re.sub(r"\s+", " ", text.strip())

    m = _JP_PLATE_RE.search(text)
    if not m:
        return ""

    region, number, kana, seq = m.groups()
    # 一連番号のハイフン・中点を除去して4桁に
    seq = re.sub(r"[-・]", "", seq).zfill(4)
    return f"{region} {number} {kana} {seq}"
