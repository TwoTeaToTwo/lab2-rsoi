# Ticket Service

Python 3.13.15, FastAPI, Pydantic v2. Рабочее приложение использует PostgreSQL через SQLAlchemy и asyncpg.
Unit-тесты используют InMemory и не требуют БД.

Из корня репозитория:

```bash
uv sync --frozen --all-packages
export TICKET_DATABASE_URL='postgresql+asyncpg://ticket:YOUR_PASSWORD@localhost:5432/ticket'
uv run --all-packages alembic -c services/ticket-service/alembic.ini upgrade head
uv run --package ticket-service python -m ticket_service.main
```

Предварительно создайте отдельную БД ticket и ее пользователя.
TICKET_DATABASE_URL обязателен, читается также из корневого .env.
Специальные символы пароля нужно URL-кодировать. В Docker имя хоста БД — postgres.
Порт 8070; настройки TICKET_HOST и TICKET_PORT.
Миграции применяются до запуска; приложение не создает таблицы автоматически.
Health проверяет доступ к таблице ticket; недоступность БД возвращает JSON 503.
При остановке приложения закрывается пул соединений.
Swagger UI: http://localhost:8070/docs.

| Метод | Маршрут | Результат |
|---|---|---|
| GET | /manage/health | 200, {"status":"UP"} |
| GET | /internal/v1/tickets | Билеты пользователя, включая отмененные |
| GET | /internal/v1/tickets/{ticketUid} | Билет пользователя |
| PUT | /internal/v1/tickets/{ticketUid} | 201 при создании, 200 при повторе |
| PUT | /internal/v1/tickets/{ticketUid}/cancellation | 204 без тела |

Все внутренние маршруты требуют X-User-Name. UUID передает Gateway.
Тело создания: {"flightNumber":"AFL031","price":1500}.
Рейс и цену предварительно проверяет Gateway; Ticket не вызывает другие сервисы.
Список упорядочен по созданию. Чужой и отсутствующий билет возвращают 404,
измененные параметры при повторном UUID — 409, ошибки валидации — 400.
Созданный билет имеет статус PAID; отмена устанавливает CANCELED.
Повтор создания отмененного билета возвращает CANCELED и не активирует его.
Бонусную операцию при возврате выполняет Gateway.

Слои: domain — модели и правила; application — сценарии, Protocol репозитория
и Unit of Work; infrastructure — ORM-модель и PostgreSQL/InMemory-адаптеры;
presentation — HTTP и DTO; main — сборка приложения.
В PostgreSQL билет сохраняется одной транзакцией; без commit изменения откатываются.
Уникальный ticket_uid и транзакционная advisory-блокировка UUID защищают
конкурентное создание, SELECT FOR UPDATE — изменение существующего билета.
Каждая транзакция получает свой AsyncSession; блокировки работают между процессами.
Список сортируется по id. Параметры покупки и статус отмены хранятся в ticket:
отдельная таблица операций для текущего контракта не требуется.
У InMemory данные теряются при перезапуске и блокировки действуют в одном процессе.

Семь unit-тестов:

```bash
uv run --all-packages pytest services/ticket-service/tests
uv run --all-packages pytest
uv run --all-packages mypy
uv run --all-packages ruff check services
uv run --all-packages ruff format --check services
```


Три PostgreSQL-интеграционных теста проверяют сохранение и отмену, конкурентные
UUID и откат. По умолчанию они пропускаются. Создайте отдельную тестовую БД:

```bash
export TICKET_TEST_DATABASE_URL='postgresql+asyncpg://ticket:YOUR_PASSWORD@localhost:5432/ticket_test'
TICKET_DATABASE_URL="$TICKET_TEST_DATABASE_URL" uv run --all-packages alembic -c services/ticket-service/alembic.ini upgrade head
uv run --all-packages pytest services/ticket-service/tests/ticket_tests/test_postgres.py
```

Тесты записывают данные с уникальными владельцами. Используйте тестовую БД.
Alembic-скрипты находятся в migrations, как и в Bonus Service.
## Docker Compose

Из корня репозитория:

```bash
docker compose up --build -d --wait
docker compose logs ticket-service
```

Compose запускает PostgreSQL 13, Bonus и Ticket. Роль ticket и база ticket
создаются шагом postgres-init, включая запуск на существующем volume.
Существующие базы и пароли не меняются. Таблицы создает только Alembic.
Ticket ожидает healthcheck PostgreSQL и успешное завершение postgres-init,
затем выполняет alembic upgrade head перед запуском приложения.
Ошибка миграции не позволяет запустить приложение.

Параметры из .env.example: TICKET_DB_PASSWORD=test, TICKET_PORT=8070.
При существующей роли укажите ее действующий пароль.
Пароль передается отдельно, URL подключения строится с корректным кодированием.
Python 3.13.15; зависимости устанавливаются через uv по uv.lock без dev-пакетов.
Контейнер работает от пользователя ticket. Данные сохраняются в volume db-data.

Health: http://localhost:8070/manage/health. Swagger: http://localhost:8070/docs.

Если DNS сборки Docker на Linux не работает:

```bash
BONUS_BUILD_NETWORK=host TICKET_BUILD_NETWORK=host docker compose up --build -d --wait
```

Остановка с сохранением данных: docker compose down.
