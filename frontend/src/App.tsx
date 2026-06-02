import { useEffect, useState } from 'react'
import { eventApi } from './api'
import type { Summary, DetectionEvent } from './types'
import './index.css'

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
          eventApi.listEvents(50, 0),
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

  if (loading) return <div className="p-8 text-center">Loading...</div>
  if (error) return <div className="p-8 text-red-500">Error: {error}</div>

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
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

        {/* Main Content */}
        <div className="grid grid-cols-3 gap-8">
          {/* Event List */}
          <div className="col-span-2 bg-slate-700 rounded-lg p-6 text-white">
            <h2 className="text-2xl font-bold mb-4">Events Timeline</h2>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {events.length === 0 ? (
                <p className="text-gray-400">No events yet</p>
              ) : (
                events.map(event => (
                  <div
                    key={event.event_id}
                    className="bg-slate-600 p-3 rounded cursor-pointer hover:bg-slate-500 transition"
                    onClick={() => setSelectedEvent(event)}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-semibold text-sm">{event.event_id}</div>
                        <div className="text-xs text-gray-300">
                          {new Date(event.started_at).toLocaleString('ja-JP')}
                        </div>
                      </div>
                      <span className={`text-xs font-bold px-2 py-1 rounded ${
                        event.detection_type.includes('person') ? 'bg-green-600' : 'bg-blue-600'
                      }`}>
                        {event.detection_type}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Detail Panel */}
          <div className="bg-slate-700 rounded-lg p-6 text-white h-96 overflow-y-auto">
            <h2 className="text-2xl font-bold mb-4">Details</h2>
            {selectedEvent ? (
              <div className="space-y-4 text-sm">
                {selectedEvent.snapshot_url && (
                  <div className="mb-4">
                    <img src={selectedEvent.snapshot_url} alt="snapshot" className="w-full rounded" />
                  </div>
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
                  <div className="text-gray-400">Duration</div>
                  <div>{selectedEvent.duration_sec?.toFixed(2) || 'N/A'} sec</div>
                </div>
                {selectedEvent.face_label && (
                  <div>
                    <div className="text-gray-400">Face Label</div>
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
