from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import Audience, Campaign, CampaignAudience, CampaignChannel, CampaignInteraction, Channel


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "marketing.sqlite3"


class MarketingRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    objective TEXT,
                    status TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    budget_amount REAL,
                    currency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audiences (
                    audience_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    segment TEXT,
                    criteria TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    provider TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaign_audiences (
                    campaign_id TEXT NOT NULL,
                    audience_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (campaign_id, audience_id)
                );
                CREATE TABLE IF NOT EXISTS campaign_channels (
                    campaign_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    allocation_percent REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (campaign_id, channel_id)
                );
                CREATE TABLE IF NOT EXISTS campaign_interactions (
                    interaction_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    channel_id TEXT,
                    occurred_at TEXT NOT NULL,
                    detail TEXT
                );
                """
            )

    @staticmethod
    def campaign(row: sqlite3.Row) -> Campaign:
        data = dict(row)
        data["start_date"] = datetime.fromisoformat(data["start_date"])
        data["end_date"] = datetime.fromisoformat(data["end_date"]) if data["end_date"] else None
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return Campaign(**data)

    @staticmethod
    def audience(row: sqlite3.Row) -> Audience:
        data = dict(row)
        data["criteria"] = json.loads(data["criteria"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Audience(**data)

    @staticmethod
    def channel(row: sqlite3.Row) -> Channel:
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Channel(**data)

    @staticmethod
    def campaign_audience(row: sqlite3.Row) -> CampaignAudience:
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return CampaignAudience(**data)

    @staticmethod
    def campaign_channel(row: sqlite3.Row) -> CampaignChannel:
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return CampaignChannel(**data)

    @staticmethod
    def campaign_interaction(row: sqlite3.Row) -> CampaignInteraction:
        data = dict(row)
        data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
        return CampaignInteraction(**data)

    def save_campaign(self, item: Campaign) -> Campaign:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, name, objective, status, start_date, end_date,
                    budget_amount, currency, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    name = excluded.name,
                    objective = excluded.objective,
                    status = excluded.status,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    budget_amount = excluded.budget_amount,
                    currency = excluded.currency,
                    updated_at = excluded.updated_at
                """,
                (
                    item.campaign_id,
                    item.name,
                    item.objective,
                    item.status,
                    item.start_date.isoformat(),
                    item.end_date.isoformat() if item.end_date else None,
                    item.budget_amount,
                    item.currency,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        return item

    def get_campaign(self, campaign_id: str) -> Campaign | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
        return self.campaign(row) if row else None

    def list_campaigns(self, status: str | None = None) -> list[Campaign]:
        parameters = (status,) if status is not None else ()
        where = "WHERE status = ?" if status is not None else ""
        with self.lock:
            rows = self.connection.execute(f"SELECT * FROM campaigns {where} ORDER BY start_date, campaign_id", parameters).fetchall()
        return [self.campaign(row) for row in rows]

    def delete_campaign(self, campaign_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM campaign_audiences WHERE campaign_id = ?", (campaign_id,))
            self.connection.execute("DELETE FROM campaign_channels WHERE campaign_id = ?", (campaign_id,))
            self.connection.execute("DELETE FROM campaign_interactions WHERE campaign_id = ?", (campaign_id,))
            self.connection.execute("DELETE FROM campaigns WHERE campaign_id = ?", (campaign_id,))

    def save_audience(self, item: Audience) -> Audience:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO audiences VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item.audience_id,
                    item.name,
                    item.description,
                    item.segment,
                    json.dumps(item.criteria, sort_keys=True),
                    item.status,
                    item.created_at.isoformat(),
                ),
            )
        return item

    def get_audience(self, audience_id: str) -> Audience | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM audiences WHERE audience_id = ?", (audience_id,)).fetchone()
        return self.audience(row) if row else None

    def list_audiences(self) -> list[Audience]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM audiences ORDER BY name, audience_id").fetchall()
        return [self.audience(row) for row in rows]

    def save_channel(self, item: Channel) -> Channel:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO channels VALUES (?, ?, ?, ?, ?, ?)",
                (item.channel_id, item.name, item.channel_type, item.provider, item.status, item.created_at.isoformat()),
            )
        return item

    def get_channel(self, channel_id: str) -> Channel | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        return self.channel(row) if row else None

    def list_channels(self) -> list[Channel]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM channels ORDER BY name, channel_id").fetchall()
        return [self.channel(row) for row in rows]

    def save_campaign_audience(self, item: CampaignAudience) -> CampaignAudience:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO campaign_audiences VALUES (?, ?, ?)",
                (item.campaign_id, item.audience_id, item.created_at.isoformat()),
            )
        return item

    def list_campaign_audiences(self, campaign_id: str) -> list[Audience]:
        with self.lock:
            rows = self.connection.execute(
                """
                SELECT audiences.* FROM campaign_audiences
                JOIN audiences ON audiences.audience_id = campaign_audiences.audience_id
                WHERE campaign_audiences.campaign_id = ?
                ORDER BY audiences.name, audiences.audience_id
                """,
                (campaign_id,),
            ).fetchall()
        return [self.audience(row) for row in rows]

    def save_campaign_channel(self, item: CampaignChannel) -> CampaignChannel:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO campaign_channels VALUES (?, ?, ?, ?)",
                (item.campaign_id, item.channel_id, item.allocation_percent, item.created_at.isoformat()),
            )
        return item

    def list_campaign_channels(self, campaign_id: str) -> list[CampaignChannel]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM campaign_channels WHERE campaign_id = ? ORDER BY channel_id",
                (campaign_id,),
            ).fetchall()
        return [self.campaign_channel(row) for row in rows]

    def add_campaign_interaction(self, item: CampaignInteraction) -> CampaignInteraction:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO campaign_interactions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item.interaction_id,
                    item.campaign_id,
                    item.customer_id,
                    item.event_type,
                    item.channel_id,
                    item.occurred_at.isoformat(),
                    item.detail,
                ),
            )
        return item

    def list_campaign_interactions(self, campaign_id: str | None = None, customer_id: str | None = None) -> list[CampaignInteraction]:
        clauses = []
        parameters: list[str] = []
        for column, value in (("campaign_id", campaign_id), ("customer_id", customer_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.lock:
            rows = self.connection.execute(
                f"SELECT * FROM campaign_interactions {where} ORDER BY occurred_at, interaction_id",
                parameters,
            ).fetchall()
        return [self.campaign_interaction(row) for row in rows]

    def close(self) -> None:
        self.connection.close()
