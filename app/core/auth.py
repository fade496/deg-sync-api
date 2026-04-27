import requests
from fastapi import HTTPException
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import get_settings


def microsoft_openid_config():
    settings = get_settings()
    url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/v2.0/.well-known/openid-configuration"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def microsoft_jwks():
    config = microsoft_openid_config()
    jwks_uri = config["jwks_uri"]

    response = requests.get(jwks_uri, timeout=15)
    response.raise_for_status()

    return response.json()


def verify_microsoft_token(authorization: str):
    settings = get_settings()

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = authorization.split(" ", 1)[1]

    try:
        jwks = microsoft_jwks()
        unverified_header = jwt.get_unverified_header(token)

        key = None
        for jwk in jwks["keys"]:
            if jwk["kid"] == unverified_header["kid"]:
                key = jwk
                break

        if not key:
            raise HTTPException(status_code=401, detail="Microsoft signing key not found")

        valid_issuers = [
            f"https://login.microsoftonline.com/{settings.ms_tenant_id}/v2.0",
            f"https://sts.windows.net/{settings.ms_tenant_id}/",
        ]

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=f"api://{settings.ms_client_id}",
            issuer=valid_issuers,
        )

        if settings.ms_allowed_group_id:
            groups = claims.get("groups", [])

            if settings.ms_allowed_group_id not in groups:
                raise HTTPException(
                    status_code=403,
                    detail="User is not in the allowed Microsoft group",
                )

        return claims

    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Microsoft token: {str(e)}",
        )


def check_key(x_api_key: str | None = None, authorization: str | None = None):
    settings = get_settings()

    if x_api_key and x_api_key == settings.api_key:
        return {
            "auth_method": "api_key",
        }

    if authorization:
        claims = verify_microsoft_token(authorization)

        return {
            "auth_method": "microsoft_oauth",
            "claims": claims,
        }

    raise HTTPException(status_code=401, detail="Unauthorized")
