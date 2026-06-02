"""
ONVIF による Tapo C520W 接続テスト

使い方:
  pip install onvif-zeep
  .venv\Scripts\python.exe tools/test_onvif_auth.py
  .venv\Scripts\python.exe tools/test_onvif_auth.py --all
"""
import sys
import socket
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config


DEFAULT_ONVIF_PORTS = [2020, 80, 8080, 10080, 8888]


def is_tcp_open(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as e:
        return False, str(e)


def field(obj, name: str, default="N/A"):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def list_len(obj, name: str) -> int:
    value = field(obj, name, [])
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 1


def test_onvif_auth(test_all=False, camera_name=None, ports=None, timeout=3.0):
    """ONVIF 認証テスト"""
    try:
        from onvif import ONVIFCamera
        from zeep.transports import Transport
    except ImportError:
        print("[ERROR] onvif-zeep is not installed")
        print("   pip install onvif-zeep")
        return

    cfg = load_config()
    ports_to_try = ports or DEFAULT_ONVIF_PORTS

    print("=" * 70)
    print("ONVIF 認証テスト (Tapo C520W)")
    print("=" * 70)

    if camera_name:
        cameras_to_test = [c for c in cfg.cameras if c.name == camera_name]
        if not cameras_to_test:
            print(f"\n[ERROR] Camera not found: {camera_name}")
            return
    elif test_all:
        cameras_to_test = cfg.cameras
    else:
        cameras_to_test = cfg.cameras[:1]
        if len(cfg.cameras) > 1:
            print(f"\n[INFO] Testing only: {cameras_to_test[0].name}")
            print("       Use --all to test every camera.\n")

    for cam_cfg in cameras_to_test:
        print(f"\n[{cam_cfg.name}] {cam_cfg.host}")
        print(f"  stream_username: {cam_cfg.stream_username}")
        print(f"  stream_password: {'*' * len(cam_cfg.stream_password)}")
        print(f"  ports: {', '.join(str(p) for p in ports_to_try)}")

        cam = None
        connected_port = None

        for port in ports_to_try:
            print(f"  -> TCP probe port {port}...", end=" ")
            open_ok, open_err = is_tcp_open(cam_cfg.host, port, timeout)
            if not open_ok:
                print(f"closed/timeout ({open_err})")
                continue

            print("open")
            try:
                print(f"     ONVIF login on port {port}...", end=" ")
                zeep_transport = Transport(
                    timeout=timeout,
                    operation_timeout=timeout,
                )
                cam = ONVIFCamera(
                    host=cam_cfg.host,
                    port=port,
                    user=cam_cfg.stream_username,
                    passwd=cam_cfg.stream_password,
                    transport=zeep_transport,
                )
                connected_port = port
                print("OK")
                break
            except Exception as e:
                cam = None
                print(f"FAILED ({type(e).__name__}: {e})")

        if not cam:
            print(f"  [FAILED] ONVIF connection failed on all ports: {ports_to_try}")
            continue

        print(f"  [OK] ONVIF connected on port {connected_port}")

        try:
            device_service = cam.create_devicemgmt_service()
            device_info = device_service.GetDeviceInformation()
            print(f"     Manufacturer: {field(device_info, 'Manufacturer')}")
            print(f"     Model: {field(device_info, 'Model')}")
            print(f"     Firmware: {field(device_info, 'FirmwareVersion')}")
        except Exception as e:
            print(f"     Device info failed: {type(e).__name__}: {e}")

        try:
            events_service = cam.create_events_service()
            event_props = events_service.GetEventProperties()
            print("  [OK] Events service available")
            print(
                "     Topic namespace locations: "
                f"{list_len(event_props, 'TopicNamespaceLocation')}"
            )
            print(
                "     Message content filters: "
                f"{list_len(event_props, 'MessageContentFilterDialect')}"
            )
        except Exception as e:
            print(f"     Events service failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ONVIF 認証テスト")
    parser.add_argument("--all", action="store_true", help="全カメラをテスト（デフォルト: 最初のカメラのみ）")
    parser.add_argument("--camera", type=str, help="特定のカメラ名を指定")
    parser.add_argument(
        "--ports",
        type=str,
        default=",".join(str(p) for p in DEFAULT_ONVIF_PORTS),
        help="試行するONVIFポートのカンマ区切りリスト",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="各接続のタイムアウト秒")
    args = parser.parse_args()

    selected_ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]
    test_onvif_auth(
        test_all=args.all,
        camera_name=args.camera,
        ports=selected_ports,
        timeout=args.timeout,
    )
