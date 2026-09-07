"""Optional Neo4j operational projection, never the system of record."""

import logging
from neo4j import GraphDatabase
from backend.config import settings
from backend.db import rows
from backend.intelligence import cascade

log = logging.getLogger(__name__)


def configured():
    s = settings()
    return bool(s.neo4j_uri and s.neo4j_password)


def driver():
    s = settings()
    return GraphDatabase.driver(
        s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=5, max_transaction_retry_time=5
    )


def sync(db):
    if not configured():
        return {"status": "unconfigured", "engine": "postgresql-recursive-cte"}
    airports = rows(db, "SELECT airport_id AS id,iata_code AS code FROM airport")
    aircraft = rows(db, "SELECT aircraft_id AS id,registration_number AS registration FROM aircraft")
    fs = rows(
        db,
        """SELECT flight_id AS id,flight_number AS number,aircraft_id,origin_airport_id AS origin,
        destination_airport_id AS destination,EXTRACT(EPOCH FROM scheduled_departure) AS departure,
        EXTRACT(EPOCH FROM scheduled_arrival) AS arrival FROM flight JOIN route USING(route_id) WHERE flight_status<>'CANCELLED' """,
    )
    # Numeric casts avoid Decimal transport surprises in the Neo4j driver.
    for f in fs:
        f["departure"] = float(f["departure"])
        f["arrival"] = float(f["arrival"])
    events = rows(
        db,
        "SELECT disruption_id AS id,description FROM disruption_event WHERE disruption_status='ACTIVE' AND expected_end_time>now()",
    )
    impacts = rows(
        db,
        "SELECT DISTINCT disruption_id,flight_id FROM disruption_impact JOIN disruption_event USING(disruption_id) WHERE resolution_status='OPEN' AND disruption_status='ACTIVE' AND expected_end_time>now() AND flight_id IS NOT NULL",
    )
    try:
        with driver() as neo, neo.session() as session:
            for label in ["Airport", "Flight", "Aircraft", "Disruption"]:
                session.run(
                    f"CREATE CONSTRAINT aeropulse_{label.lower()}_id IF NOT EXISTS FOR (n:AeroPulse{label}) REQUIRE n.id IS UNIQUE"
                ).consume()

            def write(tx):
                tx.run(
                    "UNWIND $data AS x MERGE (a:AeroPulseAirport {id:x.id}) SET a.code=x.code", data=airports
                ).consume()
                tx.run(
                    "UNWIND $data AS x MERGE (a:AeroPulseAircraft {id:x.id}) SET a.registration=x.registration",
                    data=aircraft,
                ).consume()
                tx.run(
                    """UNWIND $data AS x MERGE (f:AeroPulseFlight {id:x.id}) SET f.number=x.number,f.departure=x.departure,f.arrival=x.arrival
                    WITH f,x MATCH (a:AeroPulseAircraft {id:x.aircraft_id}), (o:AeroPulseAirport {id:x.origin}), (d:AeroPulseAirport {id:x.destination})
                    MERGE (f)-[:USES_AIRCRAFT]->(a) MERGE (f)-[:DEPARTS_FROM]->(o) MERGE (f)-[:ARRIVES_AT]->(d)""",
                    data=fs,
                ).consume()
                tx.run("MATCH (:AeroPulseFlight)-[r:NEXT_FLIGHT]->(:AeroPulseFlight) DELETE r").consume()
                tx.run("""MATCH (a:AeroPulseAircraft)<-[:USES_AIRCRAFT]-(f:AeroPulseFlight)
                    WITH a,f ORDER BY f.departure,f.id WITH a,collect(f) AS flights
                    UNWIND range(0,size(flights)-2) AS i WITH flights[i] AS f,flights[i+1] AS n
                    MERGE (f)-[r:NEXT_FLIGHT]->(n) SET r.buffer_minutes=(n.departure-f.arrival)/60""").consume()
                tx.run("MATCH (:AeroPulseDisruption)-[r:AFFECTS]->() DELETE r").consume()
                tx.run("MATCH (d:AeroPulseDisruption) SET d.active=false").consume()
                tx.run(
                    "UNWIND $data AS x MERGE (d:AeroPulseDisruption {id:x.id}) SET d.description=x.description,d.active=true",
                    data=events,
                ).consume()
                tx.run(
                    """UNWIND $data AS x MATCH (d:AeroPulseDisruption {id:x.disruption_id}),(f:AeroPulseFlight {id:x.flight_id})
                    MERGE (d)-[:AFFECTS]->(f)""",
                    data=impacts,
                ).consume()

            session.execute_write(write)
        return {"status": "synced", "engine": "neo4j", "flights": len(fs)}
    except Exception as exc:
        log.warning("Neo4j sync unavailable (%s)", type(exc).__name__)
        return {"status": "unavailable", "engine": "postgresql-recursive-cte"}


def dependency_paths(db, roots, delay=90):
    state = sync(db)
    if state["status"] == "synced":
        try:
            with driver() as neo, neo.session() as session:
                records = session.run(
                    """MATCH p=(f:AeroPulseFlight)-[:NEXT_FLIGHT*1..5]->(n:AeroPulseFlight)
                    WHERE f.id IN $roots
                    WITH p,f,n,reduce(delay=$delay,r IN relationships(p) |
                        CASE WHEN delay-CASE WHEN r.buffer_minutes>25 THEN r.buffer_minutes-25 ELSE 0 END > 0
                        THEN delay-CASE WHEN r.buffer_minutes>25 THEN r.buffer_minutes-25 ELSE 0 END ELSE 0 END) AS remaining
                    WHERE remaining>0 RETURN f.id AS root_id,n.id AS flight_id,n.number AS flight_number,
                    length(p) AS depth,[x IN nodes(p)|x.id] AS path,toInteger(remaining) AS delay_minutes
                    ORDER BY root_id,depth""",
                    roots=roots,
                    delay=delay,
                )
                paths = [
                    dict(r) | {"reason": "Same aircraft; delay after available turnaround buffer (25 minute minimum)"}
                    for r in records
                ]
                return {"engine": "neo4j", "paths": paths}
        except Exception as exc:
            log.warning("Neo4j cascade unavailable (%s)", type(exc).__name__)
    return {"engine": "postgresql-recursive-cte", "paths": cascade(db, roots, delay)}
