from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "./data/evalops.db"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    worker_poll_interval_secs: int = 5
    worker_lease_timeout_secs: int = 60
    worker_max_retries: int = 3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
