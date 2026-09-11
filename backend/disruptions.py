from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import text
from backend.db import one, rows
from backend.models import DisruptionEvent, DisruptionImpact, WeatherEvent
from backend.intelligence import cascade, alternates


def event_rows(db):
    return rows(
        db,
        """SELECT e.*,a.iata_code,a.airport_name,
        CASE WHEN e.weather_id IS NOT NULL THEN ST_AsGeoJSON(w.affected_area_geometry)::json
             ELSE ST_AsGeoJSON(ST_Buffer(a.location::geography,60000)::geometry)::json END AS geometry,
        (e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time) AS is_active
        FROM disruption_event e LEFT JOIN airport a USING(airport_id) LEFT JOIN weather_event w USING(weather_id)
        ORDER BY e.start_time DESC LIMIT 100""",
    )


def simulate(db, request):
    db.execute(text("SELECT pg_advisory_xact_lock(73003)"))
    airport = one(db, "SELECT * FROM airport WHERE airport_id=:id", id=request.airport_id)
    if not airport:
        raise HTTPException(404, "Airport not found")
    if request.runway_id:
        runway = one(
            db,
            "SELECT runway_id FROM runway WHERE runway_id=:id AND airport_id=:airport",
            id=request.runway_id,
            airport=request.airport_id,
        )
        if not runway:
            raise HTTPException(422, "Runway does not belong to the selected airport")
    if (
        one(
            db,
            "SELECT count(*) AS n FROM disruption_event WHERE disruption_status='ACTIVE' AND expected_end_time>now()",
        )["n"]
        >= 20
    ):
        raise HTTPException(409, "Resolve an active scenario before creating another (maximum 20)")
    duplicate = one(
        db,
        """SELECT disruption_id FROM disruption_event WHERE airport_id=:airport AND disruption_type=:kind
        AND runway_id IS NOT DISTINCT FROM :runway AND disruption_status='ACTIVE' AND expected_end_time>now()""",
        airport=request.airport_id,
        kind=request.disruption_type,
        runway=request.runway_id,
    )
    if duplicate:
        raise HTTPException(409, "This scenario is already active; resolve it before repeating")
    now = datetime.now(timezone.utc)
    end = now + timedelta(minutes=request.duration_minutes)
    weather_id = None
    if request.disruption_type == "SEVERE_WEATHER":
        geom = one(
            db,
            "SELECT ST_AsEWKT(ST_Buffer(location::geography,150000)::geometry) AS geom FROM airport WHERE airport_id=:id",
            id=request.airport_id,
        )["geom"]
        weather = WeatherEvent(
            weather_type="SIMULATED_STORM",
            severity=request.severity,
            movement_direction=0,
            movement_speed_kmh=0,
            start_time=now,
            end_time=end,
            weather_status="ACTIVE",
            affected_area_geometry=geom,
        )
        db.add(weather)
        db.flush()
        weather_id = weather.weather_id
    event = DisruptionEvent(
        disruption_type=request.disruption_type,
        severity=request.severity,
        airport_id=request.airport_id,
        runway_id=request.runway_id if request.disruption_type == "RUNWAY_CLOSURE" else None,
        weather_id=weather_id,
        start_time=now,
        expected_end_time=end,
        description=f"DEMO · {airport['iata_code']} · {request.disruption_type.replace('_', ' ').lower()}",
        disruption_status="ACTIVE",
    )
    db.add(event)
    db.flush()
    direct = rows(
        db,
        """SELECT f.flight_id,f.flight_number,f.aircraft_id,f.flight_status,
          r.origin_airport_id,r.destination_airport_id
        FROM flight f JOIN route r USING(route_id)
        LEFT JOIN LATERAL(SELECT position FROM flight_position fp WHERE fp.flight_id=f.flight_id
          ORDER BY recorded_at DESC LIMIT 1) p ON true
        WHERE f.flight_status IN ('SCHEDULED','BOARDING','DELAYED','TAXIING','EN_ROUTE','APPROACHING')
        AND f.scheduled_departure<:end AND f.scheduled_arrival>:now AND
        ((CAST(:weather AS integer) IS NULL AND
          ((r.origin_airport_id=:airport AND f.flight_status IN ('SCHEDULED','BOARDING','DELAYED','TAXIING'))
           OR (r.destination_airport_id=:airport AND f.flight_status IN
             ('SCHEDULED','BOARDING','DELAYED','TAXIING','EN_ROUTE','APPROACHING')))) OR
        (CAST(:weather AS integer) IS NOT NULL AND EXISTS(SELECT 1 FROM weather_event w WHERE w.weather_id=:weather
          AND ((f.flight_status IN ('SCHEDULED','BOARDING','DELAYED','TAXIING')
                AND ST_Intersects(w.affected_area_geometry,r.route_geometry))
            OR (f.flight_status IN ('EN_ROUTE','APPROACHING') AND p.position IS NOT NULL
                AND ST_Intersects(w.affected_area_geometry,
                  ST_MakeLine(ST_Force2D(p.position),(SELECT location FROM airport WHERE airport_id=r.destination_airport_id))))))))""",
        end=end,
        now=now,
        airport=request.airport_id,
        weather=weather_id,
    )
    delay = min(
        request.duration_minutes, request.severity * (25 if request.disruption_type == "AIRPORT_CLOSURE" else 15)
    )
    roots = [f["flight_id"] for f in direct]
    for f in direct:
        diversion = (
            f["flight_status"] == "EN_ROUTE"
            and f["destination_airport_id"] == request.airport_id
            and request.disruption_type in ("AIRPORT_CLOSURE", "RUNWAY_CLOSURE")
        )
        db.add(
            DisruptionImpact(
                disruption_id=event.disruption_id,
                flight_id=f["flight_id"],
                aircraft_id=f["aircraft_id"],
                airport_id=request.airport_id,
                impact_type="DIVERSION_RISK" if diversion else "FLIGHT_DELAY",
                severity=request.severity,
                estimated_delay_minutes=delay,
                detected_at=now,
                resolution_status="OPEN",
            )
        )
    downstream = cascade(db, roots, delay)
    # One downstream impact per flight; retain every root/path in the response.
    downstream_delays = {}
    for f in downstream:
        if f["flight_id"] not in roots:
            downstream_delays[f["flight_id"]] = max(f["delay_minutes"], downstream_delays.get(f["flight_id"], 0))
    for fid, minutes in downstream_delays.items():
        db.add(
            DisruptionImpact(
                disruption_id=event.disruption_id,
                flight_id=fid,
                impact_type="AIRCRAFT_UNAVAILABLE",
                severity=max(1, request.severity - 1),
                estimated_delay_minutes=minutes,
                detected_at=now,
                resolution_status="OPEN",
            )
        )
    db.flush()
    result = {
        "disruption_id": event.disruption_id,
        "direct_flights": direct,
        "downstream_flights": downstream,
        "estimated_delay_minutes": delay,
        "alternates": alternates(db, request.airport_id),
        "method": "Scenario estimates; schedule buffers and infrastructure/spatial intersections, not a prediction of real operations",
    }
    db.commit()
    return result


def resolve(db, event_id):
    db.execute(text("SELECT pg_advisory_xact_lock(73003)"))
    event = db.get(DisruptionEvent, event_id)
    if not event:
        raise HTTPException(404, "Disruption not found")
    event.disruption_status = "RESOLVED"
    event.actual_end_time = datetime.now(timezone.utc)
    db.execute(
        text("UPDATE disruption_impact SET resolution_status='RESOLVED' WHERE disruption_id=:id"), {"id": event_id}
    )
    if event.weather_id:
        db.execute(
            text(
                "UPDATE weather_event SET weather_status='RESOLVED' WHERE weather_id=:id AND weather_type='SIMULATED_STORM'"
            ),
            {"id": event.weather_id},
        )
    db.commit()
    return {"disruption_id": event_id, "status": "RESOLVED"}
