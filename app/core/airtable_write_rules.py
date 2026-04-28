from fastapi import HTTPException


HARVEST_SYNCED_FIELDS = {
    "Clients": {
        "Name",
        "Harvest Client ID",
        "Is Active",
        "Address",
        "Currency",
    },
    "Contacts": {
        "Full Name",
        "First Name",
        "Last Name",
        "Email",
        "Phone",
        "Client",
        "Harvest Contact ID",
    },
    "Projects": {
        "Name",
        "Harvest Project ID",
        "Client",
        "Code",
        "Short Code",
        "Is Active",
        "Is Billable",
        "Is Fixed Fee",
        "Hourly Rate",
        "Budget",
        "Budget Is Monthly",
        "Fee",
        "Notes",
        "Billing Method",
    },
    "People": {
        "Full Name",
        "First Name",
        "Last Name",
        "Email",
        "Telephone",
        "Harvest User ID",
        "Is Active",
        "Is Contractor",
        "Default Hourly Rate",
        "Cost Rate",
    },
    "Tasks": {
        "Name",
        "Harvest Task ID",
        "Is Active",
        "Billable By Default",
        "Default Hourly Rate",
    },
    "Project People": {
        "Name",
        "Project",
        "Person",
        "Harvest Assignment ID",
        "Is Active",
        "Is Project Manager",
        "Use Default Rates",
        "Hourly Rate",
    },
    "Project Tasks": {
        "Name",
        "Project",
        "Task",
        "Harvest Task Assignment ID",
        "Is Active",
        "Billable",
        "Hourly Rate",
    },
    "Time Entries": {
        "Name",
        "Harvest Time Entry ID",
        "Project",
        "Task",
        "Person",
        "Hours",
        "Notes",
        "Billable",
        "Approved",
        "Spent Date",
    },
    "Invoices": {
        "Invoice Number",
        "Harvest Invoice ID",
        "Client",
        "Amount",
        "Due Amount",
        "Issue Date",
        "Due Date",
        "State",
    },
}


def get_harvest_synced_fields(table_name: str) -> set[str]:
    return HARVEST_SYNCED_FIELDS.get(table_name, set())


def validate_generic_write_fields(table_name: str, fields: dict):
    synced_fields = get_harvest_synced_fields(table_name)

    if not synced_fields:
        return

    requested_fields = set(fields.keys())
    blocked_fields = sorted(requested_fields.intersection(synced_fields))

    if blocked_fields:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "These fields are managed by Harvest sync and cannot be edited through generic Airtable writes.",
                "table": table_name,
                "blocked_fields": blocked_fields,
                "allowed_note": "Use the Harvest sync/create/update endpoints for Harvest-managed fields. Generic Airtable writes are only allowed for non-synced fields.",
            },
        )


def validate_generic_bulk_write_fields(table_name: str, records: list[dict]):
    synced_fields = get_harvest_synced_fields(table_name)

    if not synced_fields:
        return

    blocked_by_record = []

    for index, fields in enumerate(records):
        requested_fields = set(fields.keys())
        blocked_fields = sorted(requested_fields.intersection(synced_fields))

        if blocked_fields:
            blocked_by_record.append({
                "index": index,
                "blocked_fields": blocked_fields,
            })

    if blocked_by_record:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "One or more records include fields managed by Harvest sync.",
                "table": table_name,
                "blocked_records": blocked_by_record,
                "allowed_note": "Remove Harvest-managed fields before using generic Airtable bulk writes.",
            },
        )
