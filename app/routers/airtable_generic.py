from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.models.airtable_requests import (
    AirtableQueryRequest,
    AirtableAddRequest,
    AirtableUpdateRequest,
    AirtableBulkAddRequest,
    AirtableBulkUpdateRequest,
    AirtableBulkEditByFilterRequest,
)
from app.services.airtable_generic import (
    list_airtable_tables,
    query_airtable,
    add_airtable_record,
    update_airtable_generic_record,
    bulk_add_airtable_records,
    bulk_update_airtable_records,
    bulk_edit_airtable_by_filter,
)

router = APIRouter(prefix="/airtable", tags=["airtable"])


@router.get("/tables")
def get_tables(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return list_airtable_tables()


@router.post("/query")
def query_table(
    payload: AirtableQueryRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return query_airtable(payload)


@router.post("/add")
def add_record(
    payload: AirtableAddRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return add_airtable_record(payload)


@router.patch("/update")
def update_record(
    payload: AirtableUpdateRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return update_airtable_generic_record(payload)


@router.post("/bulk-add")
def bulk_add(
    payload: AirtableBulkAddRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return bulk_add_airtable_records(payload)


@router.patch("/bulk-update")
def bulk_update(
    payload: AirtableBulkUpdateRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return bulk_update_airtable_records(payload)


@router.patch("/bulk-edit-by-filter")
def bulk_edit_by_filter(
    payload: AirtableBulkEditByFilterRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return bulk_edit_airtable_by_filter(payload)
