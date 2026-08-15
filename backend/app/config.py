from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELLFINDER_", protected_namespaces=())

    # Signs basemap artifact URLs that require it (see app/services/basemap_registry.py).
    basemap_signing_secret: str = "dev-secret-change-me"
    basemap_signed_url_ttl_seconds: int = 3600


settings = Settings()
