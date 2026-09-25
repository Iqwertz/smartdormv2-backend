"""
Startup checks. Django runs them before runserver, migrate (and with it every deploy, see
deploy.sh) and `manage.py check`; any Error aborts the command.
"""

from django.core.checks import Error, Tags, register

from .access_inventory import iter_api_endpoints


@register(Tags.security)
def check_api_access_rules(app_configs, **kwargs):
    """Every API endpoint must declare exactly one access rule from permissions.py."""
    errors = []
    for endpoint in iter_api_endpoints():
        if endpoint.rule is not None:
            continue

        if endpoint.view_class is None:
            found = "not a DRF view"
        else:
            found = ", ".join(getattr(c, "__name__", repr(c)) for c in endpoint.view_class.permission_classes) or "none"

        errors.append(Error(
            f"{endpoint.name} (/{endpoint.path}) does not declare exactly one access rule (found: {found}).",
            hint=(
                "Decorate the view with @permission_classes([<rule>]) using one rule from "
                "smartdorm/permissions.py (e.g. IsVerwaltung, LoggedIn). Plain DRF classes such as "
                "IsAuthenticated are not accepted, and requirements set on the view function are "
                "ignored by DRF. See docs/authentication_permissions.md."
            ),
            id="smartdorm.E001",
        ))
    return errors
