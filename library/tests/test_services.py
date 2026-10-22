from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from library import services
from library.exceptions import BusinessValidationError, PermissionDeniedError
from library.models import Notification
from library.tests.factories import BookFactory, UserFactory

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
