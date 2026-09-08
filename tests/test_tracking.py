from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import os
import pytest
from backend.tracking import replenish
from backend.seed import _waypoint_coordinates, _interpolate, AIRPORTS
from backend.config import Settings


def test_missing_live_credentials_falls_back_to_honest_demo():
    assert (
        Settings(_env_file=None, data_mode="live", opensky_client_id="", opensky_client_secret="").effective_mode
        == "demo"
    )
    assert (
        Settings(_env_file=None, data_mode="live", opensky_client_id="x", opensky_client_secret="y").effective_mode
        == "live"
    )


def test_planned_route_has_terminal_and_enroute_waypoints():
    points = _waypoint_coordinates(AIRPORTS[0], AIRPORTS[2], 7)
    assert len(points) == 8
    assert points[0] == (AIRPORTS[0][5], AIRPORTS[0][6])
    assert points[-1] == (AIRPORTS[2][5], AIRPORTS[2][6])
    midpoint = _interpolate(points, 0.5)
    direct_midpoint = ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2)
    assert midpoint != direct_midpoint


@pytest.mark.integration
def test_rotation_replenishment_preserves_history():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Needs a real test PostGIS database")
    engine = create_engine(url, hide_parameters=True)
    with Session(engine) as db:
        original = db.execute(text("SELECT count(*) FROM flight_position")).scalar()
        future = datetime.now(timezone.utc) + timedelta(days=5)
        before = db.execute(text("SELECT count(*) FROM flight")).scalar()
        aircraft = db.execute(text("SELECT count(*) FROM aircraft")).scalar()
        replenish(db, future)
        assert db.execute(text("SELECT count(*) FROM flight")).scalar() == before + aircraft * 4
        assert db.execute(text("SELECT count(*) FROM flight_position")).scalar() == original
        assert (
            db.execute(
                text("SELECT count(*) FROM flight WHERE scheduled_departure<:now AND scheduled_arrival>:now"),
                {"now": future},
            ).scalar()
            == aircraft
        )
        db.rollback()
    engine.dispose()
