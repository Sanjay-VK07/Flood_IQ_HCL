export type RiskBand = "Low" | "Moderate" | "High" | "Critical";

export type UserRole = "citizen" | "authority" | "response_team";

export interface AuthUser {
  user_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface ScoreComponent {
  raw: number;
  weight: number;
  contribution: number;
}

export interface PrepAction {
  action: string;
  reason: string;
}

export interface EvaluatedZone {
  zone_id: string;
  zone_name: string;
  latitude: number;
  longitude: number;
  drainage_score: number;
  low_lying_score: number;
  rainfall_mm: number;
  rainfall_source: string;
  forecast_precipitation_6h_mm?: number | null;
  forecast_window_start?: string | null;
  forecast_window_end?: string | null;
  forecast_source?: string | null;
  elevation_m?: number | null;
  risk_score: number;
  risk_level: RiskBand;
  reasons: string[];
  score_breakdown: {
    rainfall: ScoreComponent;
    drainage: ScoreComponent;
    low_lying: ScoreComponent;
  };
  prep_checklist: PrepAction[];
}

export interface ZoneRaw {
  zone_id: string;
  zone_name: string;
  latitude: number;
  longitude: number;
  drainage_score: number;
  low_lying_score: number;
  description: string;
}

export interface Incident {
  incident_id: string;
  zone_id: string;
  description: string;
  location_text: string;
  reported_category: string;
  people_affected: number;
  ai_category: string | null;
  ai_urgency: string | null;
  vulnerable_flag: number | boolean;
  vulnerable_group: string;
  stranded: number | boolean;
  unable_to_evacuate: number | boolean;
  immediate_hazard: number | boolean;
  ai_rationale: string;
  triage_mode: string | null;
  priority_score: number;
  operator_priority: number | null;
  status: string;
  assigned_team_id: string | null;
  created_by_user_id?: string | null;
  reporter_type?: string | null;
  tracking_code?: string | null;
  photo_data_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicTrackResponse {
  incident: {
    incident_id: string;
    tracking_code: string;
    zone_id: string;
    location_text: string;
    reported_category: string;
    ai_category: string | null;
    ai_urgency: string | null;
    status: string;
    assigned_team_id: string | null;
    reporter_type: string | null;
    created_at: string;
    updated_at: string;
  };
  timeline: IncidentUpdate[];
}

export interface TeamIncidentsResponse {
  team: ResponseTeam | null;
  incidents: Incident[];
}

export interface PriorityFactor {
  score: number;
  weight: number;
  contribution: number;
}

export interface PriorityBreakdown {
  priority_score: number;
  priority_band: RiskBand;
  factors: {
    severity: PriorityFactor;
    stranded: PriorityFactor;
    vulnerability: PriorityFactor;
    people_affected: PriorityFactor;
    hazard: PriorityFactor;
  };
  priority_rationale: string;
}

export interface IncidentUpdate {
  update_id: string;
  incident_id: string;
  old_status: string | null;
  new_status: string | null;
  assigned_team_id?: string | null;
  note: string;
  updated_at: string;
}

export interface ResponseTeam {
  team_id: string;
  team_name: string;
  specialty: string;
  base_zone: string;
  latitude: number;
  longitude: number;
  status: "Available" | "Assigned" | "Unavailable";
  current_incident_id: string | null;
}

export interface TeamCandidate {
  team: ResponseTeam;
  match_score: number;
  specialty_score: number;
  distance_score: number;
  distance_km: number;
  distance_desc: string;
  reason: string;
}

export interface TeamRecommendation {
  recommended_team: ResponseTeam | null;
  match_score?: number;
  match_reason: string;
  distance_km?: number;
  distance_desc?: string;
  alternatives: TeamCandidate[];
  available_team_count: number;
}

export interface WeatherContext {
  mode: string;
  source_label: string;
  use_simulation: boolean;
  rainfall_mm: number;
}

export interface DashboardResponse {
  weather: WeatherContext;
  risk_summary: Record<RiskBand, number>;
  zones: EvaluatedZone[];
  incidents: Incident[];
  teams: ResponseTeam[];
  recent_activity: IncidentUpdate[];
}

export interface RiskResponse {
  mode: string;
  source_label: string;
  use_simulation: boolean;
  rainfall_mm: number;
  model_mode?: string;
  dataset_available?: boolean;
  zones: EvaluatedZone[];
  summary: Record<RiskBand, number>;
}

export interface DatasetStatusResponse {
  available: boolean;
  generated_at?: string;
  cache_age_seconds?: number;
  record_count?: number;
  date_coverage?: {
    start: string | null;
    end: string | null;
    pilot_zone_archive_window: string;
  };
  geographic_coverage?: {
    zenodo_total_global_records: number;
    zenodo_india_records: number;
    zenodo_within_300km_hyderabad: number;
    zenodo_within_100km_hyderabad: number;
  };
  class_distribution?: Record<string, number>;
}

export interface HistoricalWeatherResponse {
  zone_id: string;
  zone_name: string;
  elevation_m: number | null;
  summary: {
    total_days?: number;
    max_24h_mm?: number | null;
    p95_24h_mm?: number | null;
    mean_24h_mm?: number | null;
  };
  records: {
    date: string;
    rainfall_24h: number | null;
    relative_humidity: number | null;
    temperature: number | null;
    soil_moisture: number | null;
    flood_event: string;
  }[];
}

export interface SystemStatusResponse {
  weather: {
    connected: boolean;
    latency_ms: number | null;
    error: string | null;
    offline_mode: boolean;
  };
  ai: {
    provider?: string;
    mode: string;
    model: string;
    groq_configured: boolean;
    offline_mode: boolean;
    fallback_active?: boolean;
    latest_provider_status?: string;
    rate_limited?: boolean;
    cooldown_remaining_seconds?: number;
    last_success_at?: string | null;
    last_error?: string | null;
    cache_entries?: number;
    cache_hits?: number;
  };
  radar?: {
    available: boolean;
    data_type: string;
    tile_url_template: string | null;
    attribution: string;
    latest_frame_time?: number | null;
    past_frame_count?: number;
  };
  database: {
    engine: string;
    incident_count: number;
    team_count: number;
    zone_count: number;
  };
  formulas: {
    risk: {
      expression: string;
      weights: Record<string, number>;
      rainfall_ceiling_mm: number;
    };
    priority: {
      expression: string;
      weights: Record<string, number>;
    };
  };
  status_transitions: Record<string, string[]>;
  limitations: string[];
}
