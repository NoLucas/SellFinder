from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELLFINDER_", protected_namespaces=())

    # Signs basemap artifact URLs that require it (see app/services/basemap_registry.py).
    basemap_signing_secret: str = "dev-secret-change-me"
    basemap_signed_url_ttl_seconds: int = 3600

    # ADR-003 "개발 중 임시 조치": /v1/dev/token is registered only when this is "development".
    env: str = "development"

    # app/db.py's connection pool target (SELLFINDER_DATABASE_URL). Staged
    # for the Postgres+RLS cutover (RECONCILIATION.md, 2026-08-17) - app/db.py
    # isn't wired into any route yet, so this being unset today is expected,
    # not a misconfiguration.
    database_url: str | None = None


settings = Settings()
