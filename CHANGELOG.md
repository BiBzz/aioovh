# Changelog

Notable changes to this project, newest first.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-05

First version published on PyPI.

### Added

- `OVH`, the client, read from the `OVH_*` variables of the official package,
  signing each request with the `$1$` signature and the server clock offset,
  or using OAuth2 client credentials; `with_options()` shares its connections.
- Business areas shared with aioscaleway: `compute`, `storage`, `backup`,
  `network`, `kubernetes`, `databases`, `analytics`, `ai`, `email`,
  `domains`, `web_hosting`, `observability`, `iam`, `account`, `billing`,
  `orders`, `telecom`, `licenses` and `virtualization`, covering the 70 APIs
  of version 1.0 and the 18 of v2.
- Collections iterated with `async for`, the 1.0 lists of identifiers loaded a
  few at a time, the v2 cursor pages followed, `filter()` and `ids()`;
  references that act without loading and load when awaited; loaded objects
  that are references too.
- Public Cloud resources scoped by project, with `default_project`.
- Typed errors under `OVHAPIError` with the query id, retries with `stamina`,
  dates as `whenever.Instant` and `whenever.Date`, open enumerations.
- `ovh.raw`, the underlying client, with the official package's raw calls.
- Type information shipped with the package (`py.typed`).

[Unreleased]: https://gitlab.com/businessagile/libraries/aioovh/-/compare/v0.1.0...development
[0.1.0]: https://gitlab.com/businessagile/libraries/aioovh/-/tags/v0.1.0
