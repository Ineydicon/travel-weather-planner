from app.services.simulation import SCENARIOS

BTN_TODAY = "🌤 Погода сьогодні"
BTN_TRIP = "🧳 Поїздка"
BTN_SUB = "⏰ Щоденна розсилка"
BTN_SIM = "🧪 Симуляція"
BTN_HELP = "❓ Допомога"

MAIN_MENU = {
    "keyboard": [
        [{"text": BTN_TODAY}, {"text": BTN_TRIP}],
        [{"text": BTN_SUB}, {"text": BTN_SIM}],
        [{"text": BTN_HELP}],
    ],
    "resize_keyboard": True,
    "input_field_placeholder": "Оберіть дію або напишіть місто",
}


def _inline(rows: list[list[tuple[str, str]]]) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def trip_days_kb() -> dict:
    return _inline([[("Сьогодні", "trip:1"), ("3 дні", "trip:3")],
                    [("5 днів", "trip:5"), ("Тиждень", "trip:7")]])


def hours_kb() -> dict:
    hours = [6, 7, 8, 9, 10, 12, 18, 20]
    return _inline([[(f"{h:02d}:00", f"hour:{h}") for h in hours[:4]],
                    [(f"{h:02d}:00", f"hour:{h}") for h in hours[4:]]])


def subscription_kb() -> dict:
    return _inline([[("📨 Надіслати зараз", "sub:now")],
                    [("🏙 Змінити місто", "sub:city"), ("🕐 Змінити час", "sub:hour")],
                    [("🔕 Вимкнути", "sub:off")]])


def simulation_kb() -> dict:
    items = [(v["title"], f"sim:{k}") for k, v in SCENARIOS.items()]
    return _inline([items[:3], items[3:]])
