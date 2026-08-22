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

    Declaring this per view was not an option: `required_groups` / `required_employee_types`
    are silently ignored on @api_view endpoints (see permissions.group_required), so most
    endpoints currently resolve to "any authenticated user". Guarding the API surface
    centrally means a subtenant cannot reach resident data through an endpoint whose own
    permission declaration does not hold.
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
