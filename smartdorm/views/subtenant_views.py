"""
Endpoints for the subtenant dashboard.

Subtenants only ever see their own sublet - everything else in the API is closed to them
by SubtenantApiGuardMiddleware.
"""

import logging

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..permissions import IsSubtenant
from ..serializers import SubtenantProfileSerializer
from ..utils.subtenant_utils import get_current_subtenant

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsSubtenant])
def my_profile_view(request):
    """Responds with the subtenant record of the logged-in account's running sublet."""
    subtenant = get_current_subtenant(request.user)

    if subtenant is None:
        # The LDAP account outlives the sublet, so logging in after moving out is normal.
        logger.info(f"No running sublet found for subtenant account '{request.user.username}'.")
        return Response(
            {"error": "Zu diesem Konto ist aktuell keine laufende Untermiete hinterlegt."},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(SubtenantProfileSerializer(subtenant).data, status=status.HTTP_200_OK)
