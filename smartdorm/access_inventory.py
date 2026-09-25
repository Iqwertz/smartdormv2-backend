"""
The list of API endpoints and the access rule each one declares.

Used by the startup check (checks.py), `manage.py list_api_access` and the access snapshot test,
so all three see the API the same way.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from django.urls import URLResolver, get_resolver

from .permissions import AccessRule, GroupRule

API_PREFIX = "api/"

# Reviewed record of who may call what; the snapshot test fails when the code drifts from it.
SNAPSHOT_PATH = Path(__file__).parent / "tests" / "api_access.txt"


@dataclass
class ApiEndpoint:
    path: str
    view: object  # the callable Django routes to

    @property
    def view_class(self):
        return getattr(self.view, "cls", None)  # set by DRF's as_view()

    @property
    def name(self):
        # as_view() always returns a function called "view"; @api_view names the class after
        # the decorated function instead.
        named = self.view_class or self.view
        return f"{named.__module__}.{named.__name__}"

    @property
    def methods(self):
        if self.view_class is None:
            return []
        return sorted(m.upper() for m in self.view_class.http_method_names if m != "options")

    @property
    def rule(self):
        """The single access rule the view declares, or None if it does not declare exactly one."""
        if self.view_class is None:
            return None

        classes = list(self.view_class.permission_classes)
        if len(classes) != 1:
            return None

        rule = classes[0]
        is_usable_rule = (
            isinstance(rule, type)
            and issubclass(rule, AccessRule)
            and rule not in (AccessRule, GroupRule)
        )
        return rule if is_usable_rule else None


def iter_api_endpoints(patterns=None, prefix=""):
    """Yields every URL under /api/, following include()s."""
    if patterns is None:
        patterns = get_resolver().url_patterns

    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from iter_api_endpoints(pattern.url_patterns, route)
        elif route.startswith(API_PREFIX):
            yield ApiEndpoint(route, pattern.callback)


def render_access_table(rule_name=None):
    """
    Endpoints grouped by the rule that guards them, one block per rule:

        IsVerwaltung - VERWALTUNG, ADMIN
          GET             /api/common/room-list/
    """
    by_rule = defaultdict(list)
    for endpoint in iter_api_endpoints():
        rule = endpoint.rule
        header = f"{rule.__name__} - {rule.describe()}" if rule else "!! NO VALID ACCESS RULE"
        if rule_name is None or (rule and rule.__name__ == rule_name):
            by_rule[header].append(f"  {','.join(endpoint.methods):<15} /{endpoint.path}")

    blocks = [header + "\n" + "\n".join(sorted(lines)) for header, lines in sorted(by_rule.items())]
    return "\n\n".join(blocks) + "\n" if blocks else ""
