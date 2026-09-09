"""Serverless-safe demand ticks, also callable by a scheduled/background worker."""

from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from backend.config import settings
from backend.db import one, rows
from backend.models import Flight, FlightLeg
from backend.routing import OPERATIONAL_ROUTE_LATERAL


def replenish(db, now):
    """Create new synthetic rotations when an aircraft exhausts its timetable.

    New flight IDs preserve old replay records. A resumed idle demo starts each
    aircraft partway along its next synthetic route so a returning visitor has traffic.
    """
    # Only one invocation rebuilds expired rotations. Other time buckets can
    # still update already-committed flights while this batch is being created.
    if not one(db, "SELECT pg_try_advisory_xact_lock(73003) AS locked")["locked"]:
        return
    exhausted = rows(
        db,
        """SELECT a.aircraft_id,a.airline_id,al.iata_code,r.origin_airport_id,r.destination_airport_id,
        f.scheduled_arrival FROM aircraft a JOIN airline al ON al.airline_id=a.airline_id
        JOIN LATERAL(SELECT * FROM flight WHERE aircraft_id=a.aircraft_id ORDER BY scheduled_arrival DESC LIMIT 1) f ON true
        JOIN route r ON r.route_id=f.route_id WHERE f.scheduled_arrival<:now""",
        now=now,
    )
    if not exhausted:
        return
    route_map = {(r["origin_airport_id"], r["destination_airport_id"]): r for r in rows(db, "SELECT * FROM route")}
    new_flights = []
    leg_specs = []
    for a in exhausted:
        origin, dest = a["destination_airport_id"], a["origin_airport_id"]
        route = route_map.get((origin, dest))
        if route is None:
            route = next(r for (route_origin, _), r in route_map.items() if route_origin == origin)
            dest = route["destination_airport_id"]
        departure = max(
            a["scheduled_arrival"] + timedelta(minutes=25),
            now - timedelta(minutes=route["estimated_duration_minutes"] * (0.15 + (a["aircraft_id"] % 7) * 0.1)),
        )
        for leg in range(4):
            route = route_map.get((origin, dest))
            if route is None:
                route = next(r for (route_origin, _), r in route_map.items() if route_origin == origin)
                dest = route["destination_airport_id"]
            arrival = departure + timedelta(minutes=route["estimated_duration_minutes"])
            f = Flight(
                flight_number=f"{a['iata_code']}{500 + a['aircraft_id'] * 4 + leg}",
                airline_id=a["airline_id"],
                aircraft_id=a["aircraft_id"],
                route_id=route["route_id"],
                scheduled_departure=departure,
                scheduled_arrival=arrival,
                flight_status="SCHEDULED",
                departure_gate="D1",
                arrival_gate="D2",
                last_updated=now,
            )
            db.add(f)
            new_flights.append(f)
            leg_specs.append((f, origin, dest, departure, arrival))
            departure = arrival + timedelta(minutes=25 + (a["aircraft_id"] % 3) * 10)
            origin, dest = dest, origin
    # One batched flush avoids thousands of network round trips to cloud Postgres.
    db.flush()
    db.add_all([
        FlightLeg(
            flight_id=f.flight_id,
            leg_sequence=1,
            departure_airport_id=origin,
            arrival_airport_id=dest,
            scheduled_departure=departure,
            scheduled_arrival=arrival,
            leg_status="SCHEDULED",
        )
        for f, origin, dest, departure, arrival in leg_specs
    ])
    db.flush()


def tick(db):
    if settings().effective_mode != "demo":
        return {"updated": 0, "mode": settings().effective_mode}
    # All clients share a transaction lock and a ten-second DB time bucket.
    now = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp() // 10) * 10, timezone.utc)
    # Scope the lock to this time bucket. If a serverless invocation is frozen
    # while holding an older transaction lock, later buckets can still advance.
    bucket = int(now.timestamp() // 10 % 2_147_483_647)
    if not one(db, "SELECT pg_try_advisory_xact_lock(73002,:bucket) AS locked", bucket=bucket)["locked"]:
        return {"updated": 0, "mode": "demo"}
    replenish(db, now)
    # Keep the ground phase visible as the rolling timetable advances.
    db.execute(
        text("""UPDATE flight SET flight_status='BOARDING',last_updated=:now
        WHERE flight_status='SCHEDULED'
          AND scheduled_departure>:now AND scheduled_departure<=:now+interval '30 minutes'"""),
        {"now": now},
    )
    updated = db.execute(
        text("""WITH moving AS (
        SELECT f.flight_id,f.aircraft_id,operational.geometry AS route_geometry,
          LEAST(1.0,GREATEST(0.0,EXTRACT(EPOCH FROM (CAST(:now AS timestamptz)-f.scheduled_departure))/
            EXTRACT(EPOCH FROM (f.scheduled_arrival-f.scheduled_departure)))) AS fraction,
          r.distance_km/EXTRACT(EPOCH FROM (f.scheduled_arrival-f.scheduled_departure))*3600 AS speed,
          t.cruise_speed_kmh
        FROM flight f JOIN route r USING(route_id)
        JOIN aircraft a USING(aircraft_id) JOIN aircraft_type t USING(aircraft_type_id)
        """ + OPERATIONAL_ROUTE_LATERAL + """
        WHERE f.scheduled_departure<=:now AND f.scheduled_arrival>=:now
          AND f.flight_status IN ('SCHEDULED','BOARDING','TAXIING','EN_ROUTE','APPROACHING')
    ), inserted AS (
        INSERT INTO flight_position(flight_id,position,ground_speed,heading,recorded_at)
        SELECT flight_id,ST_SetSRID(ST_MakePoint(ST_X(p),ST_Y(p),
          CASE WHEN fraction<=0.04 THEN 0
               WHEN fraction<0.24 THEN 11200*((fraction-.04)/.20)
               WHEN fraction<=0.74 THEN 11200 + 260*sin(fraction*14*pi())
               WHEN fraction<.97 THEN 11200*((.97-fraction)/.23)
               ELSE 0 END),4326),
          CASE WHEN fraction<=0.04 THEN 24 + 8*sin(fraction*80)
               WHEN fraction<0.16 THEN 250 + cruise_speed_kmh*((fraction-.04)/.12)*.72
               WHEN fraction<=0.78 THEN LEAST(cruise_speed_kmh,speed)*(1 + .025*sin(fraction*18*pi()))
               WHEN fraction<.97 THEN 220 + LEAST(cruise_speed_kmh,speed)*((.97-fraction)/.19)*.55
               ELSE 32 END,
          degrees(ST_Azimuth(
            ST_LineInterpolatePoint(route_geometry,GREATEST(0,fraction-.003)),
            ST_LineInterpolatePoint(route_geometry,LEAST(1,fraction+.003)))),:now
        FROM moving,LATERAL(SELECT ST_LineInterpolatePoint(route_geometry,fraction) AS p) point
        ON CONFLICT(flight_id,recorded_at) DO NOTHING RETURNING *
    ) UPDATE aircraft a SET current_location=p.position,current_speed=p.ground_speed,heading=p.heading,last_updated=:now
      FROM (SELECT DISTINCT ON(f.aircraft_id) f.aircraft_id,i.* FROM inserted i JOIN flight f USING(flight_id)
            ORDER BY f.aircraft_id,f.scheduled_departure DESC) p WHERE a.aircraft_id=p.aircraft_id"""),
        {"now": now},
    ).rowcount
    db.execute(
        text("""UPDATE flight SET flight_status=CASE WHEN scheduled_arrival<=:now THEN 'LANDED'
        WHEN scheduled_departure>:now-interval '10 minutes' THEN 'TAXIING'
        WHEN scheduled_arrival<=:now+interval '20 minutes' THEN 'APPROACHING' ELSE 'EN_ROUTE' END,
        actual_departure=COALESCE(actual_departure,scheduled_departure),
        actual_arrival=CASE WHEN scheduled_arrival<=:now THEN scheduled_arrival ELSE NULL END,last_updated=:now
        WHERE scheduled_departure<=:now AND flight_status IN ('SCHEDULED','BOARDING','TAXIING','EN_ROUTE','APPROACHING')"""),
        {"now": now},
    )
    db.execute(
        text("""UPDATE flight_leg l SET leg_status=f.flight_status,actual_departure=f.actual_departure,
        actual_arrival=f.actual_arrival FROM flight f WHERE f.flight_id=l.flight_id AND f.last_updated=:now"""),
        {"now": now},
    )
    # Retain seven days of high-resolution replay; cap work to one batch per tick.
    db.execute(
        text("""DELETE FROM flight_position WHERE position_id IN
        (SELECT position_id FROM flight_position WHERE recorded_at<now()-interval '7 days' LIMIT 2000)""")
    )
    db.commit()
    return {"updated": updated, "mode": "demo", "recorded_at": now}
