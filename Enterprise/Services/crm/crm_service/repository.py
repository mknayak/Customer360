"""Service-owned SQLite persistence for the CRM service."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .migrate import apply_migrations
from .models import Customer, CustomerDirectoryItem, CustomerProfile, CustomerSegment


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "crm.sqlite3"


class CrmRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            apply_migrations(self._connection)

    @staticmethod
    def _customer_from_row(row: sqlite3.Row) -> Customer:
        return Customer(
            customer_id=row["customer_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            phone=row["phone"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _profile_from_row(row: sqlite3.Row) -> CustomerProfile:
        return CustomerProfile(
            customer_id=row["customer_id"],
            age_group=row["age_group"],
            city=row["city"],
            country=row["country"],
            preferred_channel=row["preferred_channel"],
        )

    @staticmethod
    def _segment_from_row(row: sqlite3.Row) -> CustomerSegment:
        return CustomerSegment(
            customer_id=row["customer_id"],
            segment=row["segment"],
            effective_from=datetime.fromisoformat(row["effective_from"]),
            effective_to=(
                datetime.fromisoformat(row["effective_to"])
                if row["effective_to"]
                else None
            ),
        )

    def save_customer(self, customer: Customer) -> Customer:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO customers (
                    customer_id, first_name, last_name, email, phone, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    email = excluded.email,
                    phone = excluded.phone,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    customer.customer_id,
                    customer.first_name,
                    customer.last_name,
                    customer.email,
                    customer.phone,
                    customer.status,
                    customer.created_at.isoformat(),
                    customer.updated_at.isoformat(),
                ),
            )
        return customer

    def upsert_customer_by_email(self, customer: Customer) -> Customer:
        with self._lock:
            row = self._connection.execute(
                "SELECT customer_id FROM customers WHERE email = ?",
                (customer.email,),
            ).fetchone()
        if row:
            customer = customer.model_copy(update={"customer_id": row["customer_id"]})
        return self.save_customer(customer)

    def list_customers(self) -> list[Customer]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM customers ORDER BY created_at, customer_id"
            ).fetchall()
        return [self._customer_from_row(row) for row in rows]

    def list_customers_page(
        self, page: int, page_size: int, search: str = ""
    ) -> tuple[list[CustomerDirectoryItem], int]:
        offset = (page - 1) * page_size
        pattern = f"%{search.strip()}%"
        where = """
            WHERE first_name LIKE ? COLLATE NOCASE
               OR last_name LIKE ? COLLATE NOCASE
               OR email LIKE ? COLLATE NOCASE
               OR phone LIKE ? COLLATE NOCASE
               OR status LIKE ? COLLATE NOCASE
               OR customer_profiles.city LIKE ? COLLATE NOCASE
               OR customer_profiles.country LIKE ? COLLATE NOCASE
               OR customer_profiles.preferred_channel LIKE ? COLLATE NOCASE
        """
        parameters = (pattern,) * 8
        with self._lock:
            total = self._connection.execute(
                "SELECT COUNT(*) FROM customers LEFT JOIN customer_profiles "
                "ON customer_profiles.customer_id = customers.customer_id "
                f"{where}",
                parameters,
            ).fetchone()[0]
            rows = self._connection.execute(
                "SELECT customers.*, customer_profiles.age_group, customer_profiles.city, "
                "customer_profiles.country, customer_profiles.preferred_channel "
                "FROM customers LEFT JOIN customer_profiles "
                "ON customer_profiles.customer_id = customers.customer_id "
                f"{where} ORDER BY customers.created_at, customers.customer_id "
                "LIMIT ? OFFSET ?",
                (*parameters, page_size, offset),
            ).fetchall()
        return [
            CustomerDirectoryItem(
                **self._customer_from_row(row).model_dump(),
                age_group=row["age_group"],
                city=row["city"],
                country=row["country"],
                preferred_channel=row["preferred_channel"],
            )
            for row in rows
        ], total

    def get_customer(self, customer_id: str) -> Customer | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM customers WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        return self._customer_from_row(row) if row else None

    def delete_customer(self, customer_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM customers WHERE customer_id = ?",
                (customer_id,),
            )

    def save_profile(self, profile: CustomerProfile) -> CustomerProfile:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO customer_profiles (
                    customer_id, age_group, city, country, preferred_channel
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    age_group = excluded.age_group,
                    city = excluded.city,
                    country = excluded.country,
                    preferred_channel = excluded.preferred_channel
                """,
                (
                    profile.customer_id,
                    profile.age_group,
                    profile.city,
                    profile.country,
                    profile.preferred_channel,
                ),
            )
        return profile

    def get_profile(self, customer_id: str) -> CustomerProfile | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM customer_profiles WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        return self._profile_from_row(row) if row else None

    def add_segment(self, segment: CustomerSegment) -> CustomerSegment:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO customer_segments (
                    customer_id, segment, effective_from, effective_to
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    segment.customer_id,
                    segment.segment,
                    segment.effective_from.isoformat(),
                    segment.effective_to.isoformat() if segment.effective_to else None,
                ),
            )
        return segment

    def get_segments(self, customer_id: str) -> list[CustomerSegment]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM customer_segments
                WHERE customer_id = ?
                ORDER BY effective_from, segment_id
                """,
                (customer_id,),
            ).fetchall()
        return [self._segment_from_row(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()