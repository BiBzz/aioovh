import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import stamina
from httpx2 import MockTransport, Request, Response

from aioovh import OVHClient, OVHSettings

type Handler = Callable[[Request], Response]


class Recorder:
    """A transport that answers from a queue of handlers and keeps every request."""

    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.handlers: list[Handler] = []

    def reply(
        self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        def handler(request: Request) -> Response:
            return Response(status, json=body, headers=headers)

        self.handlers.append(handler)

    def push(self, handler: Handler) -> None:
        self.handlers.append(handler)

    def __call__(self, request: Request) -> Response:
        self.requests.append(request)
        if not self.handlers:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        return self.handlers.pop(0)(request)

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content)


@pytest.fixture(autouse=True)
def no_retry_wait() -> Iterator[None]:
    stamina.set_testing(True, attempts=3)
    yield
    stamina.set_testing(False)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


APPLICATION_KEY = "7kbG7Bk7S9Nt7ZSV"
APPLICATION_SECRET = "EXEgWIz07P0HYwtQDs7cNIqCiQaWSuHF"
CONSUMER_KEY = "MtSwSrPpNjqfVSmJhLbPyr2i45lSDRBNa"
NOW = 1_790_000_000.0


@pytest.fixture
def settings() -> OVHSettings:
    return OVHSettings(
        application_key=APPLICATION_KEY,
        application_secret=APPLICATION_SECRET,
        consumer_key=CONSUMER_KEY,
    )


@pytest.fixture
def client(recorder: Recorder, settings: OVHSettings) -> OVHClient:
    client = OVHClient(settings, transport=MockTransport(recorder), clock=lambda: NOW)
    recorder.reply(body=int(NOW) + 5)
    return client
