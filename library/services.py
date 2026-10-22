from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .exceptions import BusinessValidationError, PermissionDeniedError
from .models import Book, Copy, Notification

User = get_user_model()


def _require_librarian(actor):
    if not actor.is_staff:
        raise PermissionDeniedError("Это действие доступно только библиотекарю.")


def _field_error(field, message):
    return BusinessValidationError(message, extra={"fields": {field: [message]}})


def user_register(*, username, password, email="") -> User:
    try:
        with transaction.atomic():
            return User.objects.create_user(
                username=username, password=password, email=email
            )
    except IntegrityError:
        raise _field_error("username", "Пользователь с таким именем уже существует.")


def book_create(*, actor, title, author, isbn, year) -> Book:
    _require_librarian(actor)
    try:
        with transaction.atomic():
            return Book.objects.create(
                title=title, author=author, isbn=isbn, year=year
            )
    except IntegrityError:
        raise _field_error("isbn", "Книга с таким ISBN уже есть.")


def copy_create(*, actor, book_id, inventory_number) -> Copy:
    _require_librarian(actor)
    try:
        book = Book.objects.get(pk=book_id)
    except Book.DoesNotExist:
        raise _field_error("book", "Книга не найдена.")
    try:
        with transaction.atomic():
            return Copy.objects.create(book=book, inventory_number=inventory_number)
    except IntegrityError:
        raise _field_error("inventory_number", "Экземпляр с таким номером уже есть.")


def notification_send(*, notification_id, now=None) -> None:
    """Вызывается Celery-задачей. Идемпотентна: повтор не меняет sent_at."""
    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        return  # удалили, отправлять нечего
    # Здесь была бы реальная доставка (почта, push); пока только отметка.
    notification.mark_sent(now or timezone.now())
