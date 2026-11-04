import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from enum import Enum
from http import HTTPStatus
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

from httpx2 import (
    AsyncBaseTransport,
    AsyncClient,
    ConnectError,
    ConnectTimeout,
    Request,
    Response,
    TransportError,
)
from pydantic import BaseModel, TypeAdapter
from stamina import retry_context
from whenever import Date, Instant

from aioovh._endpoints import ENDPOINTS, Endpoint
from aioovh._errors import (
    OVHAPIError,
    OVHConfigurationError,
    OVHTransportError,
    api_error,
)
from aioovh._settings import OVHSettings

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
RETRYABLE_STATUSES = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)
NEVER_PROCESSED_STATUSES = frozenset(
    {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}
)
TOKEN_EXPIRY_MARGIN_SECONDS = 30
NEXT_CURSOR_HEADER = "x-pagination-cursor-next"
type QueryValue = (
    str | int | float | bool | Enum | Instant | Date | dict[str, Any] | BaseModel | None
)
type Query = Mapping[str, QueryValue | list[Any]]
type QueryPairs = list[tuple[str, str | int | float | bool | None]]


def signature(
    application_secret: str,
    consumer_key: str,
    method: str,
    url: str,
    body: str,
    timestamp: str,
) -> str:
    """The `X-Ovh-Signature` of a request: `$1$` and a SHA-1 of its parts."""
    payload = "+".join(
        (application_secret, consumer_key, method.upper(), url, body, timestamp)
    )
    return "$1$" + hashlib.sha1(payload.encode()).hexdigest()


def retry_decision(method: str, error: Exception) -> bool | float:
    """Tell stamina whether to retry, waiting Retry-After seconds when given."""
    if isinstance(error, OVHAPIError):
        if error.status_code not in RETRYABLE_STATUSES:
            return False
        if method not in IDEMPOTENT_METHODS and (
            error.status_code not in NEVER_PROCESSED_STATUSES
        ):
            return False
        retry_after = error.headers.get("retry-after", "")
        return float(retry_after) if retry_after.isdigit() else True
    if isinstance(error, OVHTransportError):
        return method in IDEMPOTENT_METHODS or isinstance(
            error.__cause__, ConnectError | ConnectTimeout
        )
    return False


def query_value(value: Any) -> str:
    if isinstance(value, dict | BaseModel):
        return json.dumps(encode_body(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Instant | Date):
        return value.format_iso()
    return str(value)


def encode_query(params: Query | None) -> QueryPairs:
    pairs: QueryPairs = []
    for name, value in (params or {}).items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        pairs.extend((name, query_value(item)) for item in values if item is not None)
    return pairs


def encode_body(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Instant | Date):
        return value.format_iso()
    if isinstance(value, dict):
        return {
            key: encode_body(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list | tuple):
        return [encode_body(item) for item in value]
    return value


ADAPTERS: dict[object, TypeAdapter[Any]] = {}


def parse[T](annotation: type[T], data: Any) -> T:
    """Validate a response against a type that is not a model (`list[str]`)."""
    if annotation not in ADAPTERS:
        ADAPTERS[annotation] = TypeAdapter(annotation)
    result: T = ADAPTERS[annotation].validate_python(data)
    return result


def endpoint(settings: OVHSettings) -> Endpoint:
    if settings.endpoint.startswith(("https://", "http://")):
        return Endpoint(settings.endpoint.rstrip("/"))
    try:
        return ENDPOINTS[settings.endpoint]
    except KeyError:
        known = ", ".join(sorted(ENDPOINTS))
        raise OVHConfigurationError(
            f"Unknown endpoint {settings.endpoint!r}, expected one of {known}."
        ) from None


class OVHClient:
    """Authenticated, retrying HTTP access to the OVHcloud API (`OVH().raw`).

    Its `get`, `post`, `put`, `patch` and `delete` cover any path, untyped, as
    the official `ovh.Client` does.
    """

    def __init__(
        self,
        settings: OVHSettings | None = None,
        *,
        transport: AsyncBaseTransport | None = None,
        http_client: AsyncClient | None = None,
        clock: Callable[[], Instant] = Instant.now,
    ) -> None:
        self.settings = OVHSettings() if settings is None else settings
        self.endpoint = endpoint(self.settings)
        self._clock = clock
        self._owns_http_client = http_client is None
        self._http = http_client or AsyncClient(
            base_url=self.endpoint.api_url,
            transport=transport,
            timeout=self.settings.timeout,
        )
        self._time_delta: int | None = None
        self._token: str | None = None
        self._token_expiry: Instant | None = None
        self._lock = asyncio.Lock()

    @property
    def http_client(self) -> AsyncClient:
        return self._http

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
        if self._owns_http_client:
            await self._http.aclose()

    @staticmethod
    def path(template: str, **values: Any) -> str:
        missing = [name for name, value in values.items() if value in (None, "")]
        if missing:
            raise OVHConfigurationError(f"Empty path parameter: {', '.join(missing)}.")
        return template.format(
            **{
                name: quote(query_value(value), safe="")
                for name, value in values.items()
            }
        )

    @property
    def uses_oauth2(self) -> bool:
        return bool(self.settings.client_id and self.settings.client_secret)

    async def time_delta(self) -> int:
        """Seconds to add to the local clock to get OVHcloud's, read once."""
        if self._time_delta is None:
            async with self._lock:
                if self._time_delta is None:
                    response = await self.request("GET", "/1.0/auth/time", auth=False)
                    self._time_delta = int(response.json()) - self._clock().timestamp()
        return self._time_delta

    async def _access_token(self) -> str:
        if (
            self._token is not None
            and self._token_expiry is not None
            and self._clock() < self._token_expiry
        ):
            return self._token
        token_url = self.endpoint.token_url
        if token_url is None:
            raise OVHConfigurationError(
                f"The {self.settings.endpoint} endpoint has no OAuth2 token URL."
            )
        assert self.settings.client_id and self.settings.client_secret
        try:
            response = await self._http.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret.get_secret_value(),
                    "scope": "all",
                },
            )
        except TransportError as error:
            raise OVHTransportError("POST", token_url, repr(error)) from error
        if response.is_error:
            raise api_error(
                "POST",
                token_url,
                response.status_code,
                response.text,
                dict(response.headers),
            )
        payload = response.json()
        self._token = str(payload["access_token"])
        lifetime = int(payload.get("expires_in", 3600)) - TOKEN_EXPIRY_MARGIN_SECONDS
        self._token_expiry = self._clock().add(seconds=lifetime)
        return self._token

    async def _authenticate(self, request: Request, body: str) -> None:
        if self.uses_oauth2:
            request.headers["Authorization"] = f"Bearer {await self._access_token()}"
            return
        key = self.settings.application_key
        secret = self.settings.application_secret
        consumer = self.settings.consumer_key
        if not (key and secret and consumer):
            raise OVHConfigurationError(
                "This call needs credentials: application_key, application_secret "
                "and consumer_key (OVH_*), or client_id and client_secret."
            )
        timestamp = str(self._clock().timestamp() + await self.time_delta())
        request.headers.update(
            {
                "X-Ovh-Application": key,
                "X-Ovh-Consumer": consumer.get_secret_value(),
                "X-Ovh-Timestamp": timestamp,
                "X-Ovh-Signature": signature(
                    secret.get_secret_value(),
                    consumer.get_secret_value(),
                    request.method,
                    str(request.url),
                    body,
                    timestamp,
                ),
            }
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Query | None = None,
        body: Any = None,
        headers: Mapping[str, str | int | None] | None = None,
        auth: bool = True,
    ) -> Response:
        """Send one request, signed, and retried on transient failures."""
        method = method.upper()
        query = encode_query(params)
        content = "" if body is None else json.dumps(encode_body(body))
        request_headers = {"User-Agent": self.settings.user_agent}
        if content:
            request_headers["Content-Type"] = "application/json"
        if self.settings.application_key and not self.uses_oauth2:
            request_headers["X-Ovh-Application"] = self.settings.application_key
        for name, value in (headers or {}).items():
            if value is not None:
                request_headers[name] = str(value)
        async for attempt in retry_context(
            on=lambda error: retry_decision(method, error),
            attempts=self.settings.retry_attempts,
            timeout=self.settings.retry_timeout,
            wait_initial=self.settings.retry_wait_initial,
            wait_max=self.settings.retry_wait_max,
        ):
            with attempt:
                request = self._http.build_request(
                    method,
                    path,
                    params=query,
                    content=content.encode() if content else None,
                    headers=request_headers,
                )
                if auth:
                    await self._authenticate(request, content)
                return await self._send(request)
        raise AssertionError("unreachable: stamina either returns or raises")

    async def _send(self, request: Request) -> Response:
        try:
            response = await self._http.send(request)
        except TransportError as error:
            raise OVHTransportError(
                request.method, str(request.url), repr(error)
            ) from error
        if response.is_error:
            try:
                error_body: Any = response.json()
            except ValueError:
                error_body = response.text
            raise api_error(
                request.method,
                str(request.url),
                response.status_code,
                error_body,
                dict(response.headers),
            )
        return response

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Query | None = None,
        body: Any = None,
        headers: Mapping[str, str | int | None] | None = None,
        auth: bool = True,
    ) -> Any:
        response = await self.request(
            method, path, params=params, body=body, headers=headers, auth=auth
        )
        if response.status_code == HTTPStatus.NO_CONTENT or not response.content:
            return None
        return response.json()

    @staticmethod
    def raw_path(path: str) -> str:
        if path.startswith(("/1.0/", "/v1/", "/v2/")):
            return path
        return "/1.0" + (path if path.startswith("/") else f"/{path}")

    async def get(self, path: str, **params: QueryValue) -> Any:
        """`GET` any path, untyped: `client.get("/me/bill", **{"date.from": day})`."""
        return await self.request_json("GET", self.raw_path(path), params=params)

    async def delete(self, path: str, **params: QueryValue) -> Any:
        return await self.request_json("DELETE", self.raw_path(path), params=params)

    async def post(self, path: str, **body: Any) -> Any:
        return await self.request_json("POST", self.raw_path(path), body=body)

    async def put(self, path: str, **body: Any) -> Any:
        return await self.request_json("PUT", self.raw_path(path), body=body)

    async def patch(self, path: str, **body: Any) -> Any:
        return await self.request_json("PATCH", self.raw_path(path), body=body)


async def paginate_cursor[Item](
    fetch: Callable[[str | None], Awaitable[tuple[list[Item], str | None]]],
) -> AsyncIterator[Item]:
    """Walk the v2 cursor pagination until no `X-Pagination-Cursor-Next` comes back."""
    cursor: str | None = None
    while True:
        items, cursor = await fetch(cursor)
        for item in items:
            yield item
        if not cursor:
            return
