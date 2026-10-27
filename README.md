# Library-API# API: примеры (дописать в README.md)

Запуск: `python manage.py migrate && python manage.py runserver`.
Фоновые уведомления: `celery -A config worker -l info` (нужен Redis).

```bash
BASE=http://127.0.0.1:8000/api

# регистрация и токен
curl -X POST $BASE/register/ -H "Content-Type: application/json" \
  -d '{"username": "reader1", "password": "secret123"}'
curl -X POST $BASE/auth/token/ -H "Content-Type: application/json" \
  -d '{"username": "reader1", "password": "secret123"}'
# -> {"token": "..."}   дальше: -H "Authorization: Token <токен>"

# библиотекарь (is_staff) создаёт книгу и экземпляр
curl -X POST $BASE/books/ -H "Authorization: Token $LIB" -H "Content-Type: application/json" \
  -d '{"title": "Дюна", "author": "Герберт", "isbn": "9780441013593", "year": 1965}'
curl -X POST $BASE/copies/ -H "Authorization: Token $LIB" -H "Content-Type: application/json" \
  -d '{"book": 1, "inventory_number": "INV-001"}'

# выдача, продление, возврат
curl -X POST $BASE/loans/ -H "Authorization: Token $LIB" -H "Content-Type: application/json" \
  -d '{"copy": 1, "reader": 2}'
curl -X POST $BASE/loans/1/extend/ -H "Authorization: Token $LIB"
curl -X POST $BASE/loans/1/return/ -H "Authorization: Token $LIB"

# списки, фильтры, сортировка, страницы
curl "$BASE/books/?search=дюна&available=true&ordering=title" -H "Authorization: Token $TOKEN"
curl "$BASE/loans/?active=true&overdue=true&reader=2&page=2" -H "Authorization: Token $LIB"
curl $BASE/notifications/ -H "Authorization: Token $TOKEN"
```

Формат ошибки одинаковый у всех эндпоинтов:

```json
{"message": "У читателя уже три книги на руках.",
 "code": "validation_error",
 "extra": {"fields": {"reader": ["У читателя уже три книги на руках."]}}}
```

Коды: нет токена 401, читатель выдаёт 403, чужая выдача 404, нарушено правило 400.

Выдача из консоли: `python manage.py library_issue --copy-id=1 --reader-id=2 --actor-id=3`.
