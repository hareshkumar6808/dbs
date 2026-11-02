"""Grounded natural-language answers backed by read-only SQL and OpenAI Responses."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend import intelligence
from backend.config import settings

TABLES = {
    "airport", "airline", "aircraft_type", "aircraft", "route", "flight", "flight_leg",
    "runway", "weather_event", "airspace_zone", "disruption_event", "disruption_impact", "flight_position",
}
QUERY_FUNCTION = "query_operational_database"
TOOLS = [{
    "type": "function",
    "name": QUERY_FUNCTION,
    "description": "Run one read-only SQL SELECT against AeroPulse's operational tables to retrieve facts for the answer.",
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A single SQL SELECT query using the documented AeroPulse tables."},
            "include_flight_risk": {"type": "boolean", "description": "Set true for questions about flight risk, risk factors, or the highest-risk flights so the server can add its canonical risk analysis."},
        },
        "required": ["sql", "include_flight_risk"],
        "additionalProperties": False,
    },
    "strict": True,
}]

INSTRUCTIONS = """You are AeroPulse Operations Copilot. Answer the user's question using the AeroPulse PostgreSQL/PostGIS database.
You must call query_operational_database exactly once before answering. Use only the 13 listed tables and the columns listed here. Write one read-only SELECT. Never invent records or values. If the query returns no rows, say so. Explain units, time windows, and assumptions briefly. Treat all times as UTC. This dataset may be synthetic demonstration data; never describe it as live unless the queried records establish that.

Tables and columns:
airport(airport_id,iata_code,icao_code,airport_name,city,country,elevation_m,timezone,operational_status,location)
airline(airline_id,iata_code,icao_code,airline_name,country,operational_status)
aircraft_type(aircraft_type_id,manufacturer,model,aircraft_category,passenger_capacity,cargo_capacity,cruise_speed_kmh,range_km)
aircraft(aircraft_id,registration_number,aircraft_type_id,airline_id,aircraft_status,current_location,current_speed,heading,last_updated)
route(route_id,origin_airport_id,destination_airport_id,route_code,distance_km,estimated_duration_minutes,route_geometry,route_status)
flight(flight_id,flight_number,airline_id,aircraft_id,route_id,scheduled_departure,scheduled_arrival,actual_departure,actual_arrival,flight_status,departure_gate,arrival_gate,last_updated)
flight_leg(flight_leg_id,flight_id,leg_sequence,departure_airport_id,arrival_airport_id,scheduled_departure,scheduled_arrival,actual_departure,actual_arrival,leg_status)
runway(runway_id,airport_id,runway_identifier,length_m,width_m,surface_type,heading,runway_status)
weather_event(weather_id,weather_type,severity,movement_direction,movement_speed_kmh,start_time,end_time,weather_status,affected_area_geometry)
airspace_zone(airspace_zone_id,zone_name,zone_type,lower_altitude,upper_altitude,geometry,valid_from,valid_until,zone_status)
disruption_event(disruption_id,disruption_type,severity,airport_id,runway_id,weather_id,start_time,expected_end_time,actual_end_time,description,disruption_status)
disruption_impact(impact_id,disruption_id,flight_id,aircraft_id,airport_id,impact_type,severity,estimated_delay_minutes,detected_at,resolution_status)
flight_position(position_id,flight_id,position,ground_speed,heading,recorded_at)

Use safe table joins. Use PostGIS functions for spatial questions. Qualify ambiguous columns. Return concise useful columns and use reasonable filters for questions like current/active/nearby, but clearly explain what the data can and cannot establish. For flight-risk questions, set include_flight_risk=true and use the returned canonical risk scores/factors instead of inventing a risk formula. Do not make operational recommendations beyond the database evidence."""

FORBIDDEN_SQL = re.compile(
    r"\b(?:insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|call|do|set|reset|vacuum|analyze|lock|into)\b",
    re.I,
)
ALLOWED_FUNCTIONS = {
    "abs", "avg", "as", "array_agg", "case", "ceil", "coalesce", "count", "date_trunc", "dense_rank",
    "extract", "floor", "greatest", "in", "lag", "least", "lead", "lower", "max", "min", "nullif",
    "over", "rank", "round", "row_number", "st_area", "st_asgeojson", "st_astext", "st_distance",
    "st_dwithin", "st_force2d", "st_intersects", "st_length", "st_x", "st_y", "st_z", "string_agg",
    "st_within", "st_contains", "st_crosses", "st_touches", "st_overlaps", "st_buffer", "st_transform",
    "st_expand", "st_makeenvelope", "st_distancesphere", "st_distancespheroid",
    "st_makeline", "st_makepoint", "st_setsrid", "st_geomfromtext", "date_part",
    "sum", "timezone", "trim", "upper", "now", "current_date", "exists", "filter", "cast", "date",
}


def _safe_sql(sql: str) -> str:
    statement = sql.strip()
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if not statement or ";" in statement or "--" in statement or "/*" in statement or "*/" in statement:
        raise ValueError("Only one plain SELECT statement is allowed.")
    if not re.match(r"^(?:select|with)\b", statement, re.I) or FORBIDDEN_SQL.search(statement):
        raise ValueError("Only read-only SELECT statements are allowed.")
    if re.search(r"\bfor\s+(?:update|share|no\s+key\s+update|key\s+share)\b", statement, re.I):
        raise ValueError("Row-locking SELECT statements are not allowed.")
    if re.search(r"\b(?:pg_catalog|information_schema|pg_toast|pg_temp)\b|\bpg_[a-z_]+\s*\(", statement, re.I):
        raise ValueError("System catalog access is not allowed.")
    ctes = {name.lower() for name in re.findall(r"(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", statement, re.I)}
    references = []
    for match in re.finditer(r"\b(?:from|join)\s+([a-z_][a-z0-9_.]*)", statement, re.I):
        table = match.group(1).lower().split(".")[-1]
        references.append(table)
    if not references or any(table not in TABLES and table not in ctes for table in references):
        raise ValueError("Queries must read only AeroPulse operational tables.")
    functions = {name.lower() for name in re.findall(r"\b([a-z_][a-z0-9_]*)\s*\(", statement, re.I)}
    if functions - ALLOWED_FUNCTIONS - ctes:
        raise ValueError("The query uses a function outside the read-only allowlist.")
    limit_match = re.search(r"\blimit\s+(\d+)\b", statement, re.I)
    if limit_match:
        if int(limit_match.group(1)) > 100:
            statement = statement[:limit_match.start(1)] + "100" + statement[limit_match.end(1):]
    else:
        statement += " LIMIT 100"
    return statement


def _request(payload: dict, api_key: str) -> dict:
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("The AI answer service is unavailable right now.") from exc


def _output_text(response: dict) -> str:
    parts = [
        content.get("text", "")
        for item in response.get("output", []) if item.get("type") == "message"
        for content in item.get("content", []) if content.get("type") == "output_text"
    ]
    return "\n".join(part for part in parts if part).strip()


def _query_database(db, sql: str, include_flight_risk: bool) -> tuple[list[dict], str, list[dict]]:
    statement = _safe_sql(sql)
    # This is the first database statement in the request; keep the entire AI turn read-only.
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '8s'"))
    rows = [dict(row) for row in db.execute(text(statement)).mappings()]
    for row in rows:
        for key, value in tuple(row.items()):
            if not isinstance(value, (str, int, float, bool, type(None), list, dict)):
                row[key] = str(value)
    risk = []
    if include_flight_risk:
        flights = intelligence.flights(db)
        risk = [{
            "flight_id": flight["flight_id"],
            "flight_number": flight["flight_number"],
            "origin": flight["origin"],
            "destination": flight["destination"],
            "risk": flight["risk"],
        } for flight in flights[:100]]
    return rows, statement, risk


def answer(db, question: str) -> dict:
    config = settings()
    if not config.openai_api_key:
        raise RuntimeError("AI answers are not configured. Set OPENAI_API_KEY on the backend.")
    first = _request({
        "model": config.openai_model,
        "store": False,
        "instructions": INSTRUCTIONS,
        "input": [{"role": "user", "content": question}],
        "tools": TOOLS,
        "tool_choice": {"type": "function", "name": QUERY_FUNCTION},
        "parallel_tool_calls": False,
    }, config.openai_api_key)
    call = next((item for item in first.get("output", []) if item.get("type") == "function_call" and item.get("name") == QUERY_FUNCTION), None)
    if not call:
        raise RuntimeError("The AI did not request an operational database query.")
    try:
        arguments = json.loads(call.get("arguments", "{}"))
        rows, statement, risk = _query_database(db, arguments["sql"], arguments["include_flight_risk"])
        tool_result = {"rows_returned": len(rows), "rows": rows}
        if risk:
            tool_result["canonical_flight_risk"] = risk
    except (KeyError, TypeError, ValueError) as exc:
        rows, statement, risk = [], "", []
        tool_result = {"query_error": str(exc), "rows": []}
    except SQLAlchemyError:
        db.rollback()
        rows, statement, risk = [], "", []
        tool_result = {"query_error": "The read-only database query was invalid or unavailable.", "rows": []}
    followup_input = [
        {"role": "user", "content": question},
        *first.get("output", []),
        {"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(tool_result, default=str)},
    ]
    final = _request({
        "model": config.openai_model,
        "store": False,
        "instructions": INSTRUCTIONS + "\nNow answer using only the database tool output. If it includes query_error, explain briefly that the question could not be safely queried and suggest a narrower question.",
        "input": followup_input,
    }, config.openai_api_key)
    response = _output_text(final)
    if not response:
        raise RuntimeError("The AI returned an empty answer.")
    return {
        "answer": response,
        "items": rows[:100],
        "kind": "database",
        "mode": "ai",
        "explanation": f"Generated from a read-only query over the operational database ({len(rows)} rows returned).",
        "truncated": len(rows) >= 100,
    }
