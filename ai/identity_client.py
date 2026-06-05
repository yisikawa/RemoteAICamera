"""Ollama Vision API を使って同カテゴリのスナップショット2枚を比較する"""
from __future__ import annotations
import base64
from dataclasses import dataclass

import cv2
import httpx
from openai import OpenAI

SIMILAR_CANDIDATES_LIMIT = 300  # 比較対象の最大件数（1行で変更可能）
_CROP_PADDING_RATIO = 0.10     # bbox の周囲に追加するパディング（画像短辺の10%）
_MAX_IMAGE_SIZE = 512          # クロップ後のリサイズ上限（px）


@dataclass
class SimilarityResult:
    event_id: str
    started_at: str
    detection_type: str
    snapshot_url: str | None
    verdict: str    # "SAME" or "DIFFERENT"
    reason: str


class IdentityClient:
    def __init__(self, base_url: str, model: str):
        self._model = model
        # httpx 0.28+ が proxies 引数を廃止したため http_client を直接渡して回避
        self._client = OpenAI(
            base_url=base_url,
            api_key="ollama",
            http_client=httpx.Client(),
        )

    def compare(
        self,
        path_a: str,
        path_b: str,
        category: str,
        detections_a: list | None = None,
        detections_b: list | None = None,
    ) -> tuple[str, str]:
        """
        2枚のスナップショットを LLM に送り (verdict, reason) を返す。
        detections_a/b が渡された場合は bbox でクロップしてから送信する。
        verdict: "SAME" | "DIFFERENT"
        reason : LLM による1文の説明
        """
        bbox_a = _best_bbox(detections_a, category)
        bbox_b = _best_bbox(detections_b, category)
        img_a = _encode_image(path_a, bbox=bbox_a)
        img_b = _encode_image(path_b, bbox=bbox_b)

        prompt = (
            f"Compare these two security camera images. "
            f"Are they the same {category}? "
            f"Reply with SAME or DIFFERENT, then explain why in one sentence."
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_a}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b}"}},
                    ],
                }
            ],
            max_tokens=120,
            temperature=0.1,
        )

        text = response.choices[0].message.content.strip()
        upper = text.upper()
        if upper.startswith("SAME"):
            verdict = "SAME"
            reason = text[4:].strip().lstrip(".,: ")
        else:
            verdict = "DIFFERENT"
            reason = text[9:].strip().lstrip(".,: ") if upper.startswith("DIFFERENT") else text

        return verdict, reason


def _best_bbox(detections: list | None, category: str) -> list | None:
    """detections_json から同カテゴリで最高 confidence の bbox を返す"""
    if not detections:
        return None
    matches = [d for d in detections if d.get("category") == category]
    if not matches:
        matches = detections  # カテゴリ一致なしの場合は全検出からフォールバック
    best = max(matches, key=lambda d: d.get("confidence", 0))
    bbox = best.get("bbox")
    return bbox if bbox and len(bbox) == 4 else None


def _encode_image(path: str, bbox: list | None = None) -> str:
    """
    画像を読み込み、bbox があればクロップ → リサイズ → base64 を返す。
    bbox がない場合はリサイズのみ行う。
    """
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")

    if bbox:
        h, w = img.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        pad = int(min(w, h) * _CROP_PADDING_RATIO)
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        img = img[y1:y2, x1:x2]

    h, w = img.shape[:2]
    if max(h, w) > _MAX_IMAGE_SIZE:
        scale = _MAX_IMAGE_SIZE / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode()
