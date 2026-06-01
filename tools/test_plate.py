"""
Step 2-4 動作確認: カメラ映像または静止画でナンバープレート認識を確認する

使い方:
  # カメラ映像でリアルタイム確認
  .venv\Scripts\python.exe tools/test_plate.py

  # 静止画で確認
  .venv\Scripts\python.exe tools/test_plate.py --image path/to/car.jpg

  # southCamera を使用
  .venv\Scripts\python.exe tools/test_plate.py --cam 1
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

from config import load_config
from pipeline.detector import YOLODetector
from pipeline.plate_recognizer import PlateRecognizer


VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def get_vehicle_bboxes(det_result) -> list[tuple]:
    boxes = []
    for d in det_result.detections:
        if d.class_id in VEHICLE_CLASSES:
            x1, y1, x2, y2 = d.bbox
            boxes.append((x1, y1, x2, y2, VEHICLE_CLASSES[d.class_id]))
    return boxes


def test_with_image(image_path: str, detector: YOLODetector, recognizer: PlateRecognizer):
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"ERROR: 画像を読み込めません: {image_path}")
        return

    det = detector.detect(frame)
    vehicles = get_vehicle_bboxes(det)
    print(f"車両検出: {len(vehicles)} 台")

    result = recognizer.detect_from_vehicle_crops(frame, vehicles)
    print(f"プレート認識: {len(result.plates)} 件  推論{result.inference_ms:.0f}ms")
    for p in result.plates:
        print(f"  {p.normalized}  (raw='{p.raw_text}'  conf={p.confidence:.3f})")

    out = detector.draw(frame, det)
    out = recognizer.draw(out, result)
    out_path = "data/snapshots/test_plate_result.jpg"
    Path("data/snapshots").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, out)
    print(f"結果画像: {out_path}")
    cv2.imshow("Plate Recognition Test", cv2.resize(out, (960, 540)))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_with_camera(cam_index: int, detector: YOLODetector, recognizer: PlateRecognizer):
    cfg = load_config()
    cam_cfg = cfg.cameras[cam_index]
    rtsp_pw = cam_cfg.stream_password if cam_cfg.stream_password else cam_cfg.password
    rtsp_url = f"rtsp://{cam_cfg.username}:{rtsp_pw}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"ERROR: カメラ接続失敗: {cam_cfg.name}")
        return

    print(f"カメラ起動: {cam_cfg.name}  (q で終了)")

    frame_count = 0
    last_plate_result = None
    last_det_result = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % 5 == 0:   # 5フレームおきに推論
            last_det_result = detector.detect(frame)
            vehicles = get_vehicle_bboxes(last_det_result)
            if vehicles:
                last_plate_result = recognizer.detect_from_vehicle_crops(frame, vehicles)
                if last_plate_result.best:
                    p = last_plate_result.best
                    print(f"[{time.strftime('%H:%M:%S')}] {p.normalized}  "
                          f"conf={p.confidence:.2f}  {p.vehicle_class}  "
                          f"{last_plate_result.inference_ms:.0f}ms")

        display = frame.copy()
        if last_det_result:
            display = detector.draw(display, last_det_result)
        if last_plate_result:
            display = recognizer.draw(display, last_plate_result)

        cv2.imshow(f"Plate Recognition [{cam_cfg.name}]", cv2.resize(display, (960, 540)))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Step 2-4: ナンバープレート認識テスト")
    parser.add_argument("--image", default="", help="テスト画像パス")
    parser.add_argument("--cam", type=int, default=0, help="カメラ番号 (default=0)")
    args = parser.parse_args()

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

    print("PlateRecognizer ロード中 (初回はモデルダウンロード ~300MB)...")
    recognizer = PlateRecognizer(device=cfg.detection.device)
    recognizer.load()
    print("ロード完了")

    if args.image:
        test_with_image(args.image, detector, recognizer)
    else:
        test_with_camera(args.cam, detector, recognizer)


if __name__ == "__main__":
    main()
