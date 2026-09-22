import os
import re
import json
import sqlite3
import hashlib
import logging
from datetime import datetime
from docx import Document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ScheduleParser")

DOCS_DIR = "Расписание"
DB_FILE = "schedule.db"
HASH_FILE = "hashes.json"
GROUP = "2 ИСП"


def load_hashes():
    if not os.path.exists(HASH_FILE):
        return {}
    try:
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения {HASH_FILE}: {e}")
        return {}


def save_hashes(hashes):
    try:
        with open(HASH_FILE, "w", encoding="utf-8") as f:
            json.dump(hashes, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения {HASH_FILE}: {e}")


def compute_hash(lessons):
    data = json.dumps(lessons, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def create_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            date TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            lessons TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def find_date(filepath):
    filename = os.path.basename(filepath)
    match = re.search(r"\d{2}\.\d{2}", filename)
    if match:
        return f"{match.group()}.{datetime.now().year}"

    parent = os.path.basename(os.path.dirname(filepath))
    match = re.search(r"\d{2}[\.\-]\d{2}", parent)
    if match:
        normalized = match.group().replace("-", ".")
        return f"{normalized}.{datetime.now().year}"

    return None


def find_group_column(table):
    for index, cell in enumerate(table.rows[0].cells):
        text = " ".join(cell.text.split())
        if text.upper() == GROUP.upper():
            return index
    return None


def parse_cell(cell):
    lines = [
        line.strip()
        for line in cell.text.splitlines()
        if line.strip()
    ]

    if not lines:
        return {"subject": None, "room": None, "teacher": None}

    return {
        "subject": lines[0],
        "room": lines[1] if len(lines) > 1 else None,
        "teacher": lines[2] if len(lines) > 2 else None
    }


def get_lessons(table, group_column):
    lessons = {}

    for lesson_number in range(1, 5):
        if lesson_number >= len(table.rows):
            break

        cell = table.rows[lesson_number].cells[group_column]
        data = parse_cell(cell)

        lessons[str(lesson_number)] = {
            "subject": data["subject"],
            "room": data["room"],
            "teacher": data["teacher"]
        }

    for number in range(1, 5):
        if str(number) not in lessons:
            lessons[str(number)] = {
                "subject": None,
                "room": None,
                "teacher": None
            }

    return lessons


def get_lessons_from_db(date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT lessons FROM schedule WHERE date = ? AND group_name = ?",
            (date, GROUP)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def save_schedule(date, lessons):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    data = json.dumps(lessons, ensure_ascii=False)

    cursor.execute("""
        INSERT INTO schedule (date, group_name, lessons)
        VALUES (?, ?, ?)
        ON CONFLICT(date)
        DO UPDATE SET
            group_name = excluded.group_name,
            lessons = excluded.lessons
    """, (date, GROUP, data))

    conn.commit()
    conn.close()


def log_diff(old_lessons, new_lessons):
    for number in ["1", "2", "3", "4"]:
        old = old_lessons.get(number) or {}
        new = new_lessons.get(number) or {}

        for field in ["subject", "room", "teacher"]:
            old_val = old.get(field)
            new_val = new.get(field)
            if old_val != new_val:
                logger.info(
                    f"  Пара {number} [{field}]: "
                    f"'{old_val or '-'}' -> '{new_val or '-'}'"
                )


def process_file(filepath, hashes):
    date = find_date(filepath)

    if not date:
        logger.warning(f"Дата не найдена: {filepath}")
        return False

    document = Document(filepath)

    for table in document.tables:
        if len(table.rows) < 5:
            continue

        group_column = find_group_column(table)
        if group_column is None:
            continue

        lessons = get_lessons(table, group_column)
        new_hash = compute_hash(lessons)
        old_hash = hashes.get(date)

        if old_hash == new_hash:
            logger.info(f"{date}: без изменений")
            return False

        old_lessons = get_lessons_from_db(date) if old_hash else None
        save_schedule(date, lessons)

        if old_hash is None:
            logger.info(f"{date}: новое расписание сохранено")
        else:
            logger.info(f"{date}: расписание изменено, обновлено")
            if old_lessons:
                log_diff(old_lessons, lessons)

        hashes[date] = new_hash
        return True

    logger.warning(f"{date}: группа {GROUP} не найдена в {filepath}")
    return False


def find_all_docx(root_dir):
    result = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".docx") and not filename.startswith("~$"):
                result.append(os.path.join(dirpath, filename))
    return sorted(result)


def cleanup_hashes(hashes):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT date FROM schedule WHERE group_name = ?",
            (GROUP,)
        )
        db_dates = {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()

    removed = [d for d in hashes if d not in db_dates]
    for date in removed:
        del hashes[date]
        logger.info(f"Удалён устаревший хэш для {date}")

    return len(removed) > 0


def main():
    create_database()

    if not os.path.isdir(DOCS_DIR):
        logger.error(f"Папка {DOCS_DIR} не найдена")
        return

    files = find_all_docx(DOCS_DIR)

    if not files:
        logger.info("DOCX файлов нет")
        return

    logger.info(f"Найдено файлов: {len(files)}")

    hashes = load_hashes()
    has_changes = False

    for filepath in files:
        try:
            if process_file(filepath, hashes):
                has_changes = True
        except Exception as error:
            logger.error(f"Ошибка {filepath}: {error}")

    if cleanup_hashes(hashes):
        has_changes = True

    save_hashes(hashes)

    if has_changes:
        logger.info("Обнаружены изменения в расписании")
    else:
        logger.info("Изменений нет")


if __name__ == "__main__":
    main()
