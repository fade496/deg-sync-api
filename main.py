from fastapi import FastAPI
from app.routers.lem import router as lem_router

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

app.include_router(lem_router)
