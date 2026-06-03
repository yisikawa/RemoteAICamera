import { useEffect, useState } from 'react'
import { eventApi } from './api'
import type { Summary, DetectionEvent } from './types'
import './index.css'

const TYPE_COLOR: Record<string, string> = {
  person:  'bg-green-600',
  vehicle: 'bg-blue-600',
  motion:  'bg-gray-500',
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
    <div className="bg-slate-700 rounded-lg p-4 text-white">
      <h2 className="text-lg font-bold mb-3">{cameraName}</h2>
      <div className="space-y-2 overflow-y-auto" style={{ maxHeight: '220px' }}>
        {events.length === 0 ? (
          <p className="text-gray-400 text-sm">No events yet</p>
        ) : (
          events.map(event => (
            <div
              key={event.event_id}
              onClick={() => onSelect(event)}
              className={`p-3 rounded cursor-pointer transition ${
                event.event_id === selectedId
                  ? 'bg-slate-400'
                  : 'bg-slate-600 hover:bg-slate-500'
              }`}
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold text-sm">{event.event_id}</div>
                  <div className="text-xs text-gray-300">
                    {new Date(event.started_at).toLocaleString('ja-JP')}
                  </div>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded ${
                  TYPE_COLOR[event.detection_type] ?? 'bg-gray-500'
                }`}>
                  {event.detection_type}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [events, setEvents] = useState<DetectionEvent[]>([])
  const [selectedEvent, setSelectedEvent] = useState<DetectionEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryData, eventsData] = await Promise.all([
          eventApi.getSummary(),
          eventApi.listEvents(100, 0),
        ])
        setSummary(summaryData)
        setEvents(eventsData.items)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error loading data')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) return <div className="p-8 text-center text-white">Loading...</div>
  if (error)   return <div className="p-8 text-red-500">Error: {error}</div>

  const cameras = Array.from(new Set(events.map(e => e.event_id.split('_')[0]))).sort()
  const byCamera = (name: string) => events.filter(e => e.event_id.startsWith(name + '_'))

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold text-white mb-8">RemoteAICamera Dashboard</h1>

        {/* Stats */}
        {summary && (
          <div className="grid grid-cols-4 gap-4 mb-8">
            <div className="bg-blue-600 rounded-lg p-4 text-white">
              <div className="text-sm opacity-90">Total Events</div>
              <div className="text-3xl font-bold">{summary.total_events}</div>
            </div>
            <div className="bg-green-600 rounded-lg p-4 text-white">
              <div className="text-sm opacity-90">Person Events</div>
              <div className="text-3xl font-bold">{summary.person_events}</div>
            </div>
            <div className="bg-purple-600 rounded-lg p-4 text-white">
              <div className="text-sm opacity-90">Vehicle Events</div>
              <div className="text-3xl font-bold">{summary.vehicle_events}</div>
            </div>
            <div className="bg-orange-600 rounded-lg p-4 text-white">
              <div className="text-sm opacity-90">Snapshots</div>
              <div className="text-3xl font-bold">{summary.snapshots}</div>
            </div>
          </div>
        )}

        {/* Main: カメラ別リスト(左) + Details(右) */}
        <div className="grid grid-cols-3 gap-8">
          {/* カメラごとに縦2段 */}
          <div className="col-span-2 flex flex-col gap-4">
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

          {/* Detail Panel */}
          <div className="bg-slate-700 rounded-lg p-6 text-white flex flex-col h-full">
            <h2 className="text-2xl font-bold mb-4">Details</h2>
            {selectedEvent ? (
              <div className="space-y-4 text-sm overflow-y-auto flex-1">
                {selectedEvent.clip_url ? (
                  <video
                    key={selectedEvent.clip_url}
                    src={selectedEvent.clip_url}
                    poster={selectedEvent.snapshot_url ?? undefined}
                    controls
                    className="w-full rounded"
                  />
                ) : selectedEvent.snapshot_url && (
                  <img src={selectedEvent.snapshot_url} alt="snapshot" className="w-full rounded" />
                )}
                <div>
                  <div className="text-gray-400">Event ID</div>
                  <div className="font-mono text-xs break-all">{selectedEvent.event_id}</div>
                </div>
                <div>
                  <div className="text-gray-400">Type</div>
                  <div>{selectedEvent.detection_type}</div>
                </div>
                <div>
                  <div className="text-gray-400">Time</div>
                  <div>{new Date(selectedEvent.started_at).toLocaleString('ja-JP')}</div>
                </div>
                <div>
                  <div className="text-gray-400">Duration</div>
                  <div>{selectedEvent.duration_sec?.toFixed(1) ?? 'N/A'} sec</div>
                </div>
                <div>
                  <div className="text-gray-400">Frames</div>
                  <div>{selectedEvent.frame_count ?? 'N/A'}</div>
                </div>
                {selectedEvent.face_label && (
                  <div>
                    <div className="text-gray-400">Face</div>
                    <div>{selectedEvent.face_label} ({selectedEvent.face_confidence?.toFixed(2)})</div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-400">Select an event to view details</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
