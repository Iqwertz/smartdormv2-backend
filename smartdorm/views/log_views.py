import logging

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..permissions import GroupAndEmployeeTypePermission
from ..utils.log_utils import get_log_page

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_logs_view(request):
    try:
        limit = int(request.GET.get("limit", "100"))
        cursor = int(request.GET.get("cursor", "0"))
    except ValueError:
        return Response({"error": "Ungültige Pagination-Parameter."}, status=status.HTTP_400_BAD_REQUEST)

    limit = max(1, min(limit, 500))
    cursor = max(0, cursor)
    level = request.GET.get("level") or None
    search = request.GET.get("search") or None

    if level:
        level = level.upper().strip()

    try:
        items, next_cursor, has_more, total = get_log_page(
            limit=limit,
            cursor=cursor,
            level=level,
            search=search,
        )

        payload = [
            {
                "timestamp": item.timestamp,
                "level": item.level,
                "logger": item.logger,
                "message": item.message,
            }
            for item in items
        ]

        return Response(
            {
                "items": payload,
                "nextCursor": next_cursor,
                "hasMore": has_more,
                "total": total,
                "limit": limit,
                "cursor": cursor,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as exc:
        logger.error("Failed to retrieve logs: %s", exc, exc_info=True)
        return Response({"error": "Protokolle konnten nicht geladen werden."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


list_logs_view.required_groups = ["Netzwerkreferat", "ADMIN"]
