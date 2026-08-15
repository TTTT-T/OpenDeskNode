"""Pydantic request contracts for the versioned HTTP API."""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, StrictStr, validator

from .repository import validate_device_id, validate_symbol


class APIModel(BaseModel):
    class Config:
        extra = "forbid"


class DeviceCreateRequest(APIModel):
    device_id: StrictStr
    name: StrictStr
    symbols: Optional[List[StrictStr]] = Field(default=None, min_items=4, max_items=4)

    @validator("device_id")
    def valid_device_id(cls, value: str) -> str:
        return validate_device_id(value)

    @validator("name")
    def valid_name(cls, value: str) -> str:
        text = value.strip()
        if not text or len(text) > 80:
            raise ValueError("name must be 1-80 characters")
        return text
    @validator("symbols")
    def valid_symbols(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [validate_symbol(symbol) for symbol in value]
        if len(set(normalized)) != 4:
            raise ValueError("symbols must contain four unique six-digit codes")
        return normalized


class DeviceUpdateRequest(APIModel):
    name: StrictStr

    @validator("name")
    def valid_name(cls, value: str) -> str:
        text = value.strip()
        if not text or len(text) > 80:
            raise ValueError("name must be 1-80 characters")
        return text


class WatchlistSaveRequest(APIModel):
    symbols: List[StrictStr] = Field(min_items=4, max_items=4)
    names: Optional[List[Optional[StrictStr]]] = Field(default=None, min_items=4, max_items=4)

    @validator("symbols")
    def valid_symbols(cls, value: List[str]) -> List[str]:
        normalized = [validate_symbol(symbol) for symbol in value]
        if len(set(normalized)) != 4:
            raise ValueError("symbols must contain four unique six-digit codes")
        return normalized

    @validator("names")
    def valid_names(cls, value: Optional[List[Optional[str]]]) -> Optional[List[Optional[str]]]:
        if value is None:
            return None
        return [
            item.strip() if item and item.strip() else None
            for item in value
        ]


class ReorderRequest(APIModel):
    slot_order: List[int] = Field(min_items=4, max_items=4)

    @validator("slot_order")
    def valid_slot_order(cls, value: List[int]) -> List[int]:
        if set(value) != {1, 2, 3, 4}:
            raise ValueError("slot_order must be a permutation of [1, 2, 3, 4]")
        return value


class SymbolResolveRequest(APIModel):
    symbol: StrictStr

    @validator("symbol")
    def valid_symbol(cls, value: str) -> str:
        return validate_symbol(value)


class SymbolConfirmRequest(APIModel):
    symbol: StrictStr
    name: StrictStr

    @validator("symbol")
    def valid_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @validator("name")
    def valid_name(cls, value: str) -> str:
        text = value.strip()
        if not text or len(text) > 80:
            raise ValueError("name must be 1-80 characters")
        return text
