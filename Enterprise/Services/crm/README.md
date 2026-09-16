# CRM Service

Owns customer identity, profiles, and customer segments.

The service stores its data in the service-owned SQLite database at
`data/crm.sqlite3`. The schema is managed by the SQL migrations in
`migrations/` and applied automatically on startup.

## Run locally

From the repository root:

```text
.venv/bin/python -m pip install -e Enterprise/Services/crm
.venv/bin/uvicorn crm_service.app:app --app-dir Enterprise/Services/crm --reload
```

To apply pending migrations explicitly:

```text
.venv/bin/python -m crm_service.migrate
```

The repository-root `.venv` is shared by all enterprise services.

## API

- `POST /api/customers`
- `GET /api/customers`
- `POST /api/customers/bulk` (upsert up to 10,000 customers by email)
- `GET /api/customers/{customer_id}`
- `PUT /api/customers/{customer_id}`
- `DELETE /api/customers/{customer_id}`
- `POST /api/customers/{customer_id}/profile`
- `GET /api/customers/{customer_id}/profile`
- `PUT /api/customers/{customer_id}/profile`
- `POST /api/customers/{customer_id}/segments`
- `GET /api/customers/{customer_id}/segments`

Domain events are represented by the service boundary now and will be wired to
the event backbone after the CRUD services are established.