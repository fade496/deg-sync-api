from typing import Optional

from pydantic import BaseModel, Field


class LemGenerateRequest(BaseModel):
    from_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    to_date: str = Field(..., description="End date in YYYY-MM-DD format")

    project_codes: Optional[list[str]] = None

    include_csv: bool = True
    include_xlsx: bool = True
    include_pdf: bool = True

    force_sync_time_entries: bool = True

    approved_only: bool = False
    billable_only: bool = False
