from fastapi import FastAPI

app = FastAPI(title="DEG Sync API")

@app.get("/")
def root():
    return {"message": "minimal root app works"}
