from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql://nexus:nexus_dev_only@localhost:5432/nexus"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
