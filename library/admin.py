from django.contrib import admin

from .models import Book, Copy, Loan, Notification


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author", "isbn", "year")
    search_fields = ("title", "author", "isbn")


@admin.register(Copy)
class CopyAdmin(admin.ModelAdmin):
    list_display = ("id", "inventory_number", "book", "status")
    list_filter = ("status",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("id", "copy", "reader", "issued_at", "due_at", "returned_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "kind", "is_read", "sent_at")
