from typing import Any, Optional

from pydantic import BaseModel, Field


class AirtableFieldValue(BaseModel):
    name: str
    value: Any


class AirtableQueryRequest(BaseModel):
    table: str
    search: Optional[str] = None
    filter_formula: Optional[str] = None
    fields: Optional[list[str]] = None
    limit: int = 100


class AirtableAddRequest(BaseModel):
    table: str
    fields: list[AirtableFieldValue] = Field(..., min_length=1)


class AirtableUpdateRequest(BaseModel):
    table: str
    record_id: str
    fields: list[AirtableFieldValue] = Field(..., min_length=1)


class AirtableBulkAddRecord(BaseModel):
    fields: list[AirtableFieldValue] = Field(..., min_length=1)


class AirtableBulkAddRequest(BaseModel):
    table: str
    records: list[AirtableBulkAddRecord] = Field(..., min_length=1)


class AirtableBulkUpdateRecord(BaseModel):
    record_id: str
    fields: list[AirtableFieldValue] = Field(..., min_length=1)


class AirtableBulkUpdateRequest(BaseModel):
    table: str
    records: list[AirtableBulkUpdateRecord] = Field(..., min_length=1)


class AirtableBulkEditByFilterRequest(BaseModel):
    table: str
    filter_formula: str
    fields: list[AirtableFieldValue] = Field(..., min_length=1)
    limit: int = 100
