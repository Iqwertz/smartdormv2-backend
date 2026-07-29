"""
Netzwerkreferat views for managing "special" LDAP role assignments.

A role assignment records that an account was deliberately put into an LDAP group by
hand. The nightly `recalculate_tenant_stats` command reads these records and treats the
groups as owed, so they survive the nightly reconciliation instead of being stripped.
"""

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from ..models import LdapRoleAssignment
from ..permissions import group_required
from ..serializers import LdapRoleAssignmentSerializer, LdapRoleAssignmentCreateSerializer
from ..utils import ldap_utils

logger = logging.getLogger(__name__)

# Built as a permission class rather than declared via `required_groups`, which has no
# effect on @api_view endpoints - see group_required() in permissions.py.
IsNetworkAdmin = group_required("Netzwerkreferat", "ADMIN")


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsNetworkAdmin])
def list_ldap_role_assignments_view(request):
    """Lists all special role assignments, newest first."""
    assignments = LdapRoleAssignment.objects.all().order_by('-created_at')
    return Response(LdapRoleAssignmentSerializer(assignments, many=True).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsNetworkAdmin])
def create_ldap_role_assignment_view(request):
    """
    Records a special role assignment and applies it in LDAP right away.

    Both the account and the group are verified to exist first: add_user_to_group()
    reports success when either is missing, so without these checks a typo would be
    stored as a working assignment.
    """
    serializer = LdapRoleAssignmentCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    username = (serializer.validated_data.get('username') or '').strip()
    group_dn = (serializer.validated_data.get('group_dn') or '').strip()

    if not username or not group_dn:
        return Response({"error": "Benutzer und Rollen-DN sind erforderlich."}, status=status.HTTP_400_BAD_REQUEST)

    if LdapRoleAssignment.objects.filter(username__iexact=username, group_dn__iexact=group_dn).exists():
        return Response(
            {"error": f"Für '{username}' existiert bereits eine Zuweisung für diese Rolle."},
            status=status.HTTP_409_CONFLICT
        )

    try:
        if not ldap_utils.ldap_username_exists(username):
            return Response({"error": f"Der LDAP-Benutzer '{username}' existiert nicht."}, status=status.HTTP_400_BAD_REQUEST)

        if not ldap_utils.ldap_group_exists(group_dn):
            return Response({"error": f"Die LDAP-Gruppe '{group_dn}' existiert nicht."}, status=status.HTTP_400_BAD_REQUEST)
    except ConnectionError as e:
        logger.error(f"LDAP unavailable while validating role assignment for '{username}': {e}")
        return Response({"error": "Der LDAP-Server ist nicht erreichbar."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        with transaction.atomic():
            assignment = serializer.save(
                username=username,
                group_dn=group_dn,
                created_by=request.user.username,
            )

            if not ldap_utils.add_user_to_group(username, group_dn):
                # Roll the record back so the list never shows a grant that was not applied.
                raise RuntimeError(f"LDAP rejected adding '{username}' to '{group_dn}'.")
    except RuntimeError as e:
        logger.error(f"Failed to grant special role: {e}")
        return Response({"error": "Die Rolle konnte in LDAP nicht gesetzt werden."}, status=status.HTTP_502_BAD_GATEWAY)

    logger.info(
        f"User '{request.user.username}' granted special LDAP role '{group_dn}' to '{username}' "
        f"(expires: {assignment.expires_at or 'never'}, reason: {assignment.note or '-'})."
    )
    return Response(LdapRoleAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsNetworkAdmin])
def delete_ldap_role_assignment_view(request, assignment_id):
    """
    Revokes a special role assignment: removes the group in LDAP, then drops the record.

    The record is kept when LDAP removal fails, so the assignment can be retried instead
    of silently staying in effect.
    """
    assignment = get_object_or_404(LdapRoleAssignment, id=assignment_id)

    try:
        removed = ldap_utils.remove_user_from_group(assignment.username, assignment.group_dn)
    except ConnectionError as e:
        logger.error(f"LDAP unavailable while revoking role assignment {assignment_id}: {e}")
        return Response({"error": "Der LDAP-Server ist nicht erreichbar."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not removed:
        return Response({"error": "Die Rolle konnte in LDAP nicht entfernt werden."}, status=status.HTTP_502_BAD_GATEWAY)

    logger.info(
        f"User '{request.user.username}' revoked special LDAP role '{assignment.group_dn}' "
        f"from '{assignment.username}'."
    )
    assignment.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsNetworkAdmin])
def list_ldap_groups_view(request):
    """Every group in the directory, for the role dropdown."""
    try:
        return Response(ldap_utils.list_ldap_groups(), status=status.HTTP_200_OK)
    except ConnectionError as e:
        logger.error(f"Could not list LDAP groups: {e}")
        return Response({"error": "LDAP-Gruppen konnten nicht geladen werden."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsNetworkAdmin])
def list_ldap_users_view(request):
    """Every account in the directory, for the user picker."""
    try:
        return Response(ldap_utils.list_ldap_users(), status=status.HTTP_200_OK)
    except ConnectionError as e:
        logger.error(f"Could not list LDAP users: {e}")
        return Response({"error": "LDAP-Benutzer konnten nicht geladen werden."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

