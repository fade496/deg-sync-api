from fastapi import FastAPI

app = FastAPI(title="DEG Sync API")

@app.get("/")
def root():
    return {"status": "ok", "message": "minimal app running"}
