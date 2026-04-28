from typing import Any, Optional
from pydantic import BaseModel, Field


class AirtableQueryRequest(BaseModel):
    table: str
    search: Optional[str] = None
    filter_formula: Optional[str] = None
    fields: Optional[list[str]] = None
    limit: int = 100


class AirtableAddRequest(BaseModel):
    table: str
    fields: dict[str, Any]


class AirtableUpdateRequest(BaseModel):
    table: str
    record_id: str
    fields: dict[str, Any]


class AirtableBulkAddRequest(BaseModel):
    table: str
    records: list[dict[str, Any]] = Field(..., min_length=1)


class AirtableBulkUpdateRecord(BaseModel):
    record_id: str
    fields: dict[str, Any]


class AirtableBulkUpdateRequest(BaseModel):
    table: str
    records: list[AirtableBulkUpdateRecord] = Field(..., min_length=1)


class AirtableBulkEditByFilterRequest(BaseModel):
    table: str
    filter_formula: str
    fields: dict[str, Any]
    limit: int = 100
