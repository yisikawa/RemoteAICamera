"""カテゴリ別サブカテゴリ分類クライアント（Ollama Qwen2.5-VL）"""
from __future__ import annotations
import base64
from pathlib import Path

import cv2
import httpx
from openai import OpenAI

_MAX_IMAGE_SIZE = 512

SUB_CATEGORIES: dict[str, list[str]] = {
    "person": ["子供", "学生", "成人（男性）", "成人（女性）", "高齢者", "グループ"],
    "car": ["軽自動車", "軽トラック", "セダン/ハッチバック", "SUV", "ミニバン/ワンボックス", "バン（商用）", "トラック", "バス"],
    "motorcycle": ["スクーター", "ビッグスクーター", "ネイキッド", "スポーツ（フルカウル）", "クルーザー（アメリカン）", "オフロード", "アドベンチャー"],
    "bicycle": ["シティサイクル", "電動アシスト", "ロードバイク", "マウンテンバイク", "クロスバイク", "子供用/その他"],
    "pet": ["犬", "猫", "その他動物"],
}


class SubCategoryClient:
    def __init__(self, base_url: str, model: str):
        self._model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key="ollama",
            http_client=httpx.Client(),
        )

    def classify(self, snapshot_path: str, detection_type: str) -> str:
        """スナップショットを見てサブカテゴリを返す。判定不能なら '不明'"""
        candidates = SUB_CATEGORIES.get(detection_type)
        if not candidates:
            return "不明"

        img_b64 = _encode_image(snapshot_path)
        choices_str = "・".join(candidates)
        prompt = (
            f"This is a security camera image taken from an overhead angle. "
            f"A {detection_type} has been detected. "
            f"Classify it into exactly one of the following Japanese categories: {choices_str}・不明\n"
            f"Reply with ONLY the category name, nothing else."
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }],
                max_tokens=30,
                temperature=0.1,
            )
            result = response.choices[0].message.content.strip()
            all_valid = candidates + ["不明"]
            return result if result in all_valid else "不明"
        except Exception:
            return "不明"


def classify_other(detections_json: list | None) -> str:
    """その他カテゴリは detections_json の class_name を直接返す（LLM不使用）"""
    if not detections_json:
        return "不明"
    best = max(detections_json, key=lambda d: d.get("confidence", 0))
    return best.get("class_name") or "不明"


def _encode_image(path: str) -> str:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    h, w = img.shape[:2]
    if max(h, w) > _MAX_IMAGE_SIZE:
        scale = _MAX_IMAGE_SIZE / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode()
