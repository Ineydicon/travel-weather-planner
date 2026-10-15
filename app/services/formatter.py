"""Перетворення прогнозу, статусів і чек-листа на текст повідомлення для Telegram."""
from app.schemas import ChecklistItem, City, DayForecast
from app.services.analysis import Alert

WEATHER_TEXT = {
    0: "ясно", 1: "переважно ясно", 2: "мінлива хмарність", 3: "хмарно",
    45: "туман", 48: "туман", 51: "мряка", 53: "мряка", 55: "мряка",
    56: "крижана мряка", 57: "крижана мряка", 61: "невеликий дощ", 63: "дощ",
    65: "сильний дощ", 66: "крижаний дощ", 67: "крижаний дощ", 71: "невеликий сніг",
    73: "сніг", 75: "сильний сніг", 77: "снігова крупа", 80: "злива", 81: "злива",
    82: "сильна злива", 85: "снігопад", 86: "сильний снігопад", 95: "гроза",
    96: "гроза з градом", 99: "гроза з градом",
}
CATEGORY_ORDER = ["Одяг", "Аксесуари", "Здоров'я", "Документи"]


def place_name(city: City) -> str:
    return f"{city.name}, {city.country}" if city.country else city.name


def day_line(d: DayForecast) -> str:
    sky = WEATHER_TEXT.get(d.weather_code, "—")
    return (f"{d.temp_min:+.0f}…{d.temp_max:+.0f} °C, {sky}, "
            f"опади {d.precipitation_probability} %, вітер {d.wind_speed_max:.0f} м/с")


def _alerts_block(alerts: list[Alert] | None) -> list[str]:
    if not alerts:
        return []
    return ["", "📢 Статус:"] + [a.text for a in alerts]


def _checklist_block(checklist: list[ChecklistItem], skip_always: bool = False) -> list[str]:
    lines = []
    for category in CATEGORY_ORDER:
        names = [i.item for i in checklist
                 if i.category == category and not (skip_always and i.reason == "Завжди")]
        if names:
            lines.append(f"{category}: {', '.join(names)}")
    return lines


def format_plan_message(city: City, days: list[DayForecast], checklist: list[ChecklistItem],
                        alerts: list[Alert] | None = None) -> str:
    """Повідомлення для поїздки: прогноз по днях + статуси + повний чек-ліст."""
    period = f"{days[0].day:%d.%m} – {days[-1].day:%d.%m.%Y}"
    lines = [f"🧳 Поїздка: {place_name(city)}", f"📅 {period}", "", "🌤 Прогноз:"]
    lines += [f"• {d.day:%d.%m}: {day_line(d)}" for d in days]
    lines += _alerts_block(alerts)
    lines += ["", "✅ Що взяти:"] + _checklist_block(checklist)
    return "\n".join(lines)


def format_today_message(city: City, day: DayForecast, checklist: list[ChecklistItem],
                         alerts: list[Alert], greeting: str = "🌤 Погода на сьогодні") -> str:
    """Коротке щоденне повідомлення: погода + статуси + що взяти (без «завжди»-речей)."""
    lines = [f"{greeting}", f"📍 {place_name(city)}, {day.day:%d.%m}", "", day_line(day)]
    lines += _alerts_block(alerts)
    items = _checklist_block(checklist, skip_always=True)
    if items:
        lines += ["", "🎒 Візьміть із собою:"] + items
    return "\n".join(lines)


def format_alert_message(city: City, alerts: list[Alert]) -> str:
    """Термінове попередження (надсилається лише при небезпечній погоді)."""
    lines = [f"⚠️ ПОПЕРЕДЖЕННЯ — {place_name(city)}"] + [a.text for a in alerts if a.is_severe]
    return "\n".join(lines)
