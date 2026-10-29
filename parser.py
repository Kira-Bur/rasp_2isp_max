# parser.py
import os
import re
from datetime import datetime
from docx import Document

from config import GROUP, get_logger

logger = get_logger("Parser")


def find_date(filepath: str) -> str | None:
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


def find_group_column(table, group: str = GROUP) -> int | None:
    for index, cell in enumerate(table.rows[0].cells):
        text = " ".join(cell.text.split())
        if text.upper() == group.upper():
            return index
    return None


def parse_cell(cell) -> dict:
    lines = [line.strip() for line in cell.text.splitlines() if line.strip()]
    if not lines:
        return {"subject": None, "room": None, "teacher": None}
    return {
        "subject": lines[0],
        "room": lines[1] if len(lines) > 1 else None,
        "teacher": lines[2] if len(lines) > 2 else None,
    }


def get_lessons(table, group_column: int, total: int = 4) -> dict:
    lessons = {}
    for lesson_number in range(1, total + 1):
        if lesson_number < len(table.rows):
            data = parse_cell(table.rows[lesson_number].cells[group_column])
        else:
            data = {"subject": None, "room": None, "teacher": None}
        lessons[str(lesson_number)] = data
    return lessons


class ScheduleParser:
    """Парсер расписания из DOCX-файла."""

    def __init__(self, group: str = GROUP):
        self.group = group

    def parse_file(self, filepath: str) -> tuple[str, dict] | None:
        """Возвращает (дата, lessons) или None, если группа не найдена."""
        date = find_date(filepath)
        if not date:
            logger.warning(f"Дата не найдена: {filepath}")
            return None

        document = Document(filepath)

        for table in document.tables:
            if len(table.rows) < 5:
                continue
            column = find_group_column(table, self.group)
            if column is None:
                continue
            return date, get_lessons(table, column)

        logger.warning(f"{date}: группа {self.group} не найдена в {filepath}")
        return None


def find_all_docx(root_dir: str) -> list[str]:
    result = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".docx") and not filename.startswith("~$"):
                result.append(os.path.join(dirpath, filename))
    return sorted(result)
