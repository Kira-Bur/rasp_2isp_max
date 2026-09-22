import os
import re
import json
import sqlite3
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Tuple

from maxapi import Bot, Dispatcher
from maxapi.enums import HTTPMethod
from maxapi.types import Command, MessageCreated

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ISPDateBot")

BOT_TOKEN = "ТОКЕН"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "schedule.db")
GROUP = "2 ИСП"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


def get_all_dates() -> List[str]:
    if not os.path.exists(DB_FILE):
        logger.error(f"База {DB_FILE} не найдена")
        return []

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT date FROM schedule WHERE group_name = ?",
            (GROUP,)
        )
        dates = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка чтения дат: {e}")
        return []
    finally:
        conn.close()

    parsed = []
    for d in dates:
        try:
            parsed.append((datetime.strptime(d, "%d.%m.%Y"), d))
        except ValueError:
            continue

    parsed.sort(key=lambda x: x[0])
    return [d for _, d in parsed]


def get_lessons(date_str: str) -> Optional[dict]:
    if not os.path.exists(DB_FILE):
        return None

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT lessons FROM schedule WHERE date = ? AND group_name = ?",
            (date_str, GROUP)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return json.loads(row[0])
    except Exception as e:
        logger.error(f"Ошибка чтения расписания: {e}")
        return None
    finally:
        conn.close()


def format_dates_list(dates: List[str]) -> str:
    if not dates:
        return f"В базе нет расписаний для группы {GROUP}"

    weekdays = [
        "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"
    ]

    lines = [f"Доступные даты для группы {GROUP}:", ""]
    for d in dates:
        try:
            dt = datetime.strptime(d, "%d.%m.%Y")
            wd = weekdays[dt.weekday()]
            lines.append(f"{d} ({wd})")
        except ValueError:
            lines.append(d)

    lines.append("")
    lines.append("Отправьте /schedule ДД.ММ.ГГГГ для получения расписания")
    lines.append("Или /today, /tomorrow для быстрого доступа")

    return "\n".join(lines)


def format_schedule(date_str: str, lessons: dict) -> str:
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        dt = None

    weekdays_full = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ]

    header = f"Расписание группы {GROUP}"
    if dt:
        header += f"\n{weekdays_full[dt.weekday()]}, {date_str}"
    else:
        header += f"\n{date_str}"

    lines = [header, ""]

    for number in ["1", "2", "3", "4"]:
        lesson = lessons.get(number) or {}
        subject = lesson.get("subject") or "—"
        room = lesson.get("room") or "—"
        teacher = lesson.get("teacher") or "—"

        lines.append(f"{number} пара: {subject}")
        lines.append(f"   Кабинет: {room}")
        lines.append(f"   Преподаватель: {teacher}")
        lines.append("")

    return "\n".join(lines).rstrip()


async def send_text(chat_id: int, text: str) -> bool:
    try:
        await bot.request(
            method=HTTPMethod.POST,
            path="/messages",
            params={"chat_id": chat_id},
            json={"text": text}
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в чат {chat_id}: {e}")
        return False


def resolve_date(arg: str) -> Optional[str]:
    arg = arg.strip().lower()

    if arg in ("today", "сегодня"):
        return datetime.now().strftime("%d.%m.%Y")
    if arg in ("tomorrow", "завтра"):
        from datetime import timedelta
        return (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")

    match = re.match(r"^(\d{1,2})[\.\-/](\d{1,2})(?:[\.\-/](\d{4}))?$", arg)
    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else datetime.now().year

    try:
        return datetime(year, month, day).strftime("%d.%m.%Y")
    except ValueError:
        return None


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    await event.message.answer(
        text=(
            f"Бот расписания группы {GROUP}\n\n"
            "Команды:\n"
            "/dates — список доступных дат\n"
            "/schedule ДД.ММ.ГГГГ — расписание на дату\n"
            "/today — расписание на сегодня\n"
            "/tomorrow — расписание на завтра"
        )
    )


@dp.message_created(Command("dates"))
async def cmd_dates(event: MessageCreated):
    dates = get_all_dates()
    text = format_dates_list(dates)
    await event.message.answer(text=text)


@dp.message_created(Command("today"))
async def cmd_today(event: MessageCreated):
    date_str = datetime.now().strftime("%d.%m.%Y")
    lessons = get_lessons(date_str)

    if not lessons:
        await event.message.answer(
            text=f"Нет расписания на {date_str}"
        )
        return

    await event.message.answer(text=format_schedule(date_str, lessons))


@dp.message_created(Command("tomorrow"))
async def cmd_tomorrow(event: MessageCreated):
    from datetime import timedelta
    date_str = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    lessons = get_lessons(date_str)

    if not lessons:
        await event.message.answer(
            text=f"Нет расписания на {date_str}"
        )
        return

    await event.message.answer(text=format_schedule(date_str, lessons))


@dp.message_created(Command("schedule"))
async def cmd_schedule(event: MessageCreated):
    text = event.message.body.text if hasattr(event.message, "body") else ""
    parts = text.strip().split(maxsplit=1)

    if len(parts) < 2:
        await event.message.answer(
            text="Укажите дату: /schedule ДД.ММ.ГГГГ"
        )
        return

    date_str = resolve_date(parts[1])

    if not date_str:
        await event.message.answer(
            text="Неверный формат даты. Используйте ДД.ММ.ГГГГ"
        )
        return

    lessons = get_lessons(date_str)

    if not lessons:
        available = get_all_dates()
        hint = ""
        if available:
            hint = "\n\nДоступные даты:\n" + "\n".join(available[:10])
        await event.message.answer(
            text=f"Нет расписания на {date_str}{hint}"
        )
        return

    await event.message.answer(text=format_schedule(date_str, lessons))


async def main():
    logger.info("Запуск MAX бота расписания")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
