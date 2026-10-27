from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

from library.exceptions import ApplicationError


def _envelope(message, code, extra=None):
    return {"message": message, "code": code, "extra": extra or {}}


def _flatten(detail, prefix=""):
    """Превращает detail ValidationError в {"поле": ["сообщение", ...]}.

    Вложенные сериализаторы дают ключи через точку: "items.0.name".
    Ошибки без поля (например, из validate()) уходят в ключ "non_field_errors".
    """
    result = {}
    if isinstance(detail, dict):
        for key, value in detail.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value, path))
    elif isinstance(detail, list):
        if all(not isinstance(item, (dict, list)) for item in detail):
            result[prefix or "non_field_errors"] = [str(item) for item in detail]
        else:
            for index, item in enumerate(detail):
                path = f"{prefix}.{index}" if prefix else str(index)
                result.update(_flatten(item, path))
    else:
        result[prefix or "non_field_errors"] = [str(detail)]
    return result


def _first_message(fields):
    for messages in fields.values():
        if messages:
            return messages[0]
    return "Ошибка валидации."


def exception_handler(exc, context):
    # 1. Наши доменные ошибки. Откат транзакции, если запрос идёт внутри ATOMIC_REQUESTS.
    if isinstance(exc, ApplicationError):
        set_rollback()
        return Response(
            _envelope(exc.message, exc.code, exc.extra), status=exc.status_code
        )

    # 2. Остальное разбирает DRF: он же вызывает set_rollback() и ставит заголовки
    #    (WWW-Authenticate у 401, Retry-After у 429). Мы меняем только тело,
    #    объект ответа остаётся тем же, поэтому заголовки не теряются.
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # необработанная ошибка, Django отдаст 500

    if isinstance(exc, drf_exceptions.ValidationError):
        fields = _flatten(exc.detail)
        response.data = _envelope(
            _first_message(fields), "validation_error", {"fields": fields}
        )
    elif isinstance(exc, drf_exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        response.data = _envelope(str(exc.detail), code)
    elif isinstance(exc, Http404):  # DRF уже превратил его в 404-ответ
        response.data = _envelope("Не найдено.", "not_found")
    elif isinstance(exc, DjangoPermissionDenied):
        response.data = _envelope("Нет доступа.", "permission_denied")
    else:
        response.data = _envelope("Ошибка запроса.", "error")
    return response
