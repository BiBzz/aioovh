from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

from httpx2 import AsyncBaseTransport, AsyncClient
from pydantic import SecretStr
from whenever import Instant

from aioovh._client import OVHClient
from aioovh._namespaces import Namespaces
from aioovh._objects import Session
from aioovh._settings import OVHSettings


class OVH(Namespaces):
    """The OVHcloud API, organised by business area: `ovh.billing.bills`.

    Values left out are read from the `OVH_*` environment variables.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        application_key: str | None = None,
        application_secret: str | None = None,
        consumer_key: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        default_project: str | None = None,
        settings: OVHSettings | None = None,
        http_client: AsyncClient | None = None,
        transport: AsyncBaseTransport | None = None,
        clock: Callable[[], Instant] = Instant.now,
    ) -> None:
        secrets = {
            "application_secret": application_secret,
            "consumer_key": consumer_key,
            "client_secret": client_secret,
        }
        changes: dict[str, Any] = {
            "endpoint": endpoint,
            "application_key": application_key,
            "client_id": client_id,
            "default_project": default_project,
            **{
                name: None if value is None else SecretStr(value)
                for name, value in secrets.items()
            },
        }
        base = OVHSettings() if settings is None else settings
        self.settings = base.model_copy(
            update={name: value for name, value in changes.items() if value is not None}
        )
        self.raw = OVHClient(
            self.settings, http_client=http_client, transport=transport, clock=clock
        )
        self._session = Session(self.raw)

    def with_options(self, **changes: Any) -> Self:
        """A client sharing this one's connections, with other settings."""
        settings = self.settings.model_copy(update=changes)
        return type(self)(settings=settings, http_client=self.raw.http_client)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.raw.aclose()
