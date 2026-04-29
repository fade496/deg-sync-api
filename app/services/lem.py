import os
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


TABLES = {
    "mapping": "tblRFhOeKAkRcYP7x",
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
}


def airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing AIRTABLE_API_KEY",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


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
        params: Dict[str, Any] = {"pageSize": page_size}

        if field_ids:
            params["fields[]"] = field_ids

        if formula:
            params["filterByFormula"] = formula

        if offset:
            params["offset"] = offset

        response = requests.get(
            f"{AIRTABLE_API_ROOT}/{table_id}",
            headers=airtable_headers(),
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

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")
        if not offset:
            break

    return records


def airtable_get_by_ids(
    table_id: str,
    ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not ids:
        return {}

    records_map: Dict[str, Dict[str, Any]] = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]

        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{record_id}'" for record_id in chunk]
        ) + ")"

        records = airtable_list_records(
            table_id,
            formula=formula,
        )

        for record in records:
            records_map[record["id"]] = record.get("fields", {})

    return records_map


def first_link(value: Any) -> Optional[str]:
    if isinstance(value, list) and value:
        return value[0]
    return None


def load_mapping() -> List[Dict[str, Any]]:
    records = airtable_list_records(TABLES["mapping"])

    mapping: List[Dict[str, Any]] = []

    for record in records:
        fields = record.get("fields", {})

        mapping.append({
            "record_id": record.get("id"),
            "index": fields.get("Index", 9999),
            "source": fields.get("Source", ""),
            "field": fields.get("Field", ""),
            "value": fields.get("Value", ""),
            "lem_field": fields.get("LEM Field", ""),
            "report_field": fields.get("Report Field", ""),
        })

    return sorted(mapping, key=lambda row: row["index"])


def load_time_entries(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    formula = (
        "AND("
        f"IS_AFTER({{Spent Date}}, DATEADD('{from_date}', -1, 'days')), "
        f"IS_BEFORE({{Spent Date}}, DATEADD('{to_date}', 1, 'days'))"
        ")"
    )

    return airtable_list_records(
        TABLES["time_entries"],
        formula=formula,
    )


def hydrate_records(
    time_entries: List[Dict[str, Any]],
) -> tuple[
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
]:
    project_ids = set()
    person_ids = set()
    task_ids = set()

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))
        task_id = first_link(fields.get("Task"))

        if project_id:
            project_ids.add(project_id)

        if person_id:
            person_ids.add(person_id)

        if task_id:
            task_ids.add(task_id)

    projects = airtable_get_by_ids(TABLES["projects"], list(project_ids))
    people = airtable_get_by_ids(TABLES["people"], list(person_ids))
    tasks = airtable_get_by_ids(TABLES["tasks"], list(task_ids))

    return projects, people, tasks


def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries(payload.from_date, payload.to_date)

    projects, people, tasks = hydrate_records(time_entries)

    return {
        "status": "date_filtered_hydration_complete",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "mapping_count": len(mapping),
        "time_entries_count": len(time_entries),
        "projects_count": len(projects),
        "people_count": len(people),
        "tasks_count": len(tasks),
        "sample_time_entry": time_entries[:1],
        "sample_project": list(projects.values())[:1],
        "sample_person": list(people.values())[:1],
        "sample_task": list(tasks.values())[:1],
    }
