from typing import Optional

from pydantic import BaseModel


class SchedulerCreateRequest(BaseModel):
    name: str
    job_type: str  # sync_all or time_entries
    frequency: str  # manual, daily, weekly
    day: Optional[str] = None  # monday, tuesday, etc. Only needed for weekly.
    time: Optional[str] = None  # HH:MM in 24-hour format, e.g. 14:30
    active: bool = True


class SchedulerRunRequest(BaseModel):
    job_type: Optional[str] = None  # Optional: sync_all or time_entries


class SchedulerDeleteRequest(BaseModel):
    record_id: str
