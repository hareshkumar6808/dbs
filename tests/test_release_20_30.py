from backend.main import AIRCRAFT_MODEL_PHOTOS, _model_photo, _scenario_examples


def test_every_supported_aircraft_model_has_distinct_licensed_photo():
    photos = [_model_photo(*aircraft_type) for aircraft_type in AIRCRAFT_MODEL_PHOTOS]
    assert len(photos) == 10
    assert len({photo["url"] for photo in photos}) == len(photos)
    assert all(photo["source"] == "Wikimedia Commons" for photo in photos)
    assert all(photo["credit"] and photo["license"] and photo["license_url"] for photo in photos)


def test_scenario_examples_cover_each_operational_state_and_hazard():
    statuses = ("EN_ROUTE", "APPROACHING", "TAXIING", "BOARDING", "DELAYED", "LANDED", "SCHEDULED", "DIVERTED", "CANCELLED")
    flights = [
        {"flight_id": index, "flight_status": status, "mitigation_type": None, "risk": {"level": "LOW"}}
        for index, status in enumerate(statuses, 1)
    ]
    flights += [
        {"flight_id": 20, "flight_status": "EN_ROUTE", "mitigation_type": "WEATHER", "risk": {"level": "HIGH"}},
        {"flight_id": 21, "flight_status": "EN_ROUTE", "mitigation_type": "AIRSPACE", "risk": {"level": "MODERATE"}},
    ]
    keys = {example["key"] for example in _scenario_examples(flights)}
    assert {status.lower() for status in statuses} | {"weather", "airspace", "high-risk"} <= keys
