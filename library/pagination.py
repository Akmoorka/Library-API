from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    """10 записей на страницу, номер страницы в ?page=N."""

    page_size = 10


def get_paginated_response(
    *, pagination_class, serializer_class, queryset, request, view
):
    """Общий помощник для всех списков: apis.py не знает деталей пагинации."""
    paginator = pagination_class()
    page = paginator.paginate_queryset(queryset, request, view=view)
    context = {"request": request}
    if page is not None:
        serializer = serializer_class(page, many=True, context=context)
        return paginator.get_paginated_response(serializer.data)
    serializer = serializer_class(queryset, many=True, context=context)
    return Response(serializer.data)
