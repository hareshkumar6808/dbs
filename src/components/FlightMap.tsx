import { useEffect, useMemo } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  CircleMarker,
  Polyline,
  Polygon,
  Tooltip,
  Popup,
  useMap,
  ZoomControl,
} from "react-leaflet";
import L from "leaflet";
import type {
  Airport,
  Flight,
  Layers,
  MapState,
  Alternate,
  Position,
} from "../types";
const latlng = (p: number[]): [number, number] => [p[1], p[0]];
function Focus({
  flight,
  airport,
  reset,
}: {
  flight: Flight | undefined;
  airport: Airport | undefined;
  reset: number;
}) {
  const map = useMap();
  useEffect(() => {
    if (flight)
      map.fitBounds(flight.route_geometry.coordinates.map(latlng), {
        padding: [75, 75],
        maxZoom: 7,
        animate: true,
      });
  }, [flight?.flight_id, map]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (airport)
      map.flyTo(latlng(airport.location.coordinates), 7, { duration: 0.8 });
  }, [airport, map]);
  useEffect(() => {
    if (reset) map.setView([20.6, 79.3], 5);
  }, [reset, map]);
  return null;
}
function AircraftMarker({
  flight,
  selected,
  onSelect,
  replay,
}: {
  flight: Flight;
  selected: boolean;
  onSelect: (id: number) => void;
  replay?: Position;
}) {
  const heading = replay?.heading ?? flight.heading ?? 0;
  const color = selected
    ? "#ffffff"
    : flight.impacts.length
      ? "#f27762"
      : flight.risk.level === "HIGH"
        ? "#efaa57"
        : "#86b5d9";
  const icon = useMemo(
    () =>
      L.divIcon({
        className: `aircraft-icon ${selected ? "selected" : ""}`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        html: `<svg style="transform:rotate(${heading}deg)" viewBox="0 0 24 24" fill="${color}" stroke="#10202c" stroke-width="0.75"><path d="M11 2Q12 0 13 2L14 9 22 14 22 16 14 13 14 19 17 21 17 23 12 21 7 23 7 21 10 19 10 13 2 16 2 14 10 9Z"/></svg>`,
      }),
    [heading, color, selected],
  );
  const position = replay?.position ?? flight.position;
  if (!position) return null;
  return (
    <Marker
      position={latlng(position.coordinates)}
      icon={icon}
      eventHandlers={{ click: () => onSelect(flight.flight_id) }}
      title={`Select ${flight.flight_number}`}
      zIndexOffset={selected ? 1000 : flight.impacts.length ? 500 : 100}
    >
      <Tooltip direction="top" offset={[0, -15]} className="flight-tooltip">
        <strong>{flight.flight_number}</strong> {flight.origin} →{" "}
        {flight.destination}
        <br />
        {flight.risk.level} RISK ·{" "}
        {Math.round(flight.altitude_m ?? 0).toLocaleString()} m
      </Tooltip>
    </Marker>
  );
}
export default function FlightMap({
  state,
  flights,
  selected,
  onSelect,
  layers,
  alternates,
  history,
  replay,
  airport,
  reset,
}: {
  state: MapState;
  flights: Flight[];
  selected?: Flight;
  onSelect: (id: number) => void;
  layers: Layers;
  alternates: Alternate[];
  history: Position[];
  replay?: Position;
  airport?: Airport;
  reset: number;
}) {
  return (
    <MapContainer
      center={[20.6, 79.3]}
      zoom={5}
      minZoom={3}
      maxZoom={13}
      zoomControl={false}
      className="flight-map"
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
        maxNativeZoom={19}
      />
      <ZoomControl position="bottomright" />
      <Focus flight={selected} airport={airport} reset={reset} />
      {layers.routes &&
        flights
          .filter((f) => f.flight_status === "EN_ROUTE")
          .map((f) => (
            <Polyline
              key={f.flight_id}
              positions={f.route_geometry.coordinates.map(latlng)}
              pathOptions={{
                color: f.impacts.length ? "#d17056" : "#5586a9",
                weight: 1,
                opacity: f.impacts.length ? 0.45 : 0.18,
              }}
            />
          ))}
      {layers.weather &&
        state.weather.map((w) => (
          <Polygon
            key={w.weather_id}
            positions={w.geometry.coordinates.map((r) => r.map(latlng))}
            pathOptions={{
              color: "#ce9855",
              weight: 1,
              dashArray: "5 5",
              fillColor: "#bd8037",
              fillOpacity: 0.17,
            }}
          >
            <Tooltip>
              {w.weather_type.replaceAll("_", " ")} · Severity {w.severity}/5 ·
              DEMO
            </Tooltip>
          </Polygon>
        ))}
      {layers.airspace &&
        state.airspace.map((z) => (
          <Polygon
            key={z.airspace_zone_id}
            positions={z.geometry.coordinates.map((r) => r.map(latlng))}
            pathOptions={{
              color: "#b37371",
              weight: 1,
              dashArray: "3 5",
              fillOpacity: 0.1,
            }}
          >
            <Tooltip>
              {z.zone_name}
              <br />
              {z.lower_altitude}–{z.upper_altitude} m
            </Tooltip>
          </Polygon>
        ))}
      {layers.disruptions &&
        state.disruptions
          .filter((d) => d.is_active && d.geometry)
          .map((d) => (
            <Polygon
              key={d.disruption_id}
              positions={d.geometry.coordinates.map((r) => r.map(latlng))}
              pathOptions={{ color: "#e77b63", weight: 1.5, fillOpacity: 0.12 }}
            >
              <Tooltip>{d.description}</Tooltip>
            </Polygon>
          ))}
      {layers.airports &&
        state.airports.map((a) => (
          <CircleMarker
            key={a.airport_id}
            center={latlng(a.location.coordinates)}
            radius={3}
            pathOptions={{
              color: "#9fadb7",
              weight: 1,
              fillColor: "#15212b",
              fillOpacity: 1,
            }}
          >
            <Tooltip
              permanent
              direction="bottom"
              className="airport-label"
              offset={[0, 3]}
            >
              {a.iata_code}
            </Tooltip>
            <Popup>
              {a.iata_code} · {a.airport_name}
              <br />
              {a.city} · Infrastructure: {a.operational_status}
            </Popup>
          </CircleMarker>
        ))}
      {selected && (
        <Polyline
          positions={selected.route_geometry.coordinates.map(latlng)}
          pathOptions={{
            color: "#e5edf3",
            weight: 2,
            opacity: 0.7,
            dashArray: "4 6",
          }}
        />
      )}
      {history.length > 1 && (
        <Polyline
          positions={history.map((p) => latlng(p.position.coordinates))}
          pathOptions={{ color: "#69b0e2", weight: 3, opacity: 0.8 }}
        />
      )}
      {alternates.map((a, i) => (
        <CircleMarker
          key={a.airport_id}
          center={latlng(a.location.coordinates)}
          radius={8}
          pathOptions={{ color: "#86c1e8", weight: 2, fillOpacity: 0.2 }}
        >
          <Tooltip permanent className="alternate-label">
            {i + 1} · {a.iata_code}
          </Tooltip>
        </CircleMarker>
      ))}
      {flights
        .filter(
          (f) =>
            f.flight_status === "EN_ROUTE" ||
            f.flight_id === selected?.flight_id,
        )
        .map((f) => (
          <AircraftMarker
            key={f.flight_id}
            flight={f}
            selected={f.flight_id === selected?.flight_id}
            onSelect={onSelect}
            replay={f.flight_id === selected?.flight_id ? replay : undefined}
          />
        ))}
    </MapContainer>
  );
}
