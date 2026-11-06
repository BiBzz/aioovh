# Design and roadmap

aioovh is developed in the open. This page states what it aims at, what it leaves out, and what comes next. Discussion happens in the [GitLab issues](https://gitlab.com/businessagile/libraries/aioovh/-/issues).

## Principles

1. **Async only.** No synchronous twin of the API: one way to do each thing.
2. **Objects, not paths.** The public surface follows what you manipulate; `/me`, `/cloud/project` and API versions are details of the routing.
3. **Types first.** If the type checker cannot follow it, it is not the API.
4. **Everything reachable.** Every operation OVHcloud publishes is either an object method or explicitly left to the raw layer.
5. **Generated, then reviewed.** The code is generated from the schemas the API serves; `mapping.yaml` places every API root in a business area, and the generator stops on a root it does not know or on a name clash.

## Two layers

- **Operations** (`aioovh._operations`), private: one typed method per operation of each schema.
- **Objects** (`aioovh.billing`, `aioovh.compute`...), public: business areas, collections, references and loaded objects, generated from the operations and `mapping.yaml`.

The [architecture](architecture.md) page details the mapping and how operations become objects.

## Non goals

- A synchronous client.
- Deprecated operations in the object layer: they stay reachable through `ovh.raw`.
- Hiding the API: `ovh.raw` keeps the official package's `get`, `post`, `put` and `delete` on any path.

## Roadmap

| Step | Content |
| --- | --- |
| 0.1 | Every API as objects, collections, references, actions, bounded loading, typed errors, retries |
| 0.2 | `wait_until(...)` on tasks and services with a life cycle |
| 0.3 | References from fields that name another resource, plural names reviewed area by area |
| 0.4 | Documentation examples executed by the test suite, recipes for FastAPI and task workers |
| later | A shared core with aioscaleway, then other European providers |

## Prior art

aioovh stands on what others built: the [official OVHcloud package](https://github.com/ovh/python-ovh) for the signature, the endpoints and the error names, the [Stainless](https://www.stainless.com) generated SDKs for the resource tree, [hcloud-python](https://github.com/hetznercloud/hcloud-python) for bound objects, and the [Azure SDK design guidelines](https://azure.github.io/azure-sdk/python_design.html) for versions and paging.
