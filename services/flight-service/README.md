# Flight Service

Каталог рейсов в памяти без подключения БД. Python 3.13.15, FastAPI, Pydantic v2.
При запуске загружаются аэропорты Шереметьево и Пулково и рейс AFL031:
Санкт-Петербург → Москва, 2021-10-08 20:00 Europe/Moscow, цена 1500 рублей.

Из корня репозитория:

```bash
uv sync --frozen --all-packages
uv run --package flight-service python -m flight_service.main
```

По умолчанию порт 8060. Настройки: FLIGHT_HOST и FLIGHT_PORT.
Swagger UI: http://localhost:8060/docs.

| Метод | Маршрут | Результат |
|---|---|---|
| GET | /manage/health | 200, {"status":"UP"} |
| GET | /internal/v1/flights?page=1&size=10 | Страница рейсов |
| GET | /internal/v1/flights/{flightNumber} | Рейс или 404 |

Заголовок X-User-Name не требуется. Нумерация страниц начинается с 1,
размер страницы от 1 до 100, сортировка по id. Страница за пределами каталога
пустая. Ошибки валидации возвращают 400. Контракт — корневой openapi.yaml.

Слои: domain — неизменяемые модели; application — сценарии и Protocol репозитория;
infrastructure — каталог в памяти; presentation — HTTP и DTO; main — сборка.
Для следующего этапа можно заменить репозиторий адаптером PostgreSQL.
Каталог доступен только для чтения, постоянное хранение пока не реализовано.

Семь unit-тестов:

```bash
uv run --all-packages pytest services/flight-service/tests
uv run --all-packages pytest
uv run --all-packages mypy
uv run --all-packages ruff check services
uv run --all-packages ruff format --check services
```
