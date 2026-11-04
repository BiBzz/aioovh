from http import HTTPStatus

import pytest
from httpx2 import ConnectError, MockTransport, Request, Response

from aioovh import (
    BadParametersError,
    NotGrantedCallError,
    OVHClient,
    OVHConfigurationError,
    OVHSettings,
    OVHTransportError,
    ResourceExpiredError,
    ResourceNotFoundError,
    ServerError,
    signature,
)
from tests.conftest import (
    APPLICATION_KEY,
    APPLICATION_SECRET,
    CONSUMER_KEY,
    NOW,
    Recorder,
)


def test_the_signature_matches_a_known_vector() -> None:
    url = "https://eu.api.ovh.com/1.0/me/bill?date.from=2026-08-31&date.to=2026-10-02"

    result = signature(APPLICATION_SECRET, CONSUMER_KEY, "get", url, "", "1790000000")

    # SHA-1 of "AS+CK+GET+url++1790000000", checked with sha1sum
    assert result == "$1$7cd498e21dc72c1130f56b9916dc61af6542649a"


async def test_requests_are_signed_with_the_server_time(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=["1"])

    await client.request(
        "GET", "/1.0/me/bill", params={"date.from": "2026-08-31", "date.to": None}
    )

    time_request, request = recorder.requests
    assert time_request.url.path == "/1.0/auth/time"
    assert "X-Ovh-Signature" not in time_request.headers
    timestamp = str(int(NOW) + 5)
    assert request.headers["X-Ovh-Application"] == APPLICATION_KEY
    assert request.headers["X-Ovh-Consumer"] == CONSUMER_KEY
    assert request.headers["X-Ovh-Timestamp"] == timestamp
    assert request.headers["X-Ovh-Signature"] == signature(
        APPLICATION_SECRET,
        CONSUMER_KEY,
        "GET",
        "https://eu.api.ovh.com/1.0/me/bill?date.from=2026-08-31",
        "",
        timestamp,
    )


async def test_the_body_is_signed_as_sent(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body={})

    await client.request("POST", "/1.0/me/task", body={"name": "x", "skip": None})

    request = recorder.requests[-1]
    assert request.content == b'{"name": "x"}'
    assert request.headers["X-Ovh-Signature"] == signature(
        APPLICATION_SECRET,
        CONSUMER_KEY,
        "POST",
        "https://eu.api.ovh.com/1.0/me/task",
        '{"name": "x"}',
        str(int(NOW) + 5),
    )


async def test_the_server_time_is_read_once(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=[])
    recorder.reply(body=[])

    await client.get("/me/bill")
    await client.get("/me/refund")

    paths = [request.url.path for request in recorder.requests]
    assert paths == ["/1.0/auth/time", "/1.0/me/bill", "/1.0/me/refund"]


async def test_oauth2_uses_a_bearer_token(recorder: Recorder) -> None:
    recorder.reply(body={"access_token": "token-1", "expires_in": 3600})
    recorder.reply(body={})
    recorder.reply(body={})
    settings = OVHSettings(client_id="id", client_secret="secret")
    client = OVHClient(settings, transport=MockTransport(recorder), clock=lambda: NOW)

    await client.get("/me")
    await client.get("/me")

    token_request, first, second = recorder.requests
    assert str(token_request.url) == "https://www.ovh.com/auth/oauth2/token"
    assert b"grant_type=client_credentials" in token_request.content
    assert first.headers["Authorization"] == "Bearer token-1"
    assert "X-Ovh-Signature" not in first.headers
    assert second.headers["Authorization"] == "Bearer token-1"


async def test_a_call_without_credentials_is_refused(recorder: Recorder) -> None:
    client = OVHClient(OVHSettings(), transport=MockTransport(recorder))

    with pytest.raises(OVHConfigurationError, match="credentials"):
        await client.get("/me")


async def test_an_unauthenticated_call_needs_no_credentials(recorder: Recorder) -> None:
    recorder.reply(body=123)
    client = OVHClient(OVHSettings(), transport=MockTransport(recorder))

    assert await client.request_json("GET", "/1.0/auth/time", auth=False) == 123


def test_an_unknown_endpoint_is_refused() -> None:
    with pytest.raises(OVHConfigurationError, match="ovh-eu"):
        OVHClient(OVHSettings(endpoint="ovh-mars"))


def test_an_endpoint_can_be_a_url() -> None:
    client = OVHClient(OVHSettings(endpoint="https://eu.api.example.test/"))

    assert client.endpoint.api_url == "https://eu.api.example.test"


def test_settings_read_the_official_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OVH_ENDPOINT", "ovh-ca")
    monkeypatch.setenv("OVH_APPLICATION_KEY", "key")

    settings = OVHSettings()

    assert settings.endpoint == "ovh-ca"
    assert settings.application_key == "key"


def test_raw_paths_default_to_the_first_version() -> None:
    assert OVHClient.raw_path("/me") == "/1.0/me"
    assert OVHClient.raw_path("me") == "/1.0/me"
    assert OVHClient.raw_path("/v2/iam/policy") == "/v2/iam/policy"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (HTTPStatus.NOT_FOUND, {"message": "gone"}, ResourceNotFoundError),
        (HTTPStatus.BAD_REQUEST, {"message": "bad"}, BadParametersError),
        (
            HTTPStatus.FORBIDDEN,
            {"errorCode": "NOT_GRANTED_CALL", "message": "no"},
            NotGrantedCallError,
        ),
        (460, {"message": "expired"}, ResourceExpiredError),
        (HTTPStatus.INTERNAL_SERVER_ERROR, "oops", ServerError),
    ],
)
async def test_errors_are_typed(
    client: OVHClient,
    recorder: Recorder,
    status: int,
    body: object,
    error: type[Exception],
) -> None:
    recorder.reply(status, body)

    with pytest.raises(error):
        await client.get("/me")


async def test_the_error_keeps_the_query_id(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(
        HTTPStatus.NOT_FOUND, {"message": "gone"}, headers={"X-Ovh-QueryID": "EU.ext-1"}
    )

    with pytest.raises(ResourceNotFoundError) as caught:
        await client.get("/me/bill/FR1")

    assert caught.value.query_id == "EU.ext-1"
    assert "EU.ext-1" in str(caught.value)


async def test_throttling_is_retried_with_a_fresh_signature(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(HTTPStatus.TOO_MANY_REQUESTS, {}, headers={"Retry-After": "1"})
    recorder.reply(body={"ok": True})

    assert await client.post("/me/task", name="x") == {"ok": True}
    assert len(recorder.requests) == 3
    assert "X-Ovh-Signature" in recorder.requests[-1].headers


async def test_a_post_is_not_retried_on_a_bad_gateway(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(HTTPStatus.BAD_GATEWAY, {})

    with pytest.raises(ServerError):
        await client.post("/me/task", name="x")
    assert len(recorder.requests) == 2


async def test_a_refused_connection_is_retried(
    client: OVHClient, recorder: Recorder
) -> None:
    def refused(request: Request) -> Response:
        raise ConnectError("refused", request=request)

    recorder.push(refused)
    recorder.reply(body=[])

    assert await client.get("/me/bill") == []


async def test_transport_errors_are_wrapped(recorder: Recorder) -> None:
    def refused(request: Request) -> Response:
        raise ConnectError("refused", request=request)

    for _ in range(3):
        recorder.push(refused)
    client = OVHClient(OVHSettings(), transport=MockTransport(recorder))

    with pytest.raises(OVHTransportError):
        await client.request("GET", "/1.0/auth/time", auth=False)


def test_path_parameters_are_quoted() -> None:
    assert OVHClient.path("/me/bill/{billId}", billId="FR/1") == "/me/bill/FR%2F1"
