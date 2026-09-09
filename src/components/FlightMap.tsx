import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, CircleMarker, Polyline, Polygon, Tooltip, Popup, useMap, useMapEvents, ZoomControl } from "react-leaflet";
import L from "leaflet";
import type { Airport, Flight, Layers, MapState, Alternate, Position } from "../types";

const latlng = (p: number[]): [number, number] => [p[1], p[0]];
const isAirborne = (status: string) => ["EN_ROUTE", "APPROACHING"].includes(status);

function Focus({ flight, airport, reset, scenarioFlights }: { flight?: Flight; airport?: Airport; reset: number; scenarioFlights: Flight[] }) {
  const map = useMap();
  useEffect(() => { if (flight) map.fitBounds(flight.operational_geometry.coordinates.map(latlng), { padding: [75, 75], maxZoom: 7, animate: true }); }, [flight?.flight_id, map]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (airport) map.flyTo(latlng(airport.location.coordinates), 7, { duration: .8 }); }, [airport, map]);
  useEffect(() => { if (reset) map.setView([22, 75], 3); }, [reset, map]);
  useEffect(() => {
    if (!scenarioFlights.length) return;
    const points = scenarioFlights.flatMap((item) => item.operational_geometry.coordinates.map(latlng));
    if (points.length) map.fitBounds(points, { padding: [90, 90], maxZoom: 6, animate: true });
  }, [scenarioFlights, map]);
  return null;
}

const silhouettes: Record<string, string> = {
  NARROW_BODY: "M11 1Q12 0 13 1L14 9 22 14 22 16 14 13 14 19 17 21 17 23 12 21 7 23 7 21 10 19 10 13 2 16 2 14 10 9Z",
  WIDE_BODY: "M10.5 1Q12-1 13.5 1L15 8 23 13 23 16 14.5 13.5 14 19 18 21 18 23 12 21 6 23 6 21 10 19 9.5 13.5 1 16 1 13 9 8Z",
  REGIONAL_JET: "M11 2Q12 0 13 2L14 10 20 14 20 16 14 14 14 19 16 21 16 22 12 21 8 22 8 21 10 19 10 14 4 16 4 14 10 10Z",
  TURBOPROP: "M11 2Q12 0 13 2L14 9 20 13 20 15 14 13 14 19 17 21 17 22 12 21 7 22 7 21 10 19 10 13 4 15 4 13 10 9Z M5 10A2 2 0 1 0 5 14A2 2 0 1 0 5 10 M19 10A2 2 0 1 0 19 14A2 2 0 1 0 19 10",
  FREIGHTER: "M10 1H14L15 9 23 13V16L15 14V20L18 22V23L12 21 6 23V22L9 20V14L1 16V13L9 9Z",
  HELICOPTER: "M11 5H13L14 10 18 12V15H13V19L16 21V22H8V21L11 19V15H7L5 13 7 10H11Z M2 3H22V5H2Z",
};

function AircraftMarker({ flight, selected, onSelect, replay }: { flight: Flight; selected: boolean; onSelect: (id: number) => void; replay?: Position }) {
  const heading = replay?.heading ?? flight.heading ?? 0;
  const airborne = isAirborne(flight.flight_status);
  const color = selected ? "#ffffff" : flight.impacts.length ? "#f27762" : flight.risk.level === "HIGH" ? "#efaa57" : "#86b5d9";
  const icon = useMemo(() => L.divIcon({ className: `aircraft-icon ${airborne ? "airborne" : "ground"} ${selected ? "selected" : ""}`, iconSize: [24, 24], iconAnchor: [12, 12], html: airborne ? `<svg class="aircraft-silhouette" style="--heading:${heading}deg" viewBox="0 0 24 24" fill="${color}" stroke="#10202c" stroke-width=".7"><path d="${silhouettes[flight.aircraft_category] ?? silhouettes.NARROW_BODY}"/></svg>` : `<span class="ground-marker" style="border-color:${color}"><i style="background:${color}"></i></span>` }), [heading, color, selected, airborne, flight.aircraft_category]);
  const position = replay?.position ?? flight.position;
  if (!position) return null;
  const coords = [...position.coordinates];
  if (!airborne) { coords[0] += ((flight.flight_id % 9) - 4) * .006; coords[1] += ((flight.flight_id % 7) - 3) * .006; }
  return <Marker position={latlng(coords)} icon={icon} eventHandlers={{ click: () => onSelect(flight.flight_id) }} title={`Select ${flight.flight_number}`} zIndexOffset={selected ? 1000 : flight.impacts.length ? 500 : airborne ? 100 : 20}>
    <Tooltip direction="top" offset={[0, -15]} className="flight-tooltip"><strong>{flight.flight_number}</strong> {flight.origin} → {flight.destination}<br />{flight.flight_status.replaceAll("_", " ")} · {airborne ? `${Math.round(flight.altitude_m ?? 0).toLocaleString()} m` : flight.departure_gate || "GROUND"}<br />{flight.aircraft_category.replaceAll("_", " ")}</Tooltip>
  </Marker>;
}

function Traffic({ flights, selected, onSelect, replay }: { flights: Flight[]; selected?: Flight; onSelect: (id: number) => void; replay?: Position }) {
  const map = useMapEvents({ moveend: () => setBounds(map.getBounds().pad(.18)) });
  const [bounds, setBounds] = useState(() => map.getBounds().pad(.18));
  const positioned = useMemo(() => flights.filter((f) => {
    if (!f.position) return false;
    if (f.flight_id === selected?.flight_id) return true;
    return bounds.contains(latlng(f.position.coordinates));
  }), [flights, bounds, selected?.flight_id]);
  return <>{positioned.map((f) => <AircraftMarker key={f.flight_id} flight={f} selected={f.flight_id === selected?.flight_id} onSelect={onSelect} replay={f.flight_id === selected?.flight_id ? replay : undefined} />)}</>;
}

export default function FlightMap({ state, flights, selected, onSelect, layers, alternates, history, replay, airport, reset, theme, scenarioFlightIds }: { state: MapState; flights: Flight[]; selected?: Flight; onSelect: (id: number) => void; layers: Layers; alternates: Alternate[]; history: Position[]; replay?: Position; airport?: Airport; reset: number; theme: "dark" | "light"; scenarioFlightIds: number[] }) {
  const actual = history.length > 1 ? history.map((p) => latlng(p.position.coordinates)) : selected?.actual_geometry?.coordinates.map(latlng);
  const scenarioFlights = flights.filter((f) => scenarioFlightIds.includes(f.flight_id));
  return <MapContainer center={[22, 75]} zoom={3} minZoom={2} maxZoom={13} zoomControl={false} className={`flight-map theme-${theme}`}>
    <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}" attribution="Tiles &copy; Esri" maxNativeZoom={16} /><ZoomControl position="bottomright" /><Focus flight={selected} airport={airport} reset={reset} scenarioFlights={scenarioFlights} />
    {layers.routes && flights.filter((f) => isAirborne(f.flight_status)).map((f) => <Polyline key={f.flight_id} positions={f.operational_geometry.coordinates.map(latlng)} pathOptions={{ color: f.impacts.length ? "#d17056" : "#5586a9", weight: 1, opacity: f.impacts.length ? .45 : .18 }} />)}
    {layers.weather && state.weather.map((w) => <Polygon key={w.weather_id} positions={w.geometry.coordinates.map((r) => r.map(latlng))} pathOptions={{ color: "#ce9855", weight: 1, dashArray: "5 5", fillColor: "#bd8037", fillOpacity: .17 }}><Tooltip>{w.weather_type.replaceAll("_", " ")} · Severity {w.severity}/5 · DEMO</Tooltip></Polygon>)}
    {layers.airspace && state.airspace.map((z) => <Polygon key={z.airspace_zone_id} positions={z.geometry.coordinates.map((r) => r.map(latlng))} pathOptions={{ color: "#b37371", weight: 1, dashArray: "3 5", fillOpacity: .1 }}><Tooltip>{z.zone_name}<br />{z.lower_altitude}–{z.upper_altitude} m</Tooltip></Polygon>)}
    {layers.disruptions && state.disruptions.filter((d) => d.is_active && d.geometry).map((d) => <Polygon key={d.disruption_id} positions={d.geometry.coordinates.map((r) => r.map(latlng))} pathOptions={{ color: "#e77b63", weight: 1.5, fillOpacity: .12 }}><Tooltip>{d.description}</Tooltip></Polygon>)}
    {layers.airports && state.airports.map((a) => <CircleMarker key={a.airport_id} center={latlng(a.location.coordinates)} radius={3} pathOptions={{ color: "#9fadb7", weight: 1, fillColor: "#15212b", fillOpacity: 1 }}><Tooltip permanent={a.country === "India" && a.airport_id <= 12} direction="bottom" className="airport-label" offset={[0, 3]}>{a.iata_code}</Tooltip><Popup>{a.iata_code} · {a.airport_name}<br />{a.city}, {a.country} · Infrastructure: {a.operational_status}</Popup></CircleMarker>)}
    {selected && <Polyline positions={selected.route_geometry.coordinates.map(latlng)} pathOptions={{ color: "#e5edf3", weight: 2, opacity: .8, dashArray: "5 7" }} />}
    {selected?.mitigation_type && <Polyline positions={selected.operational_geometry.coordinates.map(latlng)} pathOptions={{ color: "#efaa57", weight: 3, opacity: .9 }}><Tooltip sticky>{selected.mitigation_type} avoidance · {selected.mitigation_reason}</Tooltip></Polyline>}
    {actual && actual.length > 1 && <Polyline positions={actual} pathOptions={{ color: "#48a9e6", weight: 3, opacity: .9 }} />}
    {alternates.map((a, i) => <CircleMarker key={a.airport_id} center={latlng(a.location.coordinates)} radius={8} pathOptions={{ color: "#86c1e8", weight: 2, fillOpacity: .2 }}><Tooltip permanent className="alternate-label">{i + 1} · {a.iata_code}</Tooltip></CircleMarker>)}
    {scenarioFlights.map((f) => <Polyline key={`scenario-${f.flight_id}`} positions={f.operational_geometry.coordinates.map(latlng)} pathOptions={{ color: "#f27762", weight: 2.5, opacity: .7 }} />)}
    <Traffic flights={flights} selected={selected} onSelect={onSelect} replay={replay} />
  </MapContainer>;
}
