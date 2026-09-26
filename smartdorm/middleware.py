"""
Request-level guards that are easier to get right in one place than on every view.
"""

import logging

from django.http import JsonResponse

from . import config as app_config
from .utils.subtenant_utils import is_subtenant_account

logger = logging.getLogger(__name__)

API_PREFIX = '/api/'


class SubtenantApiGuardMiddleware:
    """
    Restricts subtenant accounts to the handful of API paths their dashboard needs.

    The per-view access rules cannot express this: a subtenant is a logged-in account, so every
    `LoggedIn` endpoint would admit them, and older subtenant accounts even carry the TENANT
    employeeType. Guarding the API surface centrally keeps it default-deny - an endpoint added
    later stays closed to subtenants until it is opened here deliberately.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith(API_PREFIX) and not self._is_allowed(path):
            user = getattr(request, 'user', None)
            if is_subtenant_account(user):
                logger.warning(
                    f"Blocked subtenant '{user.username}' from API path '{path}'."
                )
                return JsonResponse(
                    {"error": "Für Untermieter nicht verfügbar."}, status=403
                )

        return self.get_response(request)

    @staticmethod
    def _is_allowed(path):
        return any(
            path.startswith(prefix) or path == prefix.rstrip('/')
            for prefix in app_config.SUBTENANT_ALLOWED_API_PREFIXES
        )
