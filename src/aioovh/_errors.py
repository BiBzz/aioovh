from http import HTTPStatus
from typing import Any

RESOURCE_EXPIRED_STATUS = 460


class OVHError(Exception):
    """Base class of every error raised by aioovh."""


class OVHConfigurationError(OVHError):
    """The endpoint or the credentials are missing or unknown."""


class OVHTransportError(OVHError):
    """The API could not be reached, or the connection broke."""

    def __init__(self, method: str, url: str, reason: str) -> None:
        super().__init__(f"{method} {url} failed: {reason}")
        self.method = method
        self.url = url


class OVHAPIError(OVHError):
    """The API answered with an error status."""

    def __init__(
        self,
        method: str,
        url: str,
        status_code: int,
        body: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        details = body if isinstance(body, dict) else {}
        self.message: str = str(details.get("message") or body or "")
        self.error_code: str | None = details.get("errorCode")
        self.query_id: str | None = self.headers.get("x-ovh-queryid")
        suffix = f" (query {self.query_id})" if self.query_id else ""
        super().__init__(
            f"{method} {url} answered {status_code}: {self.message}{suffix}"
        )


class BadParametersError(OVHAPIError):
    pass


class NotCredentialError(OVHAPIError):
    pass


class InvalidKeyError(OVHAPIError):
    pass


class InvalidCredentialError(OVHAPIError):
    pass


class NotGrantedCallError(OVHAPIError):
    pass


class ForbiddenError(OVHAPIError):
    pass


class ResourceNotFoundError(OVHAPIError):
    pass


class ResourceConflictError(OVHAPIError):
    pass


class ResourceExpiredError(OVHAPIError):
    pass


class TooManyRequestsError(OVHAPIError):
    pass


class ServerError(OVHAPIError):
    pass


ERRORS_BY_CODE: dict[str, type[OVHAPIError]] = {
    "NOT_CREDENTIAL": NotCredentialError,
    "INVALID_KEY": InvalidKeyError,
    "INVALID_CREDENTIAL": InvalidCredentialError,
    "NOT_GRANTED_CALL": NotGrantedCallError,
    "FORBIDDEN": ForbiddenError,
}

ERRORS_BY_STATUS: dict[int, type[OVHAPIError]] = {
    HTTPStatus.BAD_REQUEST: BadParametersError,
    HTTPStatus.UNAUTHORIZED: InvalidCredentialError,
    HTTPStatus.FORBIDDEN: ForbiddenError,
    HTTPStatus.NOT_FOUND: ResourceNotFoundError,
    HTTPStatus.CONFLICT: ResourceConflictError,
    HTTPStatus.TOO_MANY_REQUESTS: TooManyRequestsError,
    RESOURCE_EXPIRED_STATUS: ResourceExpiredError,
}


def api_error(
    method: str,
    url: str,
    status_code: int,
    body: Any,
    headers: dict[str, str] | None = None,
) -> OVHAPIError:
    code = body.get("errorCode") if isinstance(body, dict) else None
    fallback = (
        ServerError if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR else OVHAPIError
    )
    error_class = ERRORS_BY_CODE.get(str(code)) or ERRORS_BY_STATUS.get(
        status_code, fallback
    )
    return error_class(method, url, status_code, body, headers)
