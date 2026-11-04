from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr


class OVHModel(BaseModel):
    """Base of every generated model: unknown fields are kept, not rejected."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    _session: Any = PrivateAttr(default=None)
    _key: dict[str, str | None] = PrivateAttr(default_factory=dict)
