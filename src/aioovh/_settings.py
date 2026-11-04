from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OVHSettings(BaseSettings):
    """Connection settings, read from the `OVH_*` variables of the official SDK."""

    model_config = SettingsConfigDict(env_prefix="OVH_", extra="ignore")

    endpoint: str = "ovh-eu"
    application_key: str | None = None
    application_secret: SecretStr | None = None
    consumer_key: SecretStr | None = None
    client_id: str | None = None
    client_secret: SecretStr | None = None
    default_project: str | None = None
    max_concurrency: int = 8
    timeout: float = 180.0
    retry_attempts: int = 5
    retry_timeout: float | None = 120.0
    retry_wait_initial: float = 0.5
    retry_wait_max: float = 30.0
    user_agent: str = "aioovh"
