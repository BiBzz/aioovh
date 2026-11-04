# aioovh

Asynchronous, fully typed Python client for every
[OVHcloud API](https://eu.api.ovh.com/console/), versions 1.0 and v2, built on
[httpx2](https://pypi.org/project/httpx2/) and
[pydantic](https://docs.pydantic.dev/).

It keeps what the official [`ovh`](https://pypi.org/project/ovh/) package
offers, endpoints, `OVH_*` variables, signed requests and raw
`get` / `post` / `put` / `delete` calls, and adds a typed method and pydantic
models for each of the 7,000-odd operations OVHcloud publishes:

```python
await client.get("/me/bill", **{"date.from": "2026-10-01"})  # raw, untyped
await MeV1API(client).list_bill(date_from=datetime(2026, 10, 1, tzinfo=UTC))  # typed
```

## Why it exists

The official package is synchronous: every call goes through `requests` and
blocks the event loop of an asynchronous application, and every answer is a
plain `dict`. `aioovh` is asynchronous down to the socket:

- one `httpx2.AsyncClient` per `OVHClient`, connections reused;
- the `$1$` request signature, computed on the exact URL and body sent, with
  the clock offset read once from `/auth/time`;
- OAuth2 client credentials as an alternative to application keys;
- every request and response typed, checked by `mypy --strict`;
- throttling and transient failures retried with
  [stamina](https://stamina.hynek.me/), each attempt freshly signed, a `POST`
  only when OVHcloud cannot have processed it;
- typed errors (`ResourceNotFoundError`, `NotGrantedCallError`...) that keep
  OVHcloud's message and query id;
- the v2 cursor pagination walked for you (`_iter`, `_all`).

The code is generated from the schemas the API serves itself, committed in
[`specs/`](specs/): 70 APIs in version 1.0 and 18 in v2.

## Installation

```bash
uv add aioovh
```

or:

```bash
pip install aioovh
```

Python 3.12 or later.

## Usage

```python
import asyncio
from datetime import UTC, datetime

from aioovh import OVHClient, OVHSettings
from aioovh.v1.me import MeV1API


async def main() -> None:
    settings = OVHSettings(
        endpoint="ovh-eu",
        application_key="...",
        application_secret="...",
        consumer_key="...",
    )
    async with OVHClient(settings) as client:
        me = MeV1API(client)
        for bill_id in await me.list_bill(date_from=datetime(2026, 10, 1, tzinfo=UTC)):
            bill = await me.get_bill(bill_id=bill_id)
            print(bill.bill_id, bill.date_, bill.price_without_tax.value)


asyncio.run(main())
```

### Modules and method names

One module per API, under the version it belongs to: `aioovh.v1.me`,
`aioovh.v1.dedicated_server`, `aioovh.v2.iam`. Each holds an API class
(`MeV1API`, `DedicatedServerV1API`, `IamV2API`) and the models of that API,
named after their OVHcloud type (`billing.Bill` is `BillingBill`).

Method names come from the path and the HTTP method:

| Call                                           | Method                                 |
| ---------------------------------------------- | -------------------------------------- |
| `GET /me/bill` (a list)                        | `list_bill()`                          |
| `GET /me/bill/{billId}`                        | `get_bill(bill_id=...)`                |
| `GET /me/bill/{billId}/details`                | `list_bill_details(bill_id=...)`       |
| `POST /dedicated/server/{serviceName}/reboot`  | `reboot(service_name=...)`             |
| `POST /me/billing/group` (create)              | `create_billing_group(...)`            |
| `PUT /me/billing/group/{groupId}`              | `update_billing_group(...)`            |
| `DELETE /me/billing/group/{groupId}`           | `delete_billing_group(...)`            |

Every argument is keyword-only and snake case: `date.from` is `date_from`,
`serviceName` is `service_name`. Each docstring starts with the HTTP call it
makes.

### Configuration

`OVHSettings` is a `pydantic-settings` object. Left empty, it reads the same
environment variables as the official package:

| Variable                 | Setting              |
| ------------------------ | -------------------- |
| `OVH_ENDPOINT`           | `endpoint`           |
| `OVH_APPLICATION_KEY`    | `application_key`    |
| `OVH_APPLICATION_SECRET` | `application_secret` |
| `OVH_CONSUMER_KEY`       | `consumer_key`       |
| `OVH_CLIENT_ID`          | `client_id`          |
| `OVH_CLIENT_SECRET`      | `client_secret`      |

The endpoint is one of `ovh-eu`, `ovh-ca`, `ovh-us`, `kimsufi-eu`,
`kimsufi-ca`, `soyoustart-eu` and `soyoustart-ca`, or a URL. With `client_id`
and `client_secret` set, requests carry an OAuth2 bearer token instead of a
signature. Timeouts and the retry policy are settings too.

### Pagination

The v2 API pages with a cursor header. Every operation that accepts one gets
two helpers:

```python
async for policy in iam.list_policy_iter():
    ...
policies = await iam.list_policy_all()
```

### Errors

```python
from aioovh import NotGrantedCallError, OVHAPIError, ResourceNotFoundError

try:
    await me.get_bill(bill_id="FR123")
except ResourceNotFoundError:
    ...
except NotGrantedCallError:
    ...  # the consumer key lacks this route
except OVHAPIError as error:
    print(error.status_code, error.error_code, error.message, error.query_id)
```

### Values added after generation

Enumerations are open: a value OVHcloud adds later is accepted and keeps its
text instead of failing the whole response. Fields unknown to the models are
kept in `model_extra`.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). The design choices are in
[docs/architecture.md](docs/architecture.md).

The source lives on [GitLab](https://gitlab.com/businessagile/libraries/aioovh),
mirrored to [GitHub](https://github.com/BiBzz/aioovh). A sibling package covers
Scaleway: [aioscaleway](https://pypi.org/project/aioscaleway/).

## License

MIT, see [LICENSE](LICENSE).
