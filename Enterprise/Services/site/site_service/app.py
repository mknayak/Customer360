from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, status

from .models import Site, SiteCreate, SiteUpdate, Visit, VisitCreate
from .repository import SiteRepository

app = FastAPI(title="Customer360 Site Service", version="0.1.0")
repository = SiteRepository()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_site_or_404(site_id: str) -> Site:
    item = repository.get_site(site_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return item


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_sites()
    return {"status": "ok", "service": "site"}


@app.post("/api/sites", response_model=Site, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate) -> Site:
    return repository.save_site(Site(**payload.model_dump()))


@app.get("/api/sites", response_model=list[Site])
def list_sites() -> list[Site]:
    return repository.list_sites()


@app.get("/api/sites/{site_id}", response_model=Site)
def get_site(site_id: str) -> Site:
    return get_site_or_404(site_id)


@app.put("/api/sites/{site_id}", response_model=Site)
def update_site(site_id: str, payload: SiteUpdate) -> Site:
    item = get_site_or_404(site_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = item.model_copy(update={**changes, "updated_at": utc_now()})
    return repository.save_site(updated)


@app.delete("/api/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: str) -> None:
    get_site_or_404(site_id)
    repository.delete_site(site_id)


@app.post("/api/visits", response_model=Visit, status_code=status.HTTP_201_CREATED)
def create_visit(payload: VisitCreate) -> Visit:
    get_site_or_404(payload.site_id)
    visit_data = payload.model_dump(exclude_none=True)
    visit_data.setdefault("started_at", utc_now())
    item = Visit(**visit_data)
    if item.ended_at and item.ended_at < item.started_at:
        raise HTTPException(status_code=400, detail="ended_at cannot be earlier than started_at")
    return repository.save_visit(item)


@app.get("/api/visits", response_model=list[Visit])
def list_visits(
    customer_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
) -> list[Visit]:
    return repository.list_visits(customer_id=customer_id, site_id=site_id)


@app.get("/api/visits/{visit_id}", response_model=Visit)
def get_visit(visit_id: str) -> Visit:
    item = repository.get_visit(visit_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return item
