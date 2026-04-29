from pydantic import BaseModel
from typing import Optional, List


class LemGenerateRequest(BaseModel):
    from_date: str
    to_date: str
    project_codes: Optional[List[str]] = None
