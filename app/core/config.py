import os
from functools import lru_cache
from pydantic import BaseModel


class Settings(BaseModel):
    api_key: str | None = None

    harvest_token: str | None = None
    harvest_account_id: str | None = None

    airtable_token: str | None = None
    airtable_base_id: str | None = None

    ms_tenant_id: str | None = None
    ms_client_id: str | None = None
    ms_client_secret: str | None = None
    ms_allowed_group_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("API_KEY"),
        harvest_token=os.getenv("HARVEST_TOKEN"),
        harvest_account_id=os.getenv("HARVEST_ACCOUNT_ID"),
        airtable_token=os.getenv("AIRTABLE_TOKEN"),
        airtable_base_id=os.getenv("AIRTABLE_BASE_ID"),
        ms_tenant_id=os.getenv("MS_TENANT_ID"),
        ms_client_id=os.getenv("MS_CLIENT_ID"),
        ms_client_secret=os.getenv("MS_CLIENT_SECRET"),
        ms_allowed_group_id=os.getenv("MS_ALLOWED_GROUP_ID"),
    )
