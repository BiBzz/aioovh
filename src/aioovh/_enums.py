from enum import StrEnum
from typing import Self


class OpenStrEnum(StrEnum):
    """A string enum that accepts values added to the API after generation."""

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = value.upper()
        member._value_ = value
        return member
