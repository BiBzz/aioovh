# Architecture

## Layout

- `src/aioovh/_client.py`, `_settings.py`, `_endpoints.py`, `_errors.py`,
  `_models.py`, `_enums.py`: the hand-written runtime, shared by every API.
- `src/aioovh/v1/<api>/` and `src/aioovh/v2/<api>/`: generated, one package
  per schema, with `models.py`, `api.py` and an `__init__.py` re-exporting
  both. Never edited by hand: the first line of each file says so, and CI
  fails when they drift from `specs/`.
- `specs/v1/` and `specs/v2/`: the schemas as the API serves them, one file
  per API plus the `index.json` that lists them.
- `scripts/`: the generator, the schema refresh and the release helpers.

## Where the schemas come from

The OVHcloud API describes itself: `https://eu.api.ovh.com/1.0/` and
`https://eu.api.ovh.com/v2/` list every API, and `<root><path>.json` returns
its operations and models in the format the API console reads.
`scripts/fetch_specs.py` downloads all of them. Refreshing is a deliberate
step, reviewed in a merge request: the generated diff shows exactly what
OVHcloud changed. The schemas are those of the European endpoint; the
Canadian and American ones expose a subset, so a few methods answer 404 there.

## One module per schema

Each schema is self-contained: it carries every model its operations use,
including shared ones such as `order.Price`. The generator keeps that
boundary, so `aioovh.v1.me.OrderPrice` and `aioovh.v1.cloud.OrderPrice` are two
classes with the same fields. The alternative, one module per OVHcloud
namespace, creates import cycles between namespaces that only work with
module imports and late resolution, and makes importing `aioovh.v1.me` load
most of the 7,000 models.

Model class names join the namespace and the type (`billing.Bill` becomes
`BillingBill`) because the bare type names collide inside a schema
(`dedicated.server.Task` and `dedicated.Task`).

## Method names

The schemas have no operation identifiers, so names are derived from the path
relative to the API root and the HTTP method:

- `GET` on a path that returns a list and does not end with a parameter is
  `list_<segments>`, any other `GET` is `get_<segments>`;
- `POST` on a collection (a path whose `GET` returns a list) is
  `create_<segments>`, otherwise it is an action named after its segments
  (`reboot`, `bill_debt_pay`);
- `PUT`, `DELETE` and `PATCH` are `update_`, `delete_` and `patch_`.

The segments are the static parts of the path in snake case; the root
collection takes the last segment of the root (`list_server`). When two
operations still get the same name, each takes the names of its path
parameters as a suffix (`get_virtual_network_interface_by_uuid`). The
generator fails rather than emit a duplicate.

## Types

- OVHcloud's scalar types map to Python: `long` to `int`, `double` to
  `float`, `datetime` and `date` to the standard library types (the boundary
  with the API, where callers convert to `whenever` on their side), and the
  string-like types (`ip`, `ipBlock`, `password`, `uuid`, `phoneNumber`...) to
  `str`.
- Aliased types (`coreTypes.AccountId:string`) use their base type.
- Generic models (`complexType.UnitAndValue<T>`) are generic pydantic models,
  used as `ComplexTypeUnitAndValue[float]`.
- Enumerations of strings are open (`OpenStrEnum`): an unknown value becomes a
  pseudo member instead of a validation error. Enumerations of numbers are
  plain `int` aliases.
- A property is optional only when the schema says it can be null. The
  `required` flag of a property describes the creation request, not what the
  API returns, so it is ignored for responses.
- Field names that would shadow pydantic (`json`, `register`) or the date
  types (`date`, `datetime`, `time`) get a trailing underscore and an alias
  to the wire name: `bill.date_`.
- A query parameter whose type is an object (`iamTags`) is sent as JSON.

## Requests

Every request goes through `OVHClient.request`. The request is built first,
then signed on its exact URL, query string included, and body, so the
signature always matches what is sent. Each retry builds and signs again with
a new timestamp.

The clock offset with OVHcloud is read once from `/auth/time`, behind a lock,
and added to every timestamp, as the official package does. Operations the
schema marks `noAuthentication` are sent unsigned.

With `client_id` and `client_secret`, the client exchanges them for an OAuth2
token on the endpoint's token URL, keeps it until 30 seconds before it
expires, and sends it as a bearer token.

## Retries

`stamina` retries throttling and transient failures, waiting `Retry-After`
when given. Idempotent methods are retried on `429`, `502`, `503`, `504` and
transport errors. A `POST` is only retried when the request cannot have been
processed: `429`, `503`, or a connection that never opened.

## Dependencies

As a library, the package declares lower bounds rather than exact pins. The
development tools are pinned in `pyproject.toml` and every version is locked
in `uv.lock`, each released at least two weeks before it was adopted.
