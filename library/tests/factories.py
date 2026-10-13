from datetime import timedelta

import factory
from django.contrib.auth import get_user_model
from django.utils import timezone

from library.models import Book, Copy, Loan

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f"Книга {n}")
    author = "Автор"
    isbn = factory.Sequence(lambda n: f"{n:013d}")
    year = 2000


class CopyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Copy

    book = factory.SubFactory(BookFactory)
    inventory_number = factory.Sequence(lambda n: f"INV-{n}")


class LoanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Loan

    copy = factory.SubFactory(CopyFactory)
    reader = factory.SubFactory(UserFactory)
    due_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=14))
