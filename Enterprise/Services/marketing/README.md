# Marketing Service

Owns campaigns, campaign audiences, campaign channels, their assignments, and
customer campaign interactions.

The service stores its data in the service-owned SQLite database at
`data/marketing.sqlite3`.

## Run locally

From the repository root:

```text
.venv/bin/python -m pip install -e Enterprise/Services/marketing
.venv/bin/uvicorn marketing_service.app:app --app-dir Enterprise/Services/marketing --reload --port 8006
```

The repository-root `.venv` is shared by all enterprise services.

## API

- `POST /api/campaigns`
- `GET /api/campaigns`
- `GET /api/campaigns/{campaign_id}`
- `PUT /api/campaigns/{campaign_id}`
- `DELETE /api/campaigns/{campaign_id}`
- `POST /api/audiences`
- `GET /api/audiences`
- `GET /api/audiences/{audience_id}`
- `POST /api/channels`
- `GET /api/channels`
- `GET /api/channels/{channel_id}`
- `POST /api/campaigns/{campaign_id}/audiences`
- `GET /api/campaigns/{campaign_id}/audiences`
- `POST /api/campaigns/{campaign_id}/channels`
- `GET /api/campaigns/{campaign_id}/channels`
- `POST /api/campaigns/{campaign_id}/interactions`
- `GET /api/campaigns/{campaign_id}/interactions`
- `GET /api/interactions`

Domain events represented by this boundary include `CampaignCreated`,
`CampaignStarted`, and `CampaignEnded`. Event backbone publishing will be added
after the operational CRUD services are stable.