import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.schemas import City, DayForecast

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
USER_AGENT = {"User-Agent": "TravelWeatherPlanner/1.0 (github.com/Ineydicon/travel-weather-planner)"}
TIMEOUT = httpx.Timeout(10.0)

DAILY_FIELDS = [
    "temperature_2m_min",
    "temperature_2m_max",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "uv_index_max",
    "weather_code",
]

CACHE_TTL_SECONDS = 30 * 60  # щоб не перевищувати ліміти Open-Meteo
_cache: dict[tuple, tuple[float, object]] = {}


def _cache_get(key: tuple):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _cache_set(key: tuple, value) -> None:
    _cache[key] = (time.monotonic(), value)


class WeatherServiceError(Exception):
    pass


class CityNotFoundError(WeatherServiceError):
    pass


async def _get_json(client: httpx.AsyncClient, url: str, params: dict,
                    headers: dict | None = None) -> dict:
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException:
        raise WeatherServiceError("Open-Meteo не відповідає (тайм-аут). Спробуйте пізніше.")
    except httpx.RequestError as e:
        raise WeatherServiceError(f"Немає з'єднання з Open-Meteo ({type(e).__name__}). "
                                  "Перевірте інтернет.")

    if response.status_code == 429:
        raise WeatherServiceError("Перевищено ліміт запитів до Open-Meteo. Спробуйте пізніше.")
    if response.status_code != 200:
        try:
            reason = response.json().get("reason", "")
        except ValueError:
            reason = response.text[:200]
        raise WeatherServiceError(f"Open-Meteo повернув помилку {response.status_code}: {reason}")

    try:
        return response.json()
    except ValueError:
        raise WeatherServiceError("Open-Meteo повернув некоректну відповідь (не JSON).")


# Open-Meteo не знаходить українські міста за російськими та застарілими назвами
CITY_ALIASES = {
    "киев": "Київ", "kiev": "Київ", "kyiv": "Київ", "харьков": "Харків", "kharkov": "Харків", "kharkiv": "Харків",
    "одесса": "Одеса", "львов": "Львів", "lvov": "Львів", "odessa": "Одеса", "днепр": "Дніпро",
    "днепропетровск": "Дніпро", "dnepr": "Дніпро", "dnipropetrovsk": "Дніпро",
    "николаев": "Миколаїв", "nikolaev": "Миколаїв", "запорожье": "Запоріжжя",
    "zaporozhye": "Запоріжжя", "кировоград": "Кропивницький", "кропивницкий": "Кропивницький",
    "чернигов": "Чернігів", "chernigov": "Чернігів", "ровно": "Рівне", "rovno": "Рівне",
    "винница": "Вінниця", "ивано-франковск": "Івано-Франківськ", "тернополь": "Тернопіль",
    "хмельницкий": "Хмельницький", "черкассы": "Черкаси", "сумы": "Суми", "луцк": "Луцьк",
    "черновцы": "Чернівці", "кривой рог": "Кривий Ріг", "каменец-подольский": "Кам'янець-Подільський",
    "белая церковь": "Біла Церква", "мариуполь": "Маріуполь", "лисичанск": "Лисичанськ",
    "донецк": "Донецьк", "donetsk": "Донецьк", "луганск": "Луганськ", "lugansk": "Луганськ",
    "горловка": "Горлівка", "макеевка": "Макіївка", "краматорск": "Краматорськ",
    "славянск": "Слов'янськ", "северодонецк": "Сєвєродонецьк", "бахмут": "Бахмут",
    "мелитополь": "Мелітополь", "бердянск": "Бердянськ", "никополь": "Нікополь",
    "симферополь": "Сімферополь", "ялта": "Ялта", "керчь": "Керч", "евпатория": "Євпаторія",
    "житомир": "Житомир", "полтава": "Полтава", "херсон": "Херсон", "ужгород": "Ужгород",
}


PREFIXES = ("м.", "с.", "смт", "смт.", "місто", "село", "г.", "город")
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "'": "", "ы": "y", "э": "e", "ъ": "", "ё": "io",
    "є": "ie", "ї": "i", "й": "i", "ю": "iu", "я": "ia",
}
WORD_START = {"є": "ye", "ї": "yi", "й": "y", "ю": "yu", "я": "ya", "ё": "yo"}


def normalize_city(name: str) -> str:
    name = re.sub("[’ʼ`]", "'", name).split(",")[0]
    words = name.split()
    if len(words) > 1 and words[0].lower() in PREFIXES:
        words = words[1:]
    name = " ".join(words).strip(" .")
    return CITY_ALIASES.get(name.lower().replace("ё", "е"), name)


def transliterate(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        low, prev = ch.lower(), text[i - 1].lower() if i else " "
        if low == "г" and prev == "з":
            lat = "gh"
        elif low in WORD_START and (prev.isspace() or prev == "-"):
            lat = WORD_START[low]
        else:
            lat = TRANSLIT.get(low, ch)
        out.append(lat.capitalize() if ch.isupper() else lat)
    return "".join(out)


async def search_cities(name: str, count: int = 5,
                        client: httpx.AsyncClient | None = None) -> list[City]:
    query = normalize_city(name)
    key = ("city", query.lower(), count)
    if client is None and (cached := _cache_get(key)) is not None:
        return cached

    variants = [query]
    if re.search("[а-яіїєґё]", query, re.IGNORECASE):
        variants.append(transliterate(query))
    results, error = [], None
    async with _client(client) as c:
        try:
            for variant in variants:
                params = {"name": variant, "count": max(count, 10), "language": "uk", "format": "json"}
                results = (await _get_json(c, GEOCODING_URL, params)).get("results") or []
                if results:
                    break
        except WeatherServiceError as e:
            error = e
        if not results:
            cities = await _search_osm(c, query, count)
            if not cities:
                raise error or CityNotFoundError(f"Місто «{name}» не знайдено. Перевірте назву.")
            _cache_set(key, cities)
            return cities

    results.sort(key=lambda r: r.get("population") or 0, reverse=True)
    cities = [
        City(
            name=r["name"],
            country=r.get("country", ""),
            region=r.get("admin1"),
            latitude=r["latitude"],
            longitude=r["longitude"],
            timezone=r.get("timezone", "auto"),
        )
        for r in results[:count]
    ]
    _cache_set(key, cities)
    return cities


async def _search_osm(c: httpx.AsyncClient, query: str, count: int) -> list[City]:
    params = {"q": query, "format": "jsonv2", "limit": count, "featureType": "settlement",
              "addressdetails": 1, "accept-language": "uk"}
    try:
        data = await _get_json(c, NOMINATIM_URL, params, USER_AGENT)
    except WeatherServiceError:
        return []
    cities = []
    for r in data if isinstance(data, list) else []:
        address = r.get("address", {})
        cities.append(City(
            name=r.get("name") or r.get("display_name", query).split(",")[0],
            country=address.get("country", ""),
            region=address.get("state"),
            latitude=float(r["lat"]),
            longitude=float(r["lon"]),
            timezone="auto",
        ))
    return cities


async def get_forecast(city: City, date_from: date, date_to: date,
                       client: httpx.AsyncClient | None = None) -> list[DayForecast]:
    key = ("forecast", round(city.latitude, 2), round(city.longitude, 2), date_from, date_to)
    if client is None and (cached := _cache_get(key)) is not None:
        return cached

    async with _client(client) as c:
        try:
            days = await _forecast_open_meteo(c, city, date_from, date_to)
        except WeatherServiceError as e:
            try:
                days = await _forecast_met(c, city, date_from, date_to)
            except WeatherServiceError:
                raise e
    _cache_set(key, days)
    return days


async def _forecast_open_meteo(c: httpx.AsyncClient, city: City, date_from: date,
                               date_to: date) -> list[DayForecast]:
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": ",".join(DAILY_FIELDS),
        "wind_speed_unit": "ms",
        "timezone": "auto",
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
    }
    data = await _get_json(c, FORECAST_URL, params)

    daily = data.get("daily")
    if not daily or "time" not in daily:
        raise WeatherServiceError("Відповідь Open-Meteo не містить щоденного прогнозу.")

    def value(field: str, i: int, default: float = 0):
        v = daily.get(field, [None] * len(daily["time"]))[i]
        return default if v is None else v

    return [
        DayForecast(
            day=day,
            temp_min=value("temperature_2m_min", i),
            temp_max=value("temperature_2m_max", i),
            precipitation_sum=value("precipitation_sum", i),
            precipitation_probability=int(value("precipitation_probability_max", i)),
            wind_speed_max=value("wind_speed_10m_max", i),
            uv_index_max=value("uv_index_max", i),
            weather_code=int(value("weather_code", i)),
        )
        for i, day in enumerate(daily["time"])
    ]


# Символи MET Norway -> коди WMO (як у Open-Meteo), від найнебезпечнішого
MET_SYMBOLS = [("thunder", 95), ("heavysnow", 75), ("lightsnow", 71), ("snow", 73),
               ("sleet", 66), ("heavyrain", 65), ("lightrain", 61), ("rainshowers", 80),
               ("rain", 63), ("fog", 45), ("cloudy", 3), ("partlycloudy", 2),
               ("fair", 1), ("clearsky", 0)]


def _met_code(symbol: str) -> tuple[int, int]:
    for rank, (name, code) in enumerate(MET_SYMBOLS):
        if symbol.startswith(name) if name == "cloudy" else name in symbol:
            return rank, code
    return len(MET_SYMBOLS), 3


def _city_tz(city: City):
    try:
        return ZoneInfo(city.timezone)
    except Exception:
        return timezone(timedelta(hours=round(city.longitude / 15)))


async def _forecast_met(c: httpx.AsyncClient, city: City, date_from: date,
                        date_to: date) -> list[DayForecast]:
    params = {"lat": round(city.latitude, 4), "lon": round(city.longitude, 4)}
    data = await _get_json(c, MET_URL, params, USER_AGENT)
    tz = _city_tz(city)
    days: dict[date, dict] = {}
    for step in data.get("properties", {}).get("timeseries", []):
        local = datetime.fromisoformat(step["time"].replace("Z", "+00:00")).astimezone(tz)
        if not date_from <= local.date() <= date_to:
            continue
        d = days.setdefault(local.date(), {"t": [], "rain": 0.0, "prob": 0, "wind": 0.0,
                                           "uv": 0.0, "symbol": (len(MET_SYMBOLS), 3)})
        now = step["data"]["instant"]["details"]
        d["t"].append(now.get("air_temperature", 0))
        d["wind"] = max(d["wind"], now.get("wind_speed", 0))
        d["uv"] = max(d["uv"], now.get("ultraviolet_index_clear_sky", 0))
        period = step["data"].get("next_1_hours") or step["data"].get("next_6_hours") or {}
        details = period.get("details", {})
        d["rain"] += details.get("precipitation_amount", 0)
        amount = details.get("precipitation_amount", 0)
        prob = details.get("probability_of_precipitation")
        if prob is None:  # у 6-годинних кроках MET Norway ймовірності немає
            prob = 80 if amount >= 2 else 60 if amount > 0 else 0
        d["prob"] = max(d["prob"], int(prob))
        if symbol := period.get("summary", {}).get("symbol_code"):
            d["symbol"] = min(d["symbol"], _met_code(symbol))

    result = []
    day = date_from
    while day <= date_to:
        if day not in days:
            raise WeatherServiceError("Резервний прогноз (MET Norway) доступний лише на ~9 днів.")
        d = days[day]
        result.append(DayForecast(day=day, temp_min=min(d["t"]), temp_max=max(d["t"]),
                                  precipitation_sum=round(d["rain"], 1),
                                  precipitation_probability=d["prob"],
                                  wind_speed_max=d["wind"], uv_index_max=d["uv"],
                                  weather_code=d["symbol"][1]))
        day += timedelta(days=1)
    return result


class _client:

    def __init__(self, client: httpx.AsyncClient | None):
        self._external = client
        self._own: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._external is not None:
            return self._external
        self._own = httpx.AsyncClient(timeout=TIMEOUT)
        return self._own

    async def __aexit__(self, *exc):
        if self._own is not None:
            await self._own.aclose()
