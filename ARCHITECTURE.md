# Архитектура

Уровень 2: `models / services / selectors / apis`. Зависимости идут только вниз:
`apis -> services, selectors -> models`. Обратных импортов нет.

| Слой | Файл | Отвечает за | Чего там быть не должно |
|---|---|---|---|
| Данные | `models.py` | поля, констрейнты, QuerySet-методы, инварианты состояния (`mark_returned`, `extend`) | чужие сценарии, права, HTTP |
| Запись | `services.py` | сценарии, права actor'а, правила предметной области, транзакции, `on_commit` | `rest_framework`, `request` |
| Чтение | `selectors.py`, `filters.py` | видимость (`visible_to`), фильтры, сортировка, `select_related` | `rest_framework`, запись в БД |
| Транспорт | `apis.py`, `urls.py` | разбор входа, вызов одной функции сервиса или селектора, выбор кода ответа | `.objects.`, `try/except`, `.save()`, Celery, бизнес-правила |
| Ошибки | `exceptions.py`, `config/exception_handler.py` | типы ошибок и единый конверт `{message, code, extra}` | бизнес-логика |
| Фон | `tasks.py` | тонкая обёртка: принять id, вызвать один сервис | правила, запросы |

## Порядок проверок в сервисе

`существование и видимость (404) -> права (403) -> правила (400) -> запись`.
Для выдачи, которой нет в видимости читателя, всегда 404, даже если действие
всё равно запрещено читателю: чужую выдачу нельзя отличить от несуществующей.

## Транзакции и гонки

- `loan_create`, `loan_return`, `loan_extend` обёрнуты в `transaction.atomic`.
- Блокировки берутся всегда в одном порядке: экземпляр, затем читатель/выдача.
- Уникальность активной выдачи держит частичный `UniqueConstraint`; `IntegrityError`
  превращается в доменную ошибку. `.exists()` до вставки не является защитой.

## Побочные эффекты

Уведомление создаётся в транзакции выдачи. Отправка ставится через
`transaction.on_commit(..., robust=True)`: если брокер недоступен, клиент не получает
500 после уже записанных данных. Задача идемпотентна (`sent_at`).

## Два входа в один домен

HTTP (`apis.py`) и команда `library_issue` вызывают один и тот же `loan_create`.
Права проверяет только сервис, поэтому обойти их вторым входом нельзя.

## Ошибки

`ApplicationError(message, *, code, extra)` и наследники: `NotFoundError` (404),
`PermissionDeniedError` (403), `BusinessValidationError` (400). Обработчик
`config/exception_handler.py` переводит их и ошибки DRF в один конверт и не трогает
заголовки ответа (`WWW-Authenticate` у 401).

## Проверки перед PR

```
grep -n "\.objects\.\|try:\|\.save()\|__all__" library/apis.py      # пусто
grep -rn "rest_framework" library/services.py library/selectors.py   # пусто
grep -rn "Q(" library/ --include='*.py' | grep -v models.py          # пусто
python manage.py makemigrations --check --dry-run
python manage.py test
```
