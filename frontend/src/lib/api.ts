import type {
  AuthUser,
  DashboardResponse,
  DatasetStatusResponse,
  HistoricalWeatherResponse,
  Incident,
  IncidentUpdate,
  LoginResponse,
  PriorityBreakdown,
  PublicTrackResponse,
  ResponseTeam,
  RiskResponse,
  SystemStatusResponse,
  TeamIncidentsResponse,
  TeamRecommendation,
  ZoneRaw,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return API_BASE;
}

const TOKEN_STORAGE_KEY = "floodiq_auth_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `API error ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.detail) {
        message = typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail);
      }
    } catch {
      // ignore non-JSON error
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    request<{ status: string }>("/api/auth/logout", {
      method: "POST",
    }),

  getMe: () => request<{ user: AuthUser }>("/api/auth/me"),

  getDashboard: (rainfallMm: number, useSimulation: boolean) =>
    request<DashboardResponse>(
      `/api/dashboard?rainfall_mm=${encodeURIComponent(rainfallMm)}&use_simulation=${useSimulation}`
    ),

  getZones: () => request<ZoneRaw[]>("/api/zones"),

  simulateRisk: (rainfallMm: number, useSimulation: boolean) =>
    request<RiskResponse>("/api/risk/simulate", {
      method: "POST",
      body: JSON.stringify({ rainfall_mm: rainfallMm, use_simulation: useSimulation }),
    }),

  listIncidents: (status?: string, zoneId?: string) => {
    const params = new URLSearchParams();
    if (status && status !== "All") params.set("status", status);
    if (zoneId && zoneId !== "All") params.set("zone_id", zoneId);
    const qs = params.toString();
    return request<Incident[]>(`/api/incidents${qs ? `?${qs}` : ""}`);
  },

  listCitizenIncidents: () => request<Incident[]>("/api/citizen/incidents"),

  listTeamIncidents: () => request<TeamIncidentsResponse>("/api/team/incidents"),

  trackPublicIncident: (incidentId: string, trackingCode: string) =>
    request<PublicTrackResponse>(
      `/api/public/track/${encodeURIComponent(incidentId)}?tracking_code=${encodeURIComponent(trackingCode)}`
    ),

  createIncident: (payload: {
    zone_id: string;
    description: string;
    location_text: string;
    reported_category: string;
    people_affected: number;
    photo_data_url?: string | null;
  }) =>
    request<{ incident: Incident; priority_breakdown: PriorityBreakdown; timeline: IncidentUpdate[] }>(
      "/api/incidents",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  getIncident: (id: string) =>
    request<{ incident: Incident; priority_breakdown: PriorityBreakdown; timeline: IncidentUpdate[] }>(
      `/api/incidents/${encodeURIComponent(id)}`
    ),

  getTeams: () => request<ResponseTeam[]>("/api/teams"),

  getRecommendations: (id: string) =>
    request<TeamRecommendation>(`/api/incidents/${encodeURIComponent(id)}/recommendations`),

  approveDispatch: (id: string, teamId: string, note?: string) =>
    request<{ incident: Incident; timeline: IncidentUpdate[] }>(
      `/api/incidents/${encodeURIComponent(id)}/approve-dispatch`,
      {
        method: "POST",
        body: JSON.stringify({ team_id: teamId, note }),
      }
    ),

  updateStatus: (id: string, status: string, note?: string) =>
    request<{ incident: Incident; timeline: IncidentUpdate[] }>(
      `/api/incidents/${encodeURIComponent(id)}/status`,
      {
        method: "PATCH",
        body: JSON.stringify({ status, note }),
      }
    ),

  getTimeline: (id: string) =>
    request<IncidentUpdate[]>(`/api/incidents/${encodeURIComponent(id)}/timeline`),

  resetDemo: () =>
    request<{ status: string; incident_count: number; team_count: number }>("/api/demo/reset", {
      method: "POST",
    }),

  getSystemStatus: () => request<SystemStatusResponse>("/api/system/status"),

  getDatasetStatus: () => request<DatasetStatusResponse>("/api/dataset/status"),

  refreshDataset: () =>
    request<DatasetStatusResponse>("/api/dataset/refresh", {
      method: "POST",
    }),

  getHistoricalWeather: (zoneId: string, days = 30) =>
    request<HistoricalWeatherResponse>(
      `/api/weather/historical/${encodeURIComponent(zoneId)}?days=${days}`
    ),
};
