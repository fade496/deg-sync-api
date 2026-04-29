import os
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/lem", tags=["LEM"])


# =============================================================================
# Airtable base
# =============================================================================

AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


def get_airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="AIRTABLE_API_KEY environment variable is missing",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# =============================================================================
# Airtable table IDs
# =============================================================================

TABLES = {
    "mapping": "tblRFhOeKAkRcYP7x",
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
    "contacts": "tblk1KQFBKDA1WPna",
    "lem": "tblwmiHITEK5PMV8y",
}


# =============================================================================
# Airtable field IDs
# =============================================================================

MAPPING_FIELDS = {
    "index": "fld5rHHw83cPrtkbz",
    "source": "fldcH6YdeFswjCvPH",
    "field": "fldilUgeHqft9Ywn4",
    "value": "fldZWVrO15lwHPrz3",
    "lem_field": "fldIHyjDybGLskiRv",
    "report_field": "fld7kZfhrLqa9tPgH",
}

TIME_ENTRY_FIELDS = {
    "name": "fldwt6DO7c2rs8ohA",
    "harvest_time_entry_id": "fldellt24tCiC4MRA",
    "project": "fldCIpUZ4uM60sxq1",
    "task": "fldMS1grGAfRBuqAo",
    "person": "fld5pP9ZJFtXXeVVF",
    "hours": "fldlJnV1ktFxwB8ot",
    "notes": "fldTxISXsRFkH3jui",
    "billable": "fldzkivctBgZVghaU",
    "approved": "fldIapQz7rsaQyehJ",
    "spent_date": "fldKOlADGAYQAmun6",
}

PROJECT_FIELDS = {
    "name": "fldYk2FrEDWF5NaTt",
    "harvest_project_id": "flddXsvMNyGyfe8LR",
    "billing_method": "fldboj721DBRTyADg",
    "invoice_type": "fld8Fuw1cmVHrRXnj",
    "billing_type": "fldntOZdWmdsCT93r",
    "hourly_rate": "fldvNpgsbnZkEix7C",
    "budget": "fldyQXvU5B4cE2eHv",
    "fee": "fldLvEoeOFyKmNtXJ",
    "notes": "fldEsHzETJNe08g9T",
    "approver": "fldsdMxj0Us8s4Zrc",
    "approver_email": "fld8KiMP071xCupTb",
    "client": "fldPXvbCxZfnSOeq7",
    "code": "fldnRbmshIalaBhvy",
    "short_code": "fldljc47eDNJshZBr",
    "is_active": "fldugVub7iAFljpdT",
    "is_billable": "fldMMyrZXvkkde0BW",
    "is_fixed_fee": "fldN2FhsxzzgTbjT0",
}

PEOPLE_FIELDS = {
    "full_name": "fld6vLeRhkaSZnVvk",
    "harvest_user_id": "fld6v4HWMr1aMGBxt",
    "first_name": "flducyo4L6GRQcrvS",
    "last_name": "fld6h2E8hMK2DbUwn",
    "email": "fldOYWMWABP786uYz",
    "craft1": "fldnp0XZra4SJBHAq",
    "craft1_desc": "fldzKHhnOiTIse28F",
    "craft1_801": "fldjaJRQyEbSYftgE",
    "craft2": "fldUJXvnq1KsSRuWY",
    "craft2_desc": "fld4uW6fLyIn35ooa",
    "craft2_801": "fld3IClT7nsFcYmiD",
    "craft3": "fldXSJ54o8sICOq9D",
    "craft3_desc": "fldhb7oafUiCIkuyd",
    "craft3_801": "fldaLmBJpw5OoNEBC",
}

TASK_FIELDS = {
    "name": "fldW7NAZWN7cHlopF",
    "harvest_task_id": "fld8Z4K9uwJBDoreO",
}

CONTACT_FIELDS = {
    "full_name": "fld4aVYKkIvdTWBnR",
    "first_name": "fldZvZCVY36aglzoV",
    "last_name": "fldHUQOTFlbjvTqgL",
    "email": "fldVHRyvxHTUaB6Vw",
}


# =============================================================================
# Models
# =============================================================================

class LemGenerateRequest(BaseModel):
    from_date: str
    to_date: str
    approved_only: bool = False
    billable_only: bool = False


# =============================================================================
# Airtable helpers
# =============================================================================

def airtable_list_records(
    table_id: str,
    *,
    field_ids: Optional[List[str]] = None,
    formula: Optional[str] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset: Optional[str] = None

    while True:
        params: Dict[str, Any] = {
            "pageSize": page_size,
        }

        if field_ids:
            params["fields[]"] = field_ids

        if formula:
            params["filterByFormula"] = formula

        if offset:
            params["offset"] = offset

        url = f"{AIRTABLE_API_ROOT}/{table_id}"

        response = requests.get(
            url,
            headers=get_airtable_headers(),
            params=params,
            timeout=60,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Airtable read failed",
                    "table_id": table_id,
                    "status_code": response.status_code,
                    "response": response.text,
                },
            )

        payload = response.json()
        records.extend(payload.get("records", []))

        offset = payload.get("offset")
        if not offset:
            break

    return records


def airtable_get_records_by_ids(
    table_id: str,
    record_ids: List[str],
    *,
    field_ids: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    if not record_ids:
        return {}

    output: Dict[str, Dict[str, Any]] = {}

    for i in range(0, len(record_ids), 20):
        chunk = record_ids[i:i + 20]

        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{record_id}'" for record_id in chunk]
        ) + ")"

        records = airtable_list_records(
            table_id,
            field_ids=field_ids,
            formula=formula,
        )

        for record in records:
            output[record["id"]] = record.get("fields", {})

    return output


# =============================================================================
# Mapping table
# =============================================================================

def fetch_mapping() -> List[Dict[str, Any]]:
    records = airtable_list_records(
        TABLES["mapping"],
        field_ids=list(MAPPING_FIELDS.values()),
    )

    mapping: List[Dict[str, Any]] = []

    for record in records:
        fields = record.get("fields", {})

        mapping.append({
            "record_id": record.get("id"),
            "index": fields.get(MAPPING_FIELDS["index"], 9999),
            "source": str(fields.get(MAPPING_FIELDS["source"], "")).strip(),
            "field": str(fields.get(MAPPING_FIELDS["field"], "")).strip(),
            "value": str(fields.get(MAPPING_FIELDS["value"], "")).strip(),
            "lem_field": str(fields.get(MAPPING_FIELDS["lem_field"], "")).strip(),
            "report_field": str(fields.get(MAPPING_FIELDS["report_field"], "")).strip(),
        })

    return sorted(mapping, key=lambda row: row["index"])


# =============================================================================
# Debug endpoints
# =============================================================================

@router.get("/debug/health")
def debug_health():
    return {
        "status": "ok",
        "airtable_base_id": AIRTABLE_BASE_ID,
        "airtable_api_key_present": bool(os.getenv("AIRTABLE_API_KEY")),
        "tables": TABLES,
    }


@router.get("/debug/mapping")
def debug_mapping():
    mapping = fetch_mapping()

    return {
        "count": len(mapping),
        "mapping": mapping,
    }


@router.get("/debug/fields")
def debug_fields():
    return {
        "mapping": MAPPING_FIELDS,
        "time_entries": TIME_ENTRY_FIELDS,
        "projects": PROJECT_FIELDS,
        "people": PEOPLE_FIELDS,
        "tasks": TASK_FIELDS,
        "contacts": CONTACT_FIELDS,
    }


# =============================================================================
# Temporary generate endpoint placeholder
# =============================================================================

@router.post("/generate")
def generate_lem(request: LemGenerateRequest):
    mapping = fetch_mapping()

    return {
        "status": "step_1_complete",
        "message": "Mapping table loaded successfully. Next step is to hydrate Time Entries, Projects, People, Tasks, and Approver records.",
        "from_date": request.from_date,
        "to_date": request.to_date,
        "mapping_count": len(mapping),
        "mapping": mapping,
    }
