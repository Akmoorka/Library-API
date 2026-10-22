from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from library import services
from library.constants import LOAN_PERIOD
from library.exceptions import BusinessValidationError, PermissionDeniedError
from library.models import CopyStatus, Loan, Notification
from library.tests.factories import (
    BookFactory,
    CopyFactory,
    LoanFactory,
    UserFactory,
)

PASSWORD = "S3cure-pass-77"


class RegistrationTests(TestCase):
    def test_register_creates_user_with_hashed_password(self):
        user = services.user_register(
            username="anna", password=PASSWORD, email="a@example.com"
        )
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)

    def test_duplicate_username_is_business_error(self):
        services.user_register(username="anna", password=PASSWORD)
        with self.assertRaises(BusinessValidationError) as ctx:
            services.user_register(username="anna", password=PASSWORD)
        self.assertIn("username", ctx.exception.extra["fields"])


class CatalogTests(TestCase):
    def setUp(self):
        self.reader = UserFactory()
        self.librarian = UserFactory(is_staff=True)

    def test_reader_cannot_create_book(self):
        with self.assertRaises(PermissionDeniedError):
            services.book_create(
                actor=self.reader, title="T", author="A",
                isbn="1234567890123", year=2000,
            )

    def test_librarian_creates_book(self):
        book = services.book_create(
            actor=self.librarian, title="T", author="A",
            isbn="1234567890123", year=2000,
        )
        self.assertEqual(book.isbn, "1234567890123")

    def test_duplicate_isbn_is_business_error(self):
        BookFactory(isbn="1234567890123")
        with self.assertRaises(BusinessValidationError) as ctx:
            services.book_create(
                actor=self.librarian, title="T", author="A",
                isbn="1234567890123", year=2000,
            )
        self.assertIn("isbn", ctx.exception.extra["fields"])

    def test_reader_cannot_create_copy(self):
        book = BookFactory()
        with self.assertRaises(PermissionDeniedError):
            services.copy_create(
                actor=self.reader, book_id=book.pk, inventory_number="INV-1"
            )

    def test_copy_for_missing_book_is_business_error(self):
        with self.assertRaises(BusinessValidationError) as ctx:
            services.copy_create(
                actor=self.librarian, book_id=999999, inventory_number="INV-1"
            )
        self.assertIn("book", ctx.exception.extra["fields"])

    def test_duplicate_inventory_number_is_business_error(self):
        book = BookFactory()
        services.copy_create(
            actor=self.librarian, book_id=book.pk, inventory_number="INV-1"
        )
        with self.assertRaises(BusinessValidationError) as ctx:
            services.copy_create(
                actor=self.librarian, book_id=book.pk, inventory_number="INV-1"
            )
        self.assertIn("inventory_number", ctx.exception.extra["fields"])


class NotificationSendTests(TestCase):
    def test_send_sets_sent_at_only_once(self):
        notification = Notification.objects.create(
            recipient=UserFactory(), kind=Notification.Kind.LOAN_ISSUED
        )
        first = timezone.now()
        services.notification_send(notification_id=notification.pk, now=first)
        services.notification_send(
            notification_id=notification.pk, now=first + timedelta(hours=1)
        )
        notification.refresh_from_db()
        self.assertEqual(notification.sent_at, first)

    def test_send_missing_notification_is_silent(self):
        services.notification_send(notification_id=999999)


class CeleryTaskTests(TestCase):
    def test_task_marks_notification_sent(self):
        from library.tasks import notification_send_task

        notification = Notification.objects.create(
            recipient=UserFactory(), kind=Notification.Kind.LOAN_ISSUED
        )
        notification_send_task.delay(notification_id=notification.pk)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.sent_at)


class LoanCreateTests(TestCase):
    def setUp(self):
        self.librarian = UserFactory(is_staff=True)
        self.reader = UserFactory()
        self.copy = CopyFactory()

    def issue(self, **kwargs):
        params = dict(
            actor=self.librarian, copy_id=self.copy.pk, reader_id=self.reader.pk
        )
        params.update(kwargs)
        return services.loan_create(**params)

    def test_reader_cannot_issue(self):
        with self.assertRaises(PermissionDeniedError):
            self.issue(actor=self.reader)

    def test_missing_copy_is_business_error(self):
        with self.assertRaises(BusinessValidationError) as ctx:
            self.issue(copy_id=999999)
        self.assertIn("copy", ctx.exception.extra["fields"])

    def test_missing_reader_is_business_error(self):
        with self.assertRaises(BusinessValidationError) as ctx:
            self.issue(reader_id=999999)
        self.assertIn("reader", ctx.exception.extra["fields"])

    def test_loaned_copy_is_rejected(self):
        self.issue()
        with self.assertRaises(BusinessValidationError):
            self.issue(reader_id=UserFactory().pk)

    def test_db_constraint_is_translated_to_business_error(self):
        LoanFactory(copy=self.copy)  # статус остался available
        with self.assertRaises(BusinessValidationError) as ctx:
            self.issue()
        self.assertIn("copy", ctx.exception.extra["fields"])

    def test_fourth_loan_is_rejected(self):
        LoanFactory.create_batch(3, reader=self.reader)
        with self.assertRaises(BusinessValidationError) as ctx:
            self.issue()
        self.assertIn("reader", ctx.exception.extra["fields"])

    def test_reader_with_overdue_loan_is_rejected(self):
        LoanFactory(reader=self.reader, due_at=timezone.now() - timedelta(days=1))
        with self.assertRaises(BusinessValidationError):
            self.issue()

    def test_successful_issue_sets_due_date_and_status(self):
        now = timezone.now()
        loan = self.issue(now=now)
        self.assertEqual(loan.due_at, now + LOAN_PERIOD)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, CopyStatus.ON_LOAN)

    def test_issue_creates_one_notification_sent_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            loan = self.issue()
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(Notification.objects.count(), 1)
        notification = Notification.objects.get(loan=loan)
        self.assertEqual(notification.recipient, self.reader)
        self.assertIsNotNone(notification.sent_at)

    def test_failure_leaves_no_loan_and_no_notification(self):
        with mock.patch(
            "library.services.Notification.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.issue()
        self.assertEqual(Loan.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, CopyStatus.AVAILABLE)
