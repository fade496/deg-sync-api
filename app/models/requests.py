from typing import Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    table: str
    search: Optional[str] = None
    limit: int = 10


class UpdateRequest(BaseModel):
    entity: str
    harvest_id: int
    field: str
    operation: str = "set"  # set, increment
    value: Optional[float | str | bool] = None
    amount: Optional[float] = None


class CreateClientRequest(BaseModel):
    name: str
    currency: str = "CAD"
    address: Optional[str] = ""
    is_active: bool = True


class CreateContactRequest(BaseModel):
    client_name: Optional[str] = None
    harvest_client_id: Optional[int] = None
    first_name: str
    last_name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    title: Optional[str] = ""


class CreateClientWithContactRequest(BaseModel):
    client_name: str
    currency: str = "CAD"
    address: Optional[str] = ""
    is_active: bool = True

    contact_first_name: str
    contact_last_name: str
    contact_email: Optional[str] = ""
    contact_phone: Optional[str] = ""
    contact_title: Optional[str] = ""


class CreatePersonRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    telephone: Optional[str] = ""
    is_contractor: bool = False
    is_active: bool = True
    default_hourly_rate: Optional[float] = None
    cost_rate: Optional[float] = None


class CreateProjectRequest(BaseModel):
    client_name: Optional[str] = None
    harvest_client_id: Optional[int] = None

    name: str
    code: Optional[str] = ""
    is_active: bool = True
    is_billable: bool = True
    is_fixed_fee: bool = False
    bill_by: Optional[str] = "Project"

    hourly_rate: Optional[float] = None
    budget: Optional[float] = None
    budget_by: Optional[str] = None
    budget_is_monthly: bool = False
    fee: Optional[float] = None
    notes: Optional[str] = ""
