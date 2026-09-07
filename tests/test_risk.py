import pytest
from pydantic import ValidationError
from backend.intelligence import risk
from backend.schemas import Simulation
from backend.models import Base


def sample(**kwargs):
    return (
        dict(
            flight_status="EN_ROUTE",
            weather_severity=0,
            inside_weather=False,
            approaching_weather=False,
            airspace_names=[],
            destination_closed=False,
            destination_status="OPEN",
            origin_closed=False,
            origin_status="OPEN",
            runway_closure=False,
            next_buffer_minutes=60,
            impacts=[],
            estimated_delay_minutes=0,
        )
        | kwargs
    )


def test_exactly_13_entities():
    assert len(Base.metadata.tables) == 13


def test_nominal_and_landed():
    assert risk(sample())["score"] == 0
    assert risk(sample(flight_status="LANDED", weather_severity=5, destination_closed=True))["score"] == 0


def test_weather_closure_and_buffer_are_explained_and_capped():
    r = risk(
        sample(
            weather_severity=5,
            inside_weather=True,
            airspace_names=["Test zone"],
            destination_closed=True,
            runway_closure=True,
            next_buffer_minutes=25,
            estimated_delay_minutes=90,
        )
    )
    assert r["level"] == "HIGH" and r["score"] == 100
    assert {"WEATHER", "INSIDE_WEATHER", "AIRSPACE", "DESTINATION_CLOSED", "RUNWAY", "ROTATION_BUFFER", "DELAY"} == {
        x["code"] for x in r["factors"]
    }
    assert all(x["reason"] for x in r["factors"])


def test_downstream_contribution():
    r = risk(sample(impacts=[{"impact_type": "AIRCRAFT_UNAVAILABLE"}]))
    assert r["score"] == 25 and r["level"] == "MODERATE"


@pytest.mark.parametrize(
    "data",
    [
        {"disruption_type": "RUNWAY_CLOSURE", "airport_id": 1},
        {"disruption_type": "AIRPORT_CLOSURE", "airport_id": -1},
        {"disruption_type": "SEVERE_WEATHER", "airport_id": 1, "severity": 6},
        {"disruption_type": "SEVERE_WEATHER", "airport_id": 1, "duration_minutes": 99999},
        {"disruption_type": "INVALID", "airport_id": 1},
    ],
)
def test_simulation_validation(data):
    with pytest.raises(ValidationError):
        Simulation(**data)
