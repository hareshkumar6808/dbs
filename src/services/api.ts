import type {
  Alternate,
  CascadePath,
  CopilotResult,
  MapState,
  Position,
  Runway,
  SimulationResult,
} from "../types";
const base = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(`${base}/api${path}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    if (!response.ok) {
      const body = await response
        .json()
        .catch(() => ({ detail: `API returned ${response.status}` }));
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : "The request could not be validated. Check your selections.",
      );
    }
    return response.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}
export const api = {
  state: () => request<MapState>("/map/state"),
  positions: (id: number) => request<Position[]>(`/flights/${id}/positions`),
  alternates: (id: number) => request<Alternate[]>(`/flights/${id}/alternates`),
  runways: (id: number) => request<Runway[]>(`/runways?airport_id=${id}`),
  simulate: (data: {
    disruption_type: string;
    airport_id: number;
    runway_id?: number;
    severity: number;
    duration_minutes: number;
  }) =>
    request<SimulationResult>("/disruptions/simulate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  resolve: (id: number) =>
    request(`/disruptions/${id}/resolve`, { method: "POST" }),
  cascade: (id?: number) =>
    request<{ engine: string; paths: CascadePath[] }>(
      `/intelligence/cascade${id ? `?flight_id=${id}` : ""}`,
    ),
  ask: (question: string) =>
    request<CopilotResult>("/copilot/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
