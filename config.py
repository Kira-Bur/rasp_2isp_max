# config.py
import logging

DOCS_DIR = "Расписание"
DB_FILE = "schedule.db"
HASH_FILE = "hashes.json"
GROUP = "2 ИСП"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
