import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ChevronDown,
  Crosshair,
  FlaskConical,
  Layers as LayersIcon,
  Map as MapIcon,
  MessageSquare,
  Moon,
  Plane,
  Radar,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sun,
  X,
} from "lucide-react";
import FlightMap from "./components/FlightMap";
import FlightPanel, { time } from "./components/FlightPanel";
import DisruptionPanel from "./components/DisruptionPanel";
import Copilot from "./components/Copilot";
import { api } from "./services/api";
import type { Airport, Alternate, Layers, MapState, Position } from "./types";

export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    localStorage.getItem("aeropulse-theme") === "light" ? "light" : "dark",
  );
  const [state, setState] = useState<MapState>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const inFlight = useRef(false);
  const [selectedId, setSelectedId] = useState<number>();
  const [tool, setTool] = useState<"lab" | "copilot" | null>(null);
  const [search, setSearch] = useState("");
  const [airline, setAirline] = useState("");
  const [status, setStatus] = useState("");
  const [riskFilter, setRiskFilter] = useState(false);
  const [affected, setAffected] = useState(false);
  const [layers, setLayers] = useState<Layers>({
    weather: false,
    airspace: false,
    airports: true,
    routes: false,
    disruptions: true,
  });
  const [layersOpen, setLayersOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [alternates, setAlternates] = useState<Alternate[]>([]);
  const [history, setHistory] = useState<Position[]>([]);
  const [replay, setReplay] = useState<Position>();
  const [replayIndex, setReplayIndex] = useState(-1);
  const [airport, setAirport] = useState<Airport>();
  const [reset, setReset] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scenarioFlightIds, setScenarioFlightIds] = useState<number[]>([]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("aeropulse-theme", theme);
  }, [theme]);
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const s = await api.state();
      setState(s);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      if (!document.hidden) refresh();
    }, 10000);
    return () => clearInterval(id);
  }, [refresh]);
  const selected = state?.flights.find((f) => f.flight_id === selectedId);
  const select = (id: number) => {
    const flight = state?.flights.find((item) => item.flight_id === id);
    if (flight?.mitigation_type === "WEATHER") setLayers((value) => ({ ...value, weather: true }));
    if (flight?.mitigation_type === "AIRSPACE") setLayers((value) => ({ ...value, airspace: true }));
    setSelectedId(id);
    setTool(null);
    setScenarioFlightIds([]);
    setHistory([]);
    setReplay(undefined);
    setReplayIndex(-1);
    setAlternates([]);
    setAirport(undefined);
    setSidebarOpen(false);
  };
  const visible = useMemo(
    () =>
      state?.flights.filter(
        (f) =>
          (!search ||
            `${f.flight_number} ${f.origin} ${f.destination} ${f.origin_city} ${f.destination_city}`
              .toLowerCase()
              .includes(search.toLowerCase())) &&
          (!airline || f.airline_id === +airline) &&
          (!status ||
            (status === "GROUND"
              ? !["EN_ROUTE", "APPROACHING"].includes(f.flight_status) &&
                !!f.position
              : status === "AIRBORNE"
                ? ["EN_ROUTE", "APPROACHING"].includes(f.flight_status)
              : f.flight_status === status)) &&
          (!riskFilter || f.risk.level === "HIGH") &&
          (!affected || f.impacts.length),
      ) ?? [],
    [state, search, airline, status, riskFilter, affected],
  );
  const airlines = useMemo(
    () => [
      ...new Map(
        state?.flights.map((f) => [
          f.airline_id,
          { id: f.airline_id, name: f.airline_name },
        ]),
      ).values(),
    ],
    [state],
  );
  const airportMatches =
    search.length > 1
      ? (state?.airports.filter((a) =>
          `${a.iata_code} ${a.city} ${a.airport_name}`
            .toLowerCase()
            .includes(search.toLowerCase()),
        ) ?? [])
      : [];
  const clear = () => {
    setSearch("");
    setAirline("");
    setStatus("");
    setRiskFilter(false);
    setAffected(false);
  };
  const closeTool = () => {
    setTool(null);
    setScenarioFlightIds([]);
    setAlternates([]);
  };
  const openTool = (t: "lab" | "copilot") => {
    if (tool === t) { closeTool(); return; }
    setTool(t);
    setScenarioFlightIds([]);
    setSelectedId(undefined);
    setHistory([]);
    setReplay(undefined);
    setAlternates([]);
  };
  const filtered = !!(search || airline || status || riskFilter || affected);
  const mappedVisible = useMemo(() => visible.filter((f) => !!f.position), [visible]);
  const visibleMetrics = useMemo(() => ({
    total: mappedVisible.length,
    airborne: mappedVisible.filter((f) => ["EN_ROUTE", "APPROACHING"].includes(f.flight_status)).length,
    ground: mappedVisible.filter((f) => !["EN_ROUTE", "APPROACHING"].includes(f.flight_status)).length,
    highRisk: mappedVisible.filter((f) => f.risk.level === "HIGH").length,
    delayed: mappedVisible.filter((f) => f.flight_status === "DELAYED" || f.estimated_delay_minutes > 0).length,
    affected: mappedVisible.filter((f) => f.impacts.length > 0).length,
  }), [mappedVisible]);
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="AeroPulse home">
          <div className="brand-symbol">
            <Radar size={25} />
          </div>
          <span>
            Aero<span>Pulse</span>
            <small>AVIATION NETWORK INTELLIGENCE</small>
          </span>
        </a>
        <nav>
          <button
            className={!tool ? "active" : ""}
            onClick={closeTool}
          >
            <MapIcon size={15} /> Airspace
          </button>
          <button
            className={tool === "lab" ? "active" : ""}
            onClick={() => openTool("lab")}
          >
            <FlaskConical size={15} /> Disruption lab
          </button>
        </nav>
        <div className="header-status">
          <span className="demo-badge">
            {state?.mode === "live" ? "LIVE PROVIDER" : "DEMO NETWORK"}
          </span>
          <span className="utc-clock">
            {state ? time(state.generated_at) : "--:--"} <small>UTC</small>
          </span>
          <button
            className="theme-toggle"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            className="copilot-toggle"
            aria-label="Operations copilot"
            onClick={() => openTool("copilot")}
          >
            <MessageSquare size={15} />
            <span>Operations copilot</span>
          </button>
        </div>
      </header>
      <div className="workspace">
        <aside
          className={`traffic-sidebar ${sidebarOpen ? "open" : "collapsed"}`}
          aria-label="Traffic explorer"
        >
          <div className="sidebar-title">
            <div>
              <span className="eyebrow">INDIA-LINKED TRAFFIC</span>
              <h1>Flight explorer</h1>
            </div>
            <button className="icon-button sidebar-close" aria-label="Close flight explorer" onClick={() => setSidebarOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="network-metrics">
            <div className="metrics-scope">
              <strong>{filtered ? "VISIBLE TRAFFIC" : "MAP TRAFFIC"}</strong>
              <span>{state?.network.daily_operations.toLocaleString() ?? "—"} network-wide daily ops</span>
            </div>
            <button onClick={clear}>
              <Radar size={16} />
              <strong>{visibleMetrics.total}</strong>
              <span>Visible</span>
            </button>
            <button
              onClick={() => {
                clear();
                setStatus("AIRBORNE");
              }}
            >
              <Plane size={16} />
              <strong>{visibleMetrics.airborne}</strong>
              <span>Airborne</span>
            </button>
            <button
              onClick={() => {
                clear();
                setStatus("GROUND");
              }}
              className={status === "GROUND" ? "active" : ""}
            >
              <Activity size={16} />
              <strong>{visibleMetrics.ground}</strong>
              <span>On ground</span>
            </button>
            <button onClick={() => { clear(); setRiskFilter(true); }}>
              <strong>{visibleMetrics.highRisk}</strong><span>High risk</span>
            </button>
            <button onClick={() => { clear(); setStatus("DELAYED"); }}>
              <strong>{visibleMetrics.delayed}</strong><span>Delayed</span>
            </button>
            <button onClick={() => { clear(); setAffected(true); }}>
              <strong>{visibleMetrics.affected}</strong><span>Affected</span>
            </button>
          </div>
          <div className="search-wrap">
            <Search size={15} />
            <input
              aria-label="Search flights or airports"
              placeholder="Flight, airport or city"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="icon-button"
                aria-label="Clear search"
                onClick={() => setSearch("")}
              >
                <X size={13} />
              </button>
            )}
          </div>
          {airportMatches.length > 0 && (
            <div className="airport-results">
              {airportMatches.slice(0, 3).map((a) => (
                <button
                  key={a.airport_id}
                  onClick={() => {
                    setAirport(a);
                    setSelectedId(undefined);
                    setSidebarOpen(false);
                  }}
                >
                  <Crosshair size={13} />
                  <b>{a.iata_code}</b>
                  {a.city}
                </button>
              ))}
            </div>
          )}
          <button
            className="filters-toggle"
            onClick={() => setFiltersOpen(!filtersOpen)}
            aria-expanded={filtersOpen}
          >
            <SlidersHorizontal size={13} /> Filters
            {(airline || status || riskFilter || affected) && <span>Active</span>}
            <ChevronDown size={12} />
          </button>
          {filtersOpen && <>
          <div className="filters">
            <label className="select-wrap">
              <select
                aria-label="Filter airline"
                value={airline}
                onChange={(e) => setAirline(e.target.value)}
              >
                <option value="">All airlines</option>
                {airlines.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={12} />
            </label>
            <label className="select-wrap">
              <select
                aria-label="Filter flight status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">All statuses</option>
                <option value="EN_ROUTE">En route</option>
                <option value="AIRBORNE">All airborne</option>
                <option value="APPROACHING">Approaching</option>
                <option value="TAXIING">Taxiing</option>
                <option value="BOARDING">Boarding</option>
                <option value="DELAYED">Delayed</option>
                <option value="GROUND">All on ground</option>
                <option value="SCHEDULED">Scheduled</option>
                <option value="LANDED">Landed</option>
                <option value="CANCELLED">Cancelled</option>
              </select>
              <ChevronDown size={12} />
            </label>
          </div>
          <div className="filter-chips">
            <button
              aria-pressed={affected}
              className={affected ? "active" : ""}
              onClick={() => setAffected(!affected)}
            >
              Affected flights
            </button>
            <button
              aria-pressed={riskFilter}
              className={riskFilter ? "active" : ""}
              onClick={() => setRiskFilter(!riskFilter)}
            >
              High risk
            </button>
            {filtered && (
              <button className="clear-filters" onClick={clear}>
                Reset
              </button>
            )}
          </div>
          </>}
          <div className="list-heading">
            <span>FLIGHT DIRECTORY</span>
            <span>{visible.length} flights</span>
          </div>
          <div className="flight-list">
            {loading ? (
              <div className="empty-state">
                <Radar className="spin" size={26} />
                <p>Connecting to the network…</p>
              </div>
            ) : visible.length ? (
              visible.slice(0, 150).map((f) => (
                <button
                  data-testid="flight-row"
                  key={f.flight_id}
                  className={`flight-row ${selectedId === f.flight_id ? "selected" : ""}`}
                  onClick={() => select(f.flight_id)}
                >
                  <div className="flight-row-top">
                    <strong>{f.flight_number}</strong>
                    <span className={`risk-tag ${f.risk.level.toLowerCase()}`}>
                      {f.risk.level === "LOW"
                        ? "NOMINAL"
                        : f.risk.level + " RISK"}
                    </span>
                  </div>
                  <div className="flight-row-route">
                    <b>{f.origin}</b>
                    <span className="route-dash" />
                    <Plane size={11} />
                    <span className="route-dash" />
                    <b>{f.destination}</b>
                    <span className="flight-row-time">
                      {time(f.scheduled_arrival)}
                    </span>
                  </div>
                  <div className="flight-row-bottom">
                    <span>
                      {f.airline_name} · {f.model}
                    </span>
                    <span className={f.impacts.length ? "affected-text" : ""}>
                      {f.impacts.length
                        ? `+${f.estimated_delay_minutes}m est.`
                        : f.flight_status.replaceAll("_", " ").toLowerCase()}
                    </span>
                  </div>
                </button>
              ))
            ) : (
              <div className="empty-state">
                <Search size={23} />
                <p>
                  {error
                    ? "Network data unavailable"
                    : "No flights match these filters"}
                </p>
                {filtered && <button onClick={clear}>Clear filters</button>}
              </div>
            )}
          </div>
          <div className="sidebar-footer">
            <span className={`connection-dot ${error ? "disconnected" : ""}`} />
            <span>
              {error ? "Connection interrupted" : "Shared database connection"}
            </span>
            <button
              aria-label="Refresh network"
              className="icon-button"
              onClick={refresh}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </aside>
        <main className="map-stage">
          {state ? (
            <FlightMap
              state={state}
              flights={mappedVisible}
              selected={selected}
              onSelect={select}
              layers={layers}
              alternates={alternates}
              history={history}
              replay={replay}
              airport={airport}
              reset={reset}
              theme={theme}
              scenarioFlightIds={scenarioFlightIds}
              showDisruptionImpacts={tool === "lab"}
            />
          ) : (
            <div className="map-placeholder">
              <Radar size={60} />
              <h2>
                {loading
                  ? "Establishing network connection"
                  : "Network connection required"}
              </h2>
              <p>
                {loading
                  ? "Loading airports, aircraft and spatial intelligence…"
                  : error}
              </p>
              {!loading && (
                <button className="wide-button" onClick={refresh}>
                  <RefreshCw size={14} />
                  Retry connection
                </button>
              )}
            </div>
          )}
          <div className="map-topline">
            <div className="map-label">
              <span className="connection-dot" />
              <span>{replay ? "HISTORICAL REPLAY" : "AIRSPACE MONITOR"}</span>
              <b>{replay ? time(replay.recorded_at) + " UTC" : "INDIA"}</b>
            </div>
            <div className="map-toolbar">
              <button
                className="mobile-list-toggle"
                onClick={() => setSidebarOpen(!sidebarOpen)}
              >
                <Search size={15} /> Flights
              </button>
              <button
                title="Reset map view"
                aria-label="Reset map view"
                onClick={() => {
                  setReset((n) => n + 1);
                  setAirport(undefined);
                }}
              >
                <Crosshair size={16} />
              </button>
              <button
                className={layersOpen ? "active" : ""}
                onClick={() => setLayersOpen(!layersOpen)}
              >
                <LayersIcon size={16} />
                <span>Layers</span>
              </button>
            </div>
          </div>
          {layersOpen && (
            <div className="layer-menu panel">
              <h3>MAP LAYERS</h3>
              {(Object.keys(layers) as (keyof Layers)[]).map((key) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={layers[key]}
                    onChange={() =>
                      setLayers({ ...layers, [key]: !layers[key] })
                    }
                  />
                  <span>
                    {key === "airspace"
                      ? "Restricted airspace"
                      : key[0].toUpperCase() + key.slice(1)}
                  </span>
                </label>
              ))}
              <details className="scenario-examples">
                <summary>Scenario examples</summary>
                {(state?.scenario_examples ?? []).map((scenario) => (
                  <button key={scenario.key} onClick={() => {
                    const exampleId = scenario.flight_ids[0];
                    if (exampleId) select(exampleId);
                    setScenarioFlightIds(scenario.flight_ids);
                    setLayersOpen(false);
                    if (scenario.key === "weather") setLayers((value) => ({ ...value, weather: true }));
                    if (scenario.key === "airspace") setLayers((value) => ({ ...value, airspace: true }));
                  }}>{scenario.label}</button>
                ))}
              </details>
            </div>
          )}
          {error && state && (
            <div className="map-error" role="alert">
              Showing last received data. {error}
              <button onClick={refresh}>Retry</button>
            </div>
          )}
          <div className="map-bottom">
            <div className="map-legend">
              <span>
                <i className="nominal" />
                Nominal
              </span>
              <span>
                <i className="elevated" />
                Near weather
              </span>
              <span>
                <i className="impacted" />
                Affected
              </span>
              {selected && <><span><i className="planned-line" />Planned</span><span><i className="actual-line" />Flown</span>{selected.mitigation_type && <span><i className="avoidance-line" />Avoidance</span>}</>}
            </div>
            <div className="data-note">
              {state?.mode === "live"
                ? "Provider observations"
                : "SIMULATED TRAFFIC"}
              <span>Not for navigation</span>
            </div>
          </div>
        </main>
        {selected && !tool && (
          <FlightPanel
            key={selected.flight_id}
            flight={selected}
            onClose={() => {
              setSelectedId(undefined);
              setAlternates([]);
              setHistory([]);
              setReplay(undefined);
            }}
            onAlternates={setAlternates}
            onHistory={setHistory}
            onReplay={setReplay}
            history={history}
            replayIndex={replayIndex}
            setReplayIndex={setReplayIndex}
          />
        )}
        {tool === "lab" && state && (
          <DisruptionPanel
            state={state}
            onClose={() => {
              closeTool();
            }}
            onChange={refresh}
            onAlternates={setAlternates}
            onSelect={select}
            onFocus={(ids) => {
              setScenarioFlightIds(ids);
              setLayers((value) => ({ ...value, disruptions: true }));
            }}
          />
        )}
        {tool === "copilot" && (
          <Copilot
            onClose={closeTool}
            onSelect={select}
            onAlternates={setAlternates}
          />
        )}
      </div>
      <footer className="system-bar">
        <span>
          <span className="connection-dot" /> AEROPULSE OPERATIONS
        </span>
        <span>
          {state?.graph ?? "PostGIS spatial intelligence"}
          <i />
          10s refresh
          <i />
          All times UTC
        </span>
        <span>
          India-linked demonstration <span className="version">v2.0</span>
        </span>
      </footer>
    </div>
  );
}
