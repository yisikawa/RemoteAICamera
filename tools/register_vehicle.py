"""
Step 2-6: 車両登録ツール (色・車種ベース、ナンバー不要)

使い方:
  # カメラで撮影して登録 (Space でキャプチャ)
  .venv\Scripts\python.exe tools/register_vehicle.py --label tanaka_car --owner tanaka --capture

  # 動画ファイルから登録 (一時停止して Space)
  .venv\Scripts\python.exe tools/register_vehicle.py --label tanaka_car --owner tanaka --video data/test_videos/clip.mp4

  # 登録済み一覧
  .venv\Scripts\python.exe tools/register_vehicle.py --list

  # 削除
  .venv\Scripts\python.exe tools/register_vehicle.py --delete tanaka_car
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

from config import load_config
from pipeline.detector import YOLODetector
from pipeline.vehicle_analyzer import VehicleAnalyzer, hsv_to_str, VEHICLE_TYPE_JP
from db.store import EventStore
from db.models import KnownVehicle
from datetime import datetime

VEHICLES_DIR = Path("data/vehicles")
VEHICLE_CLASSES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def _upsert_vehicle(
    store: EventStore,
    label: str,
    owner_label: str,
    color_name: str,
    color_hsv: tuple,
    vehicle_type: str,
    thumbnail_path: str,
    note: str = "",
):
    with store._session() as s:
        v = s.query(KnownVehicle).filter_by(label=label).first()
        if v:
            v.owner_label = owner_label
            v.vehicle_color = color_name
            v.vehicle_color_hsv = hsv_to_str(color_hsv)
            v.vehicle_type = vehicle_type
            v.thumbnail_path = thumbnail_path
            v.note = note
            v.registered_at = datetime.now()
            print(f"  (既存レコードを更新: {label})")
        else:
            s.add(KnownVehicle(
                label=label,
                display_name=label,
                owner_label=owner_label,
                vehicle_color=color_name,
                vehicle_color_hsv=hsv_to_str(color_hsv),
                vehicle_type=vehicle_type,
                thumbnail_path=thumbnail_path,
                note=note,
            ))


def _save_thumbnail(label: str, frame: np.ndarray, bbox: tuple) -> str:
    VEHICLES_DIR.mkdir(parents=True, exist_ok=True)
    x1, y1, x2, y2 = bbox
    crop = frame[y1:y2, x1:x2]
    path = VEHICLES_DIR / f"{label}_thumb.jpg"
    cv2.imwrite(str(path), crop)
    return str(path)


def _run_capture_loop(cap, detector, analyzer, label, owner_label, store):
    """映像ソースから車両を選択してキャプチャするメインループ"""
    frame_count = 0
    last_det = None
    selected_idx = 0   # 複数車両検出時の選択インデックス

    print("車両をクリックまたは [←→] で選択 → [Space] で登録 / [q] でキャンセル")

    while True:
        ret, frame = cap.read()
        if not ret:
            # 動画終端 → 先頭に戻る
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        frame_count += 1
        if frame_count % 4 == 0:
            last_det = detector.detect(frame)

        display = frame.copy()
        vehicles = []
        if last_det:
            vehicles = [d for d in last_det.detections if d.class_id in VEHICLE_CLASSES]

        # 選択インデックスを範囲内に収める
        if vehicles:
            selected_idx = selected_idx % len(vehicles)

        # 全車両を描画
        for i, d in enumerate(vehicles):
            x1, y1, x2, y2 = d.bbox
            vtype = VEHICLE_CLASSES.get(d.class_id, "car")
            ana = analyzer.analyze(frame, d.bbox, vtype)
            color = (0, 255, 0) if i == selected_idx else (100, 100, 100)
            thickness = 3 if i == selected_idx else 1
            cv2.rectangle(display, (x1, y1), (x2, y2), color, thickness)
            label_text = f"[{i}] {ana.vehicle_type_jp} {ana.color_name}"
            cv2.putText(display, label_text, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # ガイドテキスト
        guide = f"車両: {len(vehicles)}台  選択: [{selected_idx}]  Space=登録  q=終了"
        cv2.putText(display, guide, (8, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(display, f"登録名: {label}  オーナー: {owner_label or '未設定'}",
                    (8, display.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("Register Vehicle", cv2.resize(display, (960, 540)))
        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            return False
        if key == ord(" ") and vehicles:
            d = vehicles[selected_idx]
            vtype = VEHICLE_CLASSES.get(d.class_id, "car")
            ana = analyzer.analyze(frame, d.bbox, vtype)
            thumb_path = _save_thumbnail(label, frame, d.bbox)
            _upsert_vehicle(store, label, owner_label,
                            ana.color_name, ana.color_hsv,
                            vtype, thumb_path)
            print(f"\n登録完了: {label}")
            print(f"  車種: {ana.vehicle_type_jp}  色: {ana.color_name}"
                  f"  HSV: {ana.color_hsv}")
            print(f"  サムネイル: {thumb_path}")
            # 確認表示
            crop_disp = frame[d.bbox[1]:d.bbox[3], d.bbox[0]:d.bbox[2]]
            if crop_disp.size > 0:
                cv2.imshow("Registered Vehicle", cv2.resize(crop_disp, (320, 240)))
                cv2.waitKey(2000)
            cv2.destroyAllWindows()
            return True
        if key == 81 or key == ord("a"):   # ← 前の車両
            selected_idx = max(0, selected_idx - 1)
        if key == 83 or key == ord("d"):   # → 次の車両
            selected_idx += 1


def register_from_camera(label, owner_label, cam_index, detector, analyzer, store):
    cfg = load_config()
    cam_cfg = cfg.cameras[cam_index]
    rtsp_pw = cam_cfg.stream_password if cam_cfg.stream_password else cam_cfg.password
    rtsp_url = f"rtsp://{cam_cfg.username}:{rtsp_pw}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"ERROR: カメラ接続失敗: {cam_cfg.name}")
        return
    print(f"カメラ起動: {cam_cfg.name}")
    _run_capture_loop(cap, detector, analyzer, label, owner_label, store)
    cap.release()


def register_from_video(label, owner_label, video_path, detector, analyzer, store):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: 動画を開けません: {video_path}")
        return
    print(f"動画ロード: {video_path}")
    _run_capture_loop(cap, detector, analyzer, label, owner_label, store)
    cap.release()


def list_vehicles(store):
    with store._session() as s:
        vehicles = s.query(KnownVehicle).filter_by(is_active=True).all()
        if not vehicles:
            print("登録済み車両はありません")
            return
        print(f"{'ラベル':<20} {'オーナー':<15} {'車種':<10} {'色':<10} {'通過回数':>6}")
        print("-" * 70)
        for v in vehicles:
            print(f"{v.label:<20} {(v.owner_label or '-'):<15} "
                  f"{(v.vehicle_type or '-'):<10} {(v.vehicle_color or '-'):<10} "
                  f"{v.visit_count:>6}")


def delete_vehicle(store, label):
    with store._session() as s:
        v = s.query(KnownVehicle).filter_by(label=label).first()
        if not v:
            print(f"ERROR: '{label}' は登録されていません")
            return
        if v.thumbnail_path and Path(v.thumbnail_path).exists():
            Path(v.thumbnail_path).unlink()
        s.delete(v)
    print(f"削除完了: {label}")


def main():
    parser = argparse.ArgumentParser(description="車両登録ツール (色・車種ベース)")
    parser.add_argument("--label",  default="", help="登録ラベル (例: tanaka_car)")
    parser.add_argument("--owner",  default="", help="オーナーラベル (KnownPerson.label と対応)")
    parser.add_argument("--capture", action="store_true", help="カメラで撮影して登録")
    parser.add_argument("--video",   default="", help="動画ファイルから登録")
    parser.add_argument("--cam",     type=int, default=0, help="カメラ番号 (default=0)")
    parser.add_argument("--list",    action="store_true", help="登録済み一覧")
    parser.add_argument("--delete",  default="", help="削除するラベル")
    args = parser.parse_args()

    store = EventStore()

    if args.list:
        list_vehicles(store)
        return
    if args.delete:
        delete_vehicle(store, args.delete)
        return

    if not args.label:
        parser.error("--label が必要です")
    if not args.capture and not args.video:
        parser.error("--capture か --video を指定してください")

    cfg = load_config()
    print("YOLOv8 ロード中...")
    detector = YOLODetector(
        model_name=cfg.detection.yolo_model,
        confidence=cfg.detection.confidence,
        target_classes=[2, 3, 5, 7],
        device=cfg.detection.device,
        models_dir=cfg.storage.base_dir + "/models",
    )
    detector.load()
    analyzer = VehicleAnalyzer()

    if args.capture:
        register_from_camera(args.label, args.owner, args.cam, detector, analyzer, store)
    else:
        register_from_video(args.label, args.owner, args.video, detector, analyzer, store)


if __name__ == "__main__":
    main()
