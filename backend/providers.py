"""Live ingestion only updates known flight callsigns; never fabricates routes/assignments."""

from typing import Protocol
from datetime import datetime, timezone
import httpx
from sqlalchemy import text
from backend.config import settings
from backend.db import one


class PositionProvider(Protocol):
    def positions(self) -> list[dict]: ...


class OpenSkyProvider:
    def positions(self):
        s = settings()
        if not s.opensky_client_id or not s.opensky_client_secret:
            return []
        with httpx.Client(timeout=12) as client:
            auth = client.post(
                "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": s.opensky_client_id,
                    "client_secret": s.opensky_client_secret,
                },
            )
            auth.raise_for_status()
            response = client.get(
                "https://opensky-network.org/api/states/all",
                params={"lamin": 6, "lamax": 36, "lomin": 67, "lomax": 98},
                headers={"Authorization": "Bearer " + auth.json()["access_token"]},
            )
            response.raise_for_status()
            return [
                {
                    "callsign": (x[1] or "").strip(),
                    "longitude": x[5],
                    "latitude": x[6],
                    "altitude_m": x[13] or x[7] or 0,
                    "speed_kmh": (x[9] or 0) * 3.6,
                    "heading": x[10] or 0,
                    "recorded_at": datetime.fromtimestamp(x[3], timezone.utc),
                }
                for x in response.json().get("states") or []
                if x[5] is not None and x[6] is not None and x[3] is not None
            ]


def ingest(db, provider: PositionProvider):
    written = 0
    for p in provider.positions():
        f = one(
            db,
            """SELECT f.flight_id,f.aircraft_id FROM flight f JOIN airline a USING(airline_id)
            WHERE (f.flight_number=:callsign OR a.icao_code||substring(f.flight_number FROM length(a.iata_code)+1)=:callsign)
              AND f.flight_status='EN_ROUTE' AND now() BETWEEN f.scheduled_departure-interval '3 hours' AND f.scheduled_arrival+interval '6 hours'
            ORDER BY abs(EXTRACT(EPOCH FROM(now()-f.scheduled_departure))) LIMIT 1""",
            callsign=p["callsign"],
        )
        if not f:
            continue
        params = p | {"id": f["flight_id"], "aircraft": f["aircraft_id"]}
        written += db.execute(
            text("""INSERT INTO flight_position(flight_id,position,ground_speed,heading,recorded_at)
          VALUES(:id,ST_SetSRID(ST_MakePoint(:longitude,:latitude,:altitude_m),4326),:speed_kmh,:heading,:recorded_at)
          ON CONFLICT(flight_id,recorded_at) DO NOTHING"""),
            params,
        ).rowcount
        db.execute(
            text("""UPDATE aircraft SET current_location=ST_SetSRID(ST_MakePoint(:longitude,:latitude,:altitude_m),4326),
          current_speed=:speed_kmh,heading=:heading,last_updated=:recorded_at WHERE aircraft_id=:aircraft
          AND (last_updated IS NULL OR last_updated<:recorded_at)"""),
            params,
        )
    db.commit()
    return {"updated": written, "mode": "live", "provider": "OpenSky"}
