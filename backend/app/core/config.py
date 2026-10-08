import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default=f"postgresql+psycopg://lingdebate:{os.getenv('POSTGRES_PASSWORD', 'changeme')}@db:5432/lingdebate")
    secret_key: str = Field(default="changeme")
    public_origin: str = Field(default="http://127.0.0.1:8080")


settings = Settings()
