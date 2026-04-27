from fastapi import FastAPI

from app.routers import oauth, status, query, sync, create, update

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
