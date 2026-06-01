"""
スナップ写真付きランキング HTML レポート生成ツール

使い方:
  .venv\Scripts\python.exe tools/report.py
  .venv\Scripts\python.exe tools/report.py --out data/report.html --days 7
"""
import sys
import base64
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import EventStore
from db.models import KnownPerson, KnownVehicle, DetectionEventRecord, Snapshot


# ------------------------------------------------------------------ #
# 画像ユーティリティ                                                    #
# ------------------------------------------------------------------ #

def img_to_b64(path: str, size: tuple = (120, 120)) -> str:
    """画像ファイルを Base64 文字列に変換 (HTML 埋め込み用)"""
    import cv2, numpy as np
    if not path or not Path(path).exists():
        return _placeholder_b64(size)
    img = cv2.imread(path)
    if img is None:
        return _placeholder_b64(size)
    img = cv2.resize(img, size)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode()


def _placeholder_b64(size=(120, 120)) -> str:
    import numpy as np, cv2
    img = np.full((size[1], size[0], 3), 80, dtype=np.uint8)
    cv2.putText(img, "?", (size[0]//2-12, size[1]//2+10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 2)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode()


# ------------------------------------------------------------------ #
# データ取得                                                            #
# ------------------------------------------------------------------ #

def get_person_ranking(store: EventStore, days: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days)
    with store._session() as s:
        persons = s.query(KnownPerson).filter_by(is_active=True).all()
        result = []
        for p in persons:
            count = (
                s.query(DetectionEventRecord)
                .filter(DetectionEventRecord.face_label == p.label)
                .filter(DetectionEventRecord.started_at >= cutoff)
                .count()
            )
            # 最新スナップショットを取得
            latest_event = (
                s.query(DetectionEventRecord)
                .filter(DetectionEventRecord.face_label == p.label)
                .order_by(DetectionEventRecord.started_at.desc())
                .first()
            )
            snap = latest_event.snapshot_path if latest_event else None
            result.append({
                "label": p.label,
                "display_name": p.display_name or p.label,
                "visit_count": count,
                "last_seen": p.last_seen_at,
                "thumbnail": p.thumbnail_path,
                "latest_snap": snap,
            })
        result.sort(key=lambda x: -x["visit_count"])
        return result


def get_vehicle_ranking(store: EventStore, days: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days)
    with store._session() as s:
        vehicles = s.query(KnownVehicle).filter_by(is_active=True).all()
        result = []
        for v in vehicles:
            count = (
                s.query(DetectionEventRecord)
                .filter(DetectionEventRecord.started_at >= cutoff)
                .filter(DetectionEventRecord.vehicle_color == v.vehicle_color)
                .filter(DetectionEventRecord.vehicle_type == v.vehicle_type_jp
                        if hasattr(v, 'vehicle_type_jp') else True)
                .count()
            )
            result.append({
                "label": v.label,
                "display_name": v.display_name or v.label,
                "owner_label": v.owner_label or "",
                "color": v.vehicle_color or "",
                "vtype": v.vehicle_type or "",
                "visit_count": v.visit_count or 0,
                "last_seen": v.last_seen_at,
                "thumbnail": v.thumbnail_path,
            })
        result.sort(key=lambda x: -x["visit_count"])
        return result


def get_recent_events(store: EventStore, days: int, limit: int = 20) -> list:
    cutoff = datetime.now() - timedelta(days=days)
    with store._session() as s:
        rows = (
            s.query(DetectionEventRecord)
            .filter(DetectionEventRecord.started_at >= cutoff)
            .order_by(DetectionEventRecord.started_at.desc())
            .limit(limit)
            .all()
        )
        s.expunge_all()
        return rows


def get_stats(store: EventStore, days: int) -> dict:
    cutoff = datetime.now() - timedelta(days=days)
    with store._session() as s:
        total = s.query(DetectionEventRecord).filter(
            DetectionEventRecord.started_at >= cutoff).count()
        persons = s.query(DetectionEventRecord).filter(
            DetectionEventRecord.started_at >= cutoff,
            DetectionEventRecord.detection_type.contains("person")).count()
        vehicles = s.query(DetectionEventRecord).filter(
            DetectionEventRecord.started_at >= cutoff,
            DetectionEventRecord.detection_type.contains("vehicle")).count()
        known_faces = s.query(DetectionEventRecord).filter(
            DetectionEventRecord.started_at >= cutoff,
            DetectionEventRecord.face_label.isnot(None)).count()
    return {"total": total, "persons": persons, "vehicles": vehicles, "known_faces": known_faces}


# ------------------------------------------------------------------ #
# HTML 生成                                                             #
# ------------------------------------------------------------------ #

def build_html(
    person_ranking: list,
    vehicle_ranking: list,
    recent_events: list,
    stats: dict,
    days: int,
    generated_at: str,
) -> str:

    def card(b64, title, subtitle, badge, badge_color="#3b82f6"):
        return f"""
        <div class="card">
          <img src="data:image/jpeg;base64,{b64}" alt="{title}">
          <div class="card-body">
            <div class="badge" style="background:{badge_color}">{badge}</div>
            <div class="card-title">{title}</div>
            <div class="card-sub">{subtitle}</div>
          </div>
        </div>"""

    # 人物ランキング
    person_cards = ""
    if person_ranking:
        for i, p in enumerate(person_ranking[:10]):
            b64 = img_to_b64(p["latest_snap"] or p["thumbnail"] or "", (160, 160))
            last = p["last_seen"].strftime("%m/%d %H:%M") if p["last_seen"] else "-"
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
            person_cards += card(
                b64, p["display_name"],
                f"最終: {last}",
                f"{medal} {p['visit_count']}回",
                "#2563eb" if i == 0 else "#6b7280",
            )
    else:
        person_cards = '<p class="no-data">登録人物なし (register_face.py で登録してください)</p>'

    # 車両ランキング
    vehicle_cards = ""
    if vehicle_ranking:
        for i, v in enumerate(vehicle_ranking[:10]):
            b64 = img_to_b64(v["thumbnail"] or "", (160, 120))
            last = v["last_seen"].strftime("%m/%d %H:%M") if v["last_seen"] else "-"
            owner = f" ({v['owner_label']})" if v["owner_label"] else ""
            vehicle_cards += card(
                b64,
                f"{v['display_name']}{owner}",
                f"{v['color']} {v['vtype']}  最終: {last}",
                f"#{i+1} {v['visit_count']}回",
                "#16a34a" if i == 0 else "#6b7280",
            )
    else:
        vehicle_cards = '<p class="no-data">登録車両なし (register_vehicle.py で登録してください)</p>'

    # 最近のイベント
    event_rows = ""
    for ev in recent_events:
        ts = ev.started_at.strftime("%m/%d %H:%M:%S") if ev.started_at else "-"
        b64 = img_to_b64(ev.snapshot_path or "", (80, 60))
        face = ev.face_label or "-"
        color = ev.vehicle_color or ""
        vtype = ev.vehicle_type or ""
        vehicle_info = f"{color} {vtype}".strip() or "-"
        dtype_badge = {
            "person": "👤 人物",
            "vehicle": "🚗 車両",
            "person+vehicle": "👤🚗 人+車",
        }.get(ev.detection_type, ev.detection_type or "-")
        event_rows += f"""
        <tr>
          <td><img src="data:image/jpeg;base64,{b64}" class="event-thumb"></td>
          <td>{ts}</td>
          <td><span class="type-badge">{dtype_badge}</span></td>
          <td>{face}</td>
          <td>{vehicle_info}</td>
          <td>{ev.duration_sec or 0:.1f}s</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RemoteAICamera レポート</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
  h1 {{ color: #0f172a; margin-bottom: 4px; }}
  .subtitle {{ color: #64748b; margin-bottom: 24px; font-size: 14px; }}
  .stats-bar {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 12px; padding: 16px 24px; box-shadow: 0 1px 3px rgba(0,0,0,.1); text-align: center; }}
  .stat-num {{ font-size: 32px; font-weight: 700; color: #2563eb; }}
  .stat-label {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
  h2 {{ margin: 28px 0 12px; font-size: 20px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; }}
  .card {{ background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1);
           width: 160px; overflow: hidden; transition: transform .2s; }}
  .card:hover {{ transform: translateY(-3px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }}
  .card img {{ width: 160px; height: 140px; object-fit: cover; }}
  .card-body {{ padding: 10px; }}
  .badge {{ display: inline-block; color: white; font-size: 12px; font-weight: 700;
            padding: 2px 8px; border-radius: 20px; margin-bottom: 6px; }}
  .card-title {{ font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .card-sub {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
  .no-data {{ color: #94a3b8; font-style: italic; padding: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: white;
           border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  th {{ background: #f8fafc; padding: 10px 14px; text-align: left; font-size: 13px;
        color: #475569; border-bottom: 1px solid #e2e8f0; }}
  td {{ padding: 8px 14px; font-size: 13px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  .event-thumb {{ width: 80px; height: 60px; object-fit: cover; border-radius: 6px; }}
  .type-badge {{ background: #dbeafe; color: #1d4ed8; padding: 2px 8px;
                 border-radius: 12px; font-size: 12px; white-space: nowrap; }}
  footer {{ margin-top: 32px; color: #94a3b8; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<h1>RemoteAICamera レポート</h1>
<div class="subtitle">過去 {days} 日間  /  生成: {generated_at}</div>

<div class="stats-bar">
  <div class="stat"><div class="stat-num">{stats['total']}</div><div class="stat-label">総イベント</div></div>
  <div class="stat"><div class="stat-num">{stats['persons']}</div><div class="stat-label">人物イベント</div></div>
  <div class="stat"><div class="stat-num">{stats['vehicles']}</div><div class="stat-label">車両イベント</div></div>
  <div class="stat"><div class="stat-num">{stats['known_faces']}</div><div class="stat-label">既知人物検出</div></div>
</div>

<h2>👤 人物ランキング (過去 {days} 日)</h2>
<div class="cards">{person_cards}</div>

<h2>🚗 車両ランキング (過去 {days} 日)</h2>
<div class="cards">{vehicle_cards}</div>

<h2>🕐 最近のイベント</h2>
<table>
  <thead><tr>
    <th>スナップ</th><th>日時</th><th>種別</th><th>顔認識</th><th>車両</th><th>継続時間</th>
  </tr></thead>
  <tbody>{event_rows if event_rows else '<tr><td colspan="6" style="text-align:center;color:#94a3b8">イベントなし</td></tr>'}</tbody>
</table>

<footer>RemoteAICamera &mdash; generated by report.py</footer>
</body>
</html>"""


# ------------------------------------------------------------------ #
# main                                                                  #
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(description="スナップ写真付きランキング HTML レポート")
    parser.add_argument("--out",  default="data/report.html", help="出力HTMLパス")
    parser.add_argument("--days", type=int, default=30,       help="集計期間 (日, default=30)")
    args = parser.parse_args()

    store = EventStore()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("データ集計中...")
    persons  = get_person_ranking(store, args.days)
    vehicles = get_vehicle_ranking(store, args.days)
    events   = get_recent_events(store, args.days, limit=20)
    stats    = get_stats(store, args.days)

    print(f"  人物: {len(persons)}人  車両: {len(vehicles)}台  "
          f"イベント: {stats['total']}件")

    print("HTML 生成中...")
    html = build_html(persons, vehicles, events, stats, args.days, now_str)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"レポート生成完了: {out.resolve()}")
    print(f"ブラウザで開く: start {out.resolve()}")

    # 自動でブラウザを開く
    import webbrowser
    webbrowser.open(str(out.resolve()))


if __name__ == "__main__":
    main()
