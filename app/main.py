from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

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

app = FastAPI(
    title="DEG Sync API",
    swagger_ui_init_oauth={
        # Replace with your OAuth client ID
        "clientId": "YOUR_CLIENT_ID",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="DEG Sync API",
        version="1.0.0",
        description="DEG Sync API for Harvest, Airtable, LEM, and scheduler operations.",
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    # Replace these with your actual OAuth endpoints
                    "authorizationUrl": "YOUR_AUTHORIZATION_URL",
                    "tokenUrl": "YOUR_TOKEN_URL",
                    "scopes": {},
                }
            },
        }
    }

    # Apply OAuth globally in Swagger
    openapi_schema["security"] = [{"OAuth2": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


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
