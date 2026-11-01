"""Keyless natural-language query planner for AeroPulse's read-only database."""

import re

from backend import intelligence
from backend.db import one, rows

EXAMPLES = [
    "How many flights are scheduled today?",
    "Which flights are within 200 km of MAA right now?",
    "Show Air India flights from DEL to BOM",
    "Which airports have the most flights?",
    "List active weather and disruptions",
    "How many aircraft are there by model?",
    "What is the route distance between Chennai and Delhi?",
    "Which flights are high risk and why?",
]

# Fixed query plans keep user text out of SQL while covering every application table.
ENTITY_ALIASES = {
    "flight leg": "flight_leg", "flight legs": "flight_leg", "legs": "flight_leg",
    "position": "flight_position", "positions": "flight_position", "tracks": "flight_position",
    "aircraft type": "aircraft_type", "aircraft types": "aircraft_type", "models": "aircraft_type",
    "weather": "weather_event", "weather event": "weather_event", "weather events": "weather_event",
    "airspace": "airspace_zone", "airspace zone": "airspace_zone", "restricted zone": "airspace_zone",
    "disruption impact": "disruption_impact", "impacts": "disruption_impact",
    "disruption": "disruption_event", "disruptions": "disruption_event", "event": "disruption_event",
    "airport": "airport", "airports": "airport", "airline": "airline", "airlines": "airline", "carrier": "airline", "carriers": "airline",
    "aircraft": "aircraft", "plane": "aircraft", "planes": "aircraft", "route": "route", "routes": "route",
    "runway": "runway", "runways": "runway", "flight": "flight", "flights": "flight",
}

LIST_SQL = {
    "airport": "SELECT iata_code,icao_code,airport_name,city,country,operational_status,elevation_m FROM airport",
    "airline": "SELECT iata_code,icao_code,airline_name,country,operational_status FROM airline",
    "aircraft_type": "SELECT manufacturer,model,aircraft_category,passenger_capacity,cruise_speed_kmh,range_km FROM aircraft_type",
    "aircraft": "SELECT a.registration_number,al.airline_name,t.manufacturer,t.model,a.aircraft_status,a.current_speed,a.heading,a.last_updated FROM aircraft a JOIN airline al USING(airline_id) JOIN aircraft_type t USING(aircraft_type_id)",
    "route": "SELECT r.route_code,o.iata_code AS origin,d.iata_code AS destination,r.distance_km,r.estimated_duration_minutes,r.route_status FROM route r JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id",
    "flight": "SELECT f.flight_id,f.flight_number,al.airline_name,t.model,r.route_code,o.iata_code AS origin,d.iata_code AS destination,f.flight_status,f.scheduled_departure,f.scheduled_arrival FROM flight f JOIN airline al USING(airline_id) JOIN aircraft a USING(aircraft_id) JOIN aircraft_type t USING(aircraft_type_id) JOIN route r USING(route_id) JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id",
    "flight_leg": "SELECT l.flight_id,l.leg_sequence,o.iata_code AS departure,a.iata_code AS arrival,l.leg_status,l.scheduled_departure,l.scheduled_arrival FROM flight_leg l JOIN airport o ON o.airport_id=l.departure_airport_id JOIN airport a ON a.airport_id=l.arrival_airport_id",
    "flight_position": "SELECT p.flight_id,f.flight_number,ST_Y(p.position) AS latitude,ST_X(p.position) AS longitude,ST_Z(p.position) AS altitude_m,p.ground_speed,p.heading,p.recorded_at FROM flight_position p JOIN flight f USING(flight_id)",
    "runway": "SELECT a.iata_code,a.city,r.runway_identifier,r.length_m,r.width_m,r.surface_type,r.runway_status FROM runway r JOIN airport a USING(airport_id)",
    "weather_event": "SELECT weather_id,weather_type,severity,movement_direction,movement_speed_kmh,start_time,end_time,weather_status FROM weather_event",
    "airspace_zone": "SELECT airspace_zone_id,zone_name,zone_type,lower_altitude,upper_altitude,valid_from,valid_until,zone_status FROM airspace_zone",
    "disruption_event": "SELECT e.disruption_id,e.disruption_type,e.severity,a.iata_code,e.start_time,e.expected_end_time,e.description,e.disruption_status FROM disruption_event e LEFT JOIN airport a USING(airport_id)",
    "disruption_impact": "SELECT i.impact_id,e.disruption_type,e.description,i.flight_id,f.flight_number,i.aircraft_id,i.airport_id,i.impact_type,i.severity,i.estimated_delay_minutes,i.resolution_status FROM disruption_impact i JOIN disruption_event e USING(disruption_id) LEFT JOIN flight f USING(flight_id)",
}


def _airport(question, airports):
    q = question.lower()
    return next((a for a in airports if re.search(r"\b" + re.escape(a["iata_code"].lower()) + r"\b", q) or re.search(r"\b" + re.escape(a["city"].lower()) + r"\b", q)), None)


def _airport_mentions(question, airports):
    found=[]
    for airport in airports:
        for term in (airport["iata_code"],airport["city"]):
            match=re.search(r"\b"+re.escape(term)+r"\b",question,re.I)
            if match: found.append((match.start(),airport))
    unique={item[1]["airport_id"]:item for item in found}
    return [pair[1] for pair in sorted(unique.values(),key=lambda pair:pair[0])]


def _entity(q):
    # Prefer the most specific phrase, so "flight legs" wins over "flights".
    for alias in sorted(ENTITY_ALIASES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", q):
            return ENTITY_ALIASES[alias]
    return None


def _radius(question, airports):
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:km|kilometers?|kilometres?)\b", question, re.I)
    airport = _airport(question, airports)
    if not match or not airport or not re.search(r"\b(within|near|around|radius|close)\b", question, re.I):
        return None
    return min(float(match.group(1)), 3000), airport


def _nearby_flights(db, question, radius, airport):
    distance, _ = radius
    result = rows(db, """WITH latest AS (
      SELECT DISTINCT ON (flight_id) flight_id,position,recorded_at,ground_speed,heading
      FROM flight_position WHERE recorded_at > now()-interval '15 minutes' ORDER BY flight_id,recorded_at DESC
    )
    SELECT f.flight_id,f.flight_number,al.airline_name,r.route_code,o.iata_code AS origin,d.iata_code AS destination,
      f.flight_status,round((ST_Distance(ST_Force2D(p.position)::geography,a.location::geography)/1000)::numeric,1) AS distance_km,p.recorded_at
    FROM latest p JOIN flight f USING(flight_id) JOIN airline al USING(airline_id) JOIN route r USING(route_id)
    JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id CROSS JOIN airport a
    WHERE a.airport_id=:airport_id AND f.flight_status IN ('EN_ROUTE','APPROACHING')
      AND ST_DWithin(ST_Force2D(p.position)::geography,a.location::geography,:radius_m)
    ORDER BY distance_km LIMIT 100""", airport_id=airport["airport_id"], radius_m=distance*1000)
    return {"answer": (f"I found {len(result)} currently airborne flights within {distance:g} km of {airport['iata_code']} ({airport['city']}). "
             f"Distance is from each flight's latest position recorded in the last 15 minutes to the airport. "
             f"Flights are included by their position, not just because {airport['iata_code']} is their origin or destination."),
            "explanation": "PostGIS great-circle distance; currently en-route/approaching flights with a position recorded in the past 15 minutes.",
            "items": result, "kind": "flights", "mode": "database"}


def _nearby_airports(db, radius, airport):
    distance,_=radius
    result=rows(db,"SELECT iata_code,airport_name,city,country,operational_status,round((ST_Distance(location::geography,(SELECT location FROM airport WHERE airport_id=:id)::geography)/1000)::numeric,1) AS distance_km FROM airport WHERE airport_id<>:id AND ST_DWithin(location::geography,(SELECT location FROM airport WHERE airport_id=:id)::geography,:radius_m) ORDER BY distance_km LIMIT 100",id=airport["airport_id"],radius_m=distance*1000)
    return {"answer":f"I found {len(result)} airports within {distance:g} km of {airport['iata_code']} ({airport['city']}), ordered by great-circle distance.","items":result,"kind":"airports","mode":"database","explanation":"PostGIS geography distance between airport reference coordinates."}


def _count(db, entity, question, q, airport, airline):
    clauses, params = _filters(db, entity, question, q, airport, airline)
    if entity == "flight":
        if "high risk" in q or ("high" in q and "risk" in q):
            return sum(f["risk"]["level"] == "HIGH" for f in intelligence.flights(db))
        if not any(word in q for word in ("today", "tomorrow", "historical", "all records", "database")) and not clauses:
            clauses.extend(["f.scheduled_arrival>now()-interval '90 minutes'", "f.scheduled_departure<now()+interval '6 hours'"])
    elif entity == "airport" and "india" in q:
        clauses.append("lower(country)='india'")
    base_from = "flight" if entity == "flight" and not clauses else LIST_SQL[entity].split(" FROM ", 1)[1]
    sql = "SELECT count(*) AS n FROM " + base_from
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return one(db, sql, **params)["n"]


def _filters(db, entity, question, q, airport, airline):
    clauses, params = [], {}
    status_match = next(((word, val) for word, val in [
        ("delayed", "DELAYED"), ("landed", "LANDED"), ("cancelled", "CANCELLED"), ("canceled", "CANCELLED"),
        ("boarding", "BOARDING"), ("scheduled", "SCHEDULED"), ("taxiing", "TAXIING"),
        ("approaching", "APPROACHING"), ("en route", "EN_ROUTE"), ("airborne", "EN_ROUTE"), ("in the air", "EN_ROUTE")
    ] if word in q), None)
    if entity == "flight":
        if status_match:
            if status_match[1] == "DELAYED":
                clauses.append("(f.flight_status='DELAYED' OR EXISTS(SELECT 1 FROM disruption_impact di WHERE di.flight_id=f.flight_id AND di.resolution_status='OPEN' AND di.estimated_delay_minutes>0))")
            elif status_match[1] == "EN_ROUTE" and status_match[0] in ("airborne", "in the air"):
                clauses.append("f.flight_status IN ('EN_ROUTE','APPROACHING')")
            else:
                clauses.append("f.flight_status=:flight_status"); params["flight_status"] = status_match[1]
        if airport:
            if re.search(r"\b(from|departing|origin)\b", q):
                clauses.append("r.origin_airport_id=:airport_id")
            elif re.search(r"\b(to|arriving|destination)\b", q):
                clauses.append("r.destination_airport_id=:airport_id")
            else:
                clauses.append("(r.origin_airport_id=:airport_id OR r.destination_airport_id=:airport_id)")
            params["airport_id"] = airport["airport_id"]
        if airline:
            clauses.append("f.airline_id=:airline_id"); params["airline_id"] = airline["airline_id"]
        number = re.search(r"\b([a-z]{2})\s?(\d{2,5})\b", question, re.I)
        if number:
            clauses.append("upper(f.flight_number)=:flight_number"); params["flight_number"] = (number.group(1)+number.group(2)).upper()
        mentions=[]
        if re.search(r"\bfrom\b",q) and re.search(r"\bto\b",q):
            mentions=_airport_mentions(question,rows(db,"SELECT airport_id,iata_code,city FROM airport"))
        if len(mentions)>=2:
            clauses.append("o.airport_id=:origin_id AND d.airport_id=:destination_id")
            params["origin_id"],params["destination_id"]=mentions[0]["airport_id"],mentions[1]["airport_id"]
        if "high risk" in q or ("high" in q and "risk" in q):
            # Risk rules live in the intelligence layer; use the same current-window flight records.
            pass
        if "weather" in q:
            clauses.append("EXISTS (SELECT 1 FROM weather_event w WHERE w.weather_status='ACTIVE' AND now() BETWEEN w.start_time AND w.end_time AND ST_Intersects(r.route_geometry,w.affected_area_geometry))")
        if "affected" in q or "impact" in q or "disruption" in q:
            clauses.append("EXISTS (SELECT 1 FROM disruption_impact i JOIN disruption_event e USING(disruption_id) WHERE i.flight_id=f.flight_id AND i.resolution_status='OPEN' AND e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time)")
        if "today" in q:
            clauses.append("f.scheduled_departure >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AND f.scheduled_departure < (date_trunc('day', now() AT TIME ZONE 'UTC') + interval '1 day') AT TIME ZONE 'UTC'")
        elif "tomorrow" in q:
            clauses.append("f.scheduled_departure >= (date_trunc('day', now() AT TIME ZONE 'UTC') + interval '1 day') AT TIME ZONE 'UTC' AND f.scheduled_departure < (date_trunc('day', now() AT TIME ZONE 'UTC') + interval '2 days') AT TIME ZONE 'UTC'")
        elif "last 24 hours" in q or "past 24 hours" in q:
            clauses.append("f.scheduled_departure >= now()-interval '24 hours'")
        return clauses,params
    if entity in ("weather_event", "airspace_zone", "disruption_event"):
        col = {"weather_event":"weather_status","airspace_zone":"zone_status","disruption_event":"disruption_status"}[entity]
        if any(word in q for word in ("active", "current", "ongoing", "now")):
            clauses.append(f"{col}='ACTIVE'")
            if entity == "weather_event": clauses.append("now() BETWEEN start_time AND end_time")
            if entity == "airspace_zone": clauses.append("now() BETWEEN valid_from AND valid_until")
            if entity == "disruption_event": clauses.append("now() BETWEEN e.start_time AND e.expected_end_time")
        if "severe" in q or "high severity" in q:
            clauses.append("severity >= 4")
        if airport and entity == "disruption_event":
            clauses.append("e.airport_id=:airport_id"); params["airport_id"] = airport["airport_id"]
        return clauses,params
    if entity == "airport":
        if airport:
            clauses.append("(iata_code=:code OR lower(city)=:city)"); params.update(code=airport["iata_code"],city=airport["city"].lower())
        country = re.search(r"\b(in|of)\s+(India|UAE|United States|United Kingdom|Singapore|Australia|Qatar|Germany|France)\b", question, re.I)
        if country: clauses.append("lower(country)=:country"); params["country"] = country.group(2).lower()
        return clauses,params
    if entity in ("route","flight_leg"):
        mentions=_airport_mentions(question,rows(db,"SELECT airport_id,iata_code,city FROM airport"))
        origin_field="r.origin_airport_id" if entity=="route" else "l.departure_airport_id"
        destination_field="r.destination_airport_id" if entity=="route" else "l.arrival_airport_id"
        origin_alias="o"
        destination_alias="d" if entity=="route" else "a"
        if len(mentions)>=2:
            clauses.append(f"{origin_alias}.airport_id=:origin_id AND {destination_alias}.airport_id=:destination_id")
            params.update(origin_id=mentions[0]["airport_id"],destination_id=mentions[1]["airport_id"])
        elif airport:
            field=origin_field if re.search(r"\b(from|origin|departing)\b",q) else destination_field if re.search(r"\b(to|destination|arriving)\b",q) else None
            if field: clauses.append(f"{field}=:airport_id");params["airport_id"]=airport["airport_id"]
            else: clauses.append(f"({origin_field}=:airport_id OR {destination_field}=:airport_id)");params["airport_id"]=airport["airport_id"]
    if entity == "runway" and airport:
        clauses.append("r.airport_id=:airport_id");params["airport_id"]=airport["airport_id"]
    if entity == "aircraft":
        status=next((v for k,v in (("active","ACTIVE"),("in service","ACTIVE"),("maintenance","MAINTENANCE"),("grounded","GROUNDED")) if k in q),None)
        if status: clauses.append("a.aircraft_status=:aircraft_status");params["aircraft_status"]=status
    if entity == "airline" and "active" in q:
        clauses.append("operational_status='ACTIVE'")
    if entity == "airline" and airline:
        clauses.append("airline_id=:airline_id"); params["airline_id"] = airline["airline_id"]
    return clauses,params


def _summarize(question, result, entity, counting):
    if counting:
        count = result[0]["record_count"] if result and "record_count" in result[0] else 0
        return f"There {'is' if count == 1 else 'are'} {count} matching {entity.replace('_',' ')} record{'s' if count != 1 else ''} in the database."
    return f"I found {len(result)} matching {entity.replace('_',' ')} record{'s' if len(result) != 1 else ''}. Results are limited to 100 rows and sorted for review."


def _grouped(db, question, q, entity):
    dimension = None
    if any(w in q for w in ("by airline", "per airline", "each airline", "most flights", "top airline")):
        dimension = "airline"
    elif any(w in q for w in ("by airport", "per airport", "each airport")):
        dimension = "airport"
    elif any(w in q for w in ("by status", "per status", "each status")):
        dimension = "status"
    elif any(w in q for w in ("by model", "per model", "each model")):
        dimension = "model"
    elif any(w in q for w in ("by country", "per country", "each country")):
        dimension = "country"
    elif any(w in q for w in ("by type", "per type", "each type")):
        dimension = "type"
    if not dimension:
        return None
    plans = {
        ("flight", "airline"): ("SELECT a.iata_code,a.airline_name,count(*) AS record_count FROM flight f JOIN airline a USING(airline_id) GROUP BY a.iata_code,a.airline_name ORDER BY record_count DESC LIMIT 50", "flight records by airline"),
        ("flight", "airport"): ("SELECT a.iata_code,a.city,count(*) AS record_count FROM (SELECT origin_airport_id AS airport_id FROM flight f JOIN route r USING(route_id) UNION ALL SELECT destination_airport_id FROM flight f JOIN route r USING(route_id)) x JOIN airport a USING(airport_id) GROUP BY a.iata_code,a.city ORDER BY record_count DESC LIMIT 50", "flight departures and arrivals by airport"),
        ("flight", "status"): ("SELECT flight_status,count(*) AS record_count FROM flight GROUP BY flight_status ORDER BY record_count DESC", "flight records by status"),
        ("flight", "model"): ("SELECT t.manufacturer,t.model,count(*) AS record_count FROM flight f JOIN aircraft a USING(aircraft_id) JOIN aircraft_type t USING(aircraft_type_id) GROUP BY t.manufacturer,t.model ORDER BY record_count DESC LIMIT 50", "flight records by aircraft model"),
        ("aircraft", "airline"): ("SELECT al.airline_name,count(*) AS record_count FROM aircraft a JOIN airline al USING(airline_id) GROUP BY al.airline_name ORDER BY record_count DESC LIMIT 50", "aircraft by airline"),
        ("aircraft", "model"): ("SELECT t.manufacturer,t.model,count(*) AS record_count FROM aircraft a JOIN aircraft_type t USING(aircraft_type_id) GROUP BY t.manufacturer,t.model ORDER BY record_count DESC LIMIT 50", "aircraft by model"),
        ("airport", "country"): ("SELECT country,count(*) AS record_count FROM airport GROUP BY country ORDER BY record_count DESC LIMIT 50", "airports by country"),
        ("airport", "status"): ("SELECT operational_status,count(*) AS record_count FROM airport GROUP BY operational_status ORDER BY record_count DESC", "airports by operational status"),
        ("airline", "country"): ("SELECT country,count(*) AS record_count FROM airline GROUP BY country ORDER BY record_count DESC LIMIT 50", "airlines by country"),
        ("weather_event", "type"): ("SELECT weather_type,count(*) AS record_count FROM weather_event GROUP BY weather_type ORDER BY record_count DESC", "weather events by type"),
        ("disruption_event", "type"): ("SELECT disruption_type,count(*) AS record_count FROM disruption_event GROUP BY disruption_type ORDER BY record_count DESC", "disruptions by type"),
        ("disruption_event", "status"): ("SELECT disruption_status,count(*) AS record_count FROM disruption_event GROUP BY disruption_status ORDER BY record_count DESC", "disruptions by status"),
        ("disruption_impact", "type"): ("SELECT impact_type,count(*) AS record_count FROM disruption_impact GROUP BY impact_type ORDER BY record_count DESC", "disruption impacts by type"),
        ("airspace_zone", "type"): ("SELECT zone_type,count(*) AS record_count FROM airspace_zone GROUP BY zone_type ORDER BY record_count DESC", "airspace zones by type"),
        ("runway", "airport"): ("SELECT a.iata_code,a.city,count(*) AS record_count FROM runway r JOIN airport a USING(airport_id) GROUP BY a.iata_code,a.city ORDER BY record_count DESC LIMIT 50", "runways by airport"),
        ("aircraft_type", "model"): ("SELECT manufacturer,model,count(*) AS record_count FROM aircraft_type GROUP BY manufacturer,model ORDER BY record_count DESC LIMIT 50", "aircraft types by model"),
    }
    plan = plans.get((entity, dimension))
    if not plan:
        return _need_detail(f"I can group {entity.replace('_',' ')} by {dimension}, but that breakdown isn't available. Try a count, list, or another grouping.")
    result = rows(db, plan[0])
    if result:
        label=next((value for key,value in result[0].items() if key!="record_count"),"the leading group")
        answer=f"There are {sum(row['record_count'] for row in result)} {plan[1]}. The largest group is {label} ({result[0]['record_count']})."
    else:
        answer=f"No {plan[1]} were found."
    return {"answer":answer,"items":result,"kind":entity,"mode":"database","explanation":"Grouped directly from stored operational records and sorted by count."}


def query(db, question):
    q = question.lower().strip()
    if any(word in q for word in ("schema", "tables", "database structure", "what data", "what information")):
        return {"answer":"AeroPulse stores airports, airlines, aircraft and aircraft types, routes, flights and legs, timestamped positions, runways, weather, airspace, disruptions and disruption impacts in PostgreSQL with PostGIS. You can ask for counts, lists, filters, comparisons, schedules, routes, airport proximity, weather exposure, risk and disruption effects.","items":[],"kind":"schema","mode":"database","explanation":"The answer describes the application’s PostgreSQL/PostGIS data model."}

    entity = "flight" if ("most flights" in q or "flights by airline" in q or "flight count by airline" in q) else _entity(q)
    if not entity and not any(word in q for word in ("alternate", "divert", "restricted", "airspace")):
        return _need_detail("I cannot answer that question from the AeroPulse operational database. Ask about flights, airports, airlines, aircraft, models, routes, legs, positions, runways, weather, airspace, disruptions or impacts.")

    counting = any(word in q for word in ("how many", "count", "total", "number of"))
    if entity == "flight" and counting and "database" in q:
        count = _count(db, entity, question, q, None, None)
        return {"answer":f"There are {count} flights in the database, including historical records.","items":[{"record_count":count}],"kind":entity,"mode":"database","explanation":"Exact count of all retained flight records."}

    airports = rows(db, "SELECT airport_id,iata_code,city FROM airport")
    airport = _airport(question, airports)
    radius = _radius(question, airports)
    entity_hint=_entity(q)
    if radius and entity_hint=="airport":
        return _nearby_airports(db,radius,radius[1])
    if radius:
        return _nearby_flights(db, question, radius, radius[1])

    airlines = rows(db, "SELECT airline_id,iata_code,airline_name FROM airline") if entity in ("flight", "airline", "aircraft") else []
    airline = next((a for a in airlines if a.get("airline_name", "").lower() in q or (a.get("iata_code") and re.search(r"\b"+re.escape(a["iata_code"].lower())+r"\b",q))),None)

    # Airport-to-airport distance is a distinct question from nearby aircraft.
    if any(word in q for word in ("distance between", "how far", "route distance")) and len(re.findall(r"\b[A-Z]{3}\b",question))>=2:
        codes=re.findall(r"\b[A-Z]{3}\b",question)
        return {"answer":"The database route distance between those airports is shown below where a scheduled route exists.","items":rows(db,"SELECT r.route_code,o.iata_code AS origin,d.iata_code AS destination,r.distance_km,r.estimated_duration_minutes FROM route r JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id WHERE (o.iata_code=:a AND d.iata_code=:b) OR (o.iata_code=:b AND d.iata_code=:a) ORDER BY distance_km LIMIT 20",a=codes[0],b=codes[1]),"kind":"routes","mode":"database","explanation":"Scheduled route distance in the route table; this is not a straight-line distance."}

    if not entity and any(word in q for word in ("alternate", "divert")):
        if not airport: return _need_detail("Name the destination airport or city for alternate-airport analysis.")
        result=intelligence.alternates(db,airport["airport_id"])
        return {"answer":f"I found {len(result)} operational alternate candidates within 650 km of {airport['iata_code']}, ranked by distance and runway suitability. Fuel, weather minima and operator rules still need review.","items":result,"kind":"alternates","mode":"database","explanation":"Candidates are checked against airport status, open runway length and geographic distance."}

    if not entity and ("restricted" in q or "airspace" in q):
        result=rows(db,"SELECT r.route_id,r.route_code,z.zone_name,z.zone_type FROM route r JOIN airspace_zone z ON ST_Intersects(r.route_geometry,z.geometry) WHERE z.zone_status='ACTIVE' AND now() BETWEEN z.valid_from AND z.valid_until ORDER BY r.route_code LIMIT 100")
        return {"answer":f"I found {len(result)} route/active-airspace intersections using horizontal geometry screening.","items":result,"kind":"routes","mode":"database","explanation":"PostGIS route-line intersection against zones active at the current time."}

    if not entity:
        if any(word in q for word in ("flight", "network", "overview", "summary")): entity="flight"
        else: return _need_detail("I couldn't identify which database records you mean. Ask about flights, airports, airlines, aircraft, models, routes, legs, positions, runways, weather, airspace, disruptions or impacts. You can add filters such as an airport, airline, status, country, date or distance.")

    # Meaningful grouped comparisons supported by the operational joins.
    grouped = _grouped(db,question,q,entity)
    if grouped:
        return grouped

    counting=any(word in q for word in ("how many", "count", "total", "number of"))
    if counting and not any(word in q for word in ("by airline", "per airline", "each airline", "by airport", "per airport", "by status", "per status", "by model", "per model")):
        count=_count(db,entity,question,q,airport,airline)
        return {"answer":f"There {'is' if count == 1 else 'are'} {count} {entity.replace('_',' ')} records matching your question.","items":[{"record_count":count}],"kind":entity,"mode":"database","explanation":"Exact database count over the selected table and explicit filters."}

    sql=LIST_SQL[entity]
    clauses,params=_filters(db,entity,question,q,airport,airline)
    if entity == "flight" and "delayed" in q:
        flights = intelligence.flights(db)
        matched = [f for f in flights if f.get("estimated_delay_minutes", 0) > 0 or any(i.get("estimated_delay_minutes", 0) > 0 for i in f.get("impacts", []))]
        return {"answer":f"I found {len(matched)} flights with estimated delays.","items":matched[:100],"kind":"flights","mode":"database","explanation":"Uses operational flight delay estimates and disruption impact delays."}
    if entity == "flight" and ("high risk" in q or ("high" in q and "risk" in q)):
        fs=intelligence.flights(db)
        matched=[f for f in fs if f["risk"]["level"]=="HIGH"]
        return {"answer":f"{len(matched)} monitored flights currently have HIGH deterministic risk scores. Each score is a rule-based operational indicator, not a probability.","items":[{"flight_id":f['flight_id'],"flight_number":f['flight_number'],"route_code":f['route_code'],"origin":f['origin'],"destination":f['destination'],"risk":f['risk']} for f in matched[:100]],"kind":"flights","mode":"database","explanation":"Uses current operational-window flights and the explainable deterministic risk rules."}
    if entity == "flight" and not any(x in q for x in ("historical", "all records", "all flights", "database")):
        clauses += ["f.scheduled_arrival>now()-interval '90 minutes'", "f.scheduled_departure<now()+interval '6 hours'"]
    if clauses: sql += " WHERE " + " AND ".join(clauses)
    order={"airport":"airport_name","airline":"airline_name","aircraft_type":"manufacturer,model","aircraft":"registration_number","route":"route_code","flight":"f.scheduled_departure","flight_leg":"l.scheduled_departure","flight_position":"p.recorded_at DESC","runway":"a.iata_code,r.runway_identifier","weather_event":"start_time DESC","airspace_zone":"zone_name","disruption_event":"e.start_time DESC","disruption_impact":"i.detected_at DESC"}[entity]
    limit_match=re.search(r"\b(?:top|first|latest|last)\s+(\d{1,3})\b",q)
    limit=min(int(limit_match.group(1)),100) if limit_match else 100
    sql += f" ORDER BY {order} LIMIT {limit}"
    result=rows(db,sql,**params)
    country_match = re.search(r"\b(?:in|of)\s+(India|UAE|United States|United Kingdom|Singapore|Australia|Qatar|Germany|France)\b", question, re.I) if entity == "airport" else None
    if country_match:
        result = [row for row in result if row.get("country", "").lower() == country_match.group(1).lower()]
        items = [{"label": row.get("iata_code", ""), "detail": f"{row.get('city', '')}, {row.get('country', '')}"} for row in result]
        return {"answer":f"I found {len(items)} matching airports in {country_match.group(1)}.","items":items,"kind":"airport","mode":"database","explanation":"Filtered airport records by country."}
    if entity == "flight" and "weather" in q:
        explanation="Flight routes intersect active weather polygons."
    elif entity == "flight" and ("affected" in q or "impact" in q or "disruption" in q):
        explanation="Flights have an open impact associated with an active disruption."
    elif airport:
        explanation=f"Filtered by {airport['iata_code']} ({airport['city']}) and the requested record type."
    elif airline:
        explanation=f"Filtered by {airline['airline_name']} ({airline['iata_code']})."
    elif status:=next((w for w in ("delayed","landed","cancelled","boarding","scheduled","taxiing","approaching","airborne") if w in q),None):
        explanation=f"Filtered for {status} records in the {entity.replace('_',' ')} table."
    else:
        explanation=f"Filtered and sorted rows from the {entity.replace('_',' ')} records."
    return {"answer":_summarize(question,result,entity,False),"items":result,"kind":entity,"mode":"database","explanation":explanation,"truncated":len(result)==limit}


def _need_detail(answer):
    return {"answer":answer,"items":[],"examples":EXAMPLES,"kind":"database","mode":"database","explanation":"No database query was run because the request needs a clearer record type or location."}

