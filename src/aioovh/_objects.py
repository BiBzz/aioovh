import asyncio
from collections.abc import AsyncIterator, Callable, Generator, Iterable, Mapping
from copy import copy
from typing import Any, ClassVar, Self

from pydantic import BaseModel

from aioovh._client import OVHClient
from aioovh._models import OVHModel

type Key = dict[str, str | None]


class Session:
    """Shared by every collection, reference and object: the client and its APIs."""

    def __init__(self, client: OVHClient) -> None:
        self.client = client
        self._apis: dict[Callable[[OVHClient], Any], Any] = {}

    def api[Api](self, api_class: Callable[[OVHClient], Api]) -> Api:
        if api_class not in self._apis:
            self._apis[api_class] = api_class(self.client)
        api: Api = self._apis[api_class]
        return api


def required(key: Key, name: str) -> str:
    """A path parameter the key must hold."""
    value = key.get(name)
    if not value:
        raise ValueError(f"Missing {name} to build the request.")
    return value


def scoped(key: Key, name: str, default: str | None) -> str:
    """A scope such as the Public Cloud project: given, or the configured default."""
    value = key.get(name) or default
    if not value:
        raise ValueError(f"No {name} given and no default_{name} configured.")
    return value


async def load_each[Loaded](
    refs: Iterable["Ref[Loaded]"], concurrency: int
) -> AsyncIterator[Loaded]:
    """Load references a few at a time, in order, without leaving tasks behind."""
    batch: list[Ref[Loaded]] = []
    for ref in [*refs, None]:
        if ref is not None:
            batch.append(ref)
        if batch and (ref is None or len(batch) >= concurrency):
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(item._load()) for item in batch]
            for task in tasks:
                yield task.result()
            batch = []


def text(value: object) -> str | None:
    """A key part read from a model field: empty means unknown."""
    return None if value is None or value == "" else str(value)


def identifier(value: object) -> str:
    """Accept an identifier as a string, a reference or a loaded object."""
    if isinstance(value, Ref):
        return value._identifier()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected a non-empty identifier, got {value!r}.")
    return value


class Ref[Loaded]:
    """A resource known by its identifier: actions run on it, `await` loads it."""

    _session: Session
    _key: Key
    _id_name: ClassVar[str] = "id"

    @classmethod
    def _of(cls, session: Session, key: Key) -> Self:
        ref = cls.__new__(cls)
        ref._session = session
        ref._key = dict(key)
        return ref

    def _identifier(self) -> str:
        value = self._key.get(self._id_name)
        if not value:
            raise ValueError(f"{type(self).__name__} has no {self._id_name}.")
        return value

    async def _load(self) -> Loaded:
        raise NotImplementedError

    def __await__(self) -> Generator[Any, None, Loaded]:
        return self._load().__await__()

    async def refresh(self) -> Loaded:
        """Read the resource again."""
        return await self._load()

    def __repr__(self) -> str:
        key = ", ".join(
            f"{name}={value!r}" for name, value in self._key.items() if value
        )
        return f"<{type(self).__name__} {key} (not loaded)>"


def bind[Model: OVHModel](
    model_class: type[Model], session: Session, data: BaseModel, key: Key
) -> Model:
    """Turn an operations-layer model into a loaded object that can act."""
    loaded = model_class.model_validate(data, from_attributes=True)
    loaded._session = session
    loaded._key = key
    return loaded


class Collection[Item]:
    """Resources of one kind: iterate over them, narrow them with `filter`."""

    def __init__(
        self,
        session: Session,
        scope: Key | None = None,
        criteria: Mapping[str, Any] | None = None,
    ) -> None:
        self._session = session
        self._scope: Key = dict(scope or {})
        self._criteria: dict[str, Any] = dict(criteria or {})

    def _narrowed(self, **criteria: Any) -> Self:
        narrowed = copy(self)
        narrowed._criteria = {
            **self._criteria,
            **{name: value for name, value in criteria.items() if value is not None},
        }
        return narrowed

    def _items(self) -> AsyncIterator[Item]:
        raise NotImplementedError

    def __aiter__(self) -> AsyncIterator[Item]:
        return self._items()

    async def all(self) -> list[Item]:
        """Every item, all pages read, as a list."""
        return [item async for item in self]

    def __repr__(self) -> str:
        details = {**self._scope, **self._criteria}
        shown = ", ".join(
            f"{name}={value!r}" for name, value in details.items() if value
        )
        return (
            f"<{type(self).__name__} {shown}>" if shown else f"<{type(self).__name__}>"
        )


class Namespace:
    """A business area (`compute`, `billing`...) grouping collections."""

    def __init__(self, session: Session) -> None:
        self._session = session
