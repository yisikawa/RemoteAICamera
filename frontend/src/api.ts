import axios from 'axios';
import type { DetectionEvent, EventsListResponse, SimilarResult, SubCategoryStat, Summary } from './types';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

export const eventApi = {
  listEvents: async (limit = 50, offset = 0): Promise<EventsListResponse> => {
    const res = await api.get('/api/events', { params: { limit, offset } });
    return res.data;
  },

  getEvent: async (eventId: string): Promise<DetectionEvent> => {
    const res = await api.get(`/api/events/${eventId}`);
    return res.data;
  },

  getSummary: async (): Promise<Summary> => {
    const res = await api.get('/api/stats/summary');
    return res.data;
  },

  deleteEvent: async (eventId: string): Promise<void> => {
    await api.delete(`/api/events/${eventId}`);
  },

  updateEventType: async (eventId: string, detectionType: string): Promise<DetectionEvent> => {
    const res = await api.patch(`/api/events/${eventId}`, { detection_type: detectionType });
    return res.data;
  },

  getSimilarities: async (eventId: string): Promise<SimilarResult[]> => {
    const res = await api.get(`/api/events/${eventId}/similarities`);
    return res.data;
  },

  getSubCategoryStats: async (): Promise<SubCategoryStat[]> => {
    const res = await api.get('/api/stats/sub-categories');
    return res.data;
  },
};
