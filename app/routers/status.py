from fastapi import APIRouter, Header

import requests

from app.core.auth import check_key
from app.core.config import get_settings

router = APIRouter(tags=["status"])

settings = get_settings()


@router.get("/status")
def status(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    auth_info = check_key(
        x_api_key=x_api_key,
        authorization=authorization,
    )

    checks = {
        "api": True,
        "auth_method": auth_info.get("auth_method"),
        "harvest_token_set": bool(settings.harvest_token),
        "harvest_account_id_set": bool(settings.harvest_account_id),
        "airtable_token_set": bool(settings.airtable_token),
        "airtable_base_id_set": bool(settings.airtable_base_id),
        "microsoft_tenant_id_set": bool(settings.ms_tenant_id),
        "microsoft_client_id_set": bool(settings.ms_client_id),
        "microsoft_allowed_group_id_set": bool(settings.ms_allowed_group_id),
    }

    harvest_ok = False
    airtable_ok = False

    try:
        response = requests.get(
            "https://api.harvestapp.com/v2/users/me",
            headers={
                "Authorization": f"Bearer {settings.harvest_token}",
                "Harvest-Account-ID": settings.harvest_account_id,
                "User-Agent": "DEG Sync API",
            },
        )
        harvest_ok = response.status_code == 200
    except Exception:
        harvest_ok = False

    try:
        response = requests.get(
            f"https://api.airtable.com/v0/{settings.airtable_base_id}/Clients",
            headers={
                "Authorization": f"Bearer {settings.airtable_token}",
                "Content-Type": "application/json",
            },
            params={"pageSize": 1},
        )
        airtable_ok = response.status_code == 200
    except Exception:
        airtable_ok = False

    checks["harvest_connection_ok"] = harvest_ok
    checks["airtable_connection_ok"] = airtable_ok

    overall_status = "ok" if all(
        value for key, value in checks.items() if key != "auth_method"
    ) else "warning"

    return {
        "status": overall_status,
        "checks": checks,
    }
