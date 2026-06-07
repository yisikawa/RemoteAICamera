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
  sub_category: string | null;
}

export interface EventsListResponse {
  items: DetectionEvent[];
  total: number;
}

export interface SimilarResult {
  event_id: string
  started_at: string
  detection_type: string
  snapshot_url: string | null
  verdict: 'SAME' | 'DIFFERENT'
  reason: string
  compared_at?: string
}

export interface SubCategoryStat {
  detection_type: string
  sub_category: string
  count: number
}

export interface ClassifyProgress {
  done: number
  total: number
  event_id?: string
  detection_type?: string
  sub_category?: string
  finished: boolean
}

export interface DailySubStat {
  dates: string[]
  sub_categories: Record<string, number[]>
}

export interface DailyStat {
  date: string
  person: number
  car: number
  motorcycle: number
  bicycle: number
  pet: number
  other: number
}

export interface Summary {
  total_events: number;
  snapshots: number;
  person: number;
  car: number;
  motorcycle: number;
  bicycle: number;
  pet: number;
  other: number;
}
