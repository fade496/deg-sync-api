def generate_lem(payload):
    return {
        "status": "ok",
        "message": "LEM service imported successfully",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
    }
