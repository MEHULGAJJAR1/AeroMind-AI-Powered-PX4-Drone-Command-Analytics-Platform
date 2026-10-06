import type {
  AlertRecord,
  AnalyticsSummary,
  AuthPayload,
  Flight,
  Mission,
  SystemStatus,
  SystemEvent,
  Telemetry,
  TelemetryRecord,
  User,
  Waypoint,
} from '../types';

const API_ROOT = '/api';

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  return window.localStorage.getItem('aeromind.accessToken');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code: string | undefined;
    try {
      const body = await response.json();
      message = body?.error?.message || body?.detail || message;
      code = body?.error?.code;
    } catch {
      // Some upstream proxy errors are plain text; keep the safe status message.
    }
    throw new ApiError(message, response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    request<AuthPayload>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    request<AuthPayload>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),
  wsTicket: () => request<{ ticket: string; expires_in: number }>('/auth/ws-ticket', { method: 'POST' }),
  latest: () => request<Telemetry>('/telemetry/latest'),
  telemetryHistory: (limit = 250) => request<TelemetryRecord[]>(`/telemetry/history?limit=${limit}`),
  droneStatus: () => request<Telemetry & { configured_mode: string; control_enabled: boolean }>('/drone/status'),
  connect: () => request<{ accepted: boolean; mode: string; message: string }>('/drone/connect', { method: 'POST' }),
  command: (command: string, extra: Record<string, unknown> = {}) =>
    request<{ accepted: boolean; message: string }>('/drone/command', {
      method: 'POST',
      body: JSON.stringify({ command, ...extra }),
    }),
  missions: () => request<Mission[]>('/missions'),
  createMission: (name: string, waypoints: Waypoint[] = []) =>
    request<Mission>('/missions', { method: 'POST', body: JSON.stringify({ name, waypoints }) }),
  updateMission: (id: string, name: string, waypoints: Waypoint[]) =>
    request<Mission>(`/missions/${id}`, { method: 'PUT', body: JSON.stringify({ name, waypoints }) }),
  deleteMission: (id: string) => request<void>(`/missions/${id}`, { method: 'DELETE' }),
  uploadMission: (id: string) => request<{ accepted: boolean; message: string }>(`/missions/${id}/upload`, { method: 'POST' }),
  flights: () => request<Flight[]>('/flights'),
  alerts: (unacknowledgedOnly = false) => request<AlertRecord[]>(`/alerts${unacknowledgedOnly ? '?acknowledged=false' : ''}`),
  acknowledgeAlert: (id: string) => request<AlertRecord>(`/alerts/${id}/acknowledge`, { method: 'POST' }),
  analytics: () => request<AnalyticsSummary>('/analytics/summary'),
  systemStatus: () => request<SystemStatus>('/system/status'),
  systemEvents: () => request<SystemEvent[]>('/system/events?limit=25'),
};

export function downloadUrl(path: string): string {
  const token = getToken();
  return token ? `${API_ROOT}${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : `${API_ROOT}${path}`;
}

export function telemetrySocketUrl(token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/telemetry?token=${encodeURIComponent(token)}`;
}
