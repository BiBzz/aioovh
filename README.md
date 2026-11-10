# aioovh

Asynchronous, fully typed Python client for every
[OVHcloud API](https://eu.api.ovh.com/console/), versions 1.0 and v2, built on
[httpx2](https://pypi.org/project/httpx2/), [pydantic](https://docs.pydantic.dev/)
and [whenever](https://whenever.readthedocs.io/).

**Documentation**: https://aioovh.businessagile.eu

```python
from whenever import Date

from aioovh import OVH

async with OVH() as ovh:  # OVH_* from the environment
    async for bill in ovh.billing.bills.filter(date_from=Date(2026, 10, 1)):
        print(bill.bill_id, bill.date, bill.price_without_tax.value)
        async for line in bill.details:
            print("  ", line.description, line.total_price.value)

    await ovh.compute.vps("vps-1234.vps.ovh.net").reboot()
    account = await ovh.account
```

## Why it exists

The official [`ovh`](https://pypi.org/project/ovh/) package is synchronous and
untyped: `client.get("/me/bill/FR123")` blocks the event loop and returns a
`dict`, and the paths are the API's own (`/me`, `/cloud/project/{id}/...`).

`aioovh` is asynchronous down to the socket and organised around what you
manipulate:

- **business areas** shared with its sibling
  [aioscaleway](https://pypi.org/project/aioscaleway/): `compute`, `storage`,
  `network`, `billing`, `domains`, `email`, `telecom`...; `/me` disappears,
  its content goes where it belongs (`ovh.billing.bills`, `ovh.iam.ssh_keys`);
- **collections** you iterate with `async for` and narrow with `filter()`; the
  1.0 lists of identifiers are loaded for you, a few objects at a time, and the
  v2 cursor pages are followed;
- **references** that act without a request to read them first, and that
  `await` loads; **objects** that are references too, with typed fields;
- **no API version in any name**;
- the `$1$` request signature on the exact URL and body sent, with the clock
  offset read once from `/auth/time`, or an OAuth2 bearer token.

Everything is generated from the schemas the API serves, committed in
[`specs/`](specs/): 88 APIs and about 7,300 operations. Every operation is
reachable, through the objects or through `ovh.raw`, and
[`docs/coverage.md`](docs/coverage.md) says where.

## Installation

```bash
uv add aioovh
```

Python 3.12 or later.

## Usage

### Client

```python
ovh = OVH(
    endpoint="ovh-eu",
    application_key="...",
    application_secret="...",
    consumer_key="...",
    default_project="...",  # Public Cloud project used when none is given
)
```

Every value left out is read from the variables of the official package
(`OVH_ENDPOINT`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`,
`OVH_CONSUMER_KEY`, `OVH_CLIENT_ID`, `OVH_CLIENT_SECRET`), plus
`OVH_DEFAULT_PROJECT` and `OVH_MAX_CONCURRENCY` (objects loaded at once when a
list only returns identifiers, 8 by default).

### Collections, references, objects

| You write | You get | Requests |
| --- | --- | --- |
| `ovh.billing.bills` | a collection | none |
| `ovh.billing.bills.filter(date_from=Date(2026, 10, 1))` | the same collection, narrowed | none |
| `async for b in ovh.billing.bills` | loaded objects | the list, then one per object |
| `ovh.billing.bills(bill_id)` | a reference | none |
| `await ovh.billing.bills(bill_id)` | a loaded object | one |
| `await ovh.compute.vps(name).reboot()` | the action's result | one |
| `[i async for i in ovh.billing.bills.ids()]` | identifiers only | one |

A loaded object is also a reference. It cannot load itself when printed or
read, because those are synchronous; mypy flags a field read on a bare
reference.

Public Cloud resources take their project as a keyword, defaulting to
`default_project`:

```python
async for instance in ovh.compute.instances.filter(project=project_id):
    ...
```

### Names

Collections are named after what they hold (`bills`, `dedicated_servers`,
`ssh_keys`); under them, the OVHcloud segments in snake case
(`bill.details`, `server.service_infos()`). Actions are methods named after
their path (`reboot()`, `change_contact()`), updates `update_...`. The full
tree is in [docs/objects.md](docs/objects.md).

### Types and errors

Arguments and fields are typed; enumerations and nested models of an area live
in its `types` module. Dates are `whenever.Instant` and `whenever.Date`.
Enumerations are open.

```python
from aioovh import NotGrantedCallError, OVHAPIError, ResourceNotFoundError

try:
    await ovh.billing.bills("FR123")
except NotGrantedCallError:
    ...  # the consumer key lacks this route
except OVHAPIError as error:
    print(error.status_code, error.error_code, error.message, error.query_id)
```

### The raw layer

`ovh.raw` keeps the official package's untyped calls:

```python
await ovh.raw.get("/me/bill", **{"date.from": "2026-10-01"})
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/architecture.md](docs/architecture.md).

The source lives on [GitLab](https://gitlab.com/businessagile/libraries/aioovh),
mirrored to [GitHub](https://github.com/BiBzz/aioovh).

## Author

Created by [Alexandre BERREBI](https://businessagile.eu/en/about), maintained by
[Business Agile](https://businessagile.eu).

## License

MIT, see [LICENSE](LICENSE).
