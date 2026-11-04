import re
from pathlib import Path

import pytest
from httpx2 import MockTransport, Request, Response
from whenever import Date, Instant

import aioovh
from aioovh import OVH, ResourceNotFoundError
from aioovh.billing import Bill, BillDetail, BillRef
from tests.conftest import EPOCH, NOW, Recorder


def price(value: float) -> dict[str, object]:
    return {"currencyCode": "EUR", "text": f"{value} EUR", "value": value}


def bill(bill_id: str) -> dict[str, object]:
    return {
        "billId": bill_id,
        "category": "autorenew",
        "date": "2026-10-03T10:00:00+02:00",
        "orderId": 42,
        "password": "p",
        "pdfUrl": "https://example.test/bill.pdf",
        "priceWithTax": price(12.0),
        "priceWithoutTax": price(10.0),
        "tax": price(2.0),
        "url": "https://example.test/bill",
    }


def detail(detail_id: str) -> dict[str, object]:
    return {
        "billDetailId": detail_id,
        "description": "VPS",
        "domain": "vps-1.ovh.net",
        "quantity": "1",
        "totalPrice": price(10.0),
        "unitPrice": price(10.0),
    }


class Routes:
    """Answers by path, after the server time the client reads first."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = {"/1.0/auth/time": EPOCH, **routes}
        self.requests: list[Request] = []

    def __call__(self, request: Request) -> Response:
        self.requests.append(request)
        path = request.url.path
        if path not in self.routes:
            return Response(404, json={"message": f"no {path}"})
        return Response(200, json=self.routes[path])

    def client(self, default_project: str | None = None) -> OVH:
        return OVH(
            application_key="key",
            application_secret="secret",
            consumer_key="consumer",
            default_project=default_project,
            transport=MockTransport(self),
            clock=lambda: NOW,
        )

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]


def test_a_reference_makes_no_request(ovh: OVH, recorder: Recorder) -> None:
    ref = ovh.billing.bills("FR1")

    assert isinstance(ref, BillRef)
    assert not isinstance(ref, Bill)
    assert "not loaded" in repr(ref)
    assert len(recorder.handlers) == 1


async def test_awaiting_a_reference_loads_the_object() -> None:
    routes = Routes({"/1.0/me/bill/FR1": bill("FR1")})

    loaded = await routes.client().billing.bills("FR1")

    assert isinstance(loaded, Bill)
    assert loaded.bill_id == "FR1"
    assert loaded.date == Instant.from_utc(2026, 10, 3, 8)
    assert loaded.price_without_tax.value == 10.0
    assert routes.paths()[-1] == "/1.0/me/bill/FR1"


async def test_iterating_a_list_of_identifiers_loads_each_object() -> None:
    routes = Routes(
        {
            "/1.0/me/bill": ["FR1", "FR2"],
            "/1.0/me/bill/FR1": bill("FR1"),
            "/1.0/me/bill/FR2": bill("FR2"),
        }
    )
    bills = routes.client().billing.bills.filter(date_from=Date(2026, 9, 30))

    loaded = [item async for item in bills]

    assert [item.bill_id for item in loaded] == ["FR1", "FR2"]
    assert all(isinstance(item, Bill) for item in loaded)
    listing = next(r for r in routes.requests if r.url.path == "/1.0/me/bill")
    assert listing.url.params["date.from"] == "2026-09-30"


async def test_a_sub_collection_lists_under_its_parent() -> None:
    routes = Routes(
        {
            "/1.0/me/bill/FR1/details": ["D1"],
            "/1.0/me/bill/FR1/details/D1": detail("D1"),
        }
    )

    lines = await routes.client().billing.bills("FR1").details.all()

    assert [line.bill_detail_id for line in lines] == ["D1"]
    assert isinstance(lines[0], BillDetail)


async def test_an_action_runs_without_loading() -> None:
    task = {
        "id": 1,
        "state": "todo",
        "type": "rebootVm",
        "date": "2026-11-05T10:00:00+01:00",
        "progress": 0,
    }
    routes = Routes({"/1.0/vps/vps-1/reboot": task})

    await routes.client().compute.vps("vps-1").reboot()

    request = routes.requests[-1]
    assert request.method == "POST"
    assert request.url.path == "/1.0/vps/vps-1/reboot"
    assert "X-Ovh-Signature" in request.headers


async def test_awaiting_the_account_area_reads_the_account() -> None:
    me = {
        "nichandle": "ab123-ovh",
        "email": "a@example.test",
        "country": "FR",
        "currency": {"code": "EUR", "symbol": "EURO"},
        "legalform": "corporation",
        "ovhCompany": "ovh",
        "ovhSubsidiary": "FR",
        "state": "complete",
    }
    routes = Routes({"/1.0/me": me})

    account = await routes.client().account

    assert account.nichandle == "ab123-ovh"


async def test_a_project_scoped_collection_uses_the_default_project() -> None:
    routes = Routes({"/1.0/cloud/project/p1/instance": []})

    assert await routes.client(default_project="p1").compute.instances.all() == []
    assert routes.paths()[-1] == "/1.0/cloud/project/p1/instance"


async def test_a_project_given_to_filter_wins() -> None:
    routes = Routes({"/1.0/cloud/project/p2/instance": []})
    client = routes.client(default_project="p1")

    await client.compute.instances.filter(project="p2").all()

    assert routes.paths()[-1] == "/1.0/cloud/project/p2/instance"


async def test_a_missing_project_is_refused() -> None:
    routes = Routes({})

    with pytest.raises(ValueError, match="default_project"):
        await routes.client().compute.instances.all()


async def test_a_missing_object_raises_the_api_error() -> None:
    routes = Routes({})

    with pytest.raises(ResourceNotFoundError):
        await routes.client().billing.bills("missing")


def test_with_options_shares_the_connections(ovh: OVH) -> None:
    other = ovh.with_options(default_project="p9")

    assert other.settings.default_project == "p9"
    assert other.raw.http_client is ovh.raw.http_client


def test_no_public_name_carries_an_api_version() -> None:
    package = Path(aioovh.__file__).parent
    versioned = re.compile(r"(V\d+|v\d+)(API|Api)?\b")
    for path in [*package.glob("*/__init__.py"), *package.glob("*/types.py")]:
        if path.parent.name.startswith("_"):
            continue
        exported = re.findall(r"^    '(\w+)',$", path.read_text(encoding="utf-8"), re.M)
        assert not [name for name in exported if versioned.search(name)], path


def test_every_operation_is_placed() -> None:
    coverage = (Path(__file__).parent.parent / "docs" / "coverage.md").read_text()
    rows = [
        line
        for line in coverage.splitlines()
        if line.startswith("| ") and "---" not in line
    ]

    assert len(rows) - 1 >= 7274
