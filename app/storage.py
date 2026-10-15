"""Збереження підписок на щоденну розсилку (SQLite).

Локально база лежить у файлі data/app.db (папка data/ у .gitignore).
"""
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.schemas import City


@dataclass
class Subscription:
    chat_id: int
    city: City
    hour: int                    # година розсилки за київським часом (0–23)
    last_sent: date | None = None
    last_alert: date | None = None


class SubscriptionStorage:
    def __init__(self, path: str | Path = "data/app.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id    INTEGER PRIMARY KEY,
                city       TEXT    NOT NULL,
                country    TEXT    NOT NULL DEFAULT '',
                latitude   REAL    NOT NULL,
                longitude  REAL    NOT NULL,
                timezone   TEXT    NOT NULL DEFAULT 'auto',
                hour       INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
                last_sent  TEXT,
                last_alert TEXT
            )""")
        self.conn.commit()

    def upsert(self, chat_id: int, city: City, hour: int) -> Subscription:
        if not 0 <= hour <= 23:
            raise ValueError("Година має бути від 0 до 23")
        self.conn.execute("""
            INSERT INTO subscriptions (chat_id, city, country, latitude, longitude, timezone, hour)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                city=excluded.city, country=excluded.country, latitude=excluded.latitude,
                longitude=excluded.longitude, timezone=excluded.timezone, hour=excluded.hour,
                last_sent=NULL, last_alert=NULL""",
            (chat_id, city.name, city.country, city.latitude, city.longitude, city.timezone, hour))
        self.conn.commit()
        return self.get(chat_id)

    def get(self, chat_id: int) -> Subscription | None:
        row = self.conn.execute("SELECT * FROM subscriptions WHERE chat_id = ?",
                                (chat_id,)).fetchone()
        return self._from_row(row) if row else None

    def all(self) -> list[Subscription]:
        return [self._from_row(r) for r in self.conn.execute("SELECT * FROM subscriptions")]

    def delete(self, chat_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_sent(self, chat_id: int, day: date) -> None:
        self.conn.execute("UPDATE subscriptions SET last_sent = ? WHERE chat_id = ?",
                          (day.isoformat(), chat_id))
        self.conn.commit()

    def mark_alerted(self, chat_id: int, day: date) -> None:
        self.conn.execute("UPDATE subscriptions SET last_alert = ? WHERE chat_id = ?",
                          (day.isoformat(), chat_id))
        self.conn.commit()

    @staticmethod
    def _from_row(r: sqlite3.Row) -> Subscription:
        return Subscription(
            chat_id=r["chat_id"],
            city=City(name=r["city"], country=r["country"], latitude=r["latitude"],
                      longitude=r["longitude"], timezone=r["timezone"]),
            hour=r["hour"],
            last_sent=date.fromisoformat(r["last_sent"]) if r["last_sent"] else None,
            last_alert=date.fromisoformat(r["last_alert"]) if r["last_alert"] else None,
        )
