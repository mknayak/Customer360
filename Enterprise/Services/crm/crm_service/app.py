"""HTTP API for the CRM service."""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import (
    Customer,
    CustomerCreate,
    CustomerImport,
    CustomerProfileInput,
    CustomerProfile,
    CustomerSegment,
    CustomerSegmentInput,
    CustomerPage,
    CustomerUpdate,
)
from .repository import CrmRepository

app = FastAPI(title="Customer360 CRM Service", version="0.1.0")
repository = CrmRepository()


@app.exception_handler(HTTPException)
def handle_http_exception(_: Request, exception: HTTPException) -> JSONResponse:
    detail = exception.detail if isinstance(exception.detail, str) else "Request failed"
    code = "NOT_FOUND" if exception.status_code == 404 else "BAD_REQUEST"
    return JSONResponse(
        status_code=exception.status_code,
        content={"error": {"code": code, "message": detail, "details": None}},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(_: Request, exception: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exception.errors(),
            }
        },
    )


@app.get("/api/health")
def health_check() -> dict[str, str]:
    try:
        repository.list_customers()
    except Exception as exception:
        raise HTTPException(status_code=503, detail="CRM persistence is unavailable") from exception
    return {"status": "ok", "service": "crm"}


def require_customer(customer_id: str) -> Customer:
    customer = repository.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@app.post("/api/customers", response_model=Customer, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate) -> Customer:
    return repository.save_customer(Customer(**payload.model_dump()))


@app.get("/api/customers", response_model=CustomerPage)
def list_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    search: str = Query(default="", max_length=100),
) -> CustomerPage:
    items, total = repository.list_customers_page(page, page_size, search)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return CustomerPage(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@app.post("/api/customers/bulk", response_model=list[Customer])
def import_customers(payload: list[CustomerImport]) -> list[Customer]:
    if len(payload) > 10000:
        raise HTTPException(status_code=400, detail="Import is limited to 10,000 customers per request")

    imported = []
    for item in payload:
        customer = repository.upsert_customer_by_email(
            Customer(**item.model_dump(exclude={"age_group", "city", "country", "preferred_channel"}))
        )
        profile_fields = item.model_dump(
            include={"age_group", "city", "country", "preferred_channel"}
        )
        if any(value is not None for value in profile_fields.values()):
            repository.save_profile(CustomerProfile(customer_id=customer.customer_id, **profile_fields))
        imported.append(customer)
    return imported


@app.get("/api/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: str) -> Customer:
    return require_customer(customer_id)


@app.put("/api/customers/{customer_id}", response_model=Customer)
def update_customer(customer_id: str, payload: CustomerUpdate) -> Customer:
    customer = require_customer(customer_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = customer.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
    return repository.save_customer(updated)


@app.delete("/api/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: str) -> None:
    require_customer(customer_id)
    repository.delete_customer(customer_id)


@app.post("/api/customers/{customer_id}/profile", response_model=CustomerProfile)
def save_profile(customer_id: str, payload: CustomerProfileInput) -> CustomerProfile:
    require_customer(customer_id)
    return repository.save_profile(CustomerProfile(customer_id=customer_id, **payload.model_dump()))


@app.get("/api/customers/{customer_id}/profile", response_model=CustomerProfile)
def get_profile(customer_id: str) -> CustomerProfile:
    require_customer(customer_id)
    profile = repository.get_profile(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


@app.put("/api/customers/{customer_id}/profile", response_model=CustomerProfile)
def update_profile(customer_id: str, payload: CustomerProfileInput) -> CustomerProfile:
    return save_profile(customer_id, payload)


@app.post("/api/customers/{customer_id}/segments", response_model=CustomerSegment)
def add_segment(customer_id: str, payload: CustomerSegmentInput) -> CustomerSegment:
    require_customer(customer_id)
    return repository.add_segment(CustomerSegment(customer_id=customer_id, **payload.model_dump()))


@app.get("/api/customers/{customer_id}/segments", response_model=list[CustomerSegment])
def list_segments(customer_id: str) -> list[CustomerSegment]:
    require_customer(customer_id)
    return repository.get_segments(customer_id)