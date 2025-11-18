from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.models import Group
from django.db.models import Count

from ..models import BudgetRequest, BudgetVote, Engagement, Tenant, GlobalAppSettings
from ..serializers import BudgetRequestSerializer, CreateBudgetRequestSerializer
from ..permissions import GroupAndEmployeeTypePermission
from ..utils.email_utils import send_email_message
from .. import config as app_config

import logging

logger = logging.getLogger(__name__)

HEIMRAT_GROUP = 'Heimrat'
FINANZEN_GROUP = 'Finanzreferat'
ADMIN_GROUP = 'ADMIN'

def _is_user_in_group(user, group_name):
    return user.groups.filter(name=group_name).exists() or user.is_superuser

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_user_engagements_for_budget(request):
    """
    Returns engagements that are valid for making budget requests.
    """
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        # Get active engagements
        settings = GlobalAppSettings.load()
        engagements = Engagement.objects.filter(
            tenant=tenant,
            semester=settings.current_semester
        ).select_related('department')
        
        data = [{
            'department_id': eng.department.id,
            'department_name': eng.department.full_name
        } for eng in engagements]
        
        return Response(data)
    except Tenant.DoesNotExist:
        print("Tenant does not exist")
        return Response([], status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@parser_classes([MultiPartParser, FormParser])
@transaction.atomic
def create_budget_request(request):
    """
    Creates a new budget request.
    """
    create_budget_request.required_employee_types = ['TENANT']

    serializer = CreateBudgetRequestSerializer(data=request.data)
    if not serializer.is_valid():
        print("Serializer errors:", serializer.errors )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    receipt_file = data.pop('receipt')
    
    # Verify user has engagement in this department
    try:
        print("Fetching tenant for user:", request.user.username  )
        tenant = Tenant.objects.get(username=request.user.username)
        settings = GlobalAppSettings.load()
        has_engagement = Engagement.objects.filter(
            tenant=tenant,
            department=data['department'],
            semester=settings.current_semester
        ).exists()
        
        if not has_engagement and not request.user.is_superuser:
             return Response({"error": "You are not a member of this department."}, status=status.HTTP_403_FORBIDDEN)

        # Create object
        budget_request = BudgetRequest.objects.create(
            **data,
            tenant=tenant,
            receipt_file=receipt_file.read(),
            receipt_filename=receipt_file.name,
            status=BudgetRequest.Status.OPEN
        )

        # Send Notifications
        recipients = ['finanzen@schollheim.net']
        if budget_request.type == BudgetRequest.Type.BUDGET:
            recipients.append('heimrat@schollheim.net')
        
        email_context = {
            'requester': budget_request.requester_name,
            'department': budget_request.department.full_name,
            'amount': budget_request.amount,
            'type': budget_request.get_type_display(),
            'description': budget_request.description
        }
        
        # Note: You'll need to create this template
        # send_email_message(recipients, "Neuer Finanzantrag eingegangen", "email/budget-request-new.html", context=email_context)
        
        return Response(BudgetRequestSerializer(budget_request).data, status=status.HTTP_201_CREATED)

    except Tenant.DoesNotExist:
        return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error creating budget request: {e}", exc_info=True)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_budget_requests(request):
    """
    Lists requests based on user role.
    """
    user = request.user
    is_finanzer = _is_user_in_group(user, FINANZEN_GROUP)
    is_heimrat = _is_user_in_group(user, HEIMRAT_GROUP)
    
    queryset = BudgetRequest.objects.select_related('department', 'tenant').prefetch_related('votes', 'votes__voter')
    
    status_filter = request.query_params.get('status')
    
    if is_finanzer or user.is_superuser:
        # Finanzer see everything
        if status_filter:
            queryset = queryset.filter(status=status_filter)
    elif is_heimrat:
        # Heimrat sees OPEN Budget Requests mainly, but can see history
        # The requirement says "List of open budget requests"
        if status_filter:
             queryset = queryset.filter(status=status_filter)
        
        # Heimrat only votes on BUDGET type, but might see others for info? 
        # Prompt says "Only accessible for Finanzreferat and Heimrat". 
        # I'll show all to Heimrat but frontend handles actions.
    else:
        # Tenants only see their department's requests
        try:
            tenant = Tenant.objects.get(username=user.username)
            settings = GlobalAppSettings.load()
            my_department_ids = Engagement.objects.filter(
                tenant=tenant, 
                semester=settings.current_semester
            ).values_list('department_id', flat=True)
            
            queryset = queryset.filter(department_id__in=my_department_ids)
        except Tenant.DoesNotExist:
            return Response([], status=status.HTTP_200_OK)

    queryset = queryset.order_by('-created_at')
    serializer = BudgetRequestSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def vote_budget_request(request, request_id):
    """
    Heimrat voting logic.
    """
    vote_budget_request.required_groups = [HEIMRAT_GROUP, ADMIN_GROUP]
    
    budget_request = get_object_or_404(BudgetRequest, id=request_id)
    
    if budget_request.type != BudgetRequest.Type.BUDGET:
        return Response({"error": "Voting is only for Budget Requests."}, status=status.HTTP_400_BAD_REQUEST)
    
    if budget_request.status != BudgetRequest.Status.OPEN:
        return Response({"error": "Request is not open."}, status=status.HTTP_400_BAD_REQUEST)

    decision = request.data.get('vote') # APPROVE or REJECT
    if decision not in [BudgetVote.Vote.APPROVE, BudgetVote.Vote.REJECT]:
        return Response({"error": "Invalid vote."}, status=status.HTTP_400_BAD_REQUEST)

    # Record vote
    BudgetVote.objects.update_or_create(
        request=budget_request,
        voter=request.user,
        defaults={'vote': decision}
    )

    # Check for majority
    # 1. Get total Heimrat members
    heimrat_group = Group.objects.get(name=HEIMRAT_GROUP)
    total_members = heimrat_group.user_set.count()
    
    # 2. Count votes
    votes = BudgetVote.objects.filter(request=budget_request)
    votes_count = votes.count()
    
    if votes_count >= total_members and total_members > 0:
        # All voted, decide
        approve_count = votes.filter(vote=BudgetVote.Vote.APPROVE).count()
        # Tie implies rejection based on prompt "majority must agree"
        if approve_count > (total_members / 2):
            budget_request.status = BudgetRequest.Status.APPROVED
            _send_status_email(budget_request, True)
        else:
            budget_request.status = BudgetRequest.Status.REJECTED
            _send_status_email(budget_request, False)
        
        budget_request.save()
        return Response({"message": f"Vote cast. Request finalized as {budget_request.status}."}, status=status.HTTP_200_OK)

    return Response({"message": "Vote cast. Waiting for others."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def manage_request_status(request, request_id):
    """
    For Finanzreferat to Approve (Reimbursement) or Mark Paid.
    """
    manage_request_status.required_groups = [FINANZEN_GROUP, ADMIN_GROUP]
    
    budget_request = get_object_or_404(BudgetRequest, id=request_id)
    action = request.data.get('action') # APPROVE, REJECT, PAID

    if action == 'APPROVE':
        if budget_request.type == BudgetRequest.Type.BUDGET:
             return Response({"error": "Budget requests need Heimrat voting."}, status=status.HTTP_400_BAD_REQUEST)
        budget_request.status = BudgetRequest.Status.APPROVED
        _send_status_email(budget_request, True)
        
    elif action == 'REJECT':
        budget_request.status = BudgetRequest.Status.REJECTED
        _send_status_email(budget_request, False)
        
    elif action == 'PAID':
        if budget_request.status != BudgetRequest.Status.APPROVED:
             return Response({"error": "Request must be approved before payment."}, status=status.HTTP_400_BAD_REQUEST)
        budget_request.status = BudgetRequest.Status.PAID
    
    else:
         return Response({"error": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)

    budget_request.save()
    return Response(BudgetRequestSerializer(budget_request).data)

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def delete_budget_request(request, request_id):
    budget_request = get_object_or_404(BudgetRequest, id=request_id)
    
    # Check permissions: Creator or Finanzer/Admin
    is_finanzer = _is_user_in_group(request.user, FINANZEN_GROUP)
    is_creator = False
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        if budget_request.tenant == tenant:
            is_creator = True
    except:
        pass

    if not (is_finanzer or is_creator):
         return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
    
    if is_creator and budget_request.status != BudgetRequest.Status.OPEN:
         return Response({"error": "Cannot delete processed requests."}, status=status.HTTP_400_BAD_REQUEST)

    budget_request.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_receipt_pdf(request, request_id):
    budget_request = get_object_or_404(BudgetRequest, id=request_id)
    
    if not budget_request.receipt_file:
        return HttpResponse("No receipt found", status=404)
        
    response = HttpResponse(budget_request.receipt_file, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{budget_request.receipt_filename}"'
    return response

def _send_status_email(budget_request, approved):
    subject = f"Antrag {budget_request.id} Statusupdate"
    # template selection logic...
    # send_email_message([budget_request.email], subject, template, context)
    pass