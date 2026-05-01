from pydantic import BaseModel
from typing import List, Optional

class LemGenerateRequest(BaseModel):
    from_date: str
    to_date: str
    project_codes: Optional[List[str]] = None
    include_csv: bool = True
    include_pdf: bool = True
