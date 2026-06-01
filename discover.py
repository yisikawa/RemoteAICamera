"""
Tapo カメラの IP アドレスを自動検出するユーティリティ。

使い方:
    .venv\Scripts\python.exe discover.py
    .venv\Scripts\python.exe discover.py --subnet 192.168.0   # サブネット指定
    .venv\Scripts\python.exe discover.py --password mypass     # 接続テストも実行
"""
import argparse
import socket
import subprocess
import sys
import concurrent.futures
from dataclasses import dataclass
from typing import Optional


@dataclass
class DeviceInfo:
    ip: str
    hostname: str = ""
    mac: str = ""
    tapo_ok: bool = False
    model: str = ""


def get_local_subnet() -> str:
    """ローカル IP からサブネットを推定 (例: 192.168.1)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except Exception:
        return "192.168.1"


def arp_scan(subnet: str) -> list[tuple[str, str]]:
    """arp -a の結果からサブネット内のデバイスを列挙 (IP, MAC)"""
    # まず ping スイープでキャッシュを作る
    print(f"Pinging {subnet}.1-254 (may take ~10s)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        futures = [ex.submit(_ping, f"{subnet}.{i}") for i in range(1, 255)]
        concurrent.futures.wait(futures)

    result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    devices = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and subnet in line:
            ip = parts[0]
            mac = parts[1] if len(parts) > 1 else ""
            # ブロードキャストや無効エントリを除外
            if ip.count(".") == 3 and not ip.endswith(".255"):
                devices.append((ip, mac))
    return devices


def _ping(ip: str, timeout: int = 1) -> bool:
    result = subprocess.run(
        ["ping", "-n", "1", "-w", str(timeout * 1000), ip],
        capture_output=True,
    )
    return result.returncode == 0


def test_rtsp(ip: str, username: str = "admin", password: str = "", stream: int = 2) -> bool:
    """RTSP ポート(554)が開いているか確認"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        result = s.connect_ex((ip, 554))
        s.close()
        return result == 0
    except Exception:
        return False


def test_tapo_api(ip: str, username: str, password: str) -> tuple[bool, str]:
    """pytapo で接続できるか確認し、モデル名を返す"""
    try:
        from pytapo import Tapo
        tapo = Tapo(ip, username, password)
        info = tapo.getBasicInfo()
        model = (
            info.get("device_info", {})
                .get("basic_info", {})
                .get("device_model", "unknown")
        )
        return True, model
    except Exception as e:
        return False, str(e)[:60]


def main():
    parser = argparse.ArgumentParser(description="Tapo カメラ IP 検出ツール")
    parser.add_argument("--subnet", default="", help="サブネット (例: 192.168.1)")
    parser.add_argument("--username", default="admin", help="Tapo ユーザー名")
    parser.add_argument("--password", default="", help="Tapo パスワード (指定で接続テスト)")
    args = parser.parse_args()

    subnet = args.subnet or get_local_subnet()
    print(f"\n[ステップ1] サブネット {subnet}.0/24 をスキャン中...")

    devices = arp_scan(subnet)
    print(f"  → {len(devices)} 台のデバイスを発見\n")

    print("[ステップ2] RTSP ポート (554) チェック中...")
    rtsp_candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        futures = {ex.submit(test_rtsp, ip): (ip, mac) for ip, mac in devices}
        for fut, (ip, mac) in futures.items():
            if fut.result():
                rtsp_candidates.append((ip, mac))
                print(f"  RTSP open: {ip}  (MAC: {mac})")

    if not rtsp_candidates:
        print("  RTSPポートが開いているデバイスが見つかりませんでした。")
        print("  カメラの電源・ネットワーク接続を確認してください。")
        sys.exit(0)

    if args.password:
        print(f"\n[ステップ3] Tapo API 接続テスト (user={args.username})...")
        for ip, mac in rtsp_candidates:
            ok, model = test_tapo_api(ip, args.username, args.password)
            status = f"OK  model={model}" if ok else f"NG  {model}"
            print(f"  {ip}  {status}")
    else:
        print("\n[ヒント] --password を指定すると Tapo API 接続テストも実行できます")
        print(f"  例: .venv\\Scripts\\python.exe discover.py --password YOUR_PASS\n")

    print("\n=== config.yaml に追記する設定例 ===")
    for i, (ip, mac) in enumerate(rtsp_candidates):
        print(f"""
  - name: "cam{i+1}"
    host: "{ip}"
    username: "{args.username}"
    password: "your_password"
    rtsp_stream: 1""")


if __name__ == "__main__":
    main()
