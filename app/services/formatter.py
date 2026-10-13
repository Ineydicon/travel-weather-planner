"""Перетворення прогнозу та чек-листа на текст повідомлення для Telegram."""
from app.schemas import ChecklistItem, City, DayForecast

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


def format_plan_message(city: City, days: list[DayForecast],
                        checklist: list[ChecklistItem]) -> str:
    place = f"{city.name}, {city.country}" if city.country else city.name
    period = f"{days[0].day:%d.%m} – {days[-1].day:%d.%m.%Y}"
    lines = [f"🧳 Поїздка: {place}", f"📅 {period}", "", "🌤 Прогноз:"]

    for d in days:
        sky = WEATHER_TEXT.get(d.weather_code, "—")
        lines.append(f"• {d.day:%d.%m}: {d.temp_min:+.0f}…{d.temp_max:+.0f} °C, {sky}, "
                     f"опади {d.precipitation_probability} %, вітер {d.wind_speed_max:.0f} м/с")

    lines += ["", "✅ Що взяти:"]
    for category in CATEGORY_ORDER:
        names = [i.item for i in checklist if i.category == category]
        if names:
            lines.append(f"{category}: {', '.join(names)}")

    return "\n".join(lines)
