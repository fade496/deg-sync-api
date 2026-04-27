from app.clients.airtable import get_airtable_records


def build_client_map():
    client_map = {}

    for record in get_airtable_records("Clients"):
        fields = record.get("fields", {})
        harvest_client_id = fields.get("Harvest Client ID")

        if harvest_client_id is not None:
            client_map[str(harvest_client_id)] = record["id"]

    return client_map


def build_project_map(active_only: bool = False):
    project_map = {}

    for record in get_airtable_records("Projects"):
        fields = record.get("fields", {})

        if active_only and fields.get("Is Active") is not True:
            continue

        harvest_project_id = fields.get("Harvest Project ID")

        if harvest_project_id is not None:
            project_map[str(harvest_project_id)] = record["id"]

    return project_map


def build_people_map(active_only: bool = False):
    people_map = {}

    for record in get_airtable_records("People"):
        fields = record.get("fields", {})

        if active_only and fields.get("Is Active") is not True:
            continue

        harvest_user_id = fields.get("Harvest User ID")

        if harvest_user_id is not None:
            people_map[str(harvest_user_id)] = record["id"]

    return people_map


def build_task_map():
    task_map = {}

    for record in get_airtable_records("Tasks"):
        fields = record.get("fields", {})
        harvest_task_id = fields.get("Harvest Task ID")

        if harvest_task_id is not None:
            task_map[str(harvest_task_id)] = record["id"]

    return task_map
