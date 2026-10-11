# Bonus Service

Python 3.13.15, FastAPI, Pydantic v2, SQLAlchemy 2, asyncpg, Alembic.
Рабочее приложение использует PostgreSQL. Unit- и HTTP-тесты внедряют InMemory
и не требуют подключения БД.

## Настройка и запуск

Создайте логическую БД bonus и отдельного пользователя, имеющего права только
на эту БД. Один PostgreSQL может обслуживать bonus, flight и ticket; каждый
сервис подключается только к своей базе. Скрипты PostgreSQL в корне шаблона
пока требуют отдельной настройки и не заменяют миграции Bonus.

Из корня репозитория:

```bash
uv sync --frozen --all-packages
export BONUS_DATABASE_URL='postgresql+asyncpg://bonus:YOUR_PASSWORD@localhost:5432/bonus'
uv run --all-packages alembic -c services/bonus-service/alembic.ini upgrade head
uv run --package bonus-service python -m bonus_service.main
```

BONUS_DATABASE_URL обязателен; также можно задать его в корневом .env (не коммитить).
Пароль со специальными символами нужно URL-кодировать.
В Docker адрес БД — имя сервиса postgres вместо localhost.

Настройки: BONUS_HOST (0.0.0.0), BONUS_PORT (8050).
Swagger UI: http://localhost:8050/docs.
Миграции применяются отдельной командой до запуска; приложение не создает таблицы.
GET /manage/health проверяет доступ к таблице счета.
При недоступности БД возвращается 503 без раскрытия деталей подключения.
Пул соединений закрывается при остановке приложения.

## Проверки

```bash
uv run --all-packages pytest
uv run --all-packages mypy
uv run --all-packages ruff check services
uv run --all-packages ruff format --check services
```

Семь unit-тестов Bonus сохранены. Четыре интеграционных теста PostgreSQL
по умолчанию пропускаются. Для них создайте отдельную тестовую БД и примените миграции:

```bash
export BONUS_TEST_DATABASE_URL='postgresql+asyncpg://bonus:YOUR_PASSWORD@localhost:5432/bonus_test'
BONUS_DATABASE_URL="$BONUS_TEST_DATABASE_URL" uv run --all-packages alembic -c services/bonus-service/alembic.ini upgrade head
uv run --all-packages pytest services/bonus-service/tests/test_postgres.py
```

Интеграционные проверки записывают данные с уникальными именами пользователей.
Используйте тестовую БД. Проверяются долговечность результатов, конкурентные
списания/повторы, единственный владелец UUID и откат всей операции.

Проверка миграций:

```bash
uv run --all-packages alembic -c services/bonus-service/alembic.ini check
```

## HTTP API

Все внутренние запросы требуют X-User-Name. Их вызывает Gateway.

| Метод | Маршрут | Результат |
|---|---|---|
| GET | /manage/health | 200, {"status":"UP"}, если БД доступна |
| GET | /internal/v1/privilege | Счет и история |
| PUT | /internal/v1/privilege/operations/{ticketUid} | 201 при покупке, 200 при повторе |
| PUT | /internal/v1/privilege/operations/{ticketUid}/reversal | Баланс и статус после возврата |

Тело покупки: {"price":1500,"paidFromBalance":false}.
Новый счет: BRONZE, баланс 0. Оплата деньгами начисляет price // 10.
Оплата бонусами списывает min(balance, price) без начисления новых баллов.
Возврат восстанавливает списанные бонусы либо снимает ранее начисленные,
не делая баланс отрицательным. Даже нулевые операции сохраняются.

Повтор покупки возвращает сохраненный исходный результат, включая прежний баланс.
Измененное тело или покупка после возврата — 409. Чужая/отсутствующая операция — 404.
Повтор возврата возвращает текущий баланс без новой истории.
Ошибки валидации — 400. Полный контракт — корневой openapi.yaml.

## Хранение и архитектура

- domain: неизменяемые модели и чистые правила расчета, без ORM.
- application: сценарии, Protocol репозитория, Unit of Work и часов.
- infrastructure: отдельные ORM-модели, PostgreSQL- и InMemory-адаптеры.
- presentation: HTTP и Pydantic DTO.
- main: сборка PostgreSQL-зависимостей и управление пулом.

Таблицы: privilege, privilege_history, bonus_operation.
Последняя сохраняет UUID, владельца, параметры покупки, исходный результат,
начисленную сумму и признак отмены. История хранит время с часовым поясом.
Уникальные ограничения защищают username и UUID операции.

Один AsyncSession принадлежит одной транзакции. Сначала блокируется UUID
через pg_advisory_xact_lock, затем счет через SELECT FOR UPDATE.
INSERT ON CONFLICT корректно обрабатывает одновременное создание счета.
Баланс, история и состояние операции сохраняются одним commit; без него
изменения откатываются. Блокировки работают между процессами и экземплярами.
InMemory остается адаптером для тестов и требует одного процесса.
