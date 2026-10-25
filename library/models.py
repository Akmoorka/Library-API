from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

from .constants import MAX_EXTENSIONS
from .exceptions import BusinessValidationError

User = settings.AUTH_USER_MODEL


class CopyStatus(models.TextChoices):
    AVAILABLE = "available", "Свободен"
    ON_LOAN = "on_loan", "На руках"
    LOST = "lost", "Утерян"


class BookQuerySet(models.QuerySet):
    def with_available_copies(self):
        return self.annotate(
            available_copies=Count(
                "copies", filter=Q(copies__status=CopyStatus.AVAILABLE)
            )
        )

    def search(self, text):
        return self.filter(Q(title__icontains=text) | Q(author__icontains=text))


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    isbn = models.CharField(max_length=13, unique=True)
    year = models.IntegerField()

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = ["title", "id"]

    def __str__(self):
        return self.title


class CopyQuerySet(models.QuerySet):
    def available(self):
        return self.filter(status=CopyStatus.AVAILABLE)


class Copy(models.Model):
    Status = CopyStatus

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="copies")
    inventory_number = models.CharField(max_length=20, unique=True)
    status = models.CharField(
        max_length=20, choices=CopyStatus.choices, default=CopyStatus.AVAILABLE
    )

    objects = CopyQuerySet.as_manager()

    class Meta:
        ordering = ["inventory_number"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CopyStatus.values), name="copy_status_valid"
            ),
        ]

    def __str__(self):
        return self.inventory_number


class LoanQuerySet(models.QuerySet):
    def active(self):
        return self.filter(returned_at__isnull=True)

    def overdue(self, now):
        return self.active().filter(due_at__lt=now)

    def visible_to(self, user):
        if user.is_staff:
            return self
        return self.filter(reader=user)


class Loan(models.Model):
    copy = models.ForeignKey(Copy, on_delete=models.CASCADE, related_name="loans")
    reader = models.ForeignKey(User, on_delete=models.CASCADE, related_name="loans")
    issued_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    extensions = models.PositiveIntegerField(default=0)

    objects = LoanQuerySet.as_manager()

    class Meta:
        ordering = ["-issued_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["copy"],
                condition=Q(returned_at__isnull=True),
                name="one_active_loan_per_copy",
            ),
            models.CheckConstraint(
                condition=Q(extensions__gte=0, extensions__lte=2),
                name="loan_extensions_range",
            ),
        ]

    def __str__(self):
        return f"{self.copy} -> {self.reader}"

    @property
    def is_overdue(self):
        return self.returned_at is None and self.due_at < timezone.now()

    def mark_returned(self, now):
        if self.returned_at is not None:
            raise BusinessValidationError(
                "Выдача уже закрыта.",
                extra={"fields": {"loan": ["Выдача уже закрыта."]}},
            )
        self.returned_at = now
        self.save(update_fields=["returned_at"])

    def extend(self, period):
        if self.returned_at is not None:
            raise BusinessValidationError(
                "Нельзя продлить закрытую выдачу.",
                extra={"fields": {"loan": ["Нельзя продлить закрытую выдачу."]}},
            )
        if self.extensions >= MAX_EXTENSIONS:
            raise BusinessValidationError(
                "Продлевать можно не больше двух раз.",
                extra={"fields": {"loan": ["Продлевать можно не больше двух раз."]}},
            )
        self.due_at = self.due_at + period
        self.extensions += 1
        self.save(update_fields=["due_at", "extensions"])


class Notification(models.Model):
    class Kind(models.TextChoices):
        LOAN_ISSUED = "loan_issued", "Книга выдана"
        DUE_SOON = "due_soon", "Скоро срок возврата"
        OVERDUE = "overdue", "Просрочена"

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.recipient}"

    def mark_sent(self, now):
        if self.sent_at is not None:
            return
        self.sent_at = now
        self.save(update_fields=["sent_at"])
