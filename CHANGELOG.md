# Changelog

Notable changes to this project, newest first.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-04

First version published on PyPI.

### Added

- `OVHClient`, an asynchronous client on `httpx2` that signs each request
  with the `$1$` signature and the server clock offset, or authenticates with
  OAuth2 client credentials, and retries transient failures with `stamina`.
- `OVHSettings`, read from the `OVH_*` environment variables of the official
  package, and the same named endpoints.
- Raw `get`, `post`, `put`, `patch` and `delete` calls for any path.
- Typed errors: `ResourceNotFoundError`, `BadParametersError`,
  `NotGrantedCallError`, `InvalidCredentialError` and the rest, all under
  `OVHAPIError`, with the query id of the failed call.
- Generated API classes and pydantic models for the 70 APIs of version 1.0
  and the 18 of v2.
- `_iter` and `_all` variants for every v2 listing paged with a cursor.
- Open enumerations, which accept values added by OVHcloud after generation.
- Type information shipped with the package (`py.typed`).

[Unreleased]: https://gitlab.com/businessagile/libraries/aioovh/-/compare/v0.1.0...development
[0.1.0]: https://gitlab.com/businessagile/libraries/aioovh/-/tags/v0.1.0
