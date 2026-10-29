import os

from config import DOCS_DIR, GROUP, get_logger
from parser import ScheduleParser, find_all_docx
from storage import ScheduleStorage, HashStorage, compute_hash

logger = get_logger("Main")


def log_diff(old_lessons: dict, new_lessons: dict, total: int = 4) -> None:
    for number in [str(i) for i in range(1, total + 1)]:
        old = old_lessons.get(number) or {}
        new = new_lessons.get(number) or {}
        for field in ("subject", "room", "teacher"):
            old_val, new_val = old.get(field), new.get(field)
            if old_val != new_val:
                logger.info(
                    f"  Пара {number} [{field}]: "
                    f"'{old_val or '-'}' -> '{new_val or '-'}'"
                )


class ScheduleService:
    """Бизнес-логика: сравнение, сохранение, отчёт об изменениях."""

    def __init__(self, parser: ScheduleParser, storage: ScheduleStorage,
                 hashes: HashStorage):
        self.parser = parser
        self.storage = storage
        self.hashes = hashes
        self._cache: dict = {}

    def load_hashes(self) -> None:
        self._cache = self.hashes.load()

    def save_hashes(self) -> None:
        self.hashes.save(self._cache)

    def process_file(self, filepath: str) -> bool:
        parsed = self.parser.parse_file(filepath)
        if not parsed:
            return False

        date, lessons = parsed
        new_hash = compute_hash(lessons)
        old_hash = self._cache.get(date)

        if old_hash == new_hash:
            logger.info(f"{date}: без изменений")
            return False

        old_lessons = self.storage.get_lessons(date) if old_hash else None
        self.storage.save_schedule(date, lessons)

        if old_hash is None:
            logger.info(f"{date}: новое расписание сохранено")
        else:
            logger.info(f"{date}: расписание изменено, обновлено")
            if old_lessons:
                log_diff(old_lessons, lessons)

        self._cache[date] = new_hash
        return True

    def cleanup_hashes(self) -> bool:
        db_dates = self.storage.get_all_dates()
        removed = [d for d in self._cache if d not in db_dates]
        for date in removed:
            del self._cache[date]
            logger.info(f"Удалён устаревший хэш для {date}")
        return bool(removed)


def main() -> None:
    storage = ScheduleStorage()
    storage.create_database()

    if not os.path.isdir(DOCS_DIR):
        logger.error(f"Папка {DOCS_DIR} не найдена")
        return

    files = find_all_docx(DOCS_DIR)
    if not files:
        logger.info("DOCX файлов нет")
        return

    logger.info(f"Найдено файлов: {len(files)}")

    service = ScheduleService(
        parser=ScheduleParser(GROUP),
        storage=storage,
        hashes=HashStorage(),
    )
    service.load_hashes()

    has_changes = False
    for filepath in files:
        try:
            if service.process_file(filepath):
                has_changes = True
        except Exception as error:
            logger.error(f"Ошибка {filepath}: {error}")

    if service.cleanup_hashes():
        has_changes = True

    service.save_hashes()

    logger.info(
        "Обнаружены изменения в расписании" if has_changes
        else "Изменений нет"
    )


if __name__ == "__main__":
    main()
