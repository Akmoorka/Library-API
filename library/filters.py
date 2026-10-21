import django_filters
from django.utils import timezone

from .models import Book, Loan

TRUE_FALSE = [("true", "true"), ("false", "false")]


class BookFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    author = django_filters.CharFilter(field_name="author", lookup_expr="icontains")
    available = django_filters.ChoiceFilter(
        choices=TRUE_FALSE, method="filter_available"
    )

    class Meta:
        model = Book
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.search(value)

    def filter_available(self, queryset, name, value):
        if value == "true":
            return queryset.filter(available_copies__gt=0)
        return queryset.filter(available_copies=0)


class LoanFilter(django_filters.FilterSet):
    active = django_filters.ChoiceFilter(choices=TRUE_FALSE, method="filter_active")
    overdue = django_filters.ChoiceFilter(choices=TRUE_FALSE, method="filter_overdue")
    reader = django_filters.NumberFilter(field_name="reader_id")

    class Meta:
        model = Loan
        fields = []

    def filter_active(self, queryset, name, value):
        if value == "true":
            return queryset.active()
        return queryset.filter(returned_at__isnull=False)

    def filter_overdue(self, queryset, name, value):
        overdue = queryset.overdue(timezone.now())
        if value == "true":
            return overdue
        return queryset.exclude(pk__in=overdue)
