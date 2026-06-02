export interface DetectionEvent {
  event_id: string;
  started_at: string;
  ended_at: string;
  duration_sec: number | null;
  detection_type: string;
  face_label: string | null;
  face_confidence: number | null;
  plate_number: string | null;
  plate_confidence: number | null;
  vehicle_color: string | null;
  vehicle_type: string | null;
  ai_description: string | null;
  snapshot_url: string | null;
  clip_url: string | null;
  frame_count: number | null;
}

export interface EventsListResponse {
  items: DetectionEvent[];
  total: number;
}

export interface Summary {
  total_events: number;
  person_events: number;
  vehicle_events: number;
  snapshots: number;
}
