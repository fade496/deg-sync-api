from fastapi import FastAPI

from app.routers import lem

app = FastAPI(title="DEG Sync API")


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


app.include_router(lem.router)
