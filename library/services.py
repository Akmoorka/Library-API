from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .exceptions import BusinessValidationError, PermissionDeniedError
from .constants import LOAN_PERIOD, MAX_ACTIVE_LOANS
from .models import Book, Copy, CopyStatus, Loan, Notification
from .tasks import notification_send_task

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


def _check_copy_is_available(*, copy):
    if copy.status != CopyStatus.AVAILABLE:
        raise _field_error("copy", "Экземпляр недоступен для выдачи.")


def _check_reader_can_borrow(*, reader, now):
    active = Loan.objects.active().filter(reader=reader)
    if active.count() >= MAX_ACTIVE_LOANS:
        raise _field_error("reader", "У читателя уже три книги на руках.")
    if active.overdue(now).exists():
        raise _field_error("reader", "У читателя есть просроченная книга.")


def _notify_issued(*, loan):
    notification = Notification.objects.create(
        recipient=loan.reader, kind=Notification.Kind.LOAN_ISSUED, loan=loan
    )
    # Отправка только после коммита. robust=True: если брокер недоступен,
    # ошибка попадёт в лог, а клиент не получит 500 после записи данных.
    transaction.on_commit(
        lambda nid=notification.pk: notification_send_task.delay(notification_id=nid),
        robust=True,
    )


@transaction.atomic
def loan_create(*, actor, copy_id, reader_id, now=None) -> Loan:
    now = now or timezone.now()
    _require_librarian(actor)  # 403
    # Блокируем экземпляр, затем читателя (всегда в этом порядке, чтобы
    # транзакции не ждали друг друга по кругу). Читатель блокируется для
    # проверки лимита в три книги: иначе две выдачи разных экземпляров
    # одному читателю обе увидят «две на руках».
    try:
        copy = Copy.objects.select_for_update().get(pk=copy_id)
    except Copy.DoesNotExist:
        raise _field_error("copy", "Экземпляр не найден.")  # 400
    try:
        reader = User.objects.select_for_update().get(pk=reader_id)
    except User.DoesNotExist:
        raise _field_error("reader", "Читатель не найден.")  # 400
    _check_copy_is_available(copy=copy)  # 400
    _check_reader_can_borrow(reader=reader, now=now)  # 400
    try:
        with transaction.atomic():
            loan = Loan.objects.create(
                copy=copy, reader=reader, due_at=now + LOAN_PERIOD
            )
    except IntegrityError:
        raise _field_error("copy", "Экземпляр уже выдан.")
    copy.status = CopyStatus.ON_LOAN
    copy.save(update_fields=["status"])
    _notify_issued(loan=loan)
    return loan
