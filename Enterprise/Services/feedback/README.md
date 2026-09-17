# Feedback Service

Owns customer feedback, ratings, sources, campaign references, and review status.

The service stores its data in the service-owned SQLite database at
`data/feedback.sqlite3`.

## Run locally

From the repository root:

```text
.venv/bin/python -m pip install -e Enterprise/Services/feedback
.venv/bin/uvicorn feedback_service.app:app --app-dir Enterprise/Services/feedback --reload --port 8005
```

The repository-root `.venv` is shared by all enterprise services.

## API

- `POST /api/feedback`
- `GET /api/feedback`
- `GET /api/feedback/{feedback_id}`
- `PUT /api/feedback/{feedback_id}`
- `DELETE /api/feedback/{feedback_id}`

Domain events represented by this boundary include `FeedbackSubmitted` and
`FeedbackUpdated`. Event backbone publishing will be added after the operational
CRUD services are stable.