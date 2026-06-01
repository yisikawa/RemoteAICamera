"""
Step 2-2: 顔登録ツール

画像ファイルまたはカメラのスナップショットから顔エンコーディングを登録する。

使い方:
  # 画像ファイルから登録
  .venv\Scripts\python.exe tools/register_face.py --label "tanaka" --image photo.jpg

  # カメラで撮影して登録 (Spaceキーでキャプチャ)
  .venv\Scripts\python.exe tools/register_face.py --label "tanaka" --capture

  # 登録済み一覧を表示
  .venv\Scripts\python.exe tools/register_face.py --list

  # 登録を削除
  .venv\Scripts\python.exe tools/register_face.py --delete "tanaka"
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from loguru import logger

from config import load_config
from pipeline.face_recognizer import FaceRecognizer
from db.store import EventStore
from db.models import KnownPerson
from datetime import datetime


FACES_DIR = Path("data/faces")


def save_encoding(label: str, embedding: np.ndarray, thumbnail: np.ndarray) -> tuple[str, str]:
    """エンコーディングと顔サムネイルを保存してパスを返す"""
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    enc_path = FACES_DIR / f"{label}.npy"
    thumb_path = FACES_DIR / f"{label}_thumb.jpg"
    np.save(str(enc_path), embedding)
    cv2.imwrite(str(thumb_path), thumbnail)
    return str(enc_path), str(thumb_path)


def load_all_encodings() -> dict[str, np.ndarray]:
    """登録済みの全エンコーディングを読み込む"""
    encodings = {}
    for npy in FACES_DIR.glob("*.npy"):
        label = npy.stem
        encodings[label] = np.load(str(npy))
    return encodings


def register_from_image(label: str, image_path: str, recognizer: FaceRecognizer, store: EventStore):
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"ERROR: 画像を読み込めません: {image_path}")
        return False

    result = recognizer.detect(frame)
    if not result.has_faces:
        print("ERROR: 顔が検出されませんでした。別の画像を試してください。")
        return False

    if len(result.faces) > 1:
        print(f"WARNING: {len(result.faces)} 人の顔を検出しました。最大の顔を使用します。")

    face = result.largest_face
    if face.embedding is None:
        print("ERROR: 顔の埋め込みを取得できませんでした。")
        return False

    thumbnail = face.crop(frame)
    enc_path, thumb_path = save_encoding(label, face.embedding, thumbnail)

    # DB に登録
    _upsert_person(store, label, enc_path, thumb_path)

    print(f"登録完了: {label}")
    print(f"  エンコーディング: {enc_path}")
    print(f"  サムネイル:       {thumb_path}")
    print(f"  信頼度:           {face.confidence:.3f}")

    # 確認ウィンドウ
    display = recognizer.draw(frame, result)
    cv2.putText(display, f"Registered: {label}", (8, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    cv2.imshow("Register Face", cv2.resize(display, (960, 540)))
    cv2.waitKey(2000)
    cv2.destroyAllWindows()
    return True


def register_from_camera(label: str, cam_index: int, recognizer: FaceRecognizer, store: EventStore):
    cfg = load_config()
    if cam_index >= len(cfg.cameras):
        print(f"ERROR: カメラ {cam_index} が存在しません")
        return False

    cam_cfg = cfg.cameras[cam_index]
    rtsp_pw = cam_cfg.stream_password if cam_cfg.stream_password else cam_cfg.password
    rtsp_url = f"rtsp://{cam_cfg.username}:{rtsp_pw}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"ERROR: カメラ接続失敗: {cam_cfg.name}")
        return False

    print(f"カメラ起動: {cam_cfg.name}")
    print("顔をカメラに向けて [Space] でキャプチャ / [q] でキャンセル")

    last_result = None
    frame_count = 0
    registered = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % 3 == 0:
            last_result = recognizer.detect(frame)

        display = recognizer.draw(frame, last_result) if last_result else frame.copy()
        face_count = len(last_result.faces) if last_result else 0
        color = (0, 255, 0) if face_count == 1 else (0, 100, 255)
        status = "Space: キャプチャ" if face_count == 1 else (
            "顔が検出されません" if face_count == 0 else f"顔が{face_count}人います (1人にしてください)")
        cv2.putText(display, status, (8, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(display, f"登録名: {label}", (8, display.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.imshow(f"Register Face [{cam_cfg.name}]", cv2.resize(display, (960, 540)))

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" ") and last_result and len(last_result.faces) == 1:
            face = last_result.faces[0]
            if face.embedding is None:
                print("ERROR: 埋め込みを取得できませんでした。再試行してください。")
                continue
            thumbnail = face.crop(frame)
            enc_path, thumb_path = save_encoding(label, face.embedding, thumbnail)
            _upsert_person(store, label, enc_path, thumb_path)
            print(f"\n登録完了: {label}  信頼度={face.confidence:.3f}")
            cv2.putText(display, "登録しました!", (display.shape[1]//2 - 120, display.shape[0]//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
            cv2.imshow(f"Register Face [{cam_cfg.name}]", cv2.resize(display, (960, 540)))
            cv2.waitKey(2000)
            registered = True
            break

    cap.release()
    cv2.destroyAllWindows()
    return registered


def _upsert_person(store: EventStore, label: str, enc_path: str, thumb_path: str):
    with store._session() as s:
        person = s.query(KnownPerson).filter_by(label=label).first()
        if person:
            person.encoding_path = enc_path
            person.thumbnail_path = thumb_path
            person.registered_at = datetime.now()
            print(f"  (既存レコードを更新: {label})")
        else:
            s.add(KnownPerson(
                label=label,
                display_name=label,
                encoding_path=enc_path,
                thumbnail_path=thumb_path,
            ))


def list_persons(store: EventStore):
    with store._session() as s:
        persons = s.query(KnownPerson).filter_by(is_active=True).all()
        if not persons:
            print("登録済み人物はいません")
            return
        print(f"{'ラベル':<20} {'登録日時':<22} {'通過回数':>6}  エンコーディング")
        print("-" * 80)
        for p in persons:
            enc_exists = "✓" if p.encoding_path and Path(p.encoding_path).exists() else "✗"
            print(f"{p.label:<20} {str(p.registered_at)[:19]:<22} {p.visit_count:>6}  {enc_exists}")


def delete_person(store: EventStore, label: str):
    with store._session() as s:
        person = s.query(KnownPerson).filter_by(label=label).first()
        if not person:
            print(f"ERROR: '{label}' は登録されていません")
            return
        # ファイル削除
        for path in [person.encoding_path, person.thumbnail_path]:
            if path and Path(path).exists():
                Path(path).unlink()
        s.delete(person)
    print(f"削除完了: {label}")


def main():
    parser = argparse.ArgumentParser(description="Step 2-2: 顔登録ツール")
    parser.add_argument("--label", default="", help="登録名 (英数字推奨)")
    parser.add_argument("--image", default="", help="登録する画像ファイルパス")
    parser.add_argument("--capture", action="store_true", help="カメラで撮影して登録")
    parser.add_argument("--cam", type=int, default=0, help="使用するカメラ番号 (default=0)")
    parser.add_argument("--list", action="store_true", help="登録済み一覧を表示")
    parser.add_argument("--delete", default="", help="指定ラベルを削除")
    args = parser.parse_args()

    store = EventStore()

    if args.list:
        list_persons(store)
        return

    if args.delete:
        delete_person(store, args.delete)
        return

    if not args.label:
        parser.error("--label が必要です (例: --label tanaka)")

    print("FaceRecognizer ロード中...")
    recognizer = FaceRecognizer()
    recognizer.load()

    if args.image:
        register_from_image(args.label, args.image, recognizer, store)
    elif args.capture:
        register_from_camera(args.label, args.cam, recognizer, store)
    else:
        parser.error("--image か --capture のどちらかを指定してください")


if __name__ == "__main__":
    main()
