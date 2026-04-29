def generate_lem(payload):
    return {
        "status": "service_working",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "project_codes": payload.project_codes,
    }
