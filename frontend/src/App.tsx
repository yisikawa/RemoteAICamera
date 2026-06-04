import { useCallback, useEffect, useRef, useState } from 'react'
import { eventApi } from './api'
import type { Summary, DetectionEvent, SimilarResult } from './types'
import './index.css'

const WS_URL = 'ws://localhost:8000/ws'
const API_BASE = 'http://localhost:8000'

const TYPE_COLOR: Record<string, string> = {
  person:     'bg-emerald-500',
  car:        'bg-sky-500',
  motorcycle: 'bg-orange-400',
  bicycle:    'bg-yellow-400',
  pet:        'bg-violet-500',
  other:      'bg-slate-500',
  vehicle:    'bg-sky-500',
  motion:     'bg-slate-500',
}

const TYPE_LABEL: Record<string, string> = {
  person:     '人',
  car:        '車',
  motorcycle: 'バイク',
  bicycle:    '自転車',
  pet:        'ペット',
  other:      'その他',
  vehicle:    '車両',
  motion:     '動体',
}

function ConfirmModal({
  eventId,
  onConfirm,
  onCancel,
  loading,
}: {
  eventId: string
  onConfirm: () => void
  onCancel: () => void
  loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl p-6 w-80">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-full bg-red-500/20 flex items-center justify-center text-red-400 text-lg">✕</div>
          <h3 className="text-white font-semibold text-base">イベントを削除</h3>
        </div>
        <p className="text-slate-300 text-sm mb-1">以下のイベントを完全に削除します。</p>
        <p className="text-slate-400 text-xs font-mono bg-slate-900 rounded px-2 py-1 mb-5 break-all">{eventId}</p>
        <p className="text-slate-400 text-xs mb-5">スナップショット・クリップ動画も削除されます。この操作は取り消せません。</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 transition disabled:opacity-50"
          >
            キャンセル
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold transition disabled:opacity-50 flex items-center gap-2"
          >
            {loading && <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
            削除する
          </button>
        </div>
      </div>
    </div>
  )
}

function EventList({
  cameraName,
  events,
  selectedId,
  onSelect,
}: {
  cameraName: string
  events: DetectionEvent[]
  selectedId: string | null
  onSelect: (e: DetectionEvent) => void
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-white">
      <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">{cameraName}</h2>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '220px' }}>
        {events.length === 0 ? (
          <p className="text-slate-500 text-sm py-2">イベントなし</p>
        ) : (
          events.map(event => (
            <div
              key={event.event_id}
              onClick={() => onSelect(event)}
              className={`px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                event.event_id === selectedId
                  ? 'bg-slate-600 ring-1 ring-slate-400'
                  : 'hover:bg-slate-700'
              }`}
            >
              <div className="flex justify-between items-center gap-2">
                <div className="min-w-0">
                  <div className="text-xs text-slate-300 truncate">{event.event_id}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {new Date(event.started_at).toLocaleString('ja-JP')}
                  </div>
                </div>
                <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full text-white ${
                  TYPE_COLOR[event.detection_type] ?? 'bg-slate-500'
                }`}>
                  {TYPE_LABEL[event.detection_type] ?? event.detection_type}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function FilterCard({
  label, value, color, active, onClick,
}: {
  label: string; value: number; color: string; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl text-white text-left transition-all overflow-hidden ${color} hover:brightness-110`}
    >
      <div className="px-4 pt-4 pb-3">
        <div className="text-2xl font-bold">{value}</div>
        <div className="text-xs font-medium opacity-80 mt-0.5">{label}</div>
      </div>
      <div className={`h-1 transition-all ${active ? 'bg-white' : 'bg-transparent'}`} />
    </button>
  )
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [selectedEvent, setSelectedEvent] = useState<DetectionEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirmTarget, setConfirmTarget] = useState<DetectionEvent | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [editingType, setEditingType] = useState(false)
  const [savingType, setSavingType] = useState(false)
  const [similarResults, setSimilarResults] = useState<SimilarResult[]>([])
  const [similarLoading, setSimilarLoading] = useState(false)
  const [similarDone, setSimilarDone] = useState(0)
  const [similarTotal, setSimilarTotal] = useState(0)

  const unmountedRef = useRef(false)
  const similarSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    setEditingType(false)
    setSavingType(false)
    if (similarSourceRef.current) {
      similarSourceRef.current.close()
      similarSourceRef.current = null
    }
    setSimilarResults([])
    setSimilarLoading(false)
    setSimilarDone(0)
    setSimilarTotal(0)

    // イベント選択時にDB保存済みの類似結果を取得
    if (selectedEvent?.event_id) {
      eventApi.getSimilarities(selectedEvent.event_id)
        .then(cached => { if (cached.length > 0) setSimilarResults(cached) })
        .catch(() => {})
    }
  }, [selectedEvent?.event_id])

  const handleFindSimilar = useCallback(() => {
    if (!selectedEvent) return
    if (similarSourceRef.current) {
      similarSourceRef.current.close()
    }
    setSimilarLoading(true)
    setSimilarDone(0)
    setSimilarTotal(0)

    const source = new EventSource(
      `${API_BASE}/api/events/${selectedEvent.event_id}/similar/stream`
    )
    similarSourceRef.current = source

    source.onmessage = (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      if (data.finished) {
        setSimilarLoading(false)
        source.close()
        return
      }
      setSimilarDone(data.done)
      setSimilarTotal(data.total)
      if (data.verdict === 'SAME') {
        setSimilarResults(prev => {
          // 重複追加を防ぐ
          if (prev.some(r => r.event_id === data.event_id)) return prev
          return [...prev, {
            event_id: data.event_id,
            started_at: data.started_at,
            detection_type: data.detection_type,
            snapshot_url: data.snapshot_url,
            verdict: data.verdict,
            reason: data.reason,
          }]
        })
      }
    }

    source.onerror = () => {
      setSimilarLoading(false)
      source.close()
    }
  }, [selectedEvent])

  useEffect(() => {
    unmountedRef.current = false

    const fetchAll = async () => {
      try {
        const [summaryData, eventsData] = await Promise.all([
          eventApi.getSummary(),
          eventApi.listEvents(500, 0),
        ])
        setSummary(summaryData)
        setEvents(eventsData.items)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error loading data')
      } finally {
        setLoading(false)
      }
    }

    let ws: WebSocket | null = null
    let retryDelay = 1000
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (unmountedRef.current) return
      ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setWsConnected(true)
        retryDelay = 1000
        fetchAll()
      }

      ws.onmessage = (e: MessageEvent) => {
        try {
          const msg = JSON.parse(e.data) as { type: string; event_id: string; detection_type: string }
          if (msg.type === 'new_event') {
            eventApi.getEvent(msg.event_id).then(event => {
              setEvents(prev => {
                if (prev.some(ev => ev.event_id === event.event_id)) return prev
                return [event, ...prev].slice(0, 500)
              })
              eventApi.getSummary().then(setSummary).catch(() => {})
            }).catch(() => {})
          } else if (msg.type === 'type_updated') {
            setEvents(prev => prev.map(ev =>
              ev.event_id === msg.event_id ? { ...ev, detection_type: msg.detection_type } : ev
            ))
            setSelectedEvent(prev =>
              prev?.event_id === msg.event_id ? { ...prev, detection_type: msg.detection_type } : prev
            )
            eventApi.getSummary().then(setSummary).catch(() => {})
          } else if (msg.type === 'deleted') {
            setEvents(prev => prev.filter(ev => ev.event_id !== msg.event_id))
            setSelectedEvent(prev => prev?.event_id === msg.event_id ? null : prev)
            eventApi.getSummary().then(setSummary).catch(() => {})
          }
        } catch {}
      }

      ws.onclose = () => {
        setWsConnected(false)
        if (unmountedRef.current) return
        retryTimer = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30_000)
          connect()
        }, retryDelay)
      }

      ws.onerror = () => ws?.close()
    }

    fetchAll()
    connect()

    return () => {
      unmountedRef.current = true
      if (retryTimer) clearTimeout(retryTimer)
      ws?.close()
    }
  }, [])

  const handleTypeChange = async (newType: string) => {
    if (!selectedEvent || newType === selectedEvent.detection_type) {
      setEditingType(false)
      return
    }
    const prev = selectedEvent
    setEditingType(false)
    setSavingType(true)
    const updated = { ...selectedEvent, detection_type: newType }
    setSelectedEvent(updated)
    setEvents(evs => evs.map(e => e.event_id === updated.event_id ? updated : e))
    try {
      await eventApi.updateEventType(selectedEvent.event_id, newType)
    } catch {
      setSelectedEvent(prev)
      setEvents(evs => evs.map(e => e.event_id === prev.event_id ? prev : e))
    } finally {
      setSavingType(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!confirmTarget) return
    setDeleting(true)
    try {
      await eventApi.deleteEvent(confirmTarget.event_id)
      setEvents(prev => prev.filter(e => e.event_id !== confirmTarget.event_id))
      setSelectedEvent(null)
      setConfirmTarget(null)
    } catch {
      setConfirmTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  if (loading) return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center text-slate-400">
      読み込み中...
    </div>
  )
  if (error) return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center text-red-400">
      エラー: {error}
    </div>
  )

  const filteredEvents = activeFilter
    ? events.filter(e => e.detection_type === activeFilter)
    : events

  const cameras = Array.from(new Set(filteredEvents.map(e => e.event_id.split('_')[0]))).sort()
  const byCamera = (name: string) => filteredEvents.filter(e => e.event_id.startsWith(name + '_'))

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      {confirmTarget && (
        <ConfirmModal
          eventId={confirmTarget.event_id}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setConfirmTarget(null)}
          loading={deleting}
        />
      )}

      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <h1 className="text-2xl font-bold text-white tracking-tight">RemoteAICamera</h1>
          <span className="text-xs text-slate-500">最新 500 件表示</span>
          <span className={`ml-auto flex items-center gap-1.5 text-xs ${wsConnected ? 'text-emerald-400' : 'text-slate-500'}`}>
            <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
            {wsConnected ? 'LIVE' : '接続中...'}
          </span>
        </div>

        {summary && (
          <div className="grid grid-cols-7 gap-2 mb-6">
            <FilterCard
              label="すべて" value={summary.total_events} color="bg-slate-700"
              active={activeFilter === null}
              onClick={() => setActiveFilter(null)}
            />
            <FilterCard
              label="人" value={summary.person ?? 0} color="bg-emerald-700"
              active={activeFilter === 'person'}
              onClick={() => setActiveFilter(activeFilter === 'person' ? null : 'person')}
            />
            <FilterCard
              label="車" value={summary.car ?? 0} color="bg-sky-700"
              active={activeFilter === 'car'}
              onClick={() => setActiveFilter(activeFilter === 'car' ? null : 'car')}
            />
            <FilterCard
              label="バイク" value={summary.motorcycle ?? 0} color="bg-orange-700"
              active={activeFilter === 'motorcycle'}
              onClick={() => setActiveFilter(activeFilter === 'motorcycle' ? null : 'motorcycle')}
            />
            <FilterCard
              label="自転車" value={summary.bicycle ?? 0} color="bg-yellow-700"
              active={activeFilter === 'bicycle'}
              onClick={() => setActiveFilter(activeFilter === 'bicycle' ? null : 'bicycle')}
            />
            <FilterCard
              label="ペット" value={summary.pet ?? 0} color="bg-violet-700"
              active={activeFilter === 'pet'}
              onClick={() => setActiveFilter(activeFilter === 'pet' ? null : 'pet')}
            />
            <FilterCard
              label="その他" value={summary.other ?? 0} color="bg-slate-600"
              active={activeFilter === 'other'}
              onClick={() => setActiveFilter(activeFilter === 'other' ? null : 'other')}
            />
          </div>
        )}

        <div className="grid grid-cols-3 gap-5">
          <div className="col-span-2 flex flex-col gap-3">
            {cameras.map(name => (
              <EventList
                key={name}
                cameraName={name}
                events={byCamera(name)}
                selectedId={selectedEvent?.event_id ?? null}
                onSelect={setSelectedEvent}
              />
            ))}
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 text-white flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Details</h2>
              {selectedEvent && (
                <div className="flex gap-2">
                  <button
                    onClick={handleFindSimilar}
                    disabled={similarLoading}
                    className="text-xs text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 px-2.5 py-1 rounded-lg transition disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {similarLoading && (
                      <span className="w-3 h-3 border-2 border-violet-400/40 border-t-violet-400 rounded-full animate-spin" />
                    )}
                    類似を検索
                  </button>
                  <button
                    onClick={() => setConfirmTarget(selectedEvent)}
                    className="text-xs text-red-400 hover:text-red-300 border border-red-800 hover:border-red-600 px-2.5 py-1 rounded-lg transition"
                  >
                    削除
                  </button>
                </div>
              )}
            </div>

            {selectedEvent ? (
              <div className="space-y-3 text-sm overflow-y-auto flex-1">
                {selectedEvent.clip_url ? (
                  <video
                    key={selectedEvent.clip_url}
                    src={selectedEvent.clip_url}
                    poster={selectedEvent.snapshot_url ?? undefined}
                    controls
                    className="w-full rounded-lg"
                  />
                ) : selectedEvent.snapshot_url ? (
                  <img src={selectedEvent.snapshot_url} alt="snapshot" className="w-full rounded-lg" />
                ) : null}

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div className="col-span-2 bg-slate-900 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-500 mb-0.5">Event ID</div>
                    <div className="font-mono text-xs text-slate-300 break-all">{selectedEvent.event_id}</div>
                  </div>
                  <div className="bg-slate-900 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-500 mb-0.5">種別</div>
                    {editingType ? (
                      <select
                        autoFocus
                        defaultValue={selectedEvent.detection_type}
                        onChange={e => handleTypeChange(e.target.value)}
                        onBlur={() => setEditingType(false)}
                        className="text-xs bg-slate-700 text-white rounded px-1 py-0.5 border border-slate-500 outline-none"
                      >
                        {(['person','car','motorcycle','bicycle','pet','other'] as const).map(k => (
                          <option key={k} value={k}>{TYPE_LABEL[k]}</option>
                        ))}
                      </select>
                    ) : savingType ? (
                      <span className="text-xs text-slate-400 flex items-center gap-1.5">
                        <span className="w-3 h-3 border-2 border-slate-400/40 border-t-slate-400 rounded-full animate-spin" />
                        保存中...
                      </span>
                    ) : (
                      <span
                        onClick={() => setEditingType(true)}
                        title="クリックして種別を変更"
                        className={`text-xs font-bold px-2 py-0.5 rounded-full text-white cursor-pointer hover:brightness-125 ${TYPE_COLOR[selectedEvent.detection_type] ?? 'bg-slate-500'}`}
                      >
                        {TYPE_LABEL[selectedEvent.detection_type] ?? selectedEvent.detection_type}
                      </span>
                    )}
                  </div>
                  <div className="bg-slate-900 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-500 mb-0.5">時刻</div>
                    <div className="text-xs text-slate-300">{new Date(selectedEvent.started_at).toLocaleString('ja-JP')}</div>
                  </div>
                  <div className="bg-slate-900 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-500 mb-0.5">長さ</div>
                    <div className="text-xs text-slate-300">{selectedEvent.duration_sec?.toFixed(1) ?? '—'} 秒</div>
                  </div>
                  <div className="bg-slate-900 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-500 mb-0.5">フレーム数</div>
                    <div className="text-xs text-slate-300">{selectedEvent.frame_count ?? '—'}</div>
                  </div>
                  {selectedEvent.face_label && (
                    <div className="col-span-2 bg-slate-900 rounded-lg px-3 py-2">
                      <div className="text-xs text-slate-500 mb-0.5">顔認識</div>
                      <div className="text-xs text-slate-300">{selectedEvent.face_label} ({selectedEvent.face_confidence?.toFixed(2)})</div>
                    </div>
                  )}
                </div>

                {/* 類似イベントセクション */}
                {(similarLoading || similarResults.length > 0) && (
                  <div className="pt-3 border-t border-slate-700">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">類似イベント</span>
                      <span className="text-xs text-slate-500">
                        {similarLoading
                          ? `${similarDone} / ${similarTotal} 比較中...`
                          : `${similarResults.filter(r => r.verdict === 'SAME').length} 件一致`}
                      </span>
                    </div>

                    {/* 進捗バー */}
                    {similarLoading && (
                      <div className="w-full bg-slate-700 rounded-full h-1.5 mb-3">
                        <div
                          className="bg-violet-500 h-1.5 rounded-full transition-all duration-500"
                          style={{ width: similarTotal > 0 ? `${(similarDone / similarTotal) * 100}%` : '0%' }}
                        />
                      </div>
                    )}

                    {/* 結果リスト（1件ずつ追加） */}
                    <div className="space-y-2">
                      {similarResults.filter(r => r.verdict === 'SAME').map(r => (
                        <div
                          key={r.event_id}
                          onClick={async () => {
                            const ev = events.find(e => e.event_id === r.event_id)
                            if (ev) {
                              setSelectedEvent(ev)
                            } else {
                              const fetched = await eventApi.getEvent(r.event_id)
                              setSelectedEvent(fetched)
                            }
                          }}
                          className={`flex gap-2 items-start p-2 rounded-lg cursor-pointer transition ${
                            r.verdict === 'SAME'
                              ? 'bg-emerald-900/30 hover:bg-emerald-900/50'
                              : 'bg-slate-900/50 hover:bg-slate-700/50'
                          }`}
                        >
                          {r.snapshot_url && (
                            <img
                              src={r.snapshot_url}
                              alt="snapshot"
                              className="w-14 h-14 object-cover rounded shrink-0"
                            />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                                r.verdict === 'SAME'
                                  ? 'bg-emerald-500 text-white'
                                  : 'bg-slate-600 text-slate-300'
                              }`}>
                                {r.verdict === 'SAME' ? '一致' : '不一致'}
                              </span>
                              <span className="text-xs text-slate-400">
                                {new Date(r.started_at).toLocaleString('ja-JP')}
                              </span>
                            </div>
                            <div className="text-xs text-slate-300 line-clamp-2">{r.reason}</div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {!similarLoading && similarResults.length === 0 && (
                      <div className="text-xs text-slate-500 py-2 text-center">
                        類似イベントは見つかりませんでした
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-600 text-sm">
                イベントを選択してください
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
