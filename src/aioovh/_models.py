from pydantic import BaseModel, ConfigDict


class OVHModel(BaseModel):
    """Base of every generated model: unknown fields are kept, not rejected."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )
