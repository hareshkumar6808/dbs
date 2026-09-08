import type { Point, LineString, Polygon } from "geojson";
export type Risk = {
  score: number;
  level: "LOW" | "MODERATE" | "HIGH";
  factors: { code: string; points: number; reason: string }[];
  method: string;
};
export type Impact = {
  impact_id: number;
  disruption_id: number;
  impact_type: string;
  severity: number;
  estimated_delay_minutes: number;
  description: string;
};
export type Flight = {
  flight_id: number;
  flight_number: string;
  airline_id: number;
  airline_name: string;
  airline_code: string;
  aircraft_id: number;
  registration_number: string;
  manufacturer: string;
  model: string;
  origin: string;
  destination: string;
  origin_city: string;
  destination_city: string;
  destination_airport_id: number;
  origin_airport_id: number;
  route_code: string;
  route_geometry: LineString;
  position: Point | null;
  ground_speed: number | null;
  heading: number | null;
  altitude_m: number | null;
  recorded_at: string | null;
  distance_remaining_km: number | null;
  scheduled_departure: string;
  scheduled_arrival: string;
  actual_departure: string | null;
  actual_arrival: string | null;
  flight_status: string;
  departure_gate: string;
  arrival_gate: string;
  risk: Risk;
  impacts: Impact[];
  estimated_delay_minutes: number;
  weather_severity: number;
  inside_weather: boolean;
  approaching_weather: boolean;
  next_buffer_minutes: number | null;
};
export type Airport = {
  airport_id: number;
  iata_code: string;
  icao_code: string;
  airport_name: string;
  city: string;
  country: string;
  location: Point;
  operational_status: string;
};
export type Weather = {
  weather_id: number;
  weather_type: string;
  severity: number;
  geometry: Polygon;
};
export type Airspace = {
  airspace_zone_id: number;
  zone_name: string;
  zone_type: string;
  geometry: Polygon;
  lower_altitude: number;
  upper_altitude: number;
};
export type Disruption = {
  disruption_id: number;
  disruption_type: string;
  description: string;
  iata_code: string;
  airport_id: number;
  disruption_status: string;
  is_active: boolean;
  expected_end_time: string;
  geometry: Polygon;
};
export type MapState = {
  mode: string;
  source: string;
  generated_at: string;
  flights: Flight[];
  airports: Airport[];
  weather: Weather[];
  airspace: Airspace[];
  disruptions: Disruption[];
  network: {
    flights: number;
    daily_operations: number;
    airborne: number;
    ground: number;
    high_risk: number;
    affected: number;
  };
  graph: string;
};
export type Alternate = {
  airport_id: number;
  iata_code: string;
  airport_name: string;
  city: string;
  location: Point;
  distance_km: number;
  available_runway_m: number;
  runway_identifier: string;
  reason: string;
};
export type Position = {
  position_id: number;
  position: Point;
  ground_speed: number;
  heading: number;
  recorded_at: string;
};
export type CascadePath = {
  root_id: number;
  flight_id: number;
  flight_number: string;
  depth: number;
  path: number[];
  delay_minutes: number;
  reason: string;
};
export type SimulationResult = {
  disruption_id: number;
  direct_flights: { flight_id: number; flight_number: string }[];
  downstream_flights: CascadePath[];
  estimated_delay_minutes: number;
  alternates: Alternate[];
  method: string;
};
export type Runway = {
  runway_id: number;
  airport_id: number;
  runway_identifier: string;
  length_m: number;
  runway_status: string;
  temporarily_closed: boolean;
};
export type Layers = {
  weather: boolean;
  airspace: boolean;
  airports: boolean;
  routes: boolean;
  disruptions: boolean;
};
export type CopilotResult = {
  answer: string;
  kind?: string;
  items: ({
    flight_id?: number;
    flight_number?: string;
    route_code?: string;
    zone_name?: string;
    risk?: Risk;
  } & Partial<Alternate>)[];
  examples?: string[];
};
