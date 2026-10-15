from app.schemas import ChecklistItem, DayForecast

SNOW_CODES = {71, 73, 75, 77, 85, 86}


def build_checklist(days: list[DayForecast]) -> list[ChecklistItem]:
    if not days:
        return []

    t_min = min(d.temp_min for d in days)
    t_max = max(d.temp_max for d in days)
    rain_prob = max(d.precipitation_probability for d in days)
    rain_sum = max(d.precipitation_sum for d in days)
    wind = max(d.wind_speed_max for d in days)
    uv = max(d.uv_index_max for d in days)
    snow = any(d.weather_code in SNOW_CODES for d in days)

    items: list[ChecklistItem] = []

    def add(category: str, names: list[str], reason: str) -> None:
        for name in names:
            items.append(ChecklistItem(category=category, item=name, reason=reason))

    if t_min < 0:
        add("Одяг", ["Зимова куртка", "Шапка", "Рукавиці", "Термобілизна"],
            f"Мінімальна температура {t_min:.0f} °C")
    elif t_min < 10:
        add("Одяг", ["Тепла куртка", "Светр"], f"Мінімальна температура {t_min:.0f} °C")
    if 10 <= t_max < 20:
        add("Одяг", ["Легка куртка або худі"], f"Максимальна температура {t_max:.0f} °C")
    if t_max >= 25:
        add("Одяг", ["Легкий одяг", "Головний убір"], f"Максимальна температура {t_max:.0f} °C")
        add("Здоров'я", ["Пляшка для води"], f"Спека до {t_max:.0f} °C")

    if rain_prob >= 50 or rain_sum >= 1:
        add("Аксесуари", ["Парасолька", "Водонепроникне взуття"],
            f"Ймовірність опадів до {rain_prob} %")
    if snow:
        add("Одяг", ["Зимове взуття з протектором"], "Очікується сніг")
    if wind >= 10:
        add("Одяг", ["Вітровка"], f"Вітер до {wind:.0f} м/с")
    if uv >= 6:
        add("Аксесуари", ["Сонцезахисні окуляри"], f"UV-індекс до {uv:.0f}")
        add("Здоров'я", ["Сонцезахисний крем SPF 50"], f"UV-індекс до {uv:.0f}")

    add("Документи", ["Паспорт / ID-картка"], "Завжди")
    add("Аксесуари", ["Зарядний пристрій"], "Завжди")
    add("Здоров'я", ["Аптечка"], "Завжди")
    if len(days) > 3:
        add("Одяг", ["Додатковий комплект одягу"], f"Поїздка на {len(days)} днів")
        add("Здоров'я", ["Засоби гігієни"], f"Поїздка на {len(days)} днів")

    return items
