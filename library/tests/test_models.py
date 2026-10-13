from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from library.constants import EXTENSION_PERIOD
from library.exceptions import BusinessValidationError
from library.tests.factories import CopyFactory, LoanFactory


class ConstraintTests(TestCase):
    def test_duplicate_inventory_number_is_rejected(self):
        CopyFactory(inventory_number="INV-1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CopyFactory(inventory_number="INV-1")

    def test_second_active_loan_for_same_copy_is_rejected(self):
        loan = LoanFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LoanFactory(copy=loan.copy)

    def test_returned_loan_does_not_block_new_loan(self):
        loan = LoanFactory()
        loan.mark_returned(timezone.now())
        LoanFactory(copy=loan.copy)


class LoanStateTests(TestCase):
    def test_mark_returned_twice_raises(self):
        loan = LoanFactory()
        loan.mark_returned(timezone.now())
        with self.assertRaises(BusinessValidationError):
            loan.mark_returned(timezone.now())

    def test_third_extension_raises(self):
        loan = LoanFactory()
        loan.extend(EXTENSION_PERIOD)
        loan.extend(EXTENSION_PERIOD)
        with self.assertRaises(BusinessValidationError):
            loan.extend(EXTENSION_PERIOD)
        self.assertEqual(loan.extensions, 2)
