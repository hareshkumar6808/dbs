import { useEffect, useState } from "react";
import { ArrowRight, FlaskConical, RotateCcw, X } from "lucide-react";
import { api } from "../services/api";
import type { Alternate, MapState, Runway, SimulationResult } from "../types";
export default function DisruptionPanel({
  state,
  onClose,
  onChange,
  onAlternates,
  onSelect,
}: {
  state: MapState;
  onClose: () => void;
  onChange: () => Promise<void>;
  onAlternates: (a: Alternate[]) => void;
  onSelect: (id: number) => void;
}) {
  const [airport, setAirport] = useState(
    state.airports.find((a) => a.iata_code === "MAA")?.airport_id ??
      state.airports[0]?.airport_id ??
      1,
  );
  const [kind, setKind] = useState("RUNWAY_CLOSURE");
  const [runways, setRunways] = useState<Runway[]>([]);
  const [runway, setRunway] = useState(0);
  const [severity, setSeverity] = useState(4);
  const [duration, setDuration] = useState(120);
  const [result, setResult] = useState<SimulationResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resolvedIds, setResolvedIds] = useState<number[]>([]);
  const activeScenarios = state.disruptions.filter((d) => d.is_active && !resolvedIds.includes(d.disruption_id));
  useEffect(() => {
    let alive = true;
    setRunways([]);
    setRunway(0);
    api
      .runways(airport)
      .then((r) => {
        if (alive) {
          setRunways(r);
          setRunway(r[0]?.runway_id ?? 0);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [airport]);
  async function simulate() {
    setBusy(true);
    setError("");
    try {
      const r = await api.simulate({
        disruption_type: kind,
        airport_id: airport,
        runway_id: kind === "RUNWAY_CLOSURE" ? runway : undefined,
        severity,
        duration_minutes: duration,
      });
      setResult(r);
      onAlternates(r.alternates);
      await onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resolve(id: number) {
    setBusy(true);
    setError("");
    try {
      await api.resolve(id);
      setResolvedIds((ids) => [...ids, id]);
      if (result?.disruption_id === id) {
        setResult(undefined);
        onAlternates([]);
      }
      await onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="tool-panel panel" aria-label="Disruption simulator">
      <div className="panel-heading">
        <span>
          <FlaskConical size={14} /> DISRUPTION LAB
        </span>
        <button
          className="icon-button"
          aria-label="Close disruption lab"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>
      <div className="panel-scroll">
        <div className="tool-intro">
          <span className="eyebrow">SCENARIO ANALYSIS</span>
          <h2>
            One event.
            <br />
            Network-wide consequences.
          </h2>
          <p>
            Create a shared demo disruption to trace affected flights, alternate
            airports and aircraft rotations.
          </p>
        </div>
        <div className="simulation-form">
          <label>
            Airport
            <select
              value={airport}
              onChange={(e) => setAirport(+e.target.value)}
            >
              {state.airports.map((a) => (
                <option value={a.airport_id} key={a.airport_id}>
                  {a.iata_code} · {a.city}
                </option>
              ))}
            </select>
          </label>
          <label>
            Disruption type
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="RUNWAY_CLOSURE">Runway closure</option>
              <option value="AIRPORT_CLOSURE">Airport closure</option>
              <option value="SEVERE_WEATHER">Severe weather</option>
            </select>
          </label>
          {kind === "RUNWAY_CLOSURE" && (
            <label>
              Runway
              <select
                value={runway}
                onChange={(e) => setRunway(+e.target.value)}
              >
                {runways.map((r) => (
                  <option value={r.runway_id} key={r.runway_id}>
                    {r.runway_identifier} · {r.length_m.toLocaleString()} m{" "}
                    {r.temporarily_closed ? "· scenario active" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="form-pair">
            <label>
              Severity
              <select
                value={severity}
                onChange={(e) => setSeverity(+e.target.value)}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n} / 5
                  </option>
                ))}
              </select>
            </label>
            <label>
              Duration
              <select
                value={duration}
                onChange={(e) => setDuration(+e.target.value)}
              >
                {[30, 60, 120, 240].map((n) => (
                  <option key={n} value={n}>
                    {n} minutes
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button
            className="primary-button"
            onClick={simulate}
            disabled={
              busy ||
              state.mode !== "demo" ||
              (kind === "RUNWAY_CLOSURE" && !runway)
            }
          >
            <FlaskConical size={15} />
            {busy ? "Analyzing network…" : "Simulate disruption"}
            <ArrowRight size={15} />
          </button>
        </div>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {result && (
          <section className="simulation-result">
            <h3>SCENARIO #{result.disruption_id} · RESULTS</h3>
            <div className="result-counts">
              <div>
                <b>{result.direct_flights.length}</b>
                <span>Direct flights</span>
              </div>
              <div>
                <b>
                  {
                    new Set(result.downstream_flights.map((f) => f.flight_id))
                      .size
                  }
                </b>
                <span>Downstream</span>
              </div>
              <div>
                <b>+{result.estimated_delay_minutes}m</b>
                <span>Est. delay</span>
              </div>
            </div>
            <p className="muted">
              Shared scenario saved. Affected flights are highlighted on the
              map.
            </p>
            {result.direct_flights.slice(0, 8).map((f) => (
              <button
                className="result-flight"
                key={f.flight_id}
                onClick={() => onSelect(f.flight_id)}
              >
                {f.flight_number}
                <span>Direct impact</span>
                <ArrowRight size={13} />
              </button>
            ))}
            {result.downstream_flights.slice(0, 6).map((p) => (
              <div className="dependency" key={`${p.root_id}-${p.flight_id}`}>
                <span>↳</span>
                <button onClick={() => onSelect(p.flight_id)}>
                  {p.flight_number}
                </button>
                <small>
                  Depth {p.depth} · +{p.delay_minutes}m
                </small>
              </div>
            ))}
            <h3>NEARBY ALTERNATES</h3>
            {result.alternates.map((a) => (
              <div className="alternate" key={a.airport_id}>
                <strong>{a.iata_code}</strong>
                <span>{a.city}</span>
                <b>{Math.round(a.distance_km)} km</b>
              </div>
            ))}
            {!result.alternates.length && (
              <p className="muted">
                No suitable airport in the 650 km search radius.
              </p>
            )}
          </section>
        )}
        <section className="detail-section">
          <h3>
            ACTIVE SCENARIOS{" "}
            <span>{activeScenarios.length}</span>
          </h3>
          {activeScenarios.map((d) => (
              <div className="active-scenario" key={d.disruption_id}>
                <div>
                  <strong>
                    {d.iata_code} · {d.disruption_type.replaceAll("_", " ")}
                  </strong>
                  <span>
                    Until{" "}
                    {new Date(d.expected_end_time).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: "UTC",
                    })}{" "}
                    UTC
                  </span>
                </div>
                <button
                  title="Resolve scenario"
                  aria-label={`Resolve scenario ${d.disruption_id}`}
                  disabled={busy}
                  onClick={() => resolve(d.disruption_id)}
                >
                  <RotateCcw size={14} />
                </button>
              </div>
            ))}
          {!activeScenarios.length && (
            <p className="muted">
              No active scenarios. The network is at its baseline.
            </p>
          )}
        </section>
      </div>
      <div className="panel-foot">
        Demo only · shared state · reversible scenarios
      </div>
    </aside>
  );
}
