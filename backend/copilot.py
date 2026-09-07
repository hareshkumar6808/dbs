import re
from backend import intelligence
from backend.db import rows

EXAMPLES = [
    "Which flights are high risk?",
    "Which flights are affected by weather?",
    "Show flights affected by Chennai runway closure.",
    "What is the best alternate airport for Chennai?",
    "Which routes intersect restricted airspace?",
    "Which flights have downstream impact?",
]


def query(db, question):
    q = question.lower()
    airports = rows(db, "SELECT airport_id,iata_code,city FROM airport")
    airport = next(
        (
            a
            for a in airports
            if a["city"].lower() in q or re.search(r"\b" + re.escape(a["iata_code"].lower()) + r"\b", q)
        ),
        None,
    )
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
        return {
            "answer": "I can query supported operational questions using this database. Try one of the examples; I cannot answer arbitrary aviation questions.",
            "items": [],
            "examples": EXAMPLES,
        }
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
