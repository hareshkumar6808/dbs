"""Deterministic synthetic traffic. Airport coordinates are approximate; not navigation data."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from backend.models import (
    Airport,
    Airline,
    AircraftType,
    Aircraft,
    Route,
    Flight,
    FlightLeg,
    Runway,
    WeatherEvent,
    AirspaceZone,
)
from backend.db import one

AIRPORTS = [
    ("MAA", "VOMM", "Chennai International", "Chennai", 80.1693, 12.9941, 16, 3658),
    ("BLR", "VOBL", "Kempegowda International", "Bengaluru", 77.7066, 13.1986, 915, 4000),
    ("DEL", "VIDP", "Indira Gandhi International", "Delhi", 77.1031, 28.5562, 237, 4430),
    ("BOM", "VABB", "Chhatrapati Shivaji Maharaj International", "Mumbai", 72.8656, 19.0896, 11, 3445),
    ("HYD", "VOHS", "Rajiv Gandhi International", "Hyderabad", 78.4294, 17.2403, 617, 4260),
    ("CCU", "VECC", "Netaji Subhas Chandra Bose International", "Kolkata", 88.4467, 22.6547, 5, 3627),
    ("COK", "VOCI", "Cochin International", "Kochi", 76.4019, 10.1520, 9, 3400),
    ("GOX", "VOGA", "Manohar International", "Goa", 73.9135, 15.7443, 165, 3500),
    ("PNQ", "VAPO", "Pune Airport", "Pune", 73.9197, 18.5821, 592, 2535),
    ("AMD", "VAAH", "Sardar Vallabhbhai Patel International", "Ahmedabad", 72.6347, 23.0772, 58, 3505),
    ("TRV", "VOTV", "Thiruvananthapuram International", "Thiruvananthapuram", 76.9201, 8.4821, 4, 3400),
    ("VTZ", "VOVZ", "Visakhapatnam Airport", "Visakhapatnam", 83.2245, 17.7212, 5, 3050),
]


def seed(db):
    db.execute(text("SELECT pg_advisory_xact_lock(73001)"))
    if one(db, "SELECT count(*) AS n FROM airport")["n"]:
        return {"seeded": False, "reason": "Database already contains airports"}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for idx, (iata, icao, name, city, lon, lat, elevation, length) in enumerate(AIRPORTS, 1):
        db.add(
            Airport(
                airport_id=idx,
                iata_code=iata,
                icao_code=icao,
                airport_name=name,
                city=city,
                country="India",
                elevation_m=elevation,
                timezone="Asia/Kolkata",
                operational_status="OPEN",
                location=f"SRID=4326;POINT({lon} {lat})",
            )
        )
    for idx, (iata, icao, name) in enumerate(
        [("6E", "IGO", "IndiGo"), ("AI", "AIC", "Air India"), ("QP", "AKJ", "Akasa Air"), ("SG", "SEJ", "SpiceJet")], 1
    ):
        db.add(
            Airline(
                airline_id=idx,
                iata_code=iata,
                icao_code=icao,
                airline_name=name,
                country="India",
                operational_status="ACTIVE",
            )
        )
    for idx, (maker, model, capacity, cargo, speed, rng) in enumerate(
        [
            ("Airbus", "A320neo", 186, 19000, 830, 6300),
            ("Airbus", "A321neo", 220, 23000, 840, 7400),
            ("Boeing", "737 MAX 8", 189, 20000, 840, 6570),
            ("Boeing", "737-800", 189, 20000, 828, 5765),
        ],
        1,
    ):
        db.add(
            AircraftType(
                aircraft_type_id=idx,
                manufacturer=maker,
                model=model,
                aircraft_category="NARROW_BODY",
                passenger_capacity=capacity,
                cargo_capacity=cargo,
                cruise_speed_kmh=speed,
                range_km=rng,
            )
        )
    db.flush()
    for idx, airport in enumerate(AIRPORTS, 1):
        db.add(
            Runway(
                airport_id=idx,
                runway_identifier="07/25" if idx == 1 else "09/27",
                length_m=airport[7],
                width_m=45,
                surface_type="ASPHALT",
                heading=70 if idx == 1 else 90,
                runway_status="OPEN",
            )
        )
    # Every ordered airport pair is a route, supporting geographically continuous rotations.
    route_map = {}
    for origin in range(1, len(AIRPORTS) + 1):
        for dest in range(1, len(AIRPORTS) + 1):
            if origin == dest:
                continue
            metric = one(
                db,
                """SELECT ST_Distance(a.location::geography,b.location::geography)/1000 AS km,
                       ST_AsEWKT(ST_MakeLine(a.location,b.location)) AS geom FROM airport a,airport b
                       WHERE a.airport_id=:o AND b.airport_id=:d""",
                o=origin,
                d=dest,
            )
            route = Route(
                origin_airport_id=origin,
                destination_airport_id=dest,
                route_code=f"{AIRPORTS[origin - 1][0]}-{AIRPORTS[dest - 1][0]}",
                distance_km=metric["km"],
                estimated_duration_minutes=max(45, round(metric["km"] / 750 * 60 + 20)),
                route_geometry=metric["geom"],
                route_status="ACTIVE",
            )
            db.add(route)
            db.flush()
            route_map[origin, dest] = route
    for idx in range(1, 33):
        airline = (idx - 1) % 4 + 1
        aircraft = Aircraft(
            aircraft_id=idx,
            registration_number=f"VT-D{idx:02}",
            aircraft_type_id=airline,
            airline_id=airline,
            aircraft_status="IN_SERVICE",
            current_speed=0,
            heading=0,
            last_updated=now,
        )
        db.add(aircraft)
        db.flush()
        origin = (idx - 1) % 12 + 1
        dest = (origin + idx % 7 + 1) % 12 + 1
        if dest == origin:
            dest = origin % 12 + 1
        first = route_map[origin, dest]
        departure = now - timedelta(minutes=first.estimated_duration_minutes * (0.12 + (idx % 9) * 0.085))
        for leg in range(4):
            route = route_map[origin, dest]
            arrival = departure + timedelta(minutes=route.estimated_duration_minutes)
            flight = Flight(
                flight_number=f"{['6E', 'AI', 'QP', 'SG'][airline - 1]}{200 + idx * 4 + leg}",
                airline_id=airline,
                aircraft_id=idx,
                route_id=route.route_id,
                scheduled_departure=departure,
                scheduled_arrival=arrival,
                actual_departure=departure if leg == 0 else None,
                flight_status="EN_ROUTE" if leg == 0 else "SCHEDULED",
                departure_gate=f"{idx % 20 + 1}",
                arrival_gate=f"{idx % 15 + 1}",
                last_updated=now,
            )
            db.add(flight)
            db.flush()
            db.add(
                FlightLeg(
                    flight_id=flight.flight_id,
                    leg_sequence=1,
                    departure_airport_id=origin,
                    arrival_airport_id=dest,
                    scheduled_departure=departure,
                    scheduled_arrival=arrival,
                    actual_departure=flight.actual_departure,
                    leg_status=flight.flight_status,
                )
            )
            if leg == 0:
                # Actual historical database samples for replay, one per minute since departure.
                db.execute(
                    text("""INSERT INTO flight_position(flight_id,position,ground_speed,heading,recorded_at)
                    SELECT :id, ST_SetSRID(ST_MakePoint(ST_X(p),ST_Y(p),10000*sin(pi()*fraction)),4326),
                           :speed, degrees(ST_Azimuth(ST_StartPoint(r.route_geometry),ST_EndPoint(r.route_geometry))), t
                    FROM route r, generate_series(CAST(:depart AS timestamptz),CAST(:now AS timestamptz),interval '1 minute') t,
                    LATERAL (SELECT LEAST(1.0,EXTRACT(EPOCH FROM (t-CAST(:depart AS timestamptz)))/:duration) AS fraction) f,
                    LATERAL (SELECT ST_LineInterpolatePoint(r.route_geometry,fraction) AS p) point
                    WHERE r.route_id=:route"""),
                    {
                        "id": flight.flight_id,
                        "speed": route.distance_km / (route.estimated_duration_minutes / 60),
                        "depart": departure,
                        "now": now,
                        "duration": route.estimated_duration_minutes * 60,
                        "route": route.route_id,
                    },
                )
            departure = arrival + timedelta(minutes=25 + (idx % 3) * 10)
            origin = dest
            dest = (dest + idx % 5 + 2) % 12 + 1
            if dest == origin:
                dest = origin % 12 + 1
    db.add(
        WeatherEvent(
            weather_type="CONVECTIVE_STORM",
            severity=4,
            movement_direction=280,
            movement_speed_kmh=22,
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(days=30),
            weather_status="ACTIVE",
            affected_area_geometry="SRID=4326;POLYGON((79 12,81.8 12.8,82.2 15.8,80.1 16.5,78.9 14.5,79 12))",
        )
    )
    db.add(
        AirspaceZone(
            zone_name="Deccan training sector · DEMO",
            zone_type="MILITARY",
            lower_altitude=0,
            upper_altitude=14000,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            zone_status="ACTIVE",
            geometry="SRID=4326;POLYGON((75.8 16,77.5 16,77.5 18,75.8 18,75.8 16))",
        )
    )
    db.flush()
    db.execute(
        text("""UPDATE aircraft a SET current_location=p.position,current_speed=p.ground_speed,heading=p.heading,last_updated=p.recorded_at
        FROM (SELECT DISTINCT ON(f.aircraft_id) f.aircraft_id,p.* FROM flight_position p JOIN flight f USING(flight_id)
              ORDER BY f.aircraft_id,p.recorded_at DESC) p WHERE a.aircraft_id=p.aircraft_id""")
    )
    db.commit()
    return {"seeded": True, "airports": 12, "aircraft": 32, "flights": 128, "routes": 132}
