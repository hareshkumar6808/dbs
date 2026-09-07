"""Real PostGIS tests. Only run when explicitly pointed at a disposable test DB."""

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from backend.db import session
from backend.main import app
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
        assert db.execute(text("SELECT count(*) FROM airport")).scalar() == 12
        assert db.execute(text("SELECT count(*) FROM flight")).scalar() >= 128
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
    assert state["mode"] == "demo" and state["network"]["airborne"] >= 24
    flight = next(f for f in state["flights"] if f["flight_status"] == "EN_ROUTE")
    assert flight["position"]["type"] == "Point" and len(flight["position"]["coordinates"]) == 3
    assert flight["distance_remaining_km"] > 0
    history = client.get(f"/api/flights/{flight['flight_id']}/positions").json()
    assert len(history) > 2
    assert history == sorted(history, key=lambda p: p["recorded_at"])
    with Session(db_engine) as db:
        assert db.execute(
            text("SELECT count(*) FROM flight_position WHERE flight_id=:id"), {"id": flight["flight_id"]}
        ).scalar() >= len(history)


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
