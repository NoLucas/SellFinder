from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELLFINDER_", protected_namespaces=())

    # When False, PredictionService returns deterministic mock predictions
    # instead of calling into /model. Flip once the real model integration
    # (e.g. an import from /model or a call to a model-serving endpoint) exists.
    use_live_model: bool = False
    model_version_mock: str = "mock-0.1.0"


settings = Settings()
