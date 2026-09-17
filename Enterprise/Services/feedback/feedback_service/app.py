from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from .models import Feedback, FeedbackCreate, FeedbackUpdate
from .repository import FeedbackRepository


app = FastAPI(title="Customer360 Feedback Service", version="0.1.0")
repository = FeedbackRepository()


def get_feedback_or_404(feedback_id: str) -> Feedback:
    item = repository.get_feedback(feedback_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return item


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_feedback()
    return {"status": "ok", "service": "feedback"}


@app.post("/api/feedback", response_model=Feedback, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackCreate) -> Feedback:
    return repository.save_feedback(Feedback(**payload.model_dump()))


@app.get("/api/feedback", response_model=list[Feedback])
def list_feedback(
    customer_id: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> list[Feedback]:
    return repository.list_feedback(customer_id=customer_id, source=source, status=status)


@app.get("/api/feedback/{feedback_id}", response_model=Feedback)
def get_feedback(feedback_id: str) -> Feedback:
    return get_feedback_or_404(feedback_id)


@app.put("/api/feedback/{feedback_id}", response_model=Feedback)
def update_feedback(feedback_id: str, payload: FeedbackUpdate) -> Feedback:
    item = get_feedback_or_404(feedback_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = item.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
    return repository.save_feedback(updated)


@app.delete("/api/feedback/{feedback_id}", status_code=204)
def delete_feedback(feedback_id: str) -> None:
    get_feedback_or_404(feedback_id)
    repository.delete_feedback(feedback_id)
