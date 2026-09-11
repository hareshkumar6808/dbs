"""Real PostGIS tests. Only run when explicitly pointed at a disposable test DB."""

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from backend.db import session
from backend.main import app
from backend.routing import OPERATIONAL_ROUTE_LATERAL
from backend.seed import seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured; real PostGIS integration tests need a disposable database")
    engine = create_engine(url, hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def client(db_engine):
    def override():
        with Session(db_engine) as db:
            yield db

    app.dependency_overrides[session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_seed_idempotent_and_indexes(db_engine):
    with Session(db_engine) as db:
        assert seed(db)["seeded"] is False
        assert db.execute(text("SELECT count(*) FROM airport")).scalar() >= 70
        assert db.execute(text("SELECT count(*) FROM flight")).scalar() >= 3800
        assert (
            db.execute(
                text("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexdef LIKE '%USING gist%'")
            ).scalar()
            >= 7
        )


def test_health_map_persistence_and_replay(client, db_engine):
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/api/map/state")
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["mode"] == "demo" and state["network"]["airborne"] >= 300
    assert state["network"]["daily_operations"] >= 3800
    assert state["network"]["ground"] >= 100
    assert len(state["weather"]) == 8
    assert sum(1 for event in state["weather"] if event["geometry"]["coordinates"][0][0][0] < 60 or event["geometry"]["coordinates"][0][0][0] > 94) >= 2
    statuses = {flight["flight_status"] for flight in state["flights"]}
    assert {"EN_ROUTE", "APPROACHING", "TAXIING", "BOARDING", "DELAYED", "LANDED", "SCHEDULED", "DIVERTED", "CANCELLED"} <= statuses
    india = {a["iata_code"] for a in state["airports"] if a["country"] == "India"}
    assert any(f["origin"] in india and f["destination"] not in india for f in state["flights"])
    assert any(f["origin"] not in india and f["destination"] in india for f in state["flights"])
    flight = next(f for f in state["flights"] if f["flight_status"] == "EN_ROUTE")
    assert flight["position"]["type"] == "Point" and len(flight["position"]["coordinates"]) == 3
    assert flight["distance_remaining_km"] > 0
    assert flight["movement_phase"] in {"CLIMB", "CRUISE", "DESCENT"}
    assert flight["operational_distance_km"] >= 0 and flight["added_distance_km"] >= 0
    assert {x["key"] for x in state["scenario_examples"]} >= {"weather", "airspace", "high-risk", "diverted", "cancelled"}
    lon, lat = flight["position"]["coordinates"][:2]
    viewport = client.get(
        f"/api/map/state?west={lon - .5}&south={lat - .5}&east={lon + .5}&north={lat + .5}"
    ).json()
    assert viewport["viewport_filtered"] is True and 0 < len(viewport["flights"]) < len(state["flights"])
    history = client.get(f"/api/flights/{flight['flight_id']}/positions").json()
    assert len(history) > 2
    assert history == sorted(history, key=lambda p: p["recorded_at"])
    with Session(db_engine) as db:
        assert db.execute(
            text("SELECT count(*) FROM flight_position WHERE flight_id=:id"), {"id": flight["flight_id"]}
        ).scalar() >= len(history)
        assert db.execute(text("""SELECT count(*) FROM route r
          JOIN airport o ON o.airport_id=r.origin_airport_id
          JOIN airport d ON d.airport_id=r.destination_airport_id
          WHERE ST_Distance(ST_StartPoint(r.route_geometry)::geography,o.location::geography)>1
             OR ST_Distance(ST_EndPoint(r.route_geometry)::geography,d.location::geography)>1""")).scalar() == 0
        assert db.execute(text("""SELECT count(*) FROM airport a JOIN weather_event w
          ON w.weather_status='ACTIVE' AND ST_Intersects(a.location,w.affected_area_geometry)""")).scalar() == 0
        assert db.execute(text("""SELECT count(*) FROM airspace_zone z JOIN flight f
          ON f.flight_status IN ('EN_ROUTE','APPROACHING')
          JOIN LATERAL(SELECT position FROM flight_position p WHERE p.flight_id=f.flight_id
            ORDER BY recorded_at DESC LIMIT 1) latest ON true
          WHERE z.zone_status='ACTIVE' AND now() BETWEEN z.valid_from AND z.valid_until
            AND ST_Contains(z.geometry,ST_Force2D(latest.position))
            AND ST_Z(latest.position) BETWEEN z.lower_altitude AND z.upper_altitude""")).scalar() == 0
        assert db.execute(text("""SELECT count(*) FROM route r """ + OPERATIONAL_ROUTE_LATERAL + """
          WHERE hazard.geometry IS NOT NULL
            AND ST_Intersects(operational.geometry,ST_Buffer(hazard.geometry,-.005))""")).scalar() == 0


def test_spatial_queries_and_copilot(client):
    near = client.get("/api/airports/nearby?longitude=80.1693&latitude=12.9941&radius_km=400").json()
    assert near[0]["iata_code"] == "MAA" and near[0]["distance_km"] < 1
    assert any(a["iata_code"] == "BLR" for a in near)
    alternate = client.get("/api/airports/1/alternates").json()
    assert alternate and all(a["iata_code"] != "MAA" and a["available_runway_m"] >= 2200 for a in alternate)
    for q in [
        "Which flights are high risk?",
        "Which flights are affected by weather?",
        "Which routes intersect restricted airspace?",
        "Best alternate airport for Chennai?",
    ]:
        r = client.post("/api/copilot/query", json={"question": q})
        assert r.status_code == 200, r.text
        assert r.json()["items"]
    r = client.post("/api/copilot/query", json={"question": "Who will win the election?"})
    assert "cannot answer" in r.json()["answer"]


@pytest.mark.parametrize("kind", ["RUNWAY_CLOSURE", "AIRPORT_CLOSURE", "SEVERE_WEATHER"])
def test_simulation_risk_cascade_and_reset(client, kind):
    runway = client.get("/api/runways?airport_id=1").json()[0]["runway_id"]
    body = {"disruption_type": kind, "airport_id": 1, "severity": 5, "duration_minutes": 240}
    if kind == "RUNWAY_CLOSURE":
        body["runway_id"] = runway
    r = client.post("/api/disruptions/simulate", json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    try:
        assert result["direct_flights"] and result["downstream_flights"]
        assert not any(
            flight["flight_status"] in {"EN_ROUTE", "APPROACHING"}
            and flight["origin_airport_id"] == 1
            and flight["destination_airport_id"] != 1
            for flight in result["direct_flights"]
        )
        assert result["alternates"]
        event_id = result["disruption_id"]
        impacts = client.get(f"/api/disruptions/{event_id}/impacts").json()
        assert len(impacts) >= len(result["direct_flights"])
        fid = result["direct_flights"][0]["flight_id"]
        risk = client.get(f"/api/flights/{fid}/risk").json()
        assert risk["score"] > 0 and risk["factors"]
        assert client.get(f"/api/flights/{fid}").json()["impacts"]
        paths = client.get(f"/api/intelligence/cascade?flight_id={fid}").json()
        assert paths["paths"]
        assert client.post("/api/disruptions/simulate", json=body).status_code == 409
    finally:
        assert client.post(f"/api/disruptions/{result['disruption_id']}/resolve").status_code == 200
    assert all(
        i["resolution_status"] == "RESOLVED"
        for i in client.get(f"/api/disruptions/{result['disruption_id']}/impacts").json()
    )


def test_invalid_requests(client):
    assert client.get("/api/flights/999999").status_code == 404
    assert client.get("/api/airports/nearby?longitude=999&latitude=10").status_code == 422
    assert (
        client.post(
            "/api/disruptions/simulate", json={"disruption_type": "RUNWAY_CLOSURE", "airport_id": 1, "runway_id": 99999}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/disruptions/simulate", json={"disruption_type": "AIRPORT_CLOSURE", "airport_id": 99999}
        ).status_code
        == 404
    )
