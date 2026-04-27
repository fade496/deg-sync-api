from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.clients.airtable import get_airtable_records

router = APIRouter(prefix="/test", tags=["test"])


@router.get("/airtable")
def test_airtable(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

    records = get_airtable_records("Clients")

    return {
        "status_code": 200,
        "ok": True,
        "airtable_records_returned": len(records),
    }
