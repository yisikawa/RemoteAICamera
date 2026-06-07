# RemoteAICamera 実装計画

> 作成: 2026-06-01 / 最終更新: 2026-06-07 (日次集計タブ・UI改善・誤検知クリーンアップ)  
> ブランチ戦略: `main` (安定) / `develop` (開発)

---

## システム概要

TP-Link Tapo C520W カメラ + ローカル AI (LM Studio) を使った、プライベート監視・人物/車両認識・記録システム。  
クラウド不使用・完全ローカル動作を優先。GPU: RTX 4060 16GB / CUDA 12.8。

---

## アーキテクチャ（2026-06-01 リファクタ版）

```
Tapo C520W
 ├─[RTSP]────► RTSPCapture (常時受信・20秒リングバッファ)
 │                      │
 └─[ONVIF]───► poll_events() (2秒ポーリング)
                      │
              [検知シグナル]
                      │
              handle_clip() ← 別スレッド
                      │
         ┌────────────┴──────────────────┐
         │ sleep(12s) ← ポストロール     │
         │ get_recent_frames(15s)        │
         │ ClipAnalyzer.analyze()        │
         │ → YOLO 全80クラス推論          │
         │ → 6カテゴリ分類               │
         │ → best_frame + detections保存 │
         │ save_snapshot() / save_clip() │
         │ EventStore.save_event()       │
         │   ↳ detections_json も保存    │
         └───────────────────────────────┘
                      │
              FastAPI (port 8000)
                      │
              React ダッシュボード

複数カメラ: 各カメラ独立スレッド。YOLOv8は共有インスタンス。
GPU: イベント時のみ使用（常時稼働廃止）
```

**特徴:**
- ✅ イベント駆動型（GPU効率化）
- ✅ Tapo ONVIF 検知を活用
- ✅ 15秒クリップ単位（ディスク効率的）
- ✅ ベストフレーム自動抽出

---

## VRAM 配分計画 (16GB)

| モデル | 用途 | VRAM |
|---|---|---|
| YOLOv8s | 常駐・検出 | ~0.5 GB |
| InsightFace buffalo_l | 顔認識 (Phase 2) | ~1.0 GB |
| EasyOCR GPU | ナンバー認識 (Phase 2) | ~1.5 GB |
| Qwen2.5-VL 7B Q4_K_M | LM Studio ビジョン+チャット兼用 (Phase 3) | ~6.0 GB |
| **合計 (最大)** | ※ 1モデルでビジョン・チャット両用 | **~9.0 GB** |

---

## フェーズ詳細

---

### ✅ Phase 1: 基盤構築 + YOLO全クラス対応 (完了)

**目標:** RTSP受信 → YOLOv8検出 → イベント記録・保存の基本パイプライン確立  
**2026-06-01 リファクタ:** リアルタイム全フレーム処理 → **ONVIF駆動型イベント処理** に転換

| タスク | ファイル | 状態 |
|---|---|---|
| pytapo カメラ接続 (KLAP認証対応) | `camera/tapo_client.py` | ✅ |
| RTSP受信・自動再接続・フレームバッファ | `camera/rtsp_capture.py` | ✅ |
| YOLOv8s 全80クラス推論・6カテゴリマッピング | `pipeline/detector.py` | ✅ 拡張 |
| **ClipAnalyzer** (15秒クリップ・detections_json保存) | `pipeline/clip_analyzer.py` | ✅ 拡張 |
| SQLite ORM モデル定義 | `db/models.py` | ✅ |
| DB操作ファサード (6カテゴリsummary・delete_event) | `db/store.py` | ✅ 拡張 |
| 静止画・動画クリップ保存 | `storage/file_store.py` | ✅ |
| **ONVIF駆動型メインループ** (detections_json連携) | `main.py` | ✅ 拡張 |
| カメラIP自動検出ツール | `discover.py` | ✅ |

**削除（リファクタで廃止）:**
- FrameRingBuffer (RTSPCapture内蔵バッファに統合)
- EventFilter (ONVIF駆動に変更)
- FaceRecognizer/FaceMatcher/VehicleAnalyzer (main.pyから削除、後でバッチ化予定)

**検証結果:**
- ✅ ONVIF イベント 2秒ポーリング・実カメラ動作確認済み
- ✅ 15秒クリップ自動抽出・ベストフレーム保存
- ✅ YOLO全80クラス検出・6カテゴリ分類（人/車/バイク/自転車/ペット/その他）
- ✅ detections_json（class_id/class_name/category/confidence/bbox）をDBに保存
- ✅ 既存124件をバッチ処理で再分類済み（2026-06-03）

---

### カテゴリ分類仕様（`pipeline/detector.py` CATEGORY_MAP）

YOLOv8 は Microsoft COCO データセットの80クラスを検出する。COCO とは物体認識モデルの学習用に公開された標準データセットで、各物体に class_id（番号）が割り振られている。`CATEGORY_MAP` はその class_id をこのシステムの6カテゴリに対応付けたものである。

#### COCO class_id → カテゴリ対応表

| class_id | COCO名 | カテゴリ |
|---|---|---|
| 0 | person | 人 (person) |
| 1 | bicycle | 自転車 (bicycle) |
| 2 | car | 車 (car) |
| 3 | motorcycle | バイク (motorcycle) |
| 5 | bus | 車 (car) |
| 7 | truck | 車 (car) |
| 14 | bird | ペット (pet) |
| 15 | cat | ペット (pet) |
| 16 | dog | ペット (pet) |
| 上記以外の全クラス | — | その他 (other) |

- `target_classes: [0, 1, 2, 3, 5, 7, 14, 15, 16]` を config.yaml に設定（対象外クラスは推論から除外）
- 夜間IR映像では COCO 未収録クラス（traffic cone 等）が person に誤分類される既知の問題あり
- カテゴリへの振り分けは `CATEGORY_MAP` のみで制御する

#### 複数物体が検出された場合の優先順位

1フレームで複数カテゴリが検出された場合、**優先度が最も高いカテゴリ1つ**が `detection_type` になる（`pipeline/clip_analyzer.py` `_dominant_category()`）。

| 優先度 | カテゴリ |
|---|---|
| 5（最高） | ペット (pet) |
| 4 | バイク (motorcycle) |
| 3 | 自転車 (bicycle) |
| 2 | 人 (person) |
| 1 | 車 (car) |
| 0（最低） | その他 (other) |

例: 人と犬が同時に映った場合 → pet(5) > person(2) のため **「ペット」** に分類される。

---

### ~~Phase 2: 認識機能~~ ❌ 廃止 (2026-06-04)

**廃止理由:**
- 俯瞰カメラ（45〜60°・車両が画面の1/5以下）ではナンバープレートが約20pxとなりOCR不可能
- 顔認識も設置角度・解像度の制約で実用精度が見込めない
- Phase 3 の LLM 画像類似判定で代替できる範囲を先に検証する方針に変更

**廃止スコープ:** 顔認識 (InsightFace)・ナンバープレート認識 (EasyOCR)・車両識別・KnownPerson/KnownVehicle テーブル

---

### ✅ Phase 3: Ollama ローカルAI連携（完了）

**目標:** カテゴリ別スナップショットの画像類似判定

#### Ollama 接続情報

```
API エンドポイント : http://localhost:11434/v1  (OpenAI 互換)
使用モデル        : qwen2.5vl:7b
                   ビジョン（画像類似判定）・Ollama にロード済み
クライアント      : openai Python ライブラリ（base_url 指定で Ollama に向ける）
```

```python
# 接続サンプル
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11434/v1", api_key="lm-studio")
```

#### 設計方針

- YOLO が6カテゴリに仕分け済みのスナップショットを比較対象とする
- **手動トリガー**: ダッシュボードの Details パネルから「類似を検索」ボタンで実行
- 同カテゴリの直近 `SIMILAR_CANDIDATES_LIMIT`（= 300）件のスナップショットを1件ずつ LLM に送り SAME / DIFFERENT を判定
- SAME 判定のみ `event_similarities` テーブルに保存
- 結果は SSE（Server-Sent Events）でフロントエンドにストリーミング

#### LLM への送信内容

```
入力: スナップショット2枚（base64 エンコード・bbox クロップ済み）+ カテゴリ名
プロンプト:
  "Compare these two security camera images.
   Are they the same [person/car/pet/...]?
   Reply with SAME or DIFFERENT, then explain why in one sentence."

出力: SAME / DIFFERENT + 理由文
```

#### 実装スコープ

| タスク | ファイル | 状態 |
|---|---|---|
| 画像類似判定クライアント | `ai/identity_client.py` | ✅ |
| 類似検索 SSE API（双方向対応・上限300件） | `api/routes/events.py` | ✅ |
| 類似判定結果 DB 保存 | `db/models.py` `db/store.py` | ✅ |
| Details パネル UI（イベント選択時に既存結果自動表示） | `frontend/src/App.tsx` | ✅ |
| サブカテゴリ分類クライアント | `ai/sub_category_client.py` | ✅ |
| サブカテゴリ分類 SSE API（カテゴリ絞り込み対応） | `api/routes/stats.py` | ✅ |
| `sub_category` カラム追加・自動マイグレーション | `db/models.py` `db/store.py` | ✅ |
| 統計タブ UI（機能別タブ・ヒストグラム・ゼロ補完・件数降順） | `frontend/src/App.tsx` | ✅ |

#### サブカテゴリ定義

| カテゴリ | サブカテゴリ | 分類手法 |
|---|---|---|
| 人 | 子供・学生・成人（男性）・成人（女性）・高齢者・グループ・不明 | Qwen2.5-VL |
| 車 | 軽自動車・軽トラック・セダン/ハッチバック・SUV・ミニバン/ワンボックス・バン（商用）・トラック・バス・不明 | Qwen2.5-VL |
| バイク | スクーター・ビッグスクーター・ネイキッド・スポーツ（フルカウル）・クルーザー（アメリカン）・オフロード・アドベンチャー・不明 | Qwen2.5-VL |
| 自転車 | シティサイクル・電動アシスト・ロードバイク・マウンテンバイク・クロスバイク・子供用/その他・不明 | Qwen2.5-VL |
| ペット | 犬・猫・その他動物・不明 | Qwen2.5-VL |
| その他 | 動的（detections_json の class_name を直接集計） | LLM不使用 |

#### 将来スコープ

| タスク | ファイル | 内容 |
|---|---|---|
| Chat クライアント | `ai/chat_client.py` | 自然言語→DB検索 |
| 日次レポート生成 | `ai/reporter.py` | バッチ処理 |

---

### ✅ Phase 4: Web ダッシュボード (完了)

**目標:** ブラウザからイベント閲覧・カテゴリフィルタ・イベント削除

```
バックエンド: FastAPI + uvicorn (port 8000)
フロントエンド: React + TailwindCSS (Vite ビルド・dist配信)
通信: REST API + WebSocket (リアルタイム通知)
```

| 機能 | 状態 |
|---|---|
| 6カテゴリフィルターカード（件数表示・クリック絞り込み） | ✅ |
| カメラ別イベント一覧（全件表示・カテゴリバッジ） | ✅ |
| 詳細パネル（動画再生・スナップショット・検出情報・サブカテゴリ） | ✅ |
| イベント削除（DB + 画像/動画ファイル一括削除・確認モーダル） | ✅ |
| 古いイベント一括削除（3日以上前） | ✅ |
| WebSocket リアルタイム通知 | ✅ |
| 機能別タブ UI（イベント一覧 / 日次集計 / 統計） | ✅ |
| 統計タブ（サブカテゴリヒストグラム・LLMバッチ分類・カテゴリ連動） | ✅ |
| 日次集計タブ（日別×カテゴリ棒グラフ・サブカテゴリ別ヒストグラム） | ✅ |
| イベント一覧：サブカテゴリドロップダウンフィルター（カメラ別） | ✅ |
| イベント一覧：↑↓キーによるレコード移動（カメラ内） | ✅ |
| 詳細パネル：種別・サブカテゴリのクリック編集 | ✅ |
| 人物管理・車両管理・チャットUI | 🔲 将来 |

#### 新規 API エンドポイント（Phase 4 追加分）

| エンドポイント | 説明 |
|---|---|
| `GET /api/stats/daily?days=14` | 日別×カテゴリ件数集計 |
| `GET /api/stats/daily-sub?detection_type=&days=14` | 日別×サブカテゴリ件数集計 |
| `PATCH /api/events/{id}` | 種別・サブカテゴリの手動修正（両対応） |

---

## データベーススキーマ

```
detection_events   # 通過イベントログ (1通過=1レコード)
  id, event_id, started_at, ended_at, detection_type
  face_label, face_confidence          ← Phase 2 予定
  plate_number, plate_confidence       ← Phase 2 予定
  vehicle_color, vehicle_type          ← Phase 2 予定
  ai_description                       ← 将来
  snapshot_path, clip_path, detections_json
  sub_category                         ← ✅ Phase 3 追加（LLMサブカテゴリ分類結果）

event_similarities # ✅ 画像類似判定結果（Phase 3 実装済み）
  id, event_id_a, event_id_b, reason, compared_at
  ※ SAME 判定のみ記録。(event_id_a, event_id_b) はユニーク制約

known_persons      # 登録済み人物マスター
  id, label, display_name, encoding_path, visit_count

known_vehicles     # 登録済み車両マスター
  id, plate_number, owner_label, vehicle_color, visit_count

snapshots          # 静止画ファイル管理
  id, event_id, file_path, taken_at, snapshot_type
```

---

## ファイル構成 (最終形)

```
RemoteAICamera/
├── camera/
├── pipeline/
│   ├── detector.py          ✅
│   ├── event_filter.py      ✅
│   ├── face_recognizer.py   Phase 2
│   └── plate_recognizer.py  Phase 2
├── ai/
│   ├── identity_client.py      ✅ Phase 3（画像類似判定）
│   ├── sub_category_client.py  ✅ Phase 3（サブカテゴリ分類）
│   ├── chat_client.py          将来
│   └── reporter.py             将来
├── db/
├── storage/
├── api/                     Phase 4
│   └── routes/
├── frontend/                Phase 4
├── tools/
│   ├── cleanup_other.py        ✅ その他誤検知削除（target_classes外のみ）
│   ├── cleanup_false_person.py ✅ 人誤検知削除（非対象クラスが優位な場合）
│   ├── cleanup_false_car.py    ✅ 車誤検知削除（同上）
│   └── register_face.py        Phase 2
├── doc/                     (gitignore) 設計ドキュメント
├── main.py
├── config.py
└── discover.py
```

---

---

## 🔴 Design Change: バッチ処理型への転換 (2026-06-01 検討中)

### 背景と課題

**現在の課題:**
- リアルタイム RTSP ストリーミング処理は CPU/GPU 常時稼働
- ナンバープレート OCR は不可能（カメラ設置角度の制約）
- 複数カメラ並列処理で GPU メモリ圧迫

**新設計の方向:**
- Tapo C520W マイクロソッドカード記録を活用
- 毎日 22:00 に 1 日分の動画をダウンロード
- バッチ処理で顔認識・車両分析 → 日次ランキング生成
- リアルタイム処理を廃止、定時処理に転換

### 新アーキテクチャ（案）

```
[毎日22:00トリガー]
        │
        ▼
┌──────────────────────────────────────────┐
│     Batch Processing (深夜23:00～朝6:00)   │
├──────────────────────────────────────────┤
│                                          │
│ 1. マイクロSDカードから1日分動画DL       │
│    Tapo API + Downloader                │
│    (複数カメラ並列、帯域制限)           │
│                                          │
│ 2. ファイルベース YOLO/顔認識            │
│    VideoCapture ストリーミング読み込み   │
│                                          │
│ 3. イベント検出 → DB挿入                 │
│                                          │
│ 4. ランキング生成                        │
│    (人物 Top 10, 車両 Top 10)            │
│                                          │
│ 5. HTML レポート生成 + 古い動画削除     │
│                                          │
└──────────────────────────────────────────┘
        │
        ▼
  毎朝6:00までに
  ランキング完成
```

### 🔴 Critical Issues

| # | 課題 | 対応案 | 優先度 |
|---|------|------|------|
| **C1** | pytapo ダウンローダーの複雑性 (非同期、リトライ、タイムアウト) | `tools/batch_downloader.py` で専用実装 | 🔴 |
| **C2** | スケジューリング実装がない | Windows タスクスケジューラー vs APScheduler で決定 | 🔴 |
| **C3** | 複数カメラの並列ダウンロード時に帯域競合 | 帯域制限ロジック + タイムアウト管理 | 🔴 |
| **C4** | ディスク容量管理の仕組みなし | ローテーション削除ロジック実装 (デフォルト 7 日保持) | 🔴 |

### 🟡 Major Issues

| # | 課題 | 対応案 |
|---|------|------|
| **M1** | config.yaml が RTSP 前提 | `sd_card:`, `batch_processing:` セクション追加 |
| **M2** | TapoClient の拡張が大きい | `download_video()` メソッド追加 |
| **M3** | main.py が責務過多 | バッチ処理を `batch_processor.py` に分離 |
| **M4** | EventStore が秒単位イベント用 | 1 日分クエリ最適化が必要 |

### 実装順序（推奨）

```
Week 1:
  1. config.yaml に新セクション追加 (sd_card, batch_processing)
  2. camera/tapo_client.py に download_video() メソッド
  3. tools/batch_downloader.py 実装 (ダウンロード + リトライ)
  
Week 2:
  4. tools/batch_processor.py 実装 (ファイル入力 YOLOv8/顔認識)
  5. tools/scheduler.py 実装 (Windows タスク or APScheduler)
  6. storage/ に StorageManager 追加 (ローテーション削除)
  
Week 3:
  7. テスト動画で end-to-end テスト
  8. main.py から RTSP 処理の廃止判定
```

### ⚠️ リスク・検討事項

| 項目 | 内容 |
|------|------|
| **ダウンロード時間** | 1 日分 100～200MB → 2～6 時間。22:00 開始では完了が翌朝～翌昼になる可能性。22:00 の前倒し検討必須。 |
| **ダウンロード失敗** | pytapo のタイムアウト・セッション切れ。再試行ロジックと失敗時の通知が必須。 |
| **複数カメラの同期** | 各カメラのダウンロード完了時刻がずれる。最終カメラまで待機する仕組みが必要。 |
| **リアルタイム通知廃止** | 翌日の過去イベント表示に変わる。ユーザー体験が大幅変更。 |
| **ファイルベース処理** | メモリ使用量がリアルタイムより大幅に増加。バッチ処理中は他の用途に PC が使えない可能性。 |

### 決定待ち（ユーザー承認が必須）

- [ ] 既存 RTSP リアルタイム処理を廃止するか？（ハイブリッド運用 vs 完全置き換え）
- [ ] ダウンロード開始時刻を 22:00 より前倒しするか？（推奨: 19:00～20:00）
- [ ] スケジューリング方式：**Windows タスク** (推奨、信頼性高) **vs** **APScheduler** (汎用、柔軟)
- [ ] ディスク保持期間：7 日 / 14 日 / 30 日 のいずれか
- [ ] ダウンロード失敗時の通知方法：メール / Slack / ログファイルのみ

---

## 注意事項・制約

- pytapo は非公式ライブラリ。ファームウェア更新で動作変更の可能性あり
- 日本語ナンバープレートは角度・汚れ・距離で認識精度が変動
- 顔認識・ナンバー記録は個人情報保護法対象。私有地・私的利用の範囲で運用
- config.yaml はパスワードを含むため .gitignore で除外 (config.yaml.example を参照)
