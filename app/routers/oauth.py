from typing import Optional
from urllib.parse import urlencode, parse_qs

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.config import get_settings

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/authorize")
def oauth_authorize(
    response_type: str = Query("code"),
    client_id: Optional[str] = Query(None),
    redirect_uri: str = Query(...),
    scope: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    settings = get_settings()

    if response_type != "code":
        raise HTTPException(
            status_code=400,
            detail="Only authorization code flow is supported.",
        )

    if not settings.ms_tenant_id:
        raise HTTPException(status_code=500, detail="MS_TENANT_ID is not set")

    azure_client_id = settings.ms_client_id or client_id

    if not azure_client_id:
        raise HTTPException(status_code=500, detail="MS_CLIENT_ID is not set")

    requested_scope = scope or f"api://{azure_client_id}/access_as_admin"

    params = {
        "client_id": azure_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": requested_scope,
    }

    if state:
        params["state"] = state

    microsoft_auth_url = (
        f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/authorize"
        f"?{urlencode(params)}"
    )

    return RedirectResponse(microsoft_auth_url)


@router.post("/token")
async def oauth_token(request: Request):
    settings = get_settings()

    body = await request.body()
    form = parse_qs(body.decode())

    def first(name, default=None):
        values = form.get(name)
        if not values:
            return default
        return values[0]

    code = first("code")
    redirect_uri = first("redirect_uri")
    grant_type = first("grant_type", "authorization_code")

    incoming_client_id = first("client_id")
    incoming_client_secret = first("client_secret")

    azure_client_id = settings.ms_client_id or incoming_client_id
    azure_client_secret = settings.ms_client_secret or incoming_client_secret

    if grant_type != "authorization_code":
        raise HTTPException(
            status_code=400,
            detail="Only authorization_code grant_type is supported.",
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not redirect_uri:
        raise HTTPException(status_code=400, detail="Missing redirect_uri")

    if not settings.ms_tenant_id:
        raise HTTPException(status_code=500, detail="MS_TENANT_ID is not set")

    if not azure_client_id:
        raise HTTPException(status_code=500, detail="MS_CLIENT_ID is not set")

    if not azure_client_secret:
        raise HTTPException(status_code=500, detail="MS_CLIENT_SECRET is not set")

    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token"

    data = {
        "client_id": azure_client_id,
        "client_secret": azure_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    token_response = requests.post(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if token_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=token_response.status_code,
            detail=token_response.text,
        )

    token_data = token_response.json()

    result = {
        "access_token": token_data.get("access_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in", 3600),
    }

    if token_data.get("refresh_token"):
        result["refresh_token"] = token_data["refresh_token"]

    if token_data.get("id_token"):
        result["id_token"] = token_data["id_token"]

    return JSONResponse(result)
