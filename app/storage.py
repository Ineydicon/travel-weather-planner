import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.schemas import City

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id    BIGINT PRIMARY KEY,
    city       TEXT             NOT NULL,
    country    TEXT             NOT NULL DEFAULT '',
    latitude   DOUBLE PRECISION NOT NULL,
    longitude  DOUBLE PRECISION NOT NULL,
    timezone   TEXT             NOT NULL DEFAULT 'auto',
    hour       INTEGER          NOT NULL CHECK (hour BETWEEN 0 AND 23),
    last_sent  TEXT,
    last_alert TEXT
)"""


@dataclass
class Subscription:
    chat_id: int
    city: City
    hour: int
    last_sent: date | None = None
    last_alert: date | None = None


class SubscriptionStorage:
    def __init__(self, database_url: str = "sqlite:///./data/app.db"):
        self.is_postgres = database_url.startswith(("postgres://", "postgresql://"))
        if self.is_postgres:
            import psycopg
            self._psycopg = psycopg
            self.url = database_url
        else:
            path = database_url.removeprefix("sqlite:///")
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(path, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row
        self._run(SCHEMA)

    def _run(self, sql: str, params: tuple = (), fetch: bool = False):
        if self.is_postgres:
            from psycopg.rows import dict_row
            # нове з'єднання на кожен запит: безкоштовна БД закриває неактивні з'єднання
            with self._psycopg.connect(self.url, autocommit=True, row_factory=dict_row) as conn:
                cur = conn.execute(sql.replace("?", "%s"), params)
                return cur.fetchall() if fetch else cur.rowcount
        cur = self._sqlite.execute(sql, params)
        self._sqlite.commit()
        return cur.fetchall() if fetch else cur.rowcount

    def upsert(self, chat_id: int, city: City, hour: int) -> Subscription:
        if not 0 <= hour <= 23:
            raise ValueError("Година має бути від 0 до 23")
        self._run("""
            INSERT INTO subscriptions (chat_id, city, country, latitude, longitude, timezone, hour)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                city=excluded.city, country=excluded.country, latitude=excluded.latitude,
                longitude=excluded.longitude, timezone=excluded.timezone, hour=excluded.hour,
                last_sent=NULL, last_alert=NULL""",
            (chat_id, city.name, city.country, city.latitude, city.longitude, city.timezone, hour))
        return self.get(chat_id)

    def get(self, chat_id: int) -> Subscription | None:
        rows = self._run("SELECT * FROM subscriptions WHERE chat_id = ?", (chat_id,), fetch=True)
        return self._from_row(rows[0]) if rows else None

    def all(self) -> list[Subscription]:
        return [self._from_row(r) for r in self._run("SELECT * FROM subscriptions", fetch=True)]

    def delete(self, chat_id: int) -> bool:
        return self._run("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,)) > 0

    def mark_sent(self, chat_id: int, day: date) -> None:
        self._run("UPDATE subscriptions SET last_sent = ? WHERE chat_id = ?",
                  (day.isoformat(), chat_id))

    def mark_alerted(self, chat_id: int, day: date) -> None:
        self._run("UPDATE subscriptions SET last_alert = ? WHERE chat_id = ?",
                  (day.isoformat(), chat_id))

    @staticmethod
    def _from_row(r) -> Subscription:
        return Subscription(
            chat_id=r["chat_id"],
            city=City(name=r["city"], country=r["country"], latitude=r["latitude"],
                      longitude=r["longitude"], timezone=r["timezone"]),
            hour=r["hour"],
            last_sent=date.fromisoformat(r["last_sent"]) if r["last_sent"] else None,
            last_alert=date.fromisoformat(r["last_alert"]) if r["last_alert"] else None,
        )
