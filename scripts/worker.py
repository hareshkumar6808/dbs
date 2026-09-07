"""Optional long-running worker. Serverless map requests also persist demand ticks."""

import time
import logging
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import engine
from backend.tracking import tick
from backend.providers import ingest, OpenSkyProvider


if __name__ == "__main__":
    while True:
        try:
            with Session(engine()) as db:
                if settings().effective_mode == "demo":
                    tick(db)
                else:
                    ingest(db, OpenSkyProvider())
        except Exception as exc:
            logging.warning("Tracking update failed (%s); retrying", type(exc).__name__)
        time.sleep(10 if settings().effective_mode == "demo" else 60)
