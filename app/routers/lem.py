from fastapi import APIRouter

router = APIRouter(prefix="/lem", tags=["lem"])


@router.get("/ping")
def ping_lem():
    return {"lem": "ok"}
