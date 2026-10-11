# Flight Service

Каталог рейсов в PostgreSQL через SQLAlchemy 2 и asyncpg. Python 3.13.15, FastAPI, Pydantic v2.
При применении начальной миграции загружаются аэропорты Шереметьево и Пулково и рейс AFL031:
Санкт-Петербург → Москва, 2021-10-08 20:00 Europe/Moscow, цена 1500 рублей.

Из корня репозитория:

```bash
uv sync --frozen --all-packages
export FLIGHT_DATABASE_URL='postgresql+asyncpg://flight:YOUR_PASSWORD@localhost:5432/flight'
uv run --all-packages alembic -c services/flight-service/alembic.ini upgrade head
uv run --package flight-service python -m flight_service.main
```

Предварительно создайте отдельную логическую БД flight и ее пользователя.
FLIGHT_DATABASE_URL обязателен; можно задать в корневом .env.
Специальные символы пароля нужно URL-кодировать; в Docker хост БД — postgres.
Миграции применяются отдельной командой до запуска приложения.
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
infrastructure — ORM, PostgreSQL-репозиторий, Unit of Work и InMemory;
presentation — HTTP и DTO; main — сборка и управление пулом соединений.
Домен и сценарии не зависят от ORM. Каталог доступен только для чтения.
Каждый запрос получает отдельный AsyncSession. Адаптер PostgresFlightReader
сохраняет существующий интерфейс репозитория, открывая Unit of Work для чтения.
REPEATABLE READ обеспечивает согласованность totalElements и items одной страницы.
Аэропорты загружаются сразу с рейсом без ленивых запросов после закрытия сессии.
Блокировки для чтения не требуются. Миграция задает внешние ключи,
уникальность номера рейса, неотрицательную цену и время с часовым поясом.
Health проверяет доступ к таблице flight. Недоступность БД возвращает JSON 503.
Пул закрывается при остановке приложения. Unit-тесты остаются на InMemory.

Семь unit-тестов:

```bash
uv run --all-packages pytest services/flight-service/tests
uv run --all-packages pytest
uv run --all-packages mypy
uv run --all-packages ruff check services
uv run --all-packages ruff format --check services
```


Два PostgreSQL-интеграционных теста проверяют тестовые данные и SQL-пагинацию
с откатом временных записей. Без FLIGHT_TEST_DATABASE_URL они пропускаются.
Используйте отдельную тестовую БД с примененными миграциями:

```bash
export FLIGHT_TEST_DATABASE_URL='postgresql+asyncpg://flight:YOUR_PASSWORD@localhost:5432/flight_test'
FLIGHT_DATABASE_URL="$FLIGHT_TEST_DATABASE_URL" uv run --all-packages alembic -c services/flight-service/alembic.ini upgrade head
uv run --all-packages pytest services/flight-service/tests/flight_tests/test_postgres.py
```

Проверка соответствия ORM и миграции:

```bash
uv run --all-packages alembic -c services/flight-service/alembic.ini check
uv run --all-packages mypy services/flight-service/src services/flight-service/migrations
```

Окружение миграций Flight проверяется отдельно, поскольку env.py других сервисов
имеет такое же имя модуля. Версии миграций входят также в общий прогон mypy.
## Docker Compose

Из корня репозитория:

```bash
docker compose up --build -d --wait
docker compose logs flight-service
```

Compose запускает PostgreSQL 13, Bonus, Ticket и Flight. Роль flight и база
flight создаются шагом postgres-init, включая запуск на существующем volume.
Существующие базы и пароли не меняются. Таблицы и тестовые данные создаются
миграцией Flight. Повторное применение миграций не дублирует рейс и аэропорты.

Flight ожидает healthcheck PostgreSQL и успешное завершение postgres-init,
затем выполняет alembic upgrade head перед запуском приложения.
При ошибке миграции приложение не запускается.
Python 3.13.15; зависимости устанавливаются uv по uv.lock без dev-пакетов.
Контейнер работает от пользователя flight. Данные сохраняются в volume db-data.

Параметры из .env.example: FLIGHT_DB_PASSWORD=test, FLIGHT_PORT=8060.
При существующей роли укажите ее действующий пароль. Пароль передается отдельно,
URL подключения строится с корректным кодированием.

Health: http://localhost:8060/manage/health. Swagger: http://localhost:8060/docs.

Если DNS сборки Docker на Linux не работает:

```bash
BONUS_BUILD_NETWORK=host TICKET_BUILD_NETWORK=host FLIGHT_BUILD_NETWORK=host docker compose up --build -d --wait
```

Строгая проверка кода Flight, включая миграции и контейнерный запуск:

```bash
uv run --all-packages mypy services/flight-service/src services/flight-service/migrations services/flight-service/docker
```

Остановка с сохранением данных: docker compose down.
