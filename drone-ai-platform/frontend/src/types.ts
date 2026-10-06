export type SourceMode = 'px4' | 'mock' | 'offline';

export interface ActiveAlert {
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  category: string;
  title: string;
  message: string;
}

export interface HomePosition {
  latitude: number;
  longitude: number;
  altitude_m: number;
}

export interface Telemetry {
  timestamp: string;
  connected: boolean;
  connection_state: string;
  source: SourceMode;
  armed: boolean;
  in_air: boolean;
  flight_mode: string;
  latitude: number | null;
  longitude: number | null;
  absolute_altitude_m: number | null;
  relative_altitude_m: number | null;
  ground_speed_m_s: number | null;
  airspeed_m_s: number | null;
  heading_deg: number | null;
  battery_remaining_pct: number | null;
  battery_voltage_v: number | null;
  battery_current_a: number | null;
  gps_satellites: number | null;
  gps_fix_type: string | null;
  ekf_ok: boolean | null;
  global_position_ok: boolean | null;
  local_position_ok: boolean | null;
  home_position_ok: boolean | null;
  gyro_ok: boolean | null;
  accelerometer_ok: boolean | null;
  magnetometer_ok: boolean | null;
  home_position: HomePosition | null;
  distance_from_home_m: number | null;
  flight_time_seconds: number;
  link_quality_pct: number | null;
  cpu_load_pct: number | null;
  system_status: string;
  last_error: string | null;
  flight_risk_score: number;
  drone_health_score: number;
  anomaly_count: number;
  active_alerts: ActiveAlert[];
  warnings: string[];
  recommendations: string[];
}

export interface User {
  id: string;
  email: string;
  role: 'operator' | 'admin';
  created_at: string;
}

export interface AuthPayload {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export interface Waypoint {
  id?: string;
  sequence?: number;
  latitude: number;
  longitude: number;
  altitude_m: number;
  hold_time_s: number;
}

export interface Mission {
  id: string;
  owner_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  waypoints: Waypoint[];
}

export interface Flight {
  id: string;
  name: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  max_altitude_m: number;
  distance_m: number;
  telemetry_count: number;
  max_risk_score: number;
  battery_start_pct: number | null;
  battery_end_pct: number | null;
  summary: string | null;
}

export interface AlertRecord extends ActiveAlert {
  id: string;
  occurred_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  details: Record<string, unknown>;
}

export interface TelemetryRecord {
  id: number;
  timestamp: string;
  connected: boolean;
  source: string;
  latitude: number | null;
  longitude: number | null;
  relative_altitude_m: number | null;
  ground_speed_m_s: number | null;
  heading_deg: number | null;
  battery_remaining_pct: number | null;
  battery_voltage_v: number | null;
  gps_satellites: number | null;
  armed: boolean;
  in_air: boolean;
  flight_mode: string;
  flight_risk_score: number;
  drone_health_score: number;
  payload: Record<string, unknown>;
}

export interface AnalyticsSummary {
  flight_risk_score: number;
  drone_health_score: number;
  anomaly_count: number;
  active_alerts: ActiveAlert[];
  recommendations: string[];
  anomaly_timeline: Array<{
    timestamp: string;
    flight_risk_score: number;
    drone_health_score: number;
    anomaly_count: number;
  }>;
  history_samples: number;
  model: string;
  source: string;
}

export interface SystemEvent {
  id: number;
  level: string;
  category: string;
  message: string;
  created_at: string;
  details: Record<string, unknown>;
}

export interface SystemStatus {
  api: string;
  database: string;
  telemetry_mode: string;
  px4: string;
  mavsdk: string;
  websocket_clients: number;
  last_telemetry_at: string | null;
  frontend: string;
}
