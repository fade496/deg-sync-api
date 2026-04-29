from fastapi import FastAPI
from app.routers import lem

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

app.include_router(lem.router)
