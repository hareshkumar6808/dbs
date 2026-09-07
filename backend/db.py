from functools import lru_cache
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from backend.config import settings


@lru_cache
def engine():
    if not settings().database_url:
        raise HTTPException(
            503, "Cloud PostGIS database is not configured. Set DATABASE_URL and run python -m scripts.setup."
        )
    return create_engine(
        settings().sqlalchemy_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 8, "options": "-c statement_timeout=15000"},
        hide_parameters=True,
    )


def session():
    with Session(engine()) as db:
        yield db


def rows(db, sql, **params):
    return [dict(row) for row in db.execute(text(sql), params).mappings()]


def one(db, sql, **params):
    result = rows(db, sql, **params)
    return result[0] if result else None
