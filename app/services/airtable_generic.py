import requests
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.airtable_write_rules import (
    validate_generic_write_fields,
    validate_generic_bulk_write_fields,
)
from app.clients.airtable import (
    airtable_headers,
    airtable_url,
    get_airtable_records,
    create_airtable_record,
    update_airtable_record,
)
from app.models.airtable_requests import (
    AirtableQueryRequest,
    AirtableAddRequest,
    AirtableUpdateRequest,
    AirtableBulkAddRequest,
    AirtableBulkUpdateRequest,
    AirtableBulkEditByFilterRequest,
)


def field_values_to_dict(field_values):
    return {
        field.name: field.value
        for field in field_values
    }


def bulk_add_records_to_field_dicts(records):
    return [
        field_values_to_dict(record.fields)
        for record in records
    ]


def bulk_update_records_to_field_dicts(records):
    return [
        field_values_to_dict(record.fields)
        for record in records
    ]


def list_airtable_tables():
    settings = get_settings()

    url = f"https://api.airtable.com/v0/meta/bases/{settings.airtable_base_id}/tables"

    response = requests.get(
        url,
        headers=airtable_headers(),
        timeout=30,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    data = response.json()

    tables = []

    for table in data.get("tables", []):
        tables.append({
            "id": table.get("id"),
            "name": table.get("name"),
            "primary_field_id": table.get("primaryFieldId"),
            "fields": [
                {
                    "id": field.get("id"),
                    "name": field.get("name"),
                    "type": field.get("type"),
                }
                for field in table.get("fields", [])
            ],
        })

    return {
        "base_id": settings.airtable_base_id,
        "count": len(tables),
        "tables": tables,
    }


def validate_table_exists(table_name: str):
    tables_result = list_airtable_tables()
    valid_names = {table["name"] for table in tables_result["tables"]}

    if table_name not in valid_names:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid Airtable table name.",
                "table": table_name,
                "available_tables": sorted(valid_names),
            },
        )


def query_airtable(payload: AirtableQueryRequest):
    validate_table_exists(payload.table)

    params = {
        "pageSize": min(payload.limit, 100),
    }

    if payload.filter_formula:
        params["filterByFormula"] = payload.filter_formula

    if payload.fields:
        params["fields[]"] = payload.fields

    records = get_airtable_records(payload.table, params=params)

    results = []

    for record in records:
        fields = record.get("fields", {})

        if payload.search:
            if payload.search.lower() not in str(fields).lower():
                continue

        results.append({
            "id": record["id"],
            "fields": fields,
        })

        if len(results) >= payload.limit:
            break

    return {
        "table": payload.table,
        "count": len(results),
        "results": results,
    }


def add_airtable_record(payload: AirtableAddRequest):
    validate_table_exists(payload.table)

    fields = field_values_to_dict(payload.fields)

    validate_generic_write_fields(payload.table, fields)

    response = create_airtable_record(payload.table, fields)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return {
        "status": "created",
        "table": payload.table,
        "record": response.json(),
    }


def update_airtable_generic_record(payload: AirtableUpdateRequest):
    validate_table_exists(payload.table)

    fields = field_values_to_dict(payload.fields)

    validate_generic_write_fields(payload.table, fields)

    response = update_airtable_record(
        payload.table,
        payload.record_id,
        fields,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return {
        "status": "updated",
        "table": payload.table,
        "record_id": payload.record_id,
        "record": response.json(),
    }


def bulk_add_airtable_records(payload: AirtableBulkAddRequest):
    validate_table_exists(payload.table)

    records_as_fields = bulk_add_records_to_field_dicts(payload.records)

    validate_generic_bulk_write_fields(payload.table, records_as_fields)

    created = []
    failed = []

    batches = [
        records_as_fields[i:i + 10]
        for i in range(0, len(records_as_fields), 10)
    ]

    for batch in batches:
        url = airtable_url(payload.table)

        airtable_records = [
            {"fields": fields}
            for fields in batch
        ]

        response = requests.post(
            url,
            headers=airtable_headers(),
            json={"records": airtable_records},
            timeout=30,
        )

        if response.status_code in [200, 201]:
            created.extend(response.json().get("records", []))
        else:
            failed.append({
                "batch": batch,
                "status_code": response.status_code,
                "response": response.text,
            })

    return {
        "status": "completed" if not failed else "partial",
        "table": payload.table,
        "requested": len(records_as_fields),
        "created": len(created),
        "failed": len(failed),
        "created_records": created,
        "failed_batches": failed,
    }


def bulk_update_airtable_records(payload: AirtableBulkUpdateRequest):
    validate_table_exists(payload.table)

    records_as_fields = bulk_update_records_to_field_dicts(payload.records)

    validate_generic_bulk_write_fields(payload.table, records_as_fields)

    updated = []
    failed = []

    batches = [
        payload.records[i:i + 10]
        for i in range(0, len(payload.records), 10)
    ]

    for batch in batches:
        url = airtable_url(payload.table)

        airtable_records = [
            {
                "id": record.record_id,
                "fields": field_values_to_dict(record.fields),
            }
            for record in batch
        ]

        response = requests.patch(
            url,
            headers=airtable_headers(),
            json={"records": airtable_records},
            timeout=30,
        )

        if response.status_code in [200, 201]:
            updated.extend(response.json().get("records", []))
        else:
            failed.append({
                "batch": [
                    {
                        "record_id": record.record_id,
                        "fields": field_values_to_dict(record.fields),
                    }
                    for record in batch
                ],
                "status_code": response.status_code,
                "response": response.text,
            })

    return {
        "status": "completed" if not failed else "partial",
        "table": payload.table,
        "requested": len(payload.records),
        "updated": len(updated),
        "failed": len(failed),
        "updated_records": updated,
        "failed_batches": failed,
    }


def bulk_edit_airtable_by_filter(payload: AirtableBulkEditByFilterRequest):
    validate_table_exists(payload.table)

    fields = field_values_to_dict(payload.fields)

    validate_generic_write_fields(payload.table, fields)

    query_payload = AirtableQueryRequest(
        table=payload.table,
        filter_formula=payload.filter_formula,
        limit=payload.limit,
    )

    query_result = query_airtable(query_payload)

    records_to_update = [
        {
            "record_id": record["id"],
            "fields": payload.fields,
        }
        for record in query_result["results"]
    ]

    if not records_to_update:
        return {
            "status": "no_matching_records",
            "table": payload.table,
            "matched": 0,
            "updated": 0,
        }

    update_payload = AirtableBulkUpdateRequest(
        table=payload.table,
        records=records_to_update,
    )

    update_result = bulk_update_airtable_records(update_payload)

    return {
        "status": update_result["status"],
        "table": payload.table,
        "matched": len(records_to_update),
        "updated": update_result["updated"],
        "failed": update_result["failed"],
        "updated_records": update_result["updated_records"],
        "failed_batches": update_result["failed_batches"],
    }
