from datetime import datetime, timezone
from typing import Annotated
import hmac
import logging
from functools import lru_cache
import httpx
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import session, rows, one
from backend import intelligence, disruptions, graph, copilot, tracking
from backend.schemas import Simulation, CopilotQuestion

app = FastAPI(
    title="AeroPulse",
    description="Spatio-temporal aviation network intelligence. Demonstration data, not for navigation.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings().cors_origins.split(",") if x.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
api = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(session)]


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logging.getLogger(__name__).error("Database operation failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable or migrations pending. Please retry shortly."}
    )


def authorize(authorization: Annotated[str | None, Header()] = None):
    s = settings()
    if s.admin_token:
        if not hmac.compare_digest(authorization or "", f"Bearer {s.admin_token}"):
            raise HTTPException(401, "Operator authorization required")
    elif s.effective_mode != "demo":
        raise HTTPException(403, "Set ADMIN_TOKEN to authorize operational mutations outside demo mode")


@app.get("/health")
@api.get("/health")
def health(db: DB):
    version = one(db, "SELECT PostGIS_Version() AS postgis")["postgis"]
    return {
        "status": "ok",
        "database": "postgresql/postgis",
        "postgis": version,
        "mode": settings().effective_mode,
        "graph": "configured" if graph.configured() else "postgresql-fallback",
        "time": datetime.now(timezone.utc),
    }


@api.get("/airports")
def airports(db: DB):
    return rows(
        db,
        """SELECT airport_id,iata_code,icao_code,airport_name,city,country,elevation_m,timezone,operational_status,
        ST_AsGeoJSON(location)::json AS location FROM airport ORDER BY iata_code""",
    )


@api.get("/airports/nearby")
def nearby(
    db: DB,
    longitude: float = Query(ge=-180, le=180),
    latitude: float = Query(ge=-90, le=90),
    radius_km: float = Query(300, gt=0, le=3000),
):
    return intelligence.nearby(db, longitude, latitude, radius_km)


@api.get("/airports/{airport_id}/alternates")
def airport_alternates(
    airport_id: int,
    db: DB,
    radius_km: float = Query(650, gt=0, le=3000),
    min_runway_m: float = Query(2200, ge=500, le=5000),
):
    if not one(db, "SELECT airport_id FROM airport WHERE airport_id=:id", id=airport_id):
        raise HTTPException(404, "Airport not found")
    return intelligence.alternates(db, airport_id, radius_km, min_runway_m)


@api.get("/airlines")
def airlines(db: DB):
    return rows(db, "SELECT * FROM airline ORDER BY airline_name")


@api.get("/aircraft-types")
def aircraft_types(db: DB):
    return rows(db, "SELECT * FROM aircraft_type ORDER BY aircraft_type_id")


@api.get("/aircraft")
def aircraft(db: DB, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return rows(
        db,
        """SELECT aircraft_id,registration_number,aircraft_type_id,airline_id,aircraft_status,current_speed,heading,last_updated,
        ST_AsGeoJSON(current_location)::json AS current_location FROM aircraft ORDER BY aircraft_id LIMIT :limit OFFSET :offset""",
        limit=limit,
        offset=offset,
    )


@lru_cache(maxsize=512)
def _registration_photo(registration: str):
    """Resolve optional registration imagery; the bundled image is the reliable fallback."""
    try:
        response = httpx.get(
            f"https://api.planespotters.net/pub/photos/reg/{registration}",
            timeout=3.0,
            headers={"User-Agent": "AeroPulse/1.0"},
        )
        response.raise_for_status()
        photo = (response.json().get("photos") or [])[0]
        image = photo.get("thumbnail_large") or photo.get("thumbnail") or {}
        if image.get("src"):
            return {"url": image["src"], "source": "Planespotters.net", "credit": photo.get("photographer")}
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        pass
    return {"url": "/aircraft-fallback.webp", "source": "AeroPulse illustration", "credit": None}


@api.get("/aircraft/{aircraft_id}/photo")
def aircraft_photo(aircraft_id: int, db: DB):
    aircraft_row = one(db, "SELECT registration_number FROM aircraft WHERE aircraft_id=:id", id=aircraft_id)
    if not aircraft_row:
        raise HTTPException(404, "Aircraft not found")
    return _registration_photo(aircraft_row["registration_number"])


@api.get("/routes")
def routes(db: DB, limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
    return rows(
        db,
        """SELECT route_id,route_code,origin_airport_id,destination_airport_id,distance_km,estimated_duration_minutes,route_status,
        ST_AsGeoJSON(route_geometry)::json AS route_geometry FROM route ORDER BY route_id LIMIT :limit OFFSET :offset""",
        limit=limit,
        offset=offset,
    )


@api.get("/flights")
def flights(
    db: DB,
    search: str = Query("", max_length=100),
    airline_id: int | None = None,
    status: str | None = None,
    affected: bool = False,
    high_risk: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Bounded demo network; filter before paginating so counts/pages are consistent.
    result = intelligence.flights(db)
    if search:
        result = [
            f
            for f in result
            if search.lower()
            in " ".join(
                [f["flight_number"], f["origin"], f["destination"], f["origin_city"], f["destination_city"]]
            ).lower()
        ]
    if airline_id:
        result = [f for f in result if f["airline_id"] == airline_id]
    if status:
        result = [f for f in result if f["flight_status"] == status]
    if affected:
        result = [f for f in result if f["impacts"]]
    if high_risk:
        result = [f for f in result if f["risk"]["level"] == "HIGH"]
    return {"total": len(result), "items": result[offset : offset + limit]}


def require_flight(db, flight_id):
    fs = intelligence.flights(db, flight_id)
    if not fs:
        raise HTTPException(404, "Flight not found")
    return fs[0]


@api.get("/flights/{flight_id}")
def flight_detail(flight_id: int, db: DB):
    f = require_flight(db, flight_id)
    f["legs"] = rows(db, "SELECT * FROM flight_leg WHERE flight_id=:id ORDER BY leg_sequence", id=flight_id)
    return f


@api.get("/flights/{flight_id}/positions")
def positions(flight_id: int, db: DB, limit: int = Query(600, ge=1, le=1500), before: datetime | None = None):
    if not one(db, "SELECT flight_id FROM flight WHERE flight_id=:id", id=flight_id):
        raise HTTPException(404, "Flight not found")
    return rows(
        db,
        """SELECT * FROM(SELECT position_id,ST_AsGeoJSON(position)::json AS position,ground_speed,heading,recorded_at
        FROM flight_position WHERE flight_id=:id AND recorded_at<:before ORDER BY recorded_at DESC LIMIT :limit) p ORDER BY recorded_at""",
        id=flight_id,
        before=before or datetime.now(timezone.utc),
        limit=limit,
    )


@api.get("/flights/{flight_id}/risk")
def risk(flight_id: int, db: DB):
    return require_flight(db, flight_id)["risk"]


@api.get("/flights/{flight_id}/alternates")
def flight_alternates(flight_id: int, db: DB):
    f = require_flight(db, flight_id)
    return intelligence.alternates(db, f["destination_airport_id"])


@api.get("/flights/{flight_id}/proximity")
def proximity(flight_id: int, db: DB, radius_km: float = Query(100, gt=0, le=500)):
    require_flight(db, flight_id)
    return intelligence.proximity(db, flight_id, radius_km)


@api.get("/weather")
def weather(db: DB):
    return rows(
        db,
        """SELECT weather_id,weather_type,severity,movement_direction,movement_speed_kmh,start_time,end_time,weather_status,
        ST_AsGeoJSON(affected_area_geometry)::json AS geometry FROM weather_event
        WHERE weather_status='ACTIVE' AND now() BETWEEN start_time AND end_time ORDER BY weather_id""",
    )


@api.get("/airspace")
def airspace(db: DB):
    return rows(
        db,
        """SELECT airspace_zone_id,zone_name,zone_type,lower_altitude,upper_altitude,valid_from,valid_until,zone_status,
        ST_AsGeoJSON(geometry)::json AS geometry FROM airspace_zone WHERE zone_status='ACTIVE' AND now() BETWEEN valid_from AND valid_until""",
    )


@api.get("/runways")
def runways(db: DB, airport_id: int | None = None):
    return rows(
        db,
        """SELECT r.*,EXISTS(SELECT 1 FROM disruption_event e WHERE (e.runway_id=r.runway_id OR
        (e.airport_id=r.airport_id AND e.disruption_type='AIRPORT_CLOSURE')) AND e.disruption_status='ACTIVE'
        AND now() BETWEEN e.start_time AND e.expected_end_time) AS temporarily_closed
        FROM runway r WHERE (:id=0 OR airport_id=:id) ORDER BY runway_id""",
        id=airport_id or 0,
    )


@api.get("/disruptions")
def list_disruptions(db: DB):
    return disruptions.event_rows(db)


@api.post("/disruptions/simulate", dependencies=[Depends(authorize)])
def simulate(request: Simulation, db: DB):
    if settings().effective_mode != "demo":
        raise HTTPException(403, "Simulation is available only in demo mode")
    return disruptions.simulate(db, request)


@api.get("/disruptions/{disruption_id}")
def disruption_detail(disruption_id: int, db: DB):
    event = next((x for x in disruptions.event_rows(db) if x["disruption_id"] == disruption_id), None)
    if not event:
        raise HTTPException(404, "Disruption not found")
    return event


@api.get("/disruptions/{disruption_id}/impacts")
def impacts(disruption_id: int, db: DB):
    if not one(db, "SELECT disruption_id FROM disruption_event WHERE disruption_id=:id", id=disruption_id):
        raise HTTPException(404, "Disruption not found")
    return rows(db, "SELECT * FROM disruption_impact WHERE disruption_id=:id ORDER BY impact_id", id=disruption_id)


@api.post("/disruptions/{disruption_id}/resolve", dependencies=[Depends(authorize)])
def resolve(disruption_id: int, db: DB):
    if settings().effective_mode != "demo":
        raise HTTPException(403, "Demo reset is disabled in live mode")
    return disruptions.resolve(db, disruption_id)


@api.get("/intelligence/network")
def network(db: DB):
    return intelligence.network(db)


@api.get("/intelligence/high-risk")
def high_risk(db: DB):
    return [f for f in intelligence.flights(db) if f["risk"]["level"] == "HIGH"]


@api.get("/intelligence/cascade")
def cascade(db: DB, flight_id: int | None = None):
    if flight_id:
        f = require_flight(db, flight_id)
        result = graph.dependency_paths(db, [flight_id], f["estimated_delay_minutes"] or 90)
        result["basis"] = "active impact" if f["estimated_delay_minutes"] else "what-if: 90 minute delay"
        return result
    roots = rows(
        db,
        """SELECT i.flight_id,max(i.estimated_delay_minutes) AS delay FROM disruption_impact i JOIN disruption_event e USING(disruption_id)
              WHERE i.flight_id IS NOT NULL AND i.impact_type<>'AIRCRAFT_UNAVAILABLE' AND i.resolution_status='OPEN'
                AND e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time GROUP BY i.flight_id""",
    )
    paths = []
    source = "postgresql-recursive-cte"
    for delay in sorted({r["delay"] for r in roots}):
        result = graph.dependency_paths(db, [r["flight_id"] for r in roots if r["delay"] == delay], delay)
        paths.extend(result["paths"])
        source = result["engine"]
    return {"engine": source, "paths": paths, "basis": "active persisted impact delays"}


@api.post("/copilot/query")
def ask(request: CopilotQuestion, db: DB):
    return copilot.query(db, request.question)


@api.get("/map/state")
def map_state(db: DB):
    tracking.tick(db)
    fs = intelligence.flights(db)
    return {
        "mode": settings().effective_mode,
        "source": "Synthetic persisted demonstration"
        if settings().effective_mode == "demo"
        else "Live provider / last persisted observations",
        "generated_at": datetime.now(timezone.utc),
        "flights": fs,
        "airports": airports(db),
        "weather": weather(db),
        "airspace": airspace(db),
        "disruptions": disruptions.event_rows(db),
        "network": {
            "flights": len(fs),
            "daily_operations": one(db, "SELECT count(*) AS n FROM flight")["n"],
            "airborne": sum(f["flight_status"] in ("EN_ROUTE", "APPROACHING") for f in fs),
            "ground": sum(bool(f["position"]) and f["flight_status"] not in ("EN_ROUTE", "APPROACHING") for f in fs),
            "high_risk": sum(f["risk"]["level"] == "HIGH" for f in fs),
            "affected": sum(bool(f["impacts"]) for f in fs),
        },
        "graph": "Neo4j configured" if graph.configured() else "PostgreSQL dependency analysis",
    }


@api.get("/tracking/tick")
def scheduled_tick(db: DB, authorization: Annotated[str | None, Header()] = None):
    secret = settings().cron_secret
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "Cron authorization required")
    if settings().effective_mode == "demo":
        return tracking.tick(db)
    from backend.providers import ingest, OpenSkyProvider

    return ingest(db, OpenSkyProvider())


app.include_router(api)


@app.get("/api/openapi.json", include_in_schema=False)
def public_openapi():
    return app.openapi()


@app.get("/api/docs", include_in_schema=False)
def public_docs():
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="AeroPulse API")
