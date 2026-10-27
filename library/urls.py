from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from .apis import (
    BookCopyListApi,
    BookDetailApi,
    BookListCreateApi,
    CopyCreateApi,
    LoanExtendApi,
    LoanListCreateApi,
    LoanReturnApi,
    NotificationListApi,
    RegisterApi,
)

urlpatterns = [
    path("register/", RegisterApi.as_view(), name="register"),
    path("auth/token/", obtain_auth_token, name="token"),
    path("books/", BookListCreateApi.as_view(), name="book-list"),
    path("books/<int:book_id>/", BookDetailApi.as_view(), name="book-detail"),
    path(
        "books/<int:book_id>/copies/", BookCopyListApi.as_view(), name="book-copies"
    ),
    path("copies/", CopyCreateApi.as_view(), name="copy-create"),
    path("loans/", LoanListCreateApi.as_view(), name="loan-list"),
    path(
        "loans/<int:loan_id>/return/", LoanReturnApi.as_view(), name="loan-return"
    ),
    path(
        "loans/<int:loan_id>/extend/", LoanExtendApi.as_view(), name="loan-extend"
    ),
    path("notifications/", NotificationListApi.as_view(), name="notification-list"),
]
