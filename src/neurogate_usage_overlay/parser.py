from __future__ import annotations

import re
from datetime import datetime

from .models import UsageSnapshot, UsageWindow


NUMBER_RE = re.compile(r"\d[\d \t\u00a0]*")
WINDOW_TITLES = ("5 часов", "24 часа", "7 дней")
PLAN_SKIP_LINES = {
    "лимиты",
    "обновить",
    "кабинет клиента",
    "подробная информация о вашем тарифе",
}
PLAN_STOP_LINES = {
    "модель",
    "платный сброс",
    "история",
    "использовано",
    "токены",
    "кеш",
    "кэш",
}


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def format_number(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}".replace(",", " ")


def _first_number_after(label: str, text: str) -> int | None:
    pattern = rf"{re.escape(label)}\s*[:：]?\s*({NUMBER_RE.pattern})"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_int(match.group(1)) if match else None


def _first_limit_pair(text: str) -> tuple[int | None, int | None]:
    match = re.search(
        rf"ЛИМИТЫ\s+ТАРИФА\s*({NUMBER_RE.pattern})\s*/\s*({NUMBER_RE.pattern})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf"({NUMBER_RE.pattern})\s*/\s*({NUMBER_RE.pattern})",
            text,
            flags=re.IGNORECASE,
        )
    if not match:
        return None, None
    return parse_int(match.group(1)), parse_int(match.group(2))


def _number_before_label(label: str, segment: str) -> int | None:
    lines = [line.strip() for line in segment.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.search(re.escape(label), line, flags=re.IGNORECASE):
            for candidate in reversed(lines[:index]):
                if re.fullmatch(NUMBER_RE, candidate):
                    return parse_int(candidate)
            return None
    return None


def _extract_segment(text: str, start_label: str, next_labels: tuple[str, ...]) -> str:
    label_pattern = rf"^{re.escape(start_label)}(?:\b|\s|·|$)"
    start = re.search(label_pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not start:
        return ""
    end_index = len(text)
    for label in next_labels:
        next_pattern = rf"^{re.escape(label)}(?:\b|\s|·|$)"
        found = re.search(next_pattern, text[start.end() :], flags=re.IGNORECASE | re.MULTILINE)
        if found:
            end_index = min(end_index, start.end() + found.start())
    return text[start.start() : end_index]


def _parse_plan_name(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    marker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if "подробная информация о вашем тарифе" in line.lower()
        ),
        None,
    )
    if marker_index is None:
        marker_index = next((index for index, line in enumerate(lines) if line.lower() == "лимиты"), None)
    if marker_index is not None:
        for candidate in lines[marker_index + 1 : marker_index + 8]:
            cleaned = candidate.strip()
            candidate_key = cleaned.lower()
            if candidate_key in PLAN_SKIP_LINES:
                continue
            if candidate_key.startswith("активен ещё") or candidate_key.startswith("активен еще"):
                continue
            if candidate_key in PLAN_STOP_LINES:
                break
            if re.fullmatch(r"\d+\s*(usdt|usd|\$)?", candidate_key):
                continue
            return cleaned
    return None


def _parse_window(title: str, segment: str) -> UsageWindow | None:
    if not segment:
        return None
    reset_match = re.search(r"Сброс\s+через\s+([^\n\r]+)", segment, flags=re.IGNORECASE)
    used, total = _first_limit_pair(segment)
    credits_remaining = _number_before_label("Кредитов осталось", segment)
    return UsageWindow(
        title=title,
        tokens=_first_number_after("ТОКЕНЫ", segment),
        cache=_first_number_after("КЕШ", segment),
        limit_used=used,
        limit_total=total,
        credits_remaining=credits_remaining,
        reset_text=reset_match.group(1).strip() if reset_match else None,
    )


def parse_usage_text(text: str, source_url: str | None = None) -> UsageSnapshot:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    snapshot = UsageSnapshot(
        updated_at=datetime.now().astimezone(),
        source_url=source_url,
        raw_text=normalized,
    )

    snapshot.account = _parse_plan_name(normalized)

    model_match = re.search(r"МОДЕЛЬ\s+([^\n\r]+)", normalized, flags=re.IGNORECASE)
    if model_match:
        model_group = model_match.group(1).strip()
        if model_group.upper() not in {"ТОКЕНЫ", "КРЕДИТЫ", "СТАТУС"}:
            snapshot.model_group = model_group
    elif "Все модели" in normalized:
        snapshot.model_group = "Все модели"

    plan_status_match = re.search(r"(активен\s+ещ[ёе]\s+[^\n\r]+)", normalized, flags=re.IGNORECASE)
    if plan_status_match:
        snapshot.plan_status = plan_status_match.group(1).strip()

    total_match = re.search(
        rf"ИСПОЛЬЗОВАНО\s*({NUMBER_RE.pattern})\s*ток",
        normalized,
        flags=re.IGNORECASE,
    )
    if total_match:
        snapshot.total_used = parse_int(total_match.group(1))

    remaining_match = re.search(
        rf"остал[оа]сь\s*:\s*({NUMBER_RE.pattern})",
        normalized,
        flags=re.IGNORECASE,
    )
    if remaining_match:
        snapshot.remaining = parse_int(remaining_match.group(1))

    for title in WINDOW_TITLES:
        next_labels = tuple(item for item in WINDOW_TITLES if item != title)
        next_labels = (*next_labels, "ИСТОРИЯ", "Последние списания", "ПЛАТНЫЙ СБРОС")
        segment = _extract_segment(normalized, title, next_labels)
        window = _parse_window(title, segment)
        if window and (
            window.credits_remaining is not None
            or window.tokens
            or window.cache
            or window.limit_used
            or window.limit_total
        ):
            snapshot.windows.append(window)

    return snapshot
