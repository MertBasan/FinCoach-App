from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "fincoach"
    postgres_user: str = "fincoach"
    postgres_password: str = "changeme_local_only"

    secret_key: str = "dev_secret_change_me"
    session_cookie_name: str = "fincoach_session"
    environment: str = "development"

    anthropic_api_key: str = ""
    n8n_webhook_url: str = ""  # empty = assistant disabled

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
