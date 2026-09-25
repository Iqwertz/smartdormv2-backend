"""
German texts for the error responses DRF writes itself (403, 404, not logged in, CSRF).

The frontend shows `detail` to the user as it comes, and the rest of the API speaks German
with "du". Switching LANGUAGE_CODE to German would not help: DRF's own German translation
uses "Sie". So only DRF's default English texts are swapped here. A view's own message, and
dict bodies such as the Pi agent's {"error": "Unauthorized."}, pass through unchanged.
"""

from rest_framework.views import exception_handler as drf_exception_handler

GERMAN_DETAILS = {
    "Authentication credentials were not provided.": "Du bist nicht angemeldet. Melde dich neu an.",
    "Incorrect authentication credentials.": "Die Anmeldung ist fehlgeschlagen. Melde dich neu an.",
    "You do not have permission to perform this action.": "Dafür fehlen dir die Rechte.",
    "Not found.": "Nicht gefunden.",
    "Malformed request.": "Ungültige Anfrage.",
}

CSRF_PREFIX = "CSRF Failed"
CSRF_DETAIL = "Deine Sitzung passt nicht mehr. Lad die Seite neu und versuch's nochmal."


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response

    detail = response.data.get("detail")
    if not isinstance(detail, str):
        return response

    if detail in GERMAN_DETAILS:
        response.data["detail"] = GERMAN_DETAILS[detail]
    elif detail.startswith(CSRF_PREFIX):
        response.data["detail"] = CSRF_DETAIL
    return response
