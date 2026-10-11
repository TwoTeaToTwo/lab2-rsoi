# Ticket Service

Python 3.13.15, FastAPI, Pydantic v2. Билеты хранятся в памяти, подключения БД нет.
При запуске каталог билетов пустой.

Из корня репозитория:

```bash
uv sync --frozen --all-packages
uv run --package ticket-service python -m ticket_service.main
```

Порт 8070; настройки TICKET_HOST и TICKET_PORT.
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
и Unit of Work; infrastructure — транзакционное хранилище в памяти;
presentation — HTTP и DTO; main — сборка приложения.
Записи публикуются при commit, операции сериализуются блокировкой в одном процессе.
Данные теряются при перезапуске. Требуются один worker и один экземпляр сервиса.

Семь unit-тестов:

```bash
uv run --all-packages pytest services/ticket-service/tests
uv run --all-packages pytest
uv run --all-packages mypy
uv run --all-packages ruff check services
uv run --all-packages ruff format --check services
```
