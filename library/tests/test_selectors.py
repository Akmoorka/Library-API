from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from library import selectors
from library.exceptions import BusinessValidationError, NotFoundError
from library.models import CopyStatus
from library.tests.factories import (
    BookFactory,
    CopyFactory,
    LoanFactory,
    UserFactory,
)


class LoanVisibilityTests(TestCase):
    def setUp(self):
        self.reader = UserFactory()
        self.other_reader = UserFactory()
        self.librarian = UserFactory(is_staff=True)
        self.own = LoanFactory(reader=self.reader)
        self.foreign = LoanFactory(reader=self.other_reader)

    def test_reader_does_not_see_foreign_loan(self):
        loans = list(selectors.loan_list(user=self.reader))
        self.assertEqual(loans, [self.own])

    def test_librarian_sees_all_loans(self):
        loans = set(selectors.loan_list(user=self.librarian))
        self.assertEqual(loans, {self.own, self.foreign})

    def test_foreign_loan_get_is_not_found(self):
        with self.assertRaises(NotFoundError):
            selectors.loan_get(user=self.reader, loan_id=self.foreign.pk)


class LoanFilterTests(TestCase):
    def setUp(self):
        self.librarian = UserFactory(is_staff=True)

    def test_active_true_excludes_returned(self):
        active = LoanFactory()
        LoanFactory(returned_at=timezone.now())
        loans = list(
            selectors.loan_list(user=self.librarian, filters={"active": "true"})
        )
        self.assertEqual(loans, [active])

    def test_overdue_true_returns_only_overdue(self):
        late = LoanFactory(due_at=timezone.now() - timedelta(days=1))
        LoanFactory()
        loans = list(
            selectors.loan_list(user=self.librarian, filters={"overdue": "true"})
        )
        self.assertEqual(loans, [late])

    def test_overdue_false_excludes_overdue(self):
        LoanFactory(due_at=timezone.now() - timedelta(days=1))
        fresh = LoanFactory()
        loans = list(
            selectors.loan_list(user=self.librarian, filters={"overdue": "false"})
        )
        self.assertEqual(loans, [fresh])

    def test_reader_filter_returns_only_that_reader(self):
        target = LoanFactory()
        LoanFactory()
        loans = list(
            selectors.loan_list(
                user=self.librarian, filters={"reader": str(target.reader_id)}
            )
        )
        self.assertEqual(loans, [target])


class BookSelectorTests(TestCase):
    def setUp(self):
        self.reader = UserFactory()

    def test_available_copies_counts_only_available(self):
        book = BookFactory()
        CopyFactory(book=book)
        CopyFactory(book=book)
        CopyFactory(book=book, status=CopyStatus.ON_LOAN)
        found = selectors.book_get(user=self.reader, book_id=book.pk)
        self.assertEqual(found.available_copies, 2)

    def test_available_true_excludes_books_without_free_copies(self):
        free = BookFactory()
        CopyFactory(book=free)
        busy = BookFactory()
        CopyFactory(book=busy, status=CopyStatus.ON_LOAN)
        BookFactory()
        books = list(
            selectors.book_list(user=self.reader, filters={"available": "true"})
        )
        self.assertEqual(books, [free])

    def test_search_matches_title_or_author(self):
        by_title = BookFactory(title="Мастер и Маргарита", author="Автор")
        by_author = BookFactory(title="Другая книга", author="Булгаков")
        BookFactory(title="Третья", author="Иной")
        found = list(
            selectors.book_list(user=self.reader, filters={"search": "аргарит"})
        )
        self.assertEqual(found, [by_title])
        found = list(
            selectors.book_list(user=self.reader, filters={"search": "улгак"})
        )
        self.assertEqual(found, [by_author])

    def test_author_filter(self):
        match = BookFactory(author="Булгаков")
        BookFactory(author="Иной")
        found = list(
            selectors.book_list(user=self.reader, filters={"author": "улгак"})
        )
        self.assertEqual(found, [match])

    def test_book_get_missing_is_not_found(self):
        with self.assertRaises(NotFoundError):
            selectors.book_get(user=self.reader, book_id=999999)

    def test_copy_list_returns_copies_of_book(self):
        book = BookFactory()
        mine = CopyFactory(book=book)
        CopyFactory()
        found = list(selectors.copy_list(user=self.reader, book_id=book.pk))
        self.assertEqual(found, [mine])

    def test_copy_list_for_missing_book_is_not_found(self):
        with self.assertRaises(NotFoundError):
            selectors.copy_list(user=self.reader, book_id=999999)


class FilterValidationTests(TestCase):
    def setUp(self):
        self.librarian = UserFactory(is_staff=True)

    def test_invalid_available_value_is_rejected(self):
        with self.assertRaises(BusinessValidationError) as ctx:
            selectors.book_list(user=self.librarian, filters={"available": "bogus"})
        self.assertIn("available", ctx.exception.extra["fields"])

    def test_invalid_active_value_is_rejected(self):
        with self.assertRaises(BusinessValidationError):
            selectors.loan_list(user=self.librarian, filters={"active": "bogus"})

    def test_non_numeric_reader_is_rejected(self):
        with self.assertRaises(BusinessValidationError):
            selectors.loan_list(user=self.librarian, filters={"reader": "abc"})

    def test_garbage_ordering_for_books_is_rejected(self):
        with self.assertRaises(BusinessValidationError) as ctx:
            selectors.book_list(user=self.librarian, filters={"ordering": "bogus"})
        self.assertEqual(ctx.exception.extra["fields"]["ordering"], ["bogus"])

    def test_garbage_ordering_for_loans_is_rejected(self):
        with self.assertRaises(BusinessValidationError):
            selectors.loan_list(
                user=self.librarian, filters={"ordering": "reader__password"}
            )

    def test_valid_ordering_is_applied(self):
        old = BookFactory(year=1990)
        new = BookFactory(year=2010)
        found = list(
            selectors.book_list(user=self.librarian, filters={"ordering": "-year"})
        )
        self.assertEqual(found, [new, old])


class QueryCountTests(TestCase):
    def test_loan_list_query_count_does_not_grow(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        librarian = UserFactory(is_staff=True)

        def read_all():
            return [
                (loan.copy.book.title, loan.reader.username)
                for loan in selectors.loan_list(user=librarian)
            ]

        LoanFactory.create_batch(3)
        with CaptureQueriesContext(connection) as small:
            read_all()
        LoanFactory.create_batch(27)
        with CaptureQueriesContext(connection) as large:
            read_all()
        self.assertEqual(len(small), len(large))
