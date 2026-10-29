# storage.py
import json
import sqlite3
import hashlib
from typing import Optional

from config import DB_FILE, HASH_FILE, GROUP, get_logger

logger = get_logger("Storage")


class ScheduleStorage:
    """Хранилище расписания в SQLite."""

    def __init__(self, db_file: str = DB_FILE, group: str = GROUP):
        self.db_file = db_file
        self.group = group

    def create_database(self) -> None:
        with sqlite3.connect(self.db_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedule (
                    date TEXT PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    lessons TEXT NOT NULL
                )
            """)

    def get_lessons(self, date: str) -> Optional[dict]:
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT lessons FROM schedule WHERE date = ? AND group_name = ?",
                (date, self.group),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def save_schedule(self, date: str, lessons: dict) -> None:
        data = json.dumps(lessons, ensure_ascii=False)
        with sqlite3.connect(self.db_file) as conn:
            conn.execute("""
                INSERT INTO schedule (date, group_name, lessons)
                VALUES (?, ?, ?)
                ON CONFLICT(date)
                DO UPDATE SET
                    group_name = excluded.group_name,
                    lessons = excluded.lessons
            """, (date, self.group, data))

    def get_all_dates(self) -> set[str]:
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT date FROM schedule WHERE group_name = ?",
                (self.group,),
            )
            return {row[0] for row in cursor.fetchall()}


class HashStorage:
    """Хранилище хэшей в JSON-файле."""

    def __init__(self, hash_file: str = HASH_FILE):
        self.hash_file = hash_file

    def load(self) -> dict:
        try:
            with open(self.hash_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.error(f"Ошибка чтения {self.hash_file}: {e}")
            return {}

    def save(self, hashes: dict) -> None:
        try:
            with open(self.hash_file, "w", encoding="utf-8") as f:
                json.dump(hashes, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Ошибка сохранения {self.hash_file}: {e}")


def compute_hash(lessons: dict) -> str:
    data = json.dumps(lessons, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(data.encode("utf-8")).hexdigest()
