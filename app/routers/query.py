from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.clients.airtable import get_airtable_records
from app.models.requests import QueryRequest

router = APIRouter(tags=["query"])


@router.post("/query")
def query(
    payload: QueryRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    #check_key(x_api_key=x_api_key, authorization=authorization)

    records = get_airtable_records(payload.table)

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
        "count": len(results),
        "results": results,
    }
