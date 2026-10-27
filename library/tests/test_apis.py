"""Тесты транспорта: коды ответов, единый формат ошибок, права.

Правила предметной области здесь не перепроверяются (они в test_services.py).
Объекты создаются напрямую через ORM, чтобы файл не зависел от factories.py.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from library import services
from library.models import Book, Copy, CopyStatus, Loan

User = get_user_model()


class ApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.librarian = User.objects.create_user("lib", password="pw", is_staff=True)
        self.reader = User.objects.create_user("reader", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.book = self.make_book()
        self._copy_seq = 0

    # --- помощники ------------------------------------------------------------

    def make_book(self, n=0):
        return Book.objects.create(
            title=f"Книга {n}", author="Автор", isbn=f"{n:013d}", year=2000
        )

    def make_copy(self, book=None):
        self._copy_seq += 1
        return Copy.objects.create(
            book=book or self.book, inventory_number=f"INV-{self._copy_seq}"
        )

    def make_loan(self, reader, copy=None, due_in=timedelta(days=14)):
        copy = copy or self.make_copy()
        copy.status = CopyStatus.ON_LOAN
        copy.save(update_fields=["status"])
        return Loan.objects.create(
            copy=copy, reader=reader, due_at=timezone.now() + due_in
        )

    def login(self, user):
        self.client.force_authenticate(user)

    def assertError(self, response, status_code, code):
        """Тело ошибки всегда {"message", "code", "extra"}."""
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertEqual(set(body), {"message", "code", "extra"})
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["message"], str)
        self.assertIsInstance(body["extra"], dict)
        return body


class ErrorFormatTests(ApiTestCase):
    def test_20_no_token_is_401_in_common_format(self):
        response = self.client.get("/api/books/")
        self.assertError(response, 401, "not_authenticated")
        # заголовок DRF не потерян обработчиком
        self.assertTrue(response["WWW-Authenticate"].startswith("Token"))

    def test_21_reader_cannot_issue_loan(self):
        self.login(self.reader)
        copy = self.make_copy()
        response = self.client.post(
            "/api/loans/", {"copy": copy.pk, "reader": self.reader.pk}, format="json"
        )
        self.assertError(response, 403, "permission_denied")
        self.assertFalse(Loan.objects.exists())

    def test_22_foreign_loan_is_404(self):
        loan = self.make_loan(self.reader)
        self.login(self.other)
        for action in ("extend", "return"):
            response = self.client.post(f"/api/loans/{loan.pk}/{action}/")
            self.assertError(response, 404, "not_found")

    def test_23_rule_violation_is_400_with_field_name(self):
        for _ in range(3):
            self.make_loan(self.reader)
        fresh = self.make_copy()
        self.login(self.librarian)
        response = self.client.post(
            "/api/loans/", {"copy": fresh.pk, "reader": self.reader.pk}, format="json"
        )
        body = self.assertError(response, 400, "validation_error")
        self.assertIn("reader", body["extra"]["fields"])
        self.assertEqual(body["message"], body["extra"]["fields"]["reader"][0])

    def test_24_garbage_ordering_is_400(self):
        self.login(self.librarian)
        for url in ("/api/books/?ordering=garbage", "/api/loans/?ordering=-garbage"):
            body = self.assertError(self.client.get(url), 400, "validation_error")
            self.assertIn("ordering", body["extra"]["fields"])

    def test_garbage_filter_values_are_400(self):
        self.login(self.librarian)
        for url in (
            "/api/books/?available=maybe",
            "/api/loans/?active=maybe",
            "/api/loans/?reader=abc",
        ):
            self.assertError(self.client.get(url), 400, "validation_error")

    def test_invalid_body_is_400_with_field_names(self):
        self.login(self.librarian)
        response = self.client.post("/api/loans/", {"copy": "x"}, format="json")
        body = self.assertError(response, 400, "validation_error")
        self.assertEqual(set(body["extra"]["fields"]), {"copy", "reader"})


class AuthTests(ApiTestCase):
    def test_register_then_token_then_request(self):
        response = self.client.post(
            "/api/register/", {"username": "new", "password": "pw12345!"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("password", response.json())

        response = self.client.post(
            "/api/auth/token/", {"username": "new", "password": "pw12345!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.get("/api/books/").status_code, 200)

    def test_register_duplicate_username_is_400(self):
        response = self.client.post(
            "/api/register/", {"username": "reader", "password": "pw"}, format="json"
        )
        body = self.assertError(response, 400, "validation_error")
        self.assertIn("username", body["extra"]["fields"])

    def test_wrong_password_is_400_in_common_format(self):
        response = self.client.post(
            "/api/auth/token/", {"username": "reader", "password": "bad"}, format="json"
        )
        self.assertError(response, 400, "validation_error")


class BookApiTests(ApiTestCase):
    def test_librarian_creates_book_and_copy(self):
        self.login(self.librarian)
        response = self.client.post(
            "/api/books/",
            {"title": "T", "author": "A", "isbn": "1111111111111", "year": 1999},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(
            set(body), {"id", "title", "author", "isbn", "year", "available_copies"}
        )
        self.assertEqual(body["available_copies"], 0)

        response = self.client.post(
            "/api/copies/", {"book": body["id"], "inventory_number": "X-1"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            set(response.json()), {"id", "book", "inventory_number", "status"}
        )

    def test_reader_cannot_create_book(self):
        self.login(self.reader)
        response = self.client.post(
            "/api/books/",
            {"title": "T", "author": "A", "isbn": "1111111111111", "year": 1999},
            format="json",
        )
        self.assertError(response, 403, "permission_denied")

    def test_duplicate_isbn_is_400(self):
        self.login(self.librarian)
        response = self.client.post(
            "/api/books/",
            {"title": "T", "author": "A", "isbn": self.book.isbn, "year": 1999},
            format="json",
        )
        body = self.assertError(response, 400, "validation_error")
        self.assertIn("isbn", body["extra"]["fields"])

    def test_copy_of_missing_book_is_400(self):
        self.login(self.librarian)
        response = self.client.post(
            "/api/copies/", {"book": 99999, "inventory_number": "X-1"}, format="json"
        )
        body = self.assertError(response, 400, "validation_error")
        self.assertIn("book", body["extra"]["fields"])

    def test_list_counts_available_copies_and_filters(self):
        self.make_copy()
        self.make_copy()
        busy_book = self.make_book(1)
        self.make_loan(self.reader, copy=self.make_copy(busy_book))
        self.login(self.reader)

        response = self.client.get("/api/books/?available=true")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([b["id"] for b in results], [self.book.pk])
        self.assertEqual(results[0]["available_copies"], 2)

    def test_detail_and_copies(self):
        copy = self.make_copy()
        self.login(self.reader)
        self.assertEqual(
            self.client.get(f"/api/books/{self.book.pk}/").status_code, 200
        )
        response = self.client.get(f"/api/books/{self.book.pk}/copies/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c["id"] for c in response.json()["results"]], [copy.pk])
        self.assertError(self.client.get("/api/books/99999/"), 404, "not_found")
        self.assertError(self.client.get("/api/books/99999/copies/"), 404, "not_found")

    def test_pagination_is_ten_per_page(self):
        for n in range(1, 11):  # вместе с книгой из setUp получается 11
            self.make_book(n)
        self.login(self.reader)
        body = self.client.get("/api/books/").json()
        self.assertEqual(body["count"], 11)
        self.assertEqual(len(body["results"]), 10)
        self.assertIsNotNone(body["next"])
        body = self.client.get("/api/books/?page=2").json()
        self.assertEqual(len(body["results"]), 1)


class LoanApiTests(ApiTestCase):
    def test_librarian_issues_loan(self):
        copy = self.make_copy()
        self.login(self.librarian)
        response = self.client.post(
            "/api/loans/", {"copy": copy.pk, "reader": self.reader.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "id", "copy", "book_title", "reader", "issued_at", "due_at",
                "returned_at", "extensions", "is_overdue",
            },
        )
        self.assertEqual(body["book_title"], self.book.title)
        self.assertIsNone(body["returned_at"])
        self.assertFalse(body["is_overdue"])
        copy.refresh_from_db()
        self.assertEqual(copy.status, CopyStatus.ON_LOAN)

    def test_return_and_double_return(self):
        loan = self.make_loan(self.reader)
        self.login(self.librarian)
        response = self.client.post(f"/api/loans/{loan.pk}/return/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()["returned_at"])
        self.assertError(
            self.client.post(f"/api/loans/{loan.pk}/return/"), 400, "validation_error"
        )

    def test_extend_and_overdue_extend(self):
        loan = self.make_loan(self.reader)
        overdue = self.make_loan(self.other, due_in=timedelta(days=-1))
        self.login(self.librarian)
        response = self.client.post(f"/api/loans/{loan.pk}/extend/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["extensions"], 1)
        self.assertError(
            self.client.post(f"/api/loans/{overdue.pk}/extend/"), 400, "validation_error"
        )

    def test_reader_sees_only_own_loans_librarian_sees_all(self):
        mine = self.make_loan(self.reader)
        self.make_loan(self.other)
        self.login(self.reader)
        results = self.client.get("/api/loans/").json()["results"]
        self.assertEqual([loan["id"] for loan in results], [mine.pk])
        self.login(self.librarian)
        self.assertEqual(self.client.get("/api/loans/").json()["count"], 2)

    def test_loan_filters(self):
        active = self.make_loan(self.reader)
        late = self.make_loan(self.reader, due_in=timedelta(days=-1))
        closed = self.make_loan(self.reader)
        services.loan_return(actor=self.librarian, loan_id=closed.pk)
        self.login(self.librarian)

        def ids(query):
            results = self.client.get(f"/api/loans/{query}").json()["results"]
            return {loan["id"] for loan in results}

        self.assertEqual(ids("?active=true"), {active.pk, late.pk})
        self.assertEqual(ids("?overdue=true"), {late.pk})
        self.assertEqual(ids(f"?reader={self.other.pk}"), set())

    def test_notification_created_by_loan_is_visible_to_reader_only(self):
        copy = self.make_copy()
        services.loan_create(
            actor=self.librarian, copy_id=copy.pk, reader_id=self.reader.pk
        )
        self.login(self.reader)
        body = self.client.get("/api/notifications/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["kind"], "loan_issued")
        self.login(self.other)
        self.assertEqual(self.client.get("/api/notifications/").json()["count"], 0)


class QueryCountTests(ApiTestCase):
    def count_queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx)

    def test_books_list_queries_do_not_grow(self):
        self.login(self.librarian)
        for n in range(1, 3):
            self.make_copy(self.make_book(n))
        few = self.count_queries("/api/books/")
        for n in range(3, 9):
            self.make_copy(self.make_book(n))
        many = self.count_queries("/api/books/")
        self.assertEqual(few, many)

    def test_loans_list_queries_do_not_grow(self):
        self.login(self.librarian)
        readers = [User.objects.create_user(f"r{i}", password="pw") for i in range(9)]
        for reader in readers[:2]:
            self.make_loan(reader)
        few = self.count_queries("/api/loans/")
        for reader in readers[2:]:
            self.make_loan(reader)
        many = self.count_queries("/api/loans/")
        self.assertEqual(few, many)
