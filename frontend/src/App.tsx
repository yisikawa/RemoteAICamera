import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { eventApi } from './api'
import type { Summary, DetectionEvent, SimilarResult, SubCategoryStat, DailyStat, DailySubStat, DailyStatByCamera, DailySubStatByCamera } from './types'
import './index.css'

const WS_URL = 'ws://localhost:8000/ws'
const API_BASE = 'http://localhost:8000'

const SUB_CATEGORY_OPTIONS: Record<string, string[]> = {
  person:     ['子供', '学生', '成人（男性）', '成人（女性）', '高齢者', 'グループ', '不明'],
  car:        ['軽自動車', '軽トラック', 'セダン/ハッチバック', 'SUV', 'ミニバン/ワンボックス', 'バン（商用）', 'トラック', 'バス', '不明'],
  motorcycle: ['スクーター', 'ビッグスクーター', 'ネイキッド', 'スポーツ（フルカウル）', 'クルーザー（アメリカン）', 'オフロード', 'アドベンチャー', '不明'],
  bicycle:    ['シティサイクル', '電動アシスト', 'ロードバイク', 'マウンテンバイク', 'クロスバイク', '子供用/その他', '不明'],
  pet:        ['犬', '猫', 'その他動物', '不明'],
}

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
  showSubFilter,
}: {
  cameraName: string
  events: DetectionEvent[]
  selectedId: string | null
  onSelect: (e: DetectionEvent) => void
  showSubFilter: boolean
}) {
  const selectedRef = useRef<HTMLDivElement | null>(null)
  const [subFilter, setSubFilter] = useState('')

  useEffect(() => { setSubFilter('') }, [showSubFilter])

  const subCategories = useMemo(() =>
    Array.from(new Set(events.map(e => e.sub_category).filter(Boolean) as string[])).sort()
  , [events])

  const displayed = subFilter ? events.filter(e => e.sub_category === subFilter) : events

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedId])

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-white">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">{cameraName}</h2>
        {showSubFilter && subCategories.length > 0 && (
          <select
            value={subFilter}
            onChange={e => setSubFilter(e.target.value)}
            className="text-xs bg-slate-700 text-slate-200 rounded-lg px-2 py-1 border border-slate-600 outline-none cursor-pointer"
          >
            <option value="">すべて</option>
            {subCategories.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '220px' }}>
        {displayed.length === 0 ? (
          <p className="text-slate-500 text-sm py-2">イベントなし</p>
        ) : (
          displayed.map(event => (
            <div
              key={event.event_id}
              ref={event.event_id === selectedId ? selectedRef : null}
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
  const [showOldDeleteConfirm, setShowOldDeleteConfirm] = useState(false)
  const [deletingOld, setDeletingOld] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [editingType, setEditingType] = useState(false)
  const [savingType, setSavingType] = useState(false)
  const [editingSubCat, setEditingSubCat] = useState(false)
  const [savingSubCat, setSavingSubCat] = useState(false)
  const [activeTab, setActiveTab] = useState<'events' | 'daily' | 'stats'>('events')
  const [subCategoryStats, setSubCategoryStats] = useState<SubCategoryStat[]>([])
  const [dailyStats, setDailyStats] = useState<DailyStat[]>([])
  const [dailyDays, setDailyDays] = useState(14)
  const [dailySubStats, setDailySubStats] = useState<DailySubStat | null>(null)
  const [dailyStatsByCamera, setDailyStatsByCamera] = useState<DailyStatByCamera[]>([])
  const [dailySubStatsByCamera, setDailySubStatsByCamera] = useState<DailySubStatByCamera | null>(null)

  const [similarResults, setSimilarResults] = useState<SimilarResult[]>([])
  const [similarLoading, setSimilarLoading] = useState(false)
  const [similarDone, setSimilarDone] = useState(0)
  const [similarTotal, setSimilarTotal] = useState(0)

  const unmountedRef = useRef(false)
  const similarSourceRef = useRef<EventSource | null>(null)
  const filteredEventsRef = useRef<DetectionEvent[]>([])

  useEffect(() => {
    setEditingType(false)
    setSavingType(false)
    setEditingSubCat(false)
    setSavingSubCat(false)
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

  useEffect(() => {
    if (activeTab === 'stats' || activeTab === 'daily') {
      eventApi.getSubCategoryStats().then(setSubCategoryStats).catch(() => {})
    }
    if (activeTab === 'daily') {
      eventApi.getDailyStats(dailyDays).then(setDailyStats).catch(() => {})
      eventApi.getDailyStatsByCamera(dailyDays).then(setDailyStatsByCamera).catch(() => {})
      if (activeFilter) {
        setDailySubStats(null)
        setDailySubStatsByCamera(null)
        eventApi.getDailySubStats(activeFilter, dailyDays).then(setDailySubStats).catch(() => {})
        eventApi.getDailySubStatsByCamera(activeFilter, dailyDays).then(setDailySubStatsByCamera).catch(() => {})
      } else {
        setDailySubStats(null)
        setDailySubStatsByCamera(null)
      }
    }
  }, [activeTab, dailyDays, activeFilter])

  useEffect(() => {
    eventApi.listEvents(0, 0).then(res => {
      setEvents(res.items)
      setSelectedEvent(prev =>
        prev ? (res.items.find(e => e.event_id === prev.event_id) ?? prev) : prev
      )
    }).catch(() => {})
  }, [activeTab, activeFilter])


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
          eventApi.listEvents(0, 0),
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
                return [event, ...prev]
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

  const handleSubCatChange = async (newSubCat: string) => {
    if (!selectedEvent || newSubCat === (selectedEvent.sub_category ?? '')) {
      setEditingSubCat(false)
      return
    }
    setEditingSubCat(false)
    setSavingSubCat(true)
    const prev = selectedEvent
    const updated = { ...selectedEvent, sub_category: newSubCat }
    setSelectedEvent(updated)
    setEvents(evs => evs.map(e => e.event_id === updated.event_id ? updated : e))
    try {
      await eventApi.updateEventSubCategory(selectedEvent.event_id, newSubCat)
    } catch {
      setSelectedEvent(prev)
      setEvents(evs => evs.map(e => e.event_id === prev.event_id ? prev : e))
    } finally {
      setSavingSubCat(false)
    }
  }

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 4000)
  }

  const handleDeleteOld = async () => {
    setDeletingOld(true)
    try {
      const result = await eventApi.deleteOldEvents(3)
      setEvents(prev => prev.filter(e => {
        const d = new Date(e.started_at)
        return (Date.now() - d.getTime()) < 3 * 24 * 60 * 60 * 1000
      }))
      setSelectedEvent(null)
      setShowOldDeleteConfirm(false)
      const updated = await eventApi.getSummary()
      setSummary(updated)
      showToast(result.deleted > 0 ? `${result.deleted} 件のデータを削除しました` : '削除対象はありませんでした')
    } catch {
      setShowOldDeleteConfirm(false)
      showToast('削除中にエラーが発生しました')
    } finally {
      setDeletingOld(false)
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
      const updated = await eventApi.getSummary()
      setSummary(updated)
    } catch {
      setConfirmTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (activeTab !== 'events') return
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      e.preventDefault()
      const filtered = filteredEventsRef.current
      if (filtered.length === 0) return
      const currentCamera = selectedEvent?.event_id.split('_')[0]
      const cameraEvents = currentCamera
        ? filtered.filter(ev => ev.event_id.startsWith(currentCamera + '_'))
        : filtered
      const currentIdx = cameraEvents.findIndex(ev => ev.event_id === selectedEvent?.event_id)
      if (e.key === 'ArrowDown') {
        const nextIdx = currentIdx === -1 ? 0 : Math.min(currentIdx + 1, cameraEvents.length - 1)
        setSelectedEvent(cameraEvents[nextIdx])
      } else {
        const nextIdx = currentIdx === -1 ? cameraEvents.length - 1 : Math.max(currentIdx - 1, 0)
        setSelectedEvent(cameraEvents[nextIdx])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeTab, selectedEvent?.event_id])

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
  filteredEventsRef.current = filteredEvents

  const cameras = Array.from(new Set(filteredEvents.map(e => e.event_id.split('_')[0]))).sort()
  const byCamera = (name: string) => filteredEvents.filter(e => e.event_id.startsWith(name + '_'))

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-xl bg-slate-700 border border-slate-500 text-white text-sm shadow-xl">
          {toast}
        </div>
      )}

      {confirmTarget && (
        <ConfirmModal
          eventId={confirmTarget.event_id}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setConfirmTarget(null)}
          loading={deleting}
        />
      )}

      {showOldDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl p-6 w-80">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-orange-500/20 flex items-center justify-center text-orange-400 text-lg">🗑</div>
              <h3 className="text-white font-semibold text-base">古いデータを削除</h3>
            </div>
            <p className="text-slate-300 text-sm mb-3">3日以上前のイベントをすべて削除します。</p>
            <p className="text-slate-400 text-xs mb-5">スナップショット・クリップ動画・類似判定データも削除されます。この操作は取り消せません。</p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowOldDeleteConfirm(false)}
                disabled={deletingOld}
                className="px-4 py-2 text-sm rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 transition disabled:opacity-50"
              >
                キャンセル
              </button>
              <button
                onClick={handleDeleteOld}
                disabled={deletingOld}
                className="px-4 py-2 text-sm rounded-lg bg-orange-600 hover:bg-orange-500 text-white font-medium transition disabled:opacity-50"
              >
                {deletingOld ? '削除中...' : '削除する'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <h1 className="text-2xl font-bold text-white tracking-tight">RemoteAICamera</h1>
          <span className="text-xs text-slate-500">全件表示</span>
          <button
            onClick={() => setShowOldDeleteConfirm(true)}
            className="text-xs px-3 py-1 rounded-lg bg-slate-700 hover:bg-orange-700 text-slate-300 hover:text-white transition"
          >
            3日以上前を削除
          </button>
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

        <div className="flex gap-1 border-b border-slate-700 mb-5">
          {([
            { id: 'events', label: 'イベント一覧' },
            { id: 'daily',  label: '日次集計' },
            { id: 'stats',  label: '統計' },
          ] as const).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'text-white border-sky-500'
                  : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'daily' && (() => {
          const CATS: { key: keyof DailyStat; label: string; color: string; barColor: string }[] = [
            { key: 'person',     label: '人',     color: 'bg-emerald-500', barColor: 'bg-emerald-500' },
            { key: 'car',        label: '車',     color: 'bg-sky-500',     barColor: 'bg-sky-500'     },
            { key: 'motorcycle', label: 'バイク', color: 'bg-orange-500',  barColor: 'bg-orange-500'  },
            { key: 'bicycle',    label: '自転車', color: 'bg-yellow-500',  barColor: 'bg-yellow-500'  },
            { key: 'pet',        label: 'ペット', color: 'bg-violet-500',  barColor: 'bg-violet-500'  },
            { key: 'other',      label: 'その他', color: 'bg-slate-500',   barColor: 'bg-slate-500'   },
          ]
          const SUB_COLORS = [
            'bg-sky-400', 'bg-emerald-400', 'bg-orange-400', 'bg-violet-400',
            'bg-rose-400', 'bg-teal-400', 'bg-amber-400', 'bg-indigo-400',
          ]

          const DailyBars = ({
            cat, color, barHeight = 64,
          }: {
            cat: keyof DailyStat; color: string; barHeight?: number
          }) => {
            const values = dailyStats.map(d => d[cat] as number)
            const maxVal = Math.max(...values, 1)
            if (dailyStats.length === 0) return (
              <div className="text-center text-slate-600 text-xs py-8">データなし</div>
            )
            return (
              <div className="flex items-end gap-1" style={{ height: `${barHeight + 36}px` }}>
                {dailyStats.map(d => {
                  const v = d[cat] as number
                  const pct = (v / maxVal) * 100
                  const dateLabel = (d.date as string).slice(5)
                  return (
                    <div key={d.date as string} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                      <span className="text-slate-400 text-xs leading-none">{v > 0 ? v : ''}</span>
                      <div className="w-full flex items-end" style={{ height: `${barHeight}px` }}>
                        <div
                          className={`w-full rounded-t ${color} transition-all`}
                          style={{ height: `${pct}%`, minHeight: v > 0 ? '2px' : '0' }}
                        />
                      </div>
                      <span className="text-slate-500 leading-none truncate w-full text-center text-xs">
                        {dateLabel}
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          }

          const StackedDailyBars = ({ barHeight = 120 }: { barHeight?: number }) => {
            if (!dailySubStats || Object.keys(dailySubStats.sub_categories).length === 0) {
              const cat = CATS.find(c => c.key === activeFilter)
              return cat ? <DailyBars cat={cat.key} color={cat.barColor} barHeight={barHeight} /> : null
            }
            const cat = CATS.find(c => c.key === activeFilter)
            const subEntries = Object.entries(dailySubStats.sub_categories) as [string, number[]][]
            const dates = dailySubStats.dates
            // dailyStats（全件）から正しい合計を取得し、未分類分を補完
            const trueTotals = dates.map(date => {
              const stat = dailyStats.find(d => d.date === date)
              return stat && activeFilter ? (stat[activeFilter as keyof DailyStat] as number) : 0
            })
            const maxVal = Math.max(...trueTotals, 1)
            const hasUnclassified = trueTotals.some((t, di) => {
              const classified = subEntries.reduce((s, [, vs]) => s + (vs[di] ?? 0), 0)
              return t > classified
            })
            return (
              <div>
                <div className="flex items-end gap-1" style={{ height: `${barHeight + 36}px` }}>
                  {dates.map((date, di) => {
                    const trueTotal = trueTotals[di]
                    const classified = subEntries.reduce((s, [, vs]) => s + (vs[di] ?? 0), 0)
                    const unclassified = Math.max(trueTotal - classified, 0)
                    const dateLabel = date.slice(5)
                    return (
                      <div key={date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                        <span className="text-slate-400 text-xs leading-none">{trueTotal > 0 ? trueTotal : ''}</span>
                        <div className="w-full flex flex-col-reverse" style={{ height: `${barHeight}px` }}>
                          {subEntries.map(([subCat, vals], i) => {
                            const v = vals[di] ?? 0
                            if (v === 0) return null
                            return (
                              <div
                                key={subCat}
                                className={`w-full ${SUB_COLORS[i % SUB_COLORS.length]}`}
                                style={{ height: `${(v / maxVal) * 100}%`, minHeight: '2px' }}
                                title={`${subCat}: ${v}`}
                              />
                            )
                          })}
                          {unclassified > 0 && cat && (
                            <div
                              className={`w-full ${cat.barColor} opacity-30`}
                              style={{ height: `${(unclassified / maxVal) * 100}%`, minHeight: '2px' }}
                              title={`未分類: ${unclassified}`}
                            />
                          )}
                        </div>
                        <span className="text-slate-500 leading-none truncate w-full text-center text-xs">
                          {dateLabel}
                        </span>
                      </div>
                    )
                  })}
                </div>
                {/* 凡例 */}
                <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                  {subEntries.map(([subCat], i) => (
                    <span key={subCat} className="flex items-center gap-1 text-xs text-slate-400">
                      <span className={`inline-block w-2.5 h-2.5 rounded-sm ${SUB_COLORS[i % SUB_COLORS.length]}`} />
                      {subCat}
                    </span>
                  ))}
                  {hasUnclassified && cat && (
                    <span className="flex items-center gap-1 text-xs text-slate-500">
                      <span className={`inline-block w-2.5 h-2.5 rounded-sm ${cat.barColor} opacity-30`} />
                      未分類
                    </span>
                  )}
                </div>
              </div>
            )
          }

          const DaySelector = () => (
            <select
              value={dailyDays}
              onChange={e => setDailyDays(Number(e.target.value))}
              className="text-xs bg-slate-700 text-slate-200 rounded-lg px-2 py-1.5 border border-slate-600 outline-none"
            >
              <option value={7}>直近 7日</option>
              <option value={14}>直近 14日</option>
              <option value={30}>直近 30日</option>
            </select>
          )

          // カテゴリ選択中: そのカテゴリのみ大きく + サブカテゴリ
          if (activeFilter !== null) {
            const cat = CATS.find(c => c.key === activeFilter)
            if (!cat) return null
            const values = dailyStats.map(d => d[cat.key] as number)
            const total  = values.reduce((a, b) => a + b, 0)

            return (
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                    日次集計 — {cat.label}
                  </h2>
                  <DaySelector />
                </div>

                {/* 日次ヒストグラム（大） */}
                <div className="bg-slate-900 rounded-xl p-4 mb-4">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{cat.label}</span>
                    <span className="text-xs text-slate-500">合計 {total}</span>
                  </div>
                  <StackedDailyBars barHeight={120} />
                </div>

                {/* カメラ別ヒストグラム */}
                {(() => {
                  if (dailyStatsByCamera.length === 0) return null
                  const camDates = Array.from(new Set(dailyStatsByCamera.map(d => d.date))).sort()
                  const camNames = Array.from(new Set(dailyStatsByCamera.map(d => d.camera_name))).sort()
                  const catKey = cat.key as keyof DailyStatByCamera
                  const lookup: Record<string, Record<string, number>> = {}
                  dailyStatsByCamera.forEach(d => {
                    if (!lookup[d.date]) lookup[d.date] = {}
                    lookup[d.date][d.camera_name] = d[catKey] as number
                  })
                  const camMax = Math.max(...dailyStatsByCamera.map(d => d[catKey] as number), 1)
                  const CAM_BORDER = ['border-sky-500', 'border-orange-400']
                  const CAM_TEXT   = ['text-sky-400',   'text-orange-400']
                  const CAM_DOT    = ['bg-sky-500',      'bg-orange-400']
                  const subCamData = dailySubStatsByCamera
                  const hasSubCam  = subCamData && subCamData.sub_categories.length > 0
                  return (
                    <div className="bg-slate-900 rounded-xl p-4 mb-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">カメラ別</span>
                        <div className="flex gap-3">
                          {camNames.map((cam, ci) => (
                            <span key={cam} className={`flex items-center gap-1 text-xs ${CAM_TEXT[ci % 2]}`}>
                              <span className={`inline-block w-2.5 h-2.5 rounded-sm ${CAM_DOT[ci % 2]}`} />
                              {cam}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-end gap-1.5" style={{ height: '156px' }}>
                        {camDates.map(date => {
                          const dateLabel = date.slice(5)
                          const subDateIdx = hasSubCam ? subCamData!.dates.indexOf(date) : -1
                          return (
                            <div key={date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                              <div className="w-full flex gap-0.5" style={{ height: '120px' }}>
                                {camNames.map((cam, ci) => {
                                  const v = lookup[date]?.[cam] ?? 0
                                  const camSubData = hasSubCam ? subCamData!.data[cam] : null
                                  return (
                                    <div key={cam} className="flex-1 flex flex-col items-center justify-end min-w-0">
                                      <span className={`text-xs leading-none mb-0.5 ${CAM_TEXT[ci % 2]}`}>
                                        {v > 0 ? v : ''}
                                      </span>
                                      <div
                                        className={`w-full flex flex-col-reverse border-b-2 ${CAM_BORDER[ci % 2]}`}
                                        style={{ height: `${(v / camMax) * 100}px`, minHeight: v > 0 ? '2px' : '0' }}
                                      >
                                        {camSubData && subDateIdx >= 0
                                          ? subCamData!.sub_categories.map((sub, si) => {
                                              const sv = camSubData[sub]?.[subDateIdx] ?? 0
                                              if (sv === 0) return null
                                              return (
                                                <div
                                                  key={sub}
                                                  className={`w-full ${SUB_COLORS[si % SUB_COLORS.length]}`}
                                                  style={{ height: `${(sv / v) * 100}%`, minHeight: '2px' }}
                                                  title={`${cam} ${sub}: ${sv}`}
                                                />
                                              )
                                            })
                                          : v > 0 && <div className={`w-full h-full ${cat.barColor}`} />
                                        }
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                              <span className="text-slate-500 leading-none truncate w-full text-center text-xs">
                                {dateLabel}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                      {hasSubCam && (
                        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
                          {subCamData!.sub_categories.map((sub, si) => (
                            <span key={sub} className="flex items-center gap-1 text-xs text-slate-400">
                              <span className={`inline-block w-2.5 h-2.5 rounded-sm ${SUB_COLORS[si % SUB_COLORS.length]}`} />
                              {sub}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })()}

                {/* サブカテゴリ別ヒストグラム */}
                <div className="bg-slate-900 rounded-xl p-4">
                  <div className="mb-4">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      サブカテゴリ別日次
                    </h3>
                  </div>
                  {!dailySubStats || Object.keys(dailySubStats.sub_categories).length === 0 ? (
                    <div className="text-center text-slate-500 text-sm py-8">
                      データがありません
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-3">
                      {(Object.entries(dailySubStats.sub_categories) as [string, number[]][]).map(([subCat, values], i) => {
                        const maxV = Math.max(...values, 1)
                        const total = values.reduce((a, b) => a + b, 0)
                        const color = SUB_COLORS[i % SUB_COLORS.length]
                        return (
                          <div key={subCat} className="bg-slate-800 rounded-lg p-3">
                            <div className="flex justify-between items-center mb-2">
                              <span className="flex items-center gap-1.5 text-sm text-slate-200">
                                <span className={`inline-block w-2.5 h-2.5 rounded-sm ${color}`} />
                                {subCat}
                              </span>
                              <span className="text-xs text-slate-400">合計 {total}</span>
                            </div>
                            <div className="flex items-end gap-1" style={{ height: '80px' }}>
                              {dailySubStats.dates.map((d, di) => {
                                const v = values[di] ?? 0
                                const pct = (v / maxV) * 100
                                return (
                                  <div key={d} className="flex-1 flex flex-col items-center min-w-0">
                                    <span className="text-slate-400 leading-none mb-0.5 text-xs">
                                      {v > 0 ? v : ''}
                                    </span>
                                    <div className="w-full flex items-end" style={{ height: '52px' }}>
                                      <div
                                        className={`w-full rounded-t ${color} transition-all`}
                                        style={{ height: `${pct}%`, minHeight: v > 0 ? '2px' : '0' }}
                                      />
                                    </div>
                                    <span className="text-slate-500 leading-none truncate w-full text-center mt-1"
                                          style={{ fontSize: '10px' }}>
                                      {d.slice(5)}
                                    </span>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            )
          }

          // すべて: 積み上げ全体 + 6カテゴリグリッド
          const allTotals = dailyStats.map(d =>
            CATS.reduce((sum, c) => sum + (d[c.key] as number), 0)
          )
          const allMax = Math.max(...allTotals, 1)
          const grandTotal = allTotals.reduce((a, b) => a + b, 0)

          return (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">日次集計</h2>
                <DaySelector />
              </div>

              {/* 全カテゴリ積み上げヒストグラム */}
              <div className="bg-slate-900 rounded-xl p-4">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">すべて</span>
                  <span className="text-xs text-slate-500">合計 {grandTotal}</span>
                </div>
                <div className="flex items-end gap-1" style={{ height: '156px' }}>
                  {dailyStats.map((d, di) => {
                    const total = allTotals[di]
                    const dateLabel = (d.date as string).slice(5)
                    return (
                      <div key={d.date as string} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                        <span className="text-slate-400 text-xs leading-none">{total > 0 ? total : ''}</span>
                        <div className="w-full flex flex-col-reverse" style={{ height: '120px' }}>
                          {CATS.map(c => {
                            const v = d[c.key] as number
                            if (v === 0) return null
                            const heightPct = (v / allMax) * 100
                            return (
                              <div
                                key={c.key}
                                className={`w-full ${c.barColor}`}
                                style={{ height: `${heightPct}%`, minHeight: '2px' }}
                                title={`${c.label}: ${v}`}
                              />
                            )
                          })}
                        </div>
                        <span className="text-slate-500 leading-none truncate w-full text-center text-xs">
                          {dateLabel}
                        </span>
                      </div>
                    )
                  })}
                </div>
                {/* 凡例 */}
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                  {CATS.map(c => (
                    <span key={c.key} className="flex items-center gap-1 text-xs text-slate-400">
                      <span className={`inline-block w-2.5 h-2.5 rounded-sm ${c.barColor}`} />
                      {c.label}
                    </span>
                  ))}
                </div>
              </div>

              {/* カメラ別積み上げヒストグラム */}
              {(() => {
                if (dailyStatsByCamera.length === 0) return null
                const camDates = Array.from(new Set(dailyStatsByCamera.map(d => d.date))).sort()
                const camNames = Array.from(new Set(dailyStatsByCamera.map(d => d.camera_name))).sort()
                const lookup: Record<string, Record<string, DailyStatByCamera>> = {}
                dailyStatsByCamera.forEach(d => {
                  if (!lookup[d.date]) lookup[d.date] = {}
                  lookup[d.date][d.camera_name] = d
                })
                const allTotals = dailyStatsByCamera.map(d =>
                  CATS.reduce((s, c) => s + (d[c.key] as number), 0)
                )
                const camMax = Math.max(...allTotals, 1)
                const CAM_BORDER = ['border-sky-500', 'border-orange-400']
                const CAM_TEXT   = ['text-sky-400',   'text-orange-400']
                const CAM_DOT    = ['bg-sky-500',      'bg-orange-400']
                return (
                  <div className="bg-slate-900 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">カメラ別</span>
                      <div className="flex gap-3">
                        {camNames.map((cam, ci) => (
                          <span key={cam} className={`flex items-center gap-1 text-xs ${CAM_TEXT[ci % 2]}`}>
                            <span className={`inline-block w-2.5 h-2.5 rounded-sm ${CAM_DOT[ci % 2]}`} />
                            {cam}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-end gap-1.5" style={{ height: '156px' }}>
                      {camDates.map(date => {
                        const dateLabel = date.slice(5)
                        return (
                          <div key={date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                            <div className="w-full flex gap-0.5" style={{ height: '120px' }}>
                              {camNames.map((cam, ci) => {
                                const row = lookup[date]?.[cam]
                                const total = row ? CATS.reduce((s, c) => s + (row[c.key] as number), 0) : 0
                                return (
                                  <div key={cam} className="flex-1 flex flex-col items-center justify-end min-w-0">
                                    <span className={`text-xs leading-none mb-0.5 ${CAM_TEXT[ci % 2]}`}>
                                      {total > 0 ? total : ''}
                                    </span>
                                    <div
                                      className={`w-full flex flex-col-reverse border-b-2 ${CAM_BORDER[ci % 2]}`}
                                      style={{ height: `${(total / camMax) * 100}px`, minHeight: total > 0 ? '2px' : '0' }}
                                    >
                                      {row && CATS.map(c => {
                                        const v = row[c.key] as number
                                        if (v === 0) return null
                                        return (
                                          <div
                                            key={c.key}
                                            className={`w-full ${c.barColor}`}
                                            style={{ height: `${(v / total) * 100}%`, minHeight: '2px' }}
                                            title={`${cam} ${c.label}: ${v}`}
                                          />
                                        )
                                      })}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                            <span className="text-slate-500 leading-none truncate w-full text-center text-xs">
                              {dateLabel}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                    {/* カテゴリ凡例 */}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                      {CATS.map(c => (
                        <span key={c.key} className="flex items-center gap-1 text-xs text-slate-400">
                          <span className={`inline-block w-2.5 h-2.5 rounded-sm ${c.barColor}`} />
                          {c.label}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })()}

              {/* カテゴリ別グリッド */}
              <div className="grid grid-cols-2 gap-4">
                {CATS.map(c => {
                  const values = dailyStats.map(d => d[c.key] as number)
                  return (
                    <div key={c.key} className="bg-slate-900 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{c.label}</h3>
                        <span className="text-xs text-slate-500">合計 {values.reduce((a, b) => a + b, 0)}</span>
                      </div>
                      <DailyBars cat={c.key} color={c.barColor} barHeight={64} />
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })()}

        {activeTab === 'stats' && (() => {
          const CAT_LABEL: Record<string, string> = {
            person: '人', car: '車', motorcycle: 'バイク',
            bicycle: '自転車', pet: 'ペット', other: 'その他',
          }
          const CAT_COLOR: Record<string, string> = {
            person: 'bg-emerald-500', car: 'bg-sky-500', motorcycle: 'bg-orange-500',
            bicycle: 'bg-yellow-500', pet: 'bg-violet-500', other: 'bg-slate-500',
          }
          const SUB_COLORS = [
            'bg-sky-400', 'bg-emerald-400', 'bg-orange-400', 'bg-violet-400',
            'bg-rose-400', 'bg-teal-400', 'bg-amber-400', 'bg-indigo-400',
          ]
          // ai/sub_category_client.py の SUB_CATEGORIES と同期
          const SUB_CATEGORY_DEFS: Record<string, string[]> = {
            person:     ['子供', '学生', '成人（男性）', '成人（女性）', '高齢者', 'グループ', '不明'],
            car:        ['軽自動車', '軽トラック', 'セダン/ハッチバック', 'SUV', 'ミニバン/ワンボックス', 'バン（商用）', 'トラック', 'バス', '不明'],
            motorcycle: ['スクーター', 'ビッグスクーター', 'ネイキッド', 'スポーツ（フルカウル）', 'クルーザー（アメリカン）', 'オフロード', 'アドベンチャー', '不明'],
            bicycle:    ['シティサイクル', '電動アシスト', 'ロードバイク', 'マウンテンバイク', 'クロスバイク', '子供用/その他', '不明'],
            pet:        ['犬', '猫', 'その他動物', '不明'],
          }
          // 定義済みカテゴリはゼロ補完、その他は動的
          const fillRows = (cat: string) => {
            const defs = SUB_CATEGORY_DEFS[cat]
            const statsMap = Object.fromEntries(
              subCategoryStats.filter(s => s.detection_type === cat).map(s => [s.sub_category, s.count])
            )
            if (defs) {
              return defs
                .map(sub => ({ sub_category: sub, count: statsMap[sub] ?? 0 }))
                .sort((a, b) => b.count - a.count)
            }
            // その他: 動的（出現したものだけ表示）
            return subCategoryStats
              .filter(s => s.detection_type === cat)
              .sort((a, b) => b.count - a.count)
          }


          // 個別カテゴリ選択時: そのカテゴリのみ・サブカテゴリ色分け・分類ボタンあり
          if (activeFilter !== null) {
            const rows = fillRows(activeFilter)
            const maxCount = Math.max(...rows.map(r => r.count), 1)
            return (
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 text-white">
                <div className="mb-5">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                    {CAT_LABEL[activeFilter] ?? activeFilter} サブカテゴリ統計
                  </h2>
                </div>
                {rows.length === 0 ? (
                  <div className="text-center text-slate-500 text-sm py-16">
                    データがありません
                  </div>
                ) : (
                  <div className="space-y-3">
                    {rows.map((row, i) => (
                      <div key={row.sub_category}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="flex items-center gap-2 text-slate-200">
                            <span className={`inline-block w-2.5 h-2.5 rounded-sm ${SUB_COLORS[i % SUB_COLORS.length]}`} />
                            {row.sub_category}
                          </span>
                          <span className="text-slate-400">{row.count}</span>
                        </div>
                        <div className="w-full bg-slate-700 rounded-full h-3">
                          <div
                            className={`${SUB_COLORS[i % SUB_COLORS.length]} h-3 rounded-full transition-all`}
                            style={{ width: `${(row.count / maxCount) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          }

          // すべて選択時: 全カテゴリをグリッド表示・分類ボタンなし
          const CAT_ORDER = ['person', 'car', 'motorcycle', 'bicycle', 'pet', 'other']
          const categories = CAT_ORDER.filter(cat =>
            subCategoryStats.some(s => s.detection_type === cat)
          )
          return (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 text-white">
              <div className="mb-5">
                <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">サブカテゴリ統計</h2>
              </div>
              {categories.length === 0 ? (
                <div className="text-center text-slate-500 text-sm py-16">
                  データがありません
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-5">
                  {categories.map(cat => {
                    const rows = fillRows(cat)
                    const maxCount = Math.max(...rows.map(r => r.count), 1)
                    const barColor = CAT_COLOR[cat] ?? 'bg-slate-500'
                    return (
                      <div key={cat} className="bg-slate-900 rounded-lg p-4">
                        <h3 className="text-xs font-semibold text-slate-400 uppercase mb-3">
                          {CAT_LABEL[cat] ?? cat}
                        </h3>
                        <div className="space-y-2">
                          {rows.map(row => (
                            <div key={row.sub_category}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="text-slate-300">{row.sub_category}</span>
                                <span className="text-slate-400">{row.count}</span>
                              </div>
                              <div className="w-full bg-slate-700 rounded-full h-2">
                                <div
                                  className={`${barColor} h-2 rounded-full transition-all`}
                                  style={{ width: `${(row.count / maxCount) * 100}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })()}

        {activeTab === 'events' && <div className="grid grid-cols-3 gap-5">
          <div className="col-span-2 flex flex-col gap-3">
            {cameras.map(name => (
              <EventList
                key={name}
                cameraName={name}
                events={byCamera(name)}
                selectedId={selectedEvent?.event_id ?? null}
                onSelect={setSelectedEvent}
                showSubFilter={activeFilter !== null}
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
                    <div className="text-xs text-slate-500 mb-0.5">サブカテゴリ</div>
                    {editingSubCat ? (
                      <select
                        autoFocus
                        defaultValue={selectedEvent.sub_category ?? ''}
                        onChange={e => handleSubCatChange(e.target.value)}
                        onBlur={() => setEditingSubCat(false)}
                        className="text-xs bg-slate-700 text-white rounded px-1 py-0.5 border border-slate-500 outline-none w-full"
                      >
                        <option value="">— 選択 —</option>
                        {(SUB_CATEGORY_OPTIONS[selectedEvent.detection_type] ?? []).map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    ) : savingSubCat ? (
                      <span className="text-xs text-slate-400 flex items-center gap-1.5">
                        <span className="w-3 h-3 border-2 border-slate-400/40 border-t-slate-400 rounded-full animate-spin" />
                        保存中...
                      </span>
                    ) : (
                      <span
                        onClick={() => SUB_CATEGORY_OPTIONS[selectedEvent.detection_type] && setEditingSubCat(true)}
                        title={SUB_CATEGORY_OPTIONS[selectedEvent.detection_type] ? 'クリックしてサブカテゴリを変更' : undefined}
                        className={`text-xs text-slate-300 ${SUB_CATEGORY_OPTIONS[selectedEvent.detection_type] ? 'cursor-pointer hover:text-white' : ''}`}
                      >
                        {selectedEvent.sub_category ?? '—'}
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
        </div>}
      </div>
    </div>
  )
}

export default App
