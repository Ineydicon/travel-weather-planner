import re
import time
from datetime import date

import httpx

from app.schemas import City, DayForecast

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "TravelWeatherPlanner/1.0 (github.com/Ineydicon/travel-weather-planner)"}
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
    results = []
    async with _client(client) as c:
        for variant in variants:
            params = {"name": variant, "count": max(count, 10), "language": "uk", "format": "json"}
            results = (await _get_json(c, GEOCODING_URL, params)).get("results") or []
            if results:
                break
        if not results:
            cities = await _search_osm(c, query, count)
            if not cities:
                raise CityNotFoundError(f"Місто «{name}» не знайдено. Перевірте назву.")
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
        data = await _get_json(c, NOMINATIM_URL, params, NOMINATIM_HEADERS)
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

    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": ",".join(DAILY_FIELDS),
        "wind_speed_unit": "ms",
        "timezone": "auto",
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
    }
    async with _client(client) as c:
        data = await _get_json(c, FORECAST_URL, params)

    daily = data.get("daily")
    if not daily or "time" not in daily:
        raise WeatherServiceError("Відповідь Open-Meteo не містить щоденного прогнозу.")

    def value(field: str, i: int, default: float = 0):
        v = daily.get(field, [None] * len(daily["time"]))[i]
        return default if v is None else v

    days = [
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
    _cache_set(key, days)
    return days


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
