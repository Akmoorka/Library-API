from django.db.models import QuerySet

from .exceptions import BusinessValidationError, NotFoundError
from .filters import BookFilter, LoanFilter
from .models import Book, Copy, Loan, Notification

BOOK_ORDERING_FIELDS = {"title", "author", "year", "id"}
LOAN_ORDERING_FIELDS = {"issued_at", "due_at", "id"}


def _apply_filters(*, filterset_class, queryset, filters):
    f = filterset_class(filters, queryset=queryset)
    if not f.is_valid():
        raise BusinessValidationError(
            "Недопустимое значение фильтра.",
            extra={
                "fields": {
                    name: [str(message) for message in errors]
                    for name, errors in f.errors.items()
                }
            },
        )
    return f.qs


def _apply_ordering(queryset, raw, allowed):
    fields = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not fields:
        return queryset
    unknown = [name for name in fields if name.lstrip("-") not in allowed]
    if unknown:
        raise BusinessValidationError(
            "Недопустимое поле сортировки.",
            extra={"fields": {"ordering": unknown}},
        )
    # id в конце: при равных значениях порядок остаётся стабильным
    return queryset.order_by(*fields, "id")


def book_list(*, user, filters=None) -> QuerySet[Book]:
    params = dict(filters or {})
    ordering = params.pop("ordering", None)
    queryset = Book.objects.with_available_copies()
    queryset = _apply_filters(
        filterset_class=BookFilter, queryset=queryset, filters=params
    )
    return _apply_ordering(queryset, ordering, BOOK_ORDERING_FIELDS)


def book_get(*, user, book_id) -> Book:
    try:
        return Book.objects.with_available_copies().get(pk=book_id)
    except Book.DoesNotExist:
        raise NotFoundError("Книга не найдена.")


def copy_list(*, user, book_id) -> QuerySet[Copy]:
    book_get(user=user, book_id=book_id)  # нет книги -> 404
    return Copy.objects.filter(book_id=book_id)


def loan_list(*, user, filters=None) -> QuerySet[Loan]:
    params = dict(filters or {})
    ordering = params.pop("ordering", None)
    queryset = Loan.objects.visible_to(user).select_related("copy__book", "reader")
    queryset = _apply_filters(
        filterset_class=LoanFilter, queryset=queryset, filters=params
    )
    return _apply_ordering(queryset, ordering, LOAN_ORDERING_FIELDS)


def loan_get(*, user, loan_id) -> Loan:
    try:
        return (
            Loan.objects.visible_to(user)
            .select_related("copy__book", "reader")
            .get(pk=loan_id)
        )
    except Loan.DoesNotExist:
        raise NotFoundError("Выдача не найдена.")


def notification_list(*, user) -> QuerySet[Notification]:
    return Notification.objects.filter(recipient=user).select_related("loan")
