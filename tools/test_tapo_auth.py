"""
Tapo API 認証テスト（ログインのみ）

使い方:
  .venv\Scripts\python.exe tools/test_tapo_auth.py              # 最初のカメラだけテスト
  .venv\Scripts\python.exe tools/test_tapo_auth.py --all        # 全カメラテスト
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from camera.tapo_client import TapoClient


def test_auth(test_all=False, camera_name=None):
    """Tapo API 認証テスト"""
    cfg = load_config()

    print("=" * 70)
    print("Tapo API 認証テスト")
    print("=" * 70)

    # 対象カメラ選択
    if camera_name:
        cameras_to_test = [c for c in cfg.cameras if c.name == camera_name]
        if not cameras_to_test:
            print(f"\n❌ Camera not found: {camera_name}")
            return
    elif test_all:
        cameras_to_test = cfg.cameras
    else:
        # デフォルト: 最初のカメラだけ
        cameras_to_test = cfg.cameras[:1]
        if len(cfg.cameras) > 1:
            print(f"\n⚠️  テスト対象: {cameras_to_test[0].name} のみ")
            print(f"   全カメラテストは: python tools/test_tapo_auth.py --all\n")

    for cam_cfg in cameras_to_test:
        print(f"\n[{cam_cfg.name}] {cam_cfg.host}")
        print(f"  api_username: {cam_cfg.api_username}")
        print(f"  api_password: {'*' * len(cam_cfg.api_password)}")
        print(f"  stream_username: {cam_cfg.stream_username}")
        print(f"  stream_password: {'*' * len(cam_cfg.stream_password)}")

        tapo = TapoClient(
            host=cam_cfg.host,
            api_username=cam_cfg.api_username,
            api_password=cam_cfg.api_password,
        )

        try:
            print("  → Connecting...")
            if tapo.connect():
                print(f"  ✅ SUCCESS: Tapo API connected")

                # 簡単な API呼び出しテスト
                try:
                    info = tapo.get_device_info()
                    print(f"     Model: {info.get('model', 'N/A')}")
                except Exception as e:
                    print(f"     (Device info fetch failed: {e})")
            else:
                print(f"  ❌ FAILED: Tapo API connection failed")
        except Exception as e:
            print(f"  ❌ ERROR: {e}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tapo API 認証テスト")
    parser.add_argument("--all", action="store_true", help="全カメラをテスト（デフォルト: 最初のカメラのみ）")
    parser.add_argument("--camera", type=str, help="特定のカメラ名を指定")
    args = parser.parse_args()

    test_auth(test_all=args.all, camera_name=args.camera)
