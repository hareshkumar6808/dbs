"""Set-based spatial features, explainable risk and schedule dependency traversal."""

from backend.db import rows, one
from backend.routing import OPERATIONAL_ROUTE_LATERAL

# A single bounded query joins latest positions and aggregates independent factors.
FLIGHTS_SQL = """SELECT f.*,al.airline_name,al.iata_code AS airline_code,a.registration_number,
  t.manufacturer,t.model,t.aircraft_category,r.route_code,r.origin_airport_id,r.destination_airport_id,
  o.iata_code AS origin,o.city AS origin_city,d.iata_code AS destination,d.city AS destination_city,
  ST_AsGeoJSON(r.route_geometry)::json AS route_geometry,
  ST_AsGeoJSON(operational.geometry)::json AS operational_geometry,
  hazard.kind AS mitigation_type,hazard.name AS mitigation_reason,
  ST_AsGeoJSON(actual.geometry)::json AS actual_geometry,
  ST_AsGeoJSON(p.position)::json AS position,p.ground_speed,p.heading,p.recorded_at,
  ST_Z(p.position) AS altitude_m,
  ST_Distance(ST_Force2D(p.position)::geography,d.location::geography)/1000 AS distance_remaining_km,
  COALESCE(w.severity,0) AS weather_severity,COALESCE(w.inside,false) AS inside_weather,
  COALESCE(w.approaching,false) AS approaching_weather,
  COALESCE(z.names,'[]'::json) AS airspace_names,
  COALESCE(imp.items,'[]'::json) AS impacts,COALESCE(imp.delay,0) AS estimated_delay_minutes,
  o.operational_status AS origin_status,d.operational_status AS destination_status,
  EXISTS(SELECT 1 FROM disruption_event e WHERE e.airport_id=r.origin_airport_id AND e.disruption_type='AIRPORT_CLOSURE'
    AND e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time) AS origin_closed,
  EXISTS(SELECT 1 FROM disruption_event e WHERE e.airport_id=r.destination_airport_id AND e.disruption_type='AIRPORT_CLOSURE'
    AND e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time) AS destination_closed,
  EXISTS(SELECT 1 FROM disruption_event e WHERE e.airport_id IN(r.origin_airport_id,r.destination_airport_id)
    AND e.disruption_type='RUNWAY_CLOSURE' AND e.disruption_status='ACTIVE'
    AND now() BETWEEN e.start_time AND e.expected_end_time) AS runway_closure,
  (SELECT EXTRACT(EPOCH FROM (n.scheduled_departure-f.scheduled_arrival))/60 FROM flight n
    WHERE n.aircraft_id=f.aircraft_id AND n.scheduled_departure>=f.scheduled_arrival
      AND n.flight_id<>f.flight_id AND n.flight_status<>'CANCELLED' ORDER BY n.scheduled_departure,n.flight_id LIMIT 1) AS next_buffer_minutes
  FROM flight f JOIN airline al USING(airline_id) JOIN aircraft a USING(aircraft_id)
  JOIN aircraft_type t USING(aircraft_type_id) JOIN route r USING(route_id)
  JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id
  """ + OPERATIONAL_ROUTE_LATERAL + """
  LEFT JOIN LATERAL(SELECT * FROM flight_position fp WHERE fp.flight_id=f.flight_id ORDER BY recorded_at DESC LIMIT 1) p ON true
  LEFT JOIN LATERAL(SELECT CASE WHEN count(*) > 1 THEN ST_MakeLine(fp.position ORDER BY fp.recorded_at) END AS geometry
    FROM (SELECT position,recorded_at FROM flight_position WHERE flight_id=f.flight_id
      ORDER BY recorded_at DESC LIMIT 240) fp) actual ON true
  LEFT JOIN LATERAL(SELECT max(we.severity) AS severity,
    bool_or(ST_Contains(we.affected_area_geometry,ST_Force2D(p.position))) AS inside,
    bool_or(ST_DWithin(we.affected_area_geometry::geography,ST_Force2D(p.position)::geography,150000)
      AND ST_Intersects(ST_MakeLine(ST_Force2D(p.position),d.location),we.affected_area_geometry)) AS approaching
    FROM weather_event we WHERE we.weather_status='ACTIVE' AND now() BETWEEN we.start_time AND we.end_time
      AND ST_Intersects(r.route_geometry,we.affected_area_geometry)) w ON true
  LEFT JOIN LATERAL(SELECT json_agg(az.zone_name) AS names FROM airspace_zone az
    WHERE az.zone_status='ACTIVE' AND now() BETWEEN az.valid_from AND az.valid_until
      AND ST_Intersects(r.route_geometry,az.geometry)
      AND (p.position IS NULL OR ST_Z(p.position) BETWEEN az.lower_altitude AND az.upper_altitude)) z ON true
  LEFT JOIN LATERAL(SELECT json_agg(json_build_object('impact_id',i.impact_id,'disruption_id',i.disruption_id,
    'impact_type',i.impact_type,'severity',i.severity,'estimated_delay_minutes',i.estimated_delay_minutes,
    'description',e.description)) AS items,max(i.estimated_delay_minutes) AS delay
    FROM disruption_impact i JOIN disruption_event e USING(disruption_id)
    WHERE i.flight_id=f.flight_id AND i.resolution_status='OPEN' AND e.disruption_status='ACTIVE'
      AND now() BETWEEN e.start_time AND e.expected_end_time) imp ON true
  WHERE (:flight_id=0 OR f.flight_id=:flight_id)
    AND (:flight_id<>0 OR (f.scheduled_arrival>now()-interval '90 minutes'
      AND f.scheduled_departure<now()+interval '6 hours'))
  ORDER BY (COALESCE(imp.delay,0)>0) DESC,
    CASE f.flight_status WHEN 'EN_ROUTE' THEN 0 WHEN 'APPROACHING' THEN 1
    WHEN 'TAXIING' THEN 2 WHEN 'BOARDING' THEN 3 WHEN 'DELAYED' THEN 4 WHEN 'SCHEDULED' THEN 5 ELSE 6 END,
    f.scheduled_departure,f.flight_id
  LIMIT :limit OFFSET :offset"""


def risk(f):
    factors = []

    def add(code, points, reason):
        factors.append({"code": code, "points": points, "reason": reason})

    if f["flight_status"] in ("LANDED", "CANCELLED"):
        return {"score": 0, "level": "LOW", "factors": [], "method": "deterministic-v1"}
    if f["weather_severity"]:
        add(
            "WEATHER",
            f["weather_severity"] * 7,
            "Route intersects an active weather zone (severity %s/5)" % f["weather_severity"],
        )
    if f["inside_weather"]:
        add("INSIDE_WEATHER", 10, "Latest recorded position is inside the weather region")
    elif f["approaching_weather"]:
        add("APPROACHING_WEATHER", 5, "Within 150 km of weather with intersection on the remaining direct route")
    if f["airspace_names"]:
        add(
            "AIRSPACE",
            22,
            "Route intersects active airspace at the current altitude: " + ", ".join(f["airspace_names"]),
        )
    if f["destination_closed"] or f["destination_status"] != "OPEN":
        add("DESTINATION_CLOSED", 50, "Destination airport is unavailable; assess diversion")
    if f["origin_closed"] or f["origin_status"] != "OPEN":
        add("ORIGIN_CLOSED", 35, "Origin airport has an active closure")
    if f["runway_closure"]:
        add("RUNWAY", 25, "A runway at the origin or destination is unavailable")
    if f["next_buffer_minutes"] is not None and f["next_buffer_minutes"] < 40:
        add(
            "ROTATION_BUFFER",
            12,
            "Same aircraft operates another flight with only %d minutes of turnaround" % f["next_buffer_minutes"],
        )
    if any(i["impact_type"] == "AIRCRAFT_UNAVAILABLE" for i in f["impacts"]):
        add("DOWNSTREAM", 25, "An earlier flight on this aircraft rotation carries an unresolved delay")
    if f["estimated_delay_minutes"] >= 45:
        add("DELAY", 15, "Estimated disruption delay is at least 45 minutes; congestion/rotation exposure")
    score = min(100, sum(x["points"] for x in factors))
    return {
        "score": score,
        "level": "HIGH" if score >= 50 else "MODERATE" if score >= 20 else "LOW",
        "factors": factors,
        "method": "deterministic-v1",
    }


def flights(db, flight_id=0, limit=2000, offset=0):
    result = rows(db, FLIGHTS_SQL, flight_id=flight_id, limit=limit, offset=offset)
    for f in result:
        f["risk"] = risk(f)
    return result


def alternates(db, airport_id, radius_km=650, min_runway_m=2200):
    # Airport/runway closures are derived from active events; original infrastructure status is preserved.
    return rows(
        db,
        """SELECT a.airport_id,a.iata_code,a.airport_name,a.city,ST_AsGeoJSON(a.location)::json AS location,
        ST_Distance(a.location::geography,src.location::geography)/1000 AS distance_km,
        rw.length_m AS available_runway_m,rw.runway_identifier,
        'Operational airport with an open runway meeting the requested minimum length' AS reason
        FROM airport src JOIN airport a ON a.airport_id<>src.airport_id
        JOIN LATERAL(SELECT r.length_m,r.runway_identifier FROM runway r WHERE r.airport_id=a.airport_id
          AND r.runway_status='OPEN' AND r.length_m>=:length AND NOT EXISTS(
            SELECT 1 FROM disruption_event e WHERE e.runway_id=r.runway_id AND e.disruption_status='ACTIVE'
              AND now() BETWEEN e.start_time AND e.expected_end_time AND e.disruption_type='RUNWAY_CLOSURE')
          ORDER BY r.length_m DESC LIMIT 1) rw ON true
        WHERE src.airport_id=:id AND a.operational_status='OPEN'
          AND ST_DWithin(a.location::geography,src.location::geography,:radius*1000)
          AND NOT EXISTS(SELECT 1 FROM disruption_event e WHERE e.airport_id=a.airport_id
            AND e.disruption_type='AIRPORT_CLOSURE' AND e.disruption_status='ACTIVE'
            AND now() BETWEEN e.start_time AND e.expected_end_time)
        ORDER BY distance_km,a.airport_id LIMIT 6""",
        id=airport_id,
        radius=radius_km,
        length=min_runway_m,
    )


def nearby(db, lon, lat, radius_km):
    return rows(
        db,
        """SELECT airport_id,iata_code,airport_name,operational_status,ST_AsGeoJSON(location)::json AS location,
      ST_Distance(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography)/1000 AS distance_km
      FROM airport WHERE ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,:radius*1000)
      ORDER BY distance_km LIMIT 100""",
        lon=lon,
        lat=lat,
        radius=radius_km,
    )


def proximity(db, flight_id, radius_km):
    return rows(
        db,
        """WITH latest AS (SELECT DISTINCT ON(flight_id) flight_id,position,recorded_at
        FROM flight_position WHERE recorded_at>now()-interval '2 minutes' ORDER BY flight_id,recorded_at DESC)
      SELECT f.flight_id,f.flight_number,ST_Distance(ST_Force2D(p.position)::geography,ST_Force2D(s.position)::geography)/1000 AS distance_km,
        abs(ST_Z(p.position)-ST_Z(s.position)) AS vertical_separation_m
      FROM latest s JOIN latest p ON p.flight_id<>s.flight_id JOIN flight f ON f.flight_id=p.flight_id
      WHERE s.flight_id=:id AND f.flight_status='EN_ROUTE' AND ST_DWithin(ST_Force2D(p.position)::geography,
        ST_Force2D(s.position)::geography,:radius*1000) ORDER BY distance_km LIMIT 100""",
        id=flight_id,
        radius=radius_km,
    )


def cascade(db, roots, delay_minutes=90, max_depth=5):
    if not roots:
        return []
    # Consecutive aircraft assignments only; turnaround buffers absorb delay at each hop.
    return rows(
        db,
        """WITH RECURSIVE ordered AS (
        SELECT flight_id,flight_number,aircraft_id,scheduled_arrival,scheduled_departure,
          lead(flight_id) OVER(PARTITION BY aircraft_id ORDER BY scheduled_departure,flight_id) AS next_id
        FROM flight WHERE flight_status<>'CANCELLED'
      ), chain AS (
        SELECT f.flight_id AS root_id,f.flight_id,f.flight_number,f.next_id,f.scheduled_arrival,0 AS depth,
          ARRAY[f.flight_id] AS path,CAST(:delay AS integer) AS delay_minutes
        FROM ordered f WHERE f.flight_id=ANY(:roots)
        UNION ALL
        SELECT c.root_id,n.flight_id,n.flight_number,n.next_id,n.scheduled_arrival,c.depth+1,c.path||n.flight_id,
          GREATEST(0,c.delay_minutes-GREATEST(0,EXTRACT(EPOCH FROM(n.scheduled_departure-c.scheduled_arrival))/60-25)::integer)
        FROM chain c JOIN ordered n ON n.flight_id=c.next_id
        WHERE c.depth<:depth AND c.delay_minutes>0 AND NOT n.flight_id=ANY(c.path)
      ) SELECT root_id,flight_id,flight_number,depth,path,delay_minutes,
        'Same aircraft; delay propagates after available turnaround buffer (25 minute minimum)' AS reason
        FROM chain WHERE depth>0 AND delay_minutes>0 ORDER BY root_id,depth""",
        roots=roots,
        delay=delay_minutes,
        depth=max_depth,
    )


def network(db):
    fs = flights(db)
    return {
        "flights": len(fs),
        "airborne": sum(f["flight_status"] == "EN_ROUTE" for f in fs),
        "high_risk": sum(f["risk"]["level"] == "HIGH" for f in fs),
        "affected": sum(bool(f["impacts"]) for f in fs),
        "active_disruptions": one(
            db,
            "SELECT count(*) AS n FROM disruption_event WHERE disruption_status='ACTIVE' AND now() BETWEEN start_time AND expected_end_time",
        )["n"],
        "position_updated_at": one(db, "SELECT max(recorded_at) AS t FROM flight_position")["t"],
    }
