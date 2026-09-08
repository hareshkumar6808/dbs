"""Run: python -m scripts.setup. Idempotent migrations + seed + optional graph sync."""

from alembic.config import Config
from alembic import command
from sqlalchemy.orm import Session
from backend.db import engine
from backend.seed import ensure_demo_network
from backend.graph import sync
from backend.config import settings


def main():
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine()) as db:
        if settings().effective_mode == "demo":
            print(ensure_demo_network(db))
        else:
            print({"seeded": False, "reason": "Live mode: import real schedules and assignments before ingestion"})
        print(sync(db))


if __name__ == "__main__":
    main()
