"""
Step 2-1 動作確認: カメラ映像またはテスト画像で顔検出を確認する

使い方:
  # カメラ映像でリアルタイム確認 (config.yaml の最初のカメラを使用)
  .venv\Scripts\python.exe tools/test_face.py

  # 静止画ファイルで確認
  .venv\Scripts\python.exe tools/test_face.py --image path/to/photo.jpg

  # カメラ番号を指定 (0=eastCamera, 1=southCamera ...)
  .venv\Scripts\python.exe tools/test_face.py --cam 1
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from pipeline.face_recognizer import FaceRecognizer


def test_with_image(image_path: str, recognizer: FaceRecognizer):
    import cv2
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"ERROR: 画像を読み込めません: {image_path}")
        return

    result = recognizer.detect(frame)
    print(f"検出顔数: {len(result.faces)}  推論時間: {result.inference_ms:.1f}ms")
    for i, face in enumerate(result.faces):
        print(f"  顔{i+1}: bbox={face.bbox}  confidence={face.confidence:.3f}  "
              f"size={face.largest_side}px  embedding={'あり' if face.embedding is not None else 'なし'}")

    out = recognizer.draw(frame, result)
    out_path = "data/snapshots/test_face_result.jpg"
    Path("data/snapshots").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, out)
    print(f"結果画像保存: {out_path}")
    cv2.imshow("Face Detection Test", out)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_with_camera(cam_index: int, recognizer: FaceRecognizer):
    import cv2
    from config import load_config
    cfg = load_config()
    if cam_index >= len(cfg.cameras):
        print(f"ERROR: カメラ {cam_index} が存在しません (設定: {len(cfg.cameras)} 台)")
        return

    cam_cfg = cfg.cameras[cam_index]
    rtsp_pw = cam_cfg.stream_password if cam_cfg.stream_password else cam_cfg.password
    rtsp_url = f"rtsp://{cam_cfg.username}:{rtsp_pw}@{cam_cfg.host}:554/stream{cam_cfg.rtsp_stream}"
    print(f"カメラ接続中: {cam_cfg.name} ({cam_cfg.host})")

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"ERROR: RTSP接続失敗: {rtsp_url}")
        return

    print("顔検出開始 (q で終了)...")
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("フレーム取得失敗")
            break

        frame_count += 1
        if frame_count % 3 != 0:   # 3フレームおきに推論
            cv2.imshow(f"Face Detection [{cam_cfg.name}]", cv2.resize(frame, (960, 540)))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue

        result = recognizer.detect(frame, frame_id=frame_count)
        if result.has_faces:
            print(f"[{time.strftime('%H:%M:%S')}] 顔検出: {len(result.faces)}人  "
                  f"推論{result.inference_ms:.0f}ms")

        display = recognizer.draw(frame, result)
        cv2.putText(display,
                    f"Faces: {len(result.faces)}  {result.inference_ms:.0f}ms",
                    (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.imshow(f"Face Detection [{cam_cfg.name}]", cv2.resize(display, (960, 540)))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Step 2-1: 顔検出動作確認")
    parser.add_argument("--image", default="", help="テスト画像パス (省略でカメラ使用)")
    parser.add_argument("--cam", type=int, default=0, help="カメラインデックス (default=0)")
    parser.add_argument("--det-size", type=int, default=640, help="検出解像度 (default=640)")
    args = parser.parse_args()

    print("FaceRecognizer ロード中 (初回はモデルダウンロード ~200MB)...")
    recognizer = FaceRecognizer(det_size=(args.det_size, args.det_size))
    recognizer.load()
    print("ロード完了")

    if args.image:
        test_with_image(args.image, recognizer)
    else:
        test_with_camera(args.cam, recognizer)


if __name__ == "__main__":
    main()
