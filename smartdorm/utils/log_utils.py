from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import logging
import re
from typing import Iterable

from django.conf import settings

logger = logging.getLogger(__name__)

LOG_HEADER_RE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<level>[A-Z]+)\s+(?P<logger>\S+)\s+(?P<message>.*)$"
)


@dataclass
class LogRecord:
    timestamp: str
    level: str
    logger: str
    message: str
    raw: str
    timestamp_dt: datetime | None


def get_log_file_path() -> Path:
    return Path(settings.BASE_DIR) / "logs" / "smartdorm.log"


def parse_timestamp(timestamp: str) -> datetime | None:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        logger.debug("Failed to parse log timestamp: %s", timestamp)
        return None


def parse_log_lines(lines: Iterable[str]) -> list[LogRecord]:
    records: list[LogRecord] = []
    current: LogRecord | None = None
    raw_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current, raw_lines
        if current is None:
            return
        current.raw = "\n".join(raw_lines)
        records.append(current)
        current = None
        raw_lines = []

    for line in lines:
        stripped = line.rstrip("\n")
        match = LOG_HEADER_RE.match(stripped)
        if match:
            flush_current()
            timestamp = match.group("timestamp")
            current = LogRecord(
                timestamp=timestamp,
                level=match.group("level"),
                logger=match.group("logger"),
                message=match.group("message"),
                raw="",
                timestamp_dt=parse_timestamp(timestamp),
            )
            raw_lines = [stripped]
            continue

        if current is None:
            continue

        raw_lines.append(stripped)
        current.message = f"{current.message}\n{stripped}" if current.message else stripped

    flush_current()
    return records


def read_log_records() -> list[LogRecord]:
    log_file = get_log_file_path()
    if not log_file.exists():
        return []

    with log_file.open("r", encoding="utf-8", errors="replace") as handle:
        return parse_log_lines(handle.readlines())


def filter_log_records(
    records: list[LogRecord],
    *,
    level: str | None = None,
    search: str | None = None,
) -> list[LogRecord]:
    level_value = level.upper() if level else None
    search_value = search.lower().strip() if search else None

    filtered: list[LogRecord] = []
    for record in records:
        if level_value and record.level != level_value:
            continue

        if search_value:
            haystack = "\n".join([record.timestamp, record.level, record.logger, record.message]).lower()
            if search_value not in haystack:
                continue

        filtered.append(record)

    return filtered


def get_log_page(
    *,
    limit: int = 100,
    cursor: int = 0,
    level: str | None = None,
    search: str | None = None,
) -> tuple[list[LogRecord], int | None, bool, int]:
    records = read_log_records()
    filtered = filter_log_records(records, level=level, search=search)
    filtered.reverse()  # newest first

    start = max(cursor, 0)
    end = start + max(limit, 1)
    page = filtered[start:end]
    next_cursor = end if end < len(filtered) else None
    has_more = next_cursor is not None
    return page, next_cursor, has_more, len(filtered)


def cleanup_log_file(days: int = 30) -> dict[str, int]:
    log_file = get_log_file_path()
    if not log_file.exists():
        return {"removed": 0, "kept": 0, "total": 0}

    with log_file.open("r+", encoding="utf-8", errors="replace") as handle:
        records = parse_log_lines(handle.readlines())
        cutoff = datetime.now() - timedelta(days=days)

        kept_records: list[LogRecord] = []
        removed = 0
        for record in records:
            if record.timestamp_dt and record.timestamp_dt < cutoff:
                removed += 1
                continue
            kept_records.append(record)

        cleaned_text = "\n".join(record.raw for record in kept_records)
        if cleaned_text:
            cleaned_text += "\n"

        handle.seek(0)
        handle.truncate()
        handle.write(cleaned_text)

    return {"removed": removed, "kept": len(kept_records), "total": len(records)}
