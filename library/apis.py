from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import selectors, services
from .pagination import DefaultPagination, get_paginated_response


# --- Выходные сериализаторы (общие для нескольких вьюх) ------------------------


class BookOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    author = serializers.CharField()
    isbn = serializers.CharField()
    year = serializers.IntegerField()
    # Аннотация селектора. У только что созданной книги её нет, экземпляров 0.
    available_copies = serializers.IntegerField(read_only=True, default=0)


class CopyOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    book = serializers.IntegerField(source="book_id")
    inventory_number = serializers.CharField()
    status = serializers.CharField()


class LoanOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    copy = serializers.IntegerField(source="copy_id")
    book_title = serializers.CharField(source="copy.book.title")
    reader = serializers.IntegerField(source="reader_id")
    issued_at = serializers.DateTimeField()
    due_at = serializers.DateTimeField()
    returned_at = serializers.DateTimeField(allow_null=True)
    extensions = serializers.IntegerField()
    is_overdue = serializers.BooleanField()


# --- Регистрация -----------------------------------------------------------------


class RegisterApi(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    class InputSerializer(serializers.Serializer):
        username = serializers.CharField(max_length=150)
        password = serializers.CharField(max_length=128, write_only=True)
        email = serializers.EmailField(allow_blank=True, default="")

    class OutputSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        username = serializers.CharField()
        email = serializers.CharField()

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.user_register(**serializer.validated_data)
        return Response(
            self.OutputSerializer(user).data, status=status.HTTP_201_CREATED
        )


# --- Книги -------------------------------------------------------------------------


class BookListCreateApi(APIView):
    class InputSerializer(serializers.Serializer):
        title = serializers.CharField(max_length=200)
        author = serializers.CharField(max_length=200)
        isbn = serializers.CharField(max_length=13)
        year = serializers.IntegerField()

    def get(self, request):
        books = selectors.book_list(
            user=request.user, filters=request.query_params.dict()
        )
        return get_paginated_response(
            pagination_class=DefaultPagination,
            serializer_class=BookOutputSerializer,
            queryset=books,
            request=request,
            view=self,
        )

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = services.book_create(actor=request.user, **serializer.validated_data)
        return Response(
            BookOutputSerializer(book).data, status=status.HTTP_201_CREATED
        )


class BookDetailApi(APIView):
    def get(self, request, book_id):
        book = selectors.book_get(user=request.user, book_id=book_id)
        return Response(BookOutputSerializer(book).data)


class BookCopyListApi(APIView):
    def get(self, request, book_id):
        copies = selectors.copy_list(user=request.user, book_id=book_id)
        return get_paginated_response(
            pagination_class=DefaultPagination,
            serializer_class=CopyOutputSerializer,
            queryset=copies,
            request=request,
            view=self,
        )


# --- Экземпляры ----------------------------------------------------------------------


class CopyCreateApi(APIView):
    class InputSerializer(serializers.Serializer):
        book = serializers.IntegerField()
        inventory_number = serializers.CharField(max_length=20)

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        copy = services.copy_create(
            actor=request.user,
            book_id=data["book"],
            inventory_number=data["inventory_number"],
        )
        return Response(
            CopyOutputSerializer(copy).data, status=status.HTTP_201_CREATED
        )


# --- Выдачи --------------------------------------------------------------------------


class LoanListCreateApi(APIView):
    class InputSerializer(serializers.Serializer):
        copy = serializers.IntegerField()
        reader = serializers.IntegerField()

    def get(self, request):
        loans = selectors.loan_list(
            user=request.user, filters=request.query_params.dict()
        )
        return get_paginated_response(
            pagination_class=DefaultPagination,
            serializer_class=LoanOutputSerializer,
            queryset=loans,
            request=request,
            view=self,
        )

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        loan = services.loan_create(
            actor=request.user, copy_id=data["copy"], reader_id=data["reader"]
        )
        return Response(
            LoanOutputSerializer(loan).data, status=status.HTTP_201_CREATED
        )


class LoanReturnApi(APIView):
    def post(self, request, loan_id):
        loan = services.loan_return(actor=request.user, loan_id=loan_id)
        return Response(LoanOutputSerializer(loan).data)


class LoanExtendApi(APIView):
    def post(self, request, loan_id):
        loan = services.loan_extend(actor=request.user, loan_id=loan_id)
        return Response(LoanOutputSerializer(loan).data)


# --- Уведомления ------------------------------------------------------------------------


class NotificationListApi(APIView):
    class OutputSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        kind = serializers.CharField()
        loan = serializers.IntegerField(source="loan_id", allow_null=True)
        is_read = serializers.BooleanField()
        created_at = serializers.DateTimeField()
        sent_at = serializers.DateTimeField(allow_null=True)

    def get(self, request):
        notifications = selectors.notification_list(user=request.user)
        return get_paginated_response(
            pagination_class=DefaultPagination,
            serializer_class=self.OutputSerializer,
            queryset=notifications,
            request=request,
            view=self,
        )
