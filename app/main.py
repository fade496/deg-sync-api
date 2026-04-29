from fastapi import FastAPI
from app.routers import lem
from app.routers import (
    oauth,
    status,
    query,
    sync,
    create,
    update,
    test,
    airtable_generic,
    scheduler,
)

app = FastAPI(title="DEG Sync API")


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


app.include_router(oauth.router)
app.include_router(status.router)
app.include_router(query.router)
app.include_router(sync.router)
app.include_router(create.router)
app.include_router(update.router)
app.include_router(test.router)
app.include_router(airtable_generic.router)
app.include_router(scheduler.router)
app.include_router(lem.router)
