import { useEffect, useState } from "react";
import {
  ArrowRight,
  ChevronRight,
  History,
  Network,
  Plane,
  ShieldAlert,
  X,
  MapPin,
} from "lucide-react";
import type { Alternate, CascadePath, Flight, Position } from "../types";
import { api } from "../services/api";
export const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      })
    : "—";
const number = (value: number | null, unit: string) =>
  value == null ? "—" : `${Math.round(value).toLocaleString()} ${unit}`;
const EMPTY_PHOTO = { url: "/aircraft-fallback.webp", source: "AeroPulse illustration", credit: null as string | null, source_url: null as string | null, license: null as string | null, license_url: null as string | null };
export default function FlightPanel({
  flight,
  onClose,
  onAlternates,
  onHistory,
  onReplay,
  history,
  replayIndex,
  setReplayIndex,
}: {
  flight: Flight;
  onClose: () => void;
  onAlternates: (a: Alternate[]) => void;
  onHistory: (p: Position[]) => void;
  onReplay: (p: Position | undefined) => void;
  history: Position[];
  replayIndex: number;
  setReplayIndex: (n: number) => void;
}) {
  const [alternates, setAlternates] = useState<Alternate[]>([]);
  const [paths, setPaths] = useState<CascadePath[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"overview" | "intelligence">("overview");
  const [photo, setPhoto] = useState(EMPTY_PHOTO);
  useEffect(() => {
    setAlternates([]);
    setPaths([]);
    setError("");
    setPhoto(EMPTY_PHOTO);
    api.aircraftPhoto(flight.aircraft_id).then(setPhoto).catch(() => undefined);
  }, [flight.flight_id, flight.aircraft_id]);
  async function load(kind: "alternates" | "history" | "cascade") {
    setBusy(kind);
    setError("");
    try {
      if (kind === "alternates") {
        const a = await api.alternates(flight.flight_id);
        setAlternates(a);
        onAlternates(a);
        if (!a.length)
          setError(
            "No operational alternate meets the runway requirement within 650 km of this destination.",
          );
      }
      if (kind === "history") {
        const p = await api.positions(flight.flight_id);
        onHistory(p);
        if (!p.length) setError("No recorded positions for this flight yet.");
      }
      if (kind === "cascade") {
        const c = await api.cascade(flight.flight_id);
        setPaths(c.paths);
        if (!c.paths.length)
          setError("No downstream dependency within the next five rotations.");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <aside className="flight-panel panel" aria-label="Flight details">
      <div className="panel-heading">
        <span>
          <Plane size={14} /> FLIGHT DETAILS
        </span>
        <button
          className="icon-button"
          aria-label="Close flight details"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>
      <div className="flight-identity">
        <div className="airline-mark">{flight.airline_code}</div>
        <div>
          <h2>{flight.flight_number}</h2>
          <p>{flight.airline_name}</p>
        </div>
        <span className="status-pill">
          {flight.flight_status.replaceAll("_", " ")}
        </span>
      </div>
      <div className="route-display">
        <div>
          <strong>{flight.origin}</strong>
          <span>{flight.origin_city}</span>
        </div>
        <div className="route-track">
          <span />
          <Plane size={18} />
          <span />
        </div>
        <div>
          <strong>{flight.destination}</strong>
          <span>{flight.destination_city}</span>
        </div>
      </div>
      <div className="flight-tabs">
        <button
          className={tab === "overview" ? "active" : ""}
          onClick={() => setTab("overview")}
        >
          Overview
        </button>
        <button
          className={tab === "intelligence" ? "active" : ""}
          onClick={() => setTab("intelligence")}
        >
          Intelligence{" "}
          <span className={`risk-dot ${flight.risk.level.toLowerCase()}`} />
        </button>
      </div>
      <div className="panel-scroll">
        {tab === "overview" ? (
          <>
            <figure className="aircraft-photo">
              <img src={photo.url} alt={`${flight.manufacturer} ${flight.model}, ${flight.registration_number}`} onError={(event) => { event.currentTarget.src = "/aircraft-fallback.webp"; }} />
              <figcaption>
                <span>{flight.manufacturer} {flight.model}</span>
                <small>{photo.source_url ? <a href={photo.source_url} target="_blank" rel="noreferrer">{photo.source}</a> : photo.source}{photo.credit ? ` · ${photo.credit}` : ""}{photo.license_url && <> · <a href={photo.license_url} target="_blank" rel="noreferrer">{photo.license}</a></>}</small>
              </figcaption>
            </figure>
            <div className="telemetry">
              <div>
                <span>ALTITUDE</span>
                <strong>{number(flight.altitude_m, "m")}</strong>
              </div>
              <div>
                <span>GROUND SPEED</span>
                <strong>{number(flight.ground_speed, "km/h")}</strong>
              </div>
              <div>
                <span>HEADING</span>
                <strong>{number(flight.heading, "°")}</strong>
              </div>
              <div>
                <span>TO DESTINATION</span>
                <strong>{number(flight.distance_remaining_km, "km")}</strong>
              </div>
              <div>
                <span>FLIGHT PHASE</span>
                <strong>{flight.movement_phase.replaceAll("_", " ")}</strong>
              </div>
            </div>
            <section className="detail-section">
              <h3>AIRCRAFT</h3>
              <dl>
                <dt>Registration</dt>
                <dd>{flight.registration_number}</dd>
                <dt>Type</dt>
                <dd>
                  {flight.manufacturer} {flight.model}
                </dd>
              </dl>
            </section>
            <section className="detail-section path-status">
              <h3>ROUTE PATHS</h3>
              <div><i className="planned-line" /><span>Planned airway route</span><b>{flight.route_geometry.coordinates.length} waypoints</b></div>
              <div><i className="actual-line" /><span>Persisted flown track</span><b>{flight.actual_geometry?.coordinates.length ?? 0} samples</b></div>
              {flight.mitigation_type && <div><i className="avoidance-line" /><span>{flight.mitigation_type} avoidance</span><b>{flight.mitigation_reason}</b></div>}
              <details className="route-explanation" open={!!flight.mitigation_type}>
                <summary>Operational path explanation</summary>
                <dl>
                  <dt>Trigger</dt><dd>{flight.mitigation_reason ?? "No active hazard intersects this route"}</dd>
                  <dt>Decision</dt><dd>{flight.operational_decision}</dd>
                  <dt>Changed fixes</dt><dd>{flight.changed_waypoints}</dd>
                  <dt>Added distance</dt><dd>{number(flight.added_distance_km, "km")}</dd>
                  <dt>Added time</dt><dd>{number(flight.added_time_minutes, "min")}</dd>
                  <dt>Fuel impact</dt><dd>{number(flight.estimated_extra_fuel_kg, "kg est.")}</dd>
                </dl>
              </details>
            </section>
            <section className="detail-section">
              <h3>
                SCHEDULE <span>UTC</span>
              </h3>
              <div className="schedule-head">
                <span />
                <span>Departure</span>
                <span>Arrival</span>
              </div>
              <div className="schedule-head">
                <span>Scheduled</span>
                <strong>{time(flight.scheduled_departure)}</strong>
                <strong>{time(flight.scheduled_arrival)}</strong>
              </div>
              <div className="schedule-head">
                <span>Actual</span>
                <strong>{time(flight.actual_departure)}</strong>
                <strong>{time(flight.actual_arrival)}</strong>
              </div>
              <div className="schedule-head">
                <span>Gate</span>
                <strong>{flight.departure_gate}</strong>
                <strong>{flight.arrival_gate}</strong>
              </div>
            </section>
            <button
              className="wide-button"
              disabled={!!busy}
              onClick={() => load("history")}
            >
              <History size={15} />
              {busy === "history"
                ? "Loading positions…"
                : "Replay recorded positions"}
              <ChevronRight size={15} />
            </button>
            {history.length > 0 && (
              <div className="replay-control">
                <div>
                  <span>POSITION HISTORY</span>
                  <button
                    onClick={() => {
                      onReplay(undefined);
                      setReplayIndex(-1);
                    }}
                  >
                    Return to current
                  </button>
                </div>
                <input
                  aria-label="Replay position"
                  type="range"
                  min="0"
                  max={history.length - 1}
                  value={replayIndex < 0 ? history.length - 1 : replayIndex}
                  onChange={(e) => {
                    const i = +e.target.value;
                    setReplayIndex(i);
                    onReplay(history[i]);
                  }}
                />
                <p>
                  {history.length} persisted samples ·{" "}
                  {time(
                    history[replayIndex < 0 ? history.length - 1 : replayIndex]
                      ?.recorded_at ?? null,
                  )}{" "}
                  UTC
                </p>
              </div>
            )}
          </>
        ) : (
          <>
            <div className={`risk-summary ${flight.risk.level.toLowerCase()}`}>
              <ShieldAlert size={20} />
              <div>
                <strong>{flight.risk.level} OPERATIONAL RISK</strong>
                <span>Explainable analysis · {flight.risk.method}</span>
              </div>
              <b>
                {flight.risk.score}
                <small>/100</small>
              </b>
            </div>
            <div className="risk-meter">
              <span style={{ width: `${flight.risk.score}%` }} />
            </div>
            <section className="detail-section">
              <h3>CONTRIBUTING FACTORS</h3>
              {flight.risk.factors.length ? (
                flight.risk.factors.map((f) => (
                  <div className="factor" key={f.code}>
                    <span className="factor-line" />
                    <p>{f.reason}</p>
                    <b>+{f.points}</b>
                  </div>
                ))
              ) : (
                <p className="muted">
                  No current factors detected by the configured rules.
                </p>
              )}
            </section>
            {flight.impacts.length > 0 && (
              <section className="detail-section">
                <h3>ACTIVE IMPACTS</h3>
                {flight.impacts.map((i) => (
                  <div className="impact" key={i.impact_id}>
                    <strong>{i.impact_type.replaceAll("_", " ")}</strong>
                    <span>+{i.estimated_delay_minutes} min est.</span>
                    <p>{i.description}</p>
                  </div>
                ))}
              </section>
            )}
            <button
              className="wide-button"
              disabled={!!busy}
              onClick={() => load("alternates")}
            >
              <MapPin size={15} />
              {busy === "alternates"
                ? "Finding airports…"
                : "Find alternate airports"}
              <ChevronRight size={15} />
            </button>
            {alternates.map((a, i) => (
              <div className="alternate" key={a.airport_id}>
                <b>{i + 1}</b>
                <div>
                  <strong>
                    {a.iata_code} <span>{a.city}</span>
                  </strong>
                  <small>
                    {Math.round(a.available_runway_m).toLocaleString()} m open
                    runway
                  </small>
                </div>
                <span>{Math.round(a.distance_km)} km</span>
              </div>
            ))}
            <button
              className="wide-button"
              disabled={!!busy}
              onClick={() => load("cascade")}
            >
              <Network size={15} />
              {busy === "cascade"
                ? "Tracing dependencies…"
                : "Trace downstream flights"}
              <ChevronRight size={15} />
            </button>
            {paths.length > 0 && (
              <div className="cascade">
                <p className="muted">
                  {flight.estimated_delay_minutes
                    ? "Current estimated delay"
                    : "What-if: 90 minute delay"}{" "}
                  · same aircraft
                </p>
                {paths.map((p) => (
                  <div key={`${p.root_id}-${p.flight_id}`}>
                    <ArrowRight size={13} />
                    <strong>{p.flight_number}</strong>
                    <span>Depth {p.depth}</span>
                    <b>+{p.delay_minutes}m</b>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="panel-foot">
        Last position {time(flight.recorded_at)} UTC ·{" "}
        {flight.recorded_at
          ? new Date(flight.recorded_at).toLocaleDateString("en-GB")
          : "Not yet tracked"}
      </div>
    </aside>
  );
}
