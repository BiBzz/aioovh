---
description: "Asynchronous, fully typed Python client for every OVHcloud API, organised by business area, with collections you iterate with async for and references you await."
---

<style>
.md-content .md-typeset h1 { display: none; }
</style>

# aioovh

<p align="center">
  <a href="https://aioovh.businessagile.eu"><img src="img/logo.svg" alt="aioovh" width="360"></a>
</p>
<p align="center">
    <em>aioovh, every OVHcloud API in Python, fully async and strongly typed.</em>
</p>
<p align="center">
<a href="https://gitlab.com/businessagile/libraries/aioovh/-/blob/development/LICENSE" target="_blank"><img src="img/badges/license.svg" alt="License: MIT"></a>
<img src="img/badges/status.svg" alt="Status: beta">
<img src="img/badges/python.svg" alt="Python 3.12+">
</p>

---

**Documentation**: <a href="https://aioovh.businessagile.eu" target="_blank">https://aioovh.businessagile.eu</a>

**Source Code**: <a href="https://gitlab.com/businessagile/libraries/aioovh" target="_blank">https://gitlab.com/businessagile/libraries/aioovh</a>

**Issues and pull requests**: <a href="https://github.com/BiBzz/aioovh" target="_blank">github.com/BiBzz/aioovh</a>

**Created by**: <a href="https://businessagile.eu/en/about" target="_blank">Alexandre BERREBI</a>, maintained by <a href="https://businessagile.eu" target="_blank">Business Agile</a>

---

aioovh is a client for the **OVHcloud APIs**, versions 1.0 and v2, organised around what you manipulate (bills, servers, domains, Public Cloud instances) rather than the API's paths. It is **async from end to end**, **strongly typed**, and covers **every published API**, not only the popular ones.

**aioovh** is based on Python type annotations, and powered by <a href="https://docs.pydantic.dev" target="_blank">Pydantic</a>, <a href="https://pypi.org/project/httpx2/" target="_blank">httpx2</a>, <a href="https://whenever.readthedocs.io" target="_blank">whenever</a> and <a href="https://stamina.hynek.me" target="_blank">stamina</a>.

The key features are:

* **Async first**: the official `ovh` package is synchronous and blocks the event loop; aioovh awaits every request on one HTTP client.
* **Business areas**: `compute`, `billing`, `domains`, `email`, `telecom`... the same areas as its sibling <a href="https://aioscaleway.businessagile.eu" target="_blank">aioscaleway</a>. `/me` disappears: bills are in `billing`, SSH keys in `iam`.
* **References and objects**: `ovh.billing.bills(bill_id)` acts without reading the bill first, `await` loads it, and a loaded bill is still a reference.
* **Collections**: `async for` loads the objects behind a list of identifiers, a few at a time, or follows the v2 cursor; `filter()` narrows, `ids()` skips the loading.
* **Signed for you**: the `$1$` signature on the exact URL and body sent, the clock offset read once, or OAuth2 client credentials.
* **No API version in any name**, and Public Cloud resources scoped by project, with a default.
* **Complete**: generated from the schemas the API serves, 88 APIs and about 7,300 operations, each reachable.

## Requirements

A recent and currently supported <a href="https://www.python.org/downloads/" target="_blank">version of Python</a>: 3.12 or later.

OVHcloud API credentials, an application key, secret and consumer key, or OAuth2 client credentials, given as arguments or read from the `OVH_*` variables of the official package.

## Installation

```console
$ pip install aioovh
---> 100%
Successfully installed aioovh httpx2 pydantic pydantic-settings stamina whenever
```

## Example

### Connect

```python
from aioovh import OVH

ovh = OVH(
    endpoint="ovh-eu",
    application_key="...",
    application_secret="...",
    consumer_key="...",
    default_project="...",
)
```

Every value left out is read from `OVH_ENDPOINT`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY` and the other variables of the official package.

### Bills and their lines

```python hl_lines="4  6"
from whenever import Date

async with ovh:
    async for bill in ovh.billing.bills.filter(date_from=Date(2026, 10, 1)):
        print(bill.bill_id, bill.date, bill.price_without_tax.value)
        async for line in bill.details:
            print("  ", line.description, line.total_price.value)
```

The 1.0 API lists bills as identifiers; iterating the collection loads each bill, a few at a time.

### Act without loading

```python
await ovh.compute.vps("vps-1234.vps.ovh.net").reboot()
account = await ovh.account
```

### Public Cloud

```python
async for instance in ovh.compute.instances.filter(project=project_id):
    print(instance.name, instance.status)
```

Without `project`, the client's `default_project` is used.

### Editor support everywhere

Arguments, fields and results are typed, and checked with `mypy --strict`. Dates are `whenever.Instant` and `whenever.Date`, enumerations are open so that a value OVHcloud adds later does not break your code.

## License

This project is licensed under the terms of the [MIT license](https://gitlab.com/businessagile/libraries/aioovh/-/blob/development/LICENSE).
