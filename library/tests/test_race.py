import threading

from django.db import connection
from django.test import TransactionTestCase

from library import services
from library.models import CopyStatus, Loan
from library.tests.factories import CopyFactory, UserFactory


class LoanRaceTests(TransactionTestCase):
    def test_two_librarians_cannot_issue_same_copy(self):
        librarian = UserFactory(is_staff=True)
        readers = [UserFactory(), UserFactory()]
        copy = CopyFactory()
        barrier = threading.Barrier(2)
        results = [None, None]

        def worker(index):
            try:
                barrier.wait(timeout=10)
                loan = services.loan_create(
                    actor=librarian, copy_id=copy.pk, reader_id=readers[index].pk
                )
                results[index] = loan.pk
            except Exception as exc:
                results[index] = type(exc).__name__
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        successes = [r for r in results if isinstance(r, int)]
        failures = [r for r in results if isinstance(r, str)]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(failures, ["BusinessValidationError"], results)
        self.assertEqual(Loan.objects.active().count(), 1)
        copy.refresh_from_db()
        self.assertEqual(copy.status, CopyStatus.ON_LOAN)
