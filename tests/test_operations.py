import importlib
import inspect
from pathlib import Path

import pytest
from httpx2 import MockTransport
from pydantic import BaseModel
from whenever import Date, Instant

import aioovh
from aioovh._client import OVHClient
from aioovh._operations.v1.auth import AuthV1API
from aioovh._operations.v1.me import BillingBill, BillingCategoryEnum, MeV1API
from aioovh._operations.v2.iam import IamV2API
from tests.conftest import EPOCH, Recorder

PACKAGE = Path(aioovh.__file__).parent
GENERATED_PACKAGES = sorted(
    "aioovh." + ".".join(init.parent.relative_to(PACKAGE).parts)
    for init in PACKAGE.glob("_operations/v*/*/__init__.py")
)


def test_every_schema_is_generated() -> None:
    assert len(GENERATED_PACKAGES) >= 88


@pytest.mark.parametrize("package", GENERATED_PACKAGES)
def test_every_model_resolves_its_references(package: str) -> None:
    importlib.import_module(package)
    module = importlib.import_module(f"{package}.models")
    models = [
        value
        for value in vars(module).values()
        if inspect.isclass(value)
        and issubclass(value, BaseModel)
        and value.__module__ == module.__name__
    ]

    for model in models:
        assert model.model_rebuild(raise_errors=True) in (None, True)


BILL = {
    "billId": "FR123",
    "category": "autorenew",
    "date": "2026-10-03T10:00:00+02:00",
    "orderId": 42,
    "password": "p",
    "pdfUrl": "https://example.test/bill.pdf",
    "priceWithTax": {"currencyCode": "EUR", "text": "12.00 €", "value": 12.0},
    "priceWithoutTax": {"currencyCode": "EUR", "text": "10.00 €", "value": 10.0},
    "tax": {"currencyCode": "EUR", "text": "2.00 €", "value": 2.0},
    "url": "https://example.test/bill",
}


async def test_a_listing_maps_its_filters(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=["FR123", "FR124"])

    bills = await MeV1API(client).list_bill(
        date_from=Instant.from_utc(2026, 9, 30),
        category=BillingCategoryEnum.AUTORENEW,
    )

    assert bills == ["FR123", "FR124"]
    params = recorder.requests[-1].url.params
    assert recorder.requests[-1].url.path == "/1.0/me/bill"
    assert params["date.from"] == "2026-09-30T00:00:00Z"
    assert params["category"] == "autorenew"
    assert "date.to" not in params


async def test_a_date_filter_accepts_a_plain_date(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=[])

    await MeV1API(client).list_bill(date_from=Date(2026, 8, 31))

    assert recorder.requests[-1].url.params["date.from"] == "2026-08-31"


async def test_a_model_is_parsed_from_its_wire_names(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=BILL)

    bill = await MeV1API(client).get_bill(bill_id="FR123")

    assert isinstance(bill, BillingBill)
    assert bill.bill_id == "FR123"
    assert bill.date == Instant.from_utc(2026, 10, 3, 8)
    assert bill.price_without_tax.value == 10.0
    assert recorder.requests[-1].url.path == "/1.0/me/bill/FR123"


async def test_an_unknown_enum_value_does_not_fail_the_response(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body={**BILL, "category": "brand-new"})

    bill = await MeV1API(client).get_bill(bill_id="FR123")

    assert bill.category == "brand-new"


async def test_an_unauthenticated_operation_is_not_signed(recorder: Recorder) -> None:
    recorder.reply(body=EPOCH)
    client = OVHClient(transport=MockTransport(recorder))

    assert await AuthV1API(client).get_time() == EPOCH
    assert "X-Ovh-Signature" not in recorder.requests[0].headers


async def test_v2_listings_follow_the_cursor(
    client: OVHClient, recorder: Recorder
) -> None:
    recorder.reply(body=["a", "b"], headers={"X-Pagination-Cursor-Next": "next"})
    recorder.reply(body=["c"])

    kinds = await IamV2API(client).list_log_kind_all(x_pagination_size=2)

    assert kinds == ["a", "b", "c"]
    first, second = recorder.requests[1:]
    assert first.url.path == "/v2/iam/log/kind"
    assert "X-Pagination-Cursor" not in first.headers
    assert first.headers["X-Pagination-Size"] == "2"
    assert second.headers["X-Pagination-Cursor"] == "next"
