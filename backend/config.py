from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    data_mode: Literal["demo", "live"] = "demo"
    cors_origins: str = "http://localhost:5173"
    admin_token: str = ""
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    opensky_client_id: str = ""
    opensky_client_secret: str = ""
    cron_secret: str = ""

    @property
    def effective_mode(self):
        return "live" if self.data_mode == "live" and self.opensky_client_id and self.opensky_client_secret else "demo"

    @property
    def sqlalchemy_url(self):
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def settings():
    return Settings()
