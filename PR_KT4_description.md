## Что сделано
Транспорт и ошибки: `apis.py`, `urls.py`, `pagination.py`, `config/exception_handler.py`,
команда `library_issue`, `test_apis.py` (тесты 20–24 из ТЗ и несколько сверх). Документация:
`ARCHITECTURE.md`, `DECISIONS.md`, README с curl-примерами.

## Какие правила где лежат
| Правило | Файл | Код при отказе |
|---|---|---|
| Нет токена | `config/settings.py` (`IsAuthenticated`), `exception_handler.py` | 401 |
| Выдаёт и принимает только библиотекарь | `services._require_librarian` | 403 |
| Чужая выдача не видна | `models.LoanQuerySet.visible_to`, `selectors.loan_get` | 404 |
| Экземпляр доступен, лимит 3, нет просрочки | `services.loan_create` | 400 |
| Продление: не более 2, не просроченной, не закрытой | `models.Loan.extend`, `services.loan_extend` | 400 |
| Повторный возврат | `models.Loan.mark_returned` | 400 |
| Одна активная выдача на экземпляр | констрейнт `one_active_loan_per_copy` | 400 |
| Мусор в `ordering` и фильтрах | `selectors._apply_ordering`, `_apply_filters` | 400 |
| Уведомление после коммита | `services._notify_issued` (`on_commit`) | не отказ |

## Как проверить
```
python manage.py test
python manage.py makemigrations --check --dry-run
grep -n "\.objects\.\|try:\|\.save()\|__all__" library/apis.py      # пусто
grep -rn "rest_framework" library/services.py library/selectors.py   # пусто
grep -rn "Q(" library/ --include='*.py' | grep -v models.py          # пусто
```
Примеры запросов: раздел API в README.

## Вопросы / сомнения
- Формат списков: `{"count", "next", "previous", "results"}` (стандартный DRF). Если
  контракт ожидает голый массив, нужно поменять `pagination.py`.
- Вложенные объекты (`copy`, `book`, `reader`) отдаются id.
