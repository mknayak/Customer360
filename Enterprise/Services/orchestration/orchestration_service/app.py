import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from .client import ServiceCallError, ServiceClient
from .models import ShoppingJourneyCreate, WorkflowResult
from .repository import WorkflowRepository

SERVICE_ORIGINS = {
    "site": os.getenv("SITE_ORIGIN", "http://127.0.0.1:8004"),
    "shopping": os.getenv("SHOPPING_ORIGIN", "http://127.0.0.1:8003"),
    "events": os.getenv("EVENTS_ORIGIN", "http://127.0.0.1:8007"),
}

app = FastAPI(title="Customer360 Orchestration Service", version="0.1.0")
client = ServiceClient(SERVICE_ORIGINS)
repository = WorkflowRepository()


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.get("health-check")
    return {"status": "ok", "service": "orchestration"}


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowResult)
def get_workflow(workflow_id: str) -> WorkflowResult:
    workflow = repository.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def publish_event(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict,
    correlation_id: str,
) -> str:
    event = client.post(
        "events",
        "/api/events",
        {
            "source_service": aggregate_type,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "correlation_id": correlation_id,
        },
    )
    return event["event_id"]


@app.post("/api/workflows/shopping-journey", response_model=WorkflowResult, status_code=status.HTTP_201_CREATED)
def start_shopping_journey(payload: ShoppingJourneyCreate) -> WorkflowResult:
    workflow_id = str(uuid4())
    correlation_id = payload.correlation_id or workflow_id
    published_event_ids: list[str] = []
    visit_id = None
    cart_id = None
    running = WorkflowResult(workflow_id=workflow_id, correlation_id=correlation_id, status="running")
    repository.save(running)
    try:
        visit = client.post(
            "site",
            "/api/visits",
            {"customer_id": payload.customer_id, "site_id": payload.site_id, "channel": "web"},
        )
        visit_id = visit["visit_id"]
        published_event_ids.append(
            publish_event(
                "VisitStarted",
                "site",
                visit_id,
                {"customer_id": payload.customer_id, "site_id": payload.site_id},
                correlation_id,
            )
        )

        cart = client.post(
            "shopping",
            "/api/carts",
            {
                "customer_id": payload.customer_id,
                "site_id": payload.site_id,
                "store_id": payload.store_id,
                "delivery_mode": payload.delivery_mode,
            },
        )
        cart_id = cart["cart_id"]
        for item in payload.items:
            client.post(
                "shopping",
                f"/api/carts/{cart_id}/items",
                item.model_dump(),
            )
        published_event_ids.append(
            publish_event(
                "CartCreated",
                "shopping",
                cart_id,
                {"customer_id": payload.customer_id, "site_id": payload.site_id, "item_count": len(payload.items)},
                correlation_id,
            )
        )
        result = WorkflowResult(
            workflow_id=workflow_id,
            correlation_id=correlation_id,
            status="completed",
            visit_id=visit_id,
            cart_id=cart_id,
            published_event_ids=published_event_ids,
        )
        repository.save(result)
        return result
    except (KeyError, ServiceCallError) as error:
        failed = WorkflowResult(
            workflow_id=workflow_id,
            correlation_id=correlation_id,
            status="failed",
            visit_id=visit_id,
            cart_id=cart_id,
            published_event_ids=published_event_ids,
            failure=str(error),
        )
        repository.save(failed)
        raise HTTPException(
            status_code=502,
            detail={
                "workflow_id": workflow_id,
                "correlation_id": correlation_id,
                "message": str(error),
                "visit_id": visit_id,
                "cart_id": cart_id,
            },
        ) from error
