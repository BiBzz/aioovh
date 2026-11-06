# Features

## Async down to the socket

The official [`ovh`](https://pypi.org/project/ovh/) package is synchronous: each `client.get(...)` blocks the event loop of a FastAPI application or a task worker while it waits for OVHcloud, and returns a plain `dict`.

aioovh keeps one `httpx2.AsyncClient` per `OVH` object and awaits every request. It signs each one with the `$1$` signature on the exact URL and body sent, adding the clock offset it reads once from `/auth/time`, or sends an OAuth2 bearer token obtained with client credentials.

## Business objects, not paths

OVHcloud's paths follow its own history: bills under `/me/bill`, Public Cloud instances under `/cloud/project/{serviceName}/instance`, a newer v2 tree next to version 1.0. aioovh exposes what you manipulate instead:

| You write | You get | Requests |
| --- | --- | --- |
| `ovh.billing.bills` | a collection | none |
| `ovh.billing.bills.filter(date_from=Date(2026, 10, 1))` | the same collection, narrowed | none |
| `async for b in ovh.billing.bills` | loaded objects | the list, then one per object |
| `ovh.billing.bills(bill_id)` | a reference | none |
| `await ovh.billing.bills(bill_id)` | a loaded object | one |
| `await ovh.compute.vps(name).reboot()` | the action's result | one |
| `[i async for i in ovh.billing.bills.ids()]` | identifiers only | one |

A loaded object is a reference too. A reference does not load itself when printed or read, because those are synchronous; mypy flags a field read on a bare reference.

## Lists of identifiers, loaded for you

Most 1.0 lists return identifiers only. Iterating a collection loads each object, `max_concurrency` at a time (8 by default, `OVH_MAX_CONCURRENCY`), in a task group that ends before the next batch: no task outlives your `async for`. `ids()` skips the loading. The v2 lists return objects and page with a cursor, followed for you.

## Business areas

| Area | What it holds |
| --- | --- |
| `compute` | dedicated servers, VPS, Public Cloud instances, images and flavors |
| `storage`, `backup` | NAS-HA, Ceph, NetApp, Public Cloud volumes and object storage, Veeam |
| `network` | IP blocks, IP load balancers, vRack, OVHcloud Connect, CDN, Public Cloud networks |
| `kubernetes`, `databases`, `analytics`, `ai` | managed Kubernetes and registries, managed databases, analytics, AI notebooks and jobs |
| `email`, `domains`, `web_hosting` | email offers, domains and DNS zones, web hosting and CMS |
| `observability`, `iam` | Logs Data Platform, IAM policies, KMS, API applications and SSH keys |
| `account`, `billing`, `orders` | the account itself, bills, refunds, payments, services, carts and catalog |
| `telecom`, `licenses`, `virtualization` | telephony, SMS, xDSL, software licenses, VMware and Nutanix |

The full tree, with every collection and action, is on the [object tree](objects.md) page.

## Public Cloud, scoped by project

Public Cloud resources live in a project. Their collections take `project=` in `filter()` and in the call that builds a reference, and fall back to `default_project` (`OVH_DEFAULT_PROJECT`).

## Strongly typed, end to end

- Every argument, field and result is typed, and the package is checked with `mypy --strict` in CI.
- Responses are Pydantic models; dates are `whenever.Instant` and `whenever.Date`, and a date filter also takes a `Date`.
- Enumerations are open: a value OVHcloud adds later is accepted instead of failing the response.

## Reliable by default

Throttling and transient failures are retried with stamina, each attempt signed again; a `POST` is only retried when OVHcloud cannot have processed it. API errors are typed (`ResourceNotFoundError`, `NotGrantedCallError`, `InvalidCredentialError`...) and keep OVHcloud's message and query id.

## Complete

The code is generated from the schemas the API serves, committed in the repository: 70 APIs of version 1.0 and 18 of v2, about 7,300 operations. Every operation is reachable, through the objects or through `ovh.raw`, and the [coverage](coverage.md) page says where.
