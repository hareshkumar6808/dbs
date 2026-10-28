import re
from backend import intelligence
from backend.db import rows, one

EXAMPLES = [
    "How many flights are in the database?",
    "List airports in India",
    "Show delayed flights",
    "Which flights are high risk?",
    "Which flights are affected by weather?",
    "Show flights affected by Chennai runway closure.",
    "What is the best alternate airport for Chennai?",
    "Which routes intersect restricted airspace?",
    "Which flights have downstream impact?",
]


def query(db, question):
    q = question.lower().strip()
    # Fixed, parameterized read queries: user text is never executed as SQL.
    counting = any(word in q for word in ("how many", "count", "total", "number of"))
    if any(word in q for word in ("schema", "tables", "database structure")):
        return {"answer": "AeroPulse stores airports, airlines, aircraft types, aircraft, routes, flights, flight legs, recorded positions, runways, weather events, airspace zones, disruption events and their impacts. Flights link an airline, aircraft and route; routes connect origin and destination airports. Positions retain each flight's timestamped track. Weather and airspace use PostGIS geometry. Ask for counts, flight status, an airport, airline or flight number.", "items": [], "examples": EXAMPLES}
    entities = {
        "airport": ("airport", "airport_name"), "airline": ("airline", "airline_name"),
        "aircraft type": ("aircraft_type", "model"), "aircraft": ("aircraft", "registration_number"),
        "route": ("route", "route_code"), "flight": ("flight", "flight_number"),
        "runway": ("runway", "runway_identifier"), "position": ("flight_position", "position_id"),
        "weather event": ("weather_event", "weather_type"), "disruption": ("disruption_event", "description"),
    }
    entity = next((key for key in entities if key in q), None)
    filters = ("risk", "weather", "affected", "closure", "delayed", "landed", "airborne", "en route", "boarding", "cancelled", "scheduled", "downstream", "cascade", "from ", " to ", " at ", " in ", " for ")
    count_scope = q.replace("in the database", "").replace("in database", "")
    if counting and entity and not any(word in count_scope for word in filters):
        table = entities[entity][0]
        count = one(db, f"SELECT count(*) AS n FROM {table}")["n"]
        return {"answer": f"The database contains {count} {entity} records (all retained records, including historical and scheduled data).", "items": []}

    airports = rows(db, "SELECT airport_id,iata_code,city FROM airport")
    airport = next(
        (
            a
            for a in airports
            if a["city"].lower() in q or re.search(r"\b" + re.escape(a["iata_code"].lower()) + r"\b", q)
        ),
        None,
    )
    if entity in ("airport", "airline", "aircraft type", "aircraft", "route", "runway", "weather event", "disruption") and not any(word in q for word in ("flight", "alternate", "divert", "closure", "affected", "risk", "restricted", "airspace")):
        list_queries = {
            "airport": ("SELECT airport_id,iata_code,airport_name,city,country FROM airport ORDER BY airport_name", "airport_name"),
            "airline": ("SELECT iata_code,airline_name,country FROM airline ORDER BY airline_name", "airline_name"),
            "aircraft type": ("SELECT manufacturer,model,aircraft_category FROM aircraft_type ORDER BY manufacturer,model", "model"),
            "aircraft": ("SELECT registration_number,aircraft_type_id,aircraft_status FROM aircraft ORDER BY registration_number", "registration_number"),
            "route": ("SELECT route_code,origin_airport_id,destination_airport_id,distance_km,route_status FROM route ORDER BY route_code", "route_code"),
            "runway": ("SELECT runway_identifier,airport_id,length_m,runway_status FROM runway ORDER BY runway_identifier", "runway_identifier"),
            "weather event": ("SELECT weather_type,severity,weather_status FROM weather_event ORDER BY weather_type", "weather_type"),
            "disruption": ("SELECT description,disruption_type,severity,disruption_status FROM disruption_event ORDER BY description", "description"),
        }
        sql, label = list_queries[entity]
        result = rows(db, sql)
        if entity == "airport":
            if airport:
                result = [a for a in result if a["airport_id"] == airport["airport_id"]]
            elif "india" in q or "indian" in q:
                result = [a for a in result if a["country"] == "India"]
        labels = [str(item[label]) for item in result]
        items = []
        for item in result[:100]:
            if entity == "airport":
                detail = f"{item['city']}, {item['country']}"
                item_label = item["iata_code"]
            elif entity == "airline":
                detail = item["country"]
                item_label = f"{item['iata_code']} · {item['airline_name']}"
            elif entity == "aircraft type":
                detail = item["aircraft_category"]
                item_label = f"{item['manufacturer']} {item['model']}"
            elif entity == "aircraft":
                detail = f"Type {item['aircraft_type_id']} · {item['aircraft_status']}"
                item_label = item["registration_number"]
            elif entity == "route":
                detail = f"Airport {item['origin_airport_id']} to {item['destination_airport_id']} · {item['distance_km']:.0f} km · {item['route_status']}"
                item_label = item["route_code"]
            elif entity == "runway":
                detail = f"Airport {item['airport_id']} · {item['length_m']:.0f} m · {item['runway_status']}"
                item_label = item["runway_identifier"]
            elif entity == "weather event":
                detail = f"Severity {item['severity']} · {item['weather_status']}"
                item_label = item["weather_type"]
            else:
                detail = f"{item['disruption_type']} · severity {item['severity']} · {item['disruption_status']}"
                item_label = item["description"]
            items.append({"label": item_label, "detail": detail})
        return {
            "answer": f"{len(result)} matching {entity} records" + (" (first 100 shown)" if len(result) > 100 else ""),
            "items": items,
        }
    if "alternate" in q or "divert" in q:
        if not airport:
            return {"answer": "Name an airport or city to rank nearby alternates.", "items": [], "examples": EXAMPLES}
        result = intelligence.alternates(db, airport["airport_id"])
        return {
            "answer": f"{len(result)} operational alternate candidates within 650 km of {airport['iata_code']}, ranked by distance with at least 2,200 m of open runway. Suitability still requires fuel, weather and operator checks.",
            "items": result,
            "kind": "alternates",
        }
    if "restricted" in q or "airspace" in q:
        result = rows(
            db,
            """SELECT r.route_id,r.route_code,z.zone_name FROM route r JOIN airspace_zone z ON ST_Intersects(r.route_geometry,z.geometry)
            WHERE z.zone_status='ACTIVE' AND now() BETWEEN z.valid_from AND z.valid_until ORDER BY r.route_code LIMIT 100""",
        )
        return {
            "answer": f"{len(result)} route/airspace intersections in the active database (horizontal route screening).",
            "items": result,
            "kind": "routes",
        }
    fs = intelligence.flights(db)
    if "high" in q and "risk" in q:
        result = [f for f in fs if f["risk"]["level"] == "HIGH"]
        explanation = "high-risk flights; scores are deterministic and explanations are attached"
    elif "weather" in q:
        result = [f for f in fs if f["weather_severity"] and f["flight_status"] not in ("LANDED", "CANCELLED")]
        explanation = "flights whose routes intersect active weather"
    elif "downstream" in q or "cascade" in q:
        result = [f for f in fs if any(i["impact_type"] == "AIRCRAFT_UNAVAILABLE" for i in f["impacts"])]
        explanation = "flights with persisted downstream aircraft impacts"
    elif ("affected" in q or "closure" in q) and airport:
        impacts = rows(
            db,
            """SELECT DISTINCT i.flight_id FROM disruption_impact i JOIN disruption_event e USING(disruption_id)
            WHERE e.airport_id=:id AND e.disruption_status='ACTIVE' AND now() BETWEEN e.start_time AND e.expected_end_time
              AND i.resolution_status='OPEN' """,
            id=airport["airport_id"],
        )
        ids = {i["flight_id"] for i in impacts}
        result = [f for f in fs if f["flight_id"] in ids]
        explanation = f"flights affected by active disruptions at {airport['iata_code']}"
    else:
        result = fs
        explanation = "flights in the current operational window"
        matched = False
        statuses = {"delayed": "DELAYED", "landed": "LANDED", "cancelled": "CANCELLED",
                    "canceled": "CANCELLED", "boarding": "BOARDING", "scheduled": "SCHEDULED",
                    "taxiing": "TAXIING", "approaching": "APPROACHING", "en route": "EN_ROUTE"}
        for word, status in statuses.items():
            if word in q:
                result = [f for f in result if f["flight_status"] == status or
                          (status == "DELAYED" and f["estimated_delay_minutes"] > 0)]
                explanation = word + " " + explanation
                matched = True
                break
        if "airborne" in q or "flying" in q:
            result = [f for f in result if f["flight_status"] in ("EN_ROUTE", "APPROACHING")]
            matched = True
        if airport:
            field = "origin_airport_id" if re.search(r"\b(from|departing)\b", q) else "destination_airport_id" if re.search(r"\b(to|arriving)\b", q) else None
            result = [f for f in result if f.get(field) == airport["airport_id"]] if field else [f for f in result if airport["airport_id"] in (f["origin_airport_id"], f["destination_airport_id"])]
            explanation += f" involving {airport['iata_code']}"
            matched = True
        airlines = rows(db, "SELECT airline_id,airline_name,iata_code FROM airline")
        airline = next((a for a in airlines if a["airline_name"].lower() in q or re.search(r"\b" + re.escape(a["iata_code"].lower()) + r"\b", q)), None)
        if airline:
            result = [f for f in result if f["airline_id"] == airline["airline_id"]]
            explanation += f" operated by {airline['airline_name']}"
            matched = True
        flight_number = re.search(r"\b[a-z]{2}\s?\d{2,5}\b", q)
        if flight_number:
            number = flight_number.group().replace(" ", "").upper()
            result = [f for f in result if f["flight_number"].upper() == number]
            explanation = f"matching {number} in the current operational window"
            matched = True
        if "affected" in q:
            result = [f for f in result if f["impacts"]]
            matched = True
        if not matched and not any(word in q for word in ("flight", "network", "summary", "overview")):
            return {"answer": "I cannot answer that question from the supported database queries. Ask about record counts, tables, airports, airlines, aircraft, flight numbers, flight status, weather, risk, alternates or disruptions.", "items": [], "examples": EXAMPLES}
    return {
        "answer": f"{len(result)} {explanation}.",
        "kind": "flights",
        "items": [
            {
                "flight_id": f["flight_id"],
                "flight_number": f["flight_number"],
                "route_code": f["route_code"],
                "risk": f["risk"],
                "estimated_delay_minutes": f["estimated_delay_minutes"],
            }
            for f in result
        ],
    }

