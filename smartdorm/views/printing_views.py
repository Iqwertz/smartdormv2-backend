"""
Print & Scan System Views for SmartDorm

This module implements the API endpoints for the printing and scanning system.
"""
import os
import logging
import requests
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.http import FileResponse, Http404
from datetime import timedelta
from decimal import Decimal

from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from ..models import Tenant, Device, PrintSession, PrintJob, Scan
from ..serializers import (
    DeviceStatusSerializer, MyCostsSerializer, PrintSessionSerializer,
    PrintSessionDetailSerializer, PrintJobSerializer, PrintJobCreateSerializer, ScanSerializer
)
from ..utils.cups_utils import submit_print_job, get_job_status, is_job_completed, is_job_failed
from ..permissions import GroupAndEmployeeTypePermission

logger = logging.getLogger(__name__)


# ============================================================================
# Tenant Endpoints (for regular users)
# ============================================================================

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_status_view(request):
    """
    GET /api/tenants/printing/device-status/
    
    Returns the current status of the printer:
    - Available/Occupied
    - Active session info (if available)
    """
    device_status_view.required_employee_types = ['TENANT']
    
    try:
        # Get the first (and only) device
        device = Device.objects.filter(is_active=True).first()
        if not device:
            # Return a proper response with device not found info
            # Use 200 OK instead of 404 so the frontend can handle it gracefully
            return Response(
                {
                    "error": "No active device found.",
                    "device_id": None,
                    "device_name": None,
                    "location": None,
                    "is_active": False,
                    "allow_new_sessions": False,
                    "price_per_page_color": "0.10",
                    "price_per_page_gray": "0.05",
                    "active_session": None,
                    "available": False
                },
                status=status.HTTP_200_OK
            )
        
        # Check for active session
        active_session = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        active_session_data = None
        if active_session:
            # Check if session has expired
            max_duration = timedelta(minutes=device.max_session_duration_minutes)
            if timezone.now() > active_session.started_at + max_duration:
                # Automatically mark session as EXPIRED
                active_session.status = PrintSession.Status.EXPIRED
                active_session.ended_at = timezone.now()
                active_session.save()
                active_session = None
            else:
                active_session_data = {
                    'session_id': active_session.external_id,
                    'tenant_name': active_session.tenant.get_full_name(),
                    'started_at': active_session.started_at,
                    'is_mine': active_session.tenant.username == request.user.username
                }
        
        serializer = DeviceStatusSerializer({
            'device_id': device.id,
            'device_name': device.name,
            'location': device.location,
            'is_active': device.is_active,
            'allow_new_sessions': device.allow_new_sessions,
            'price_per_page_color': str(device.price_per_page_color),
            'price_per_page_gray': str(device.price_per_page_gray),
            'active_session': active_session_data,
            'available': device.is_active and device.allow_new_sessions and active_session is None
        })
        
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in device_status_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving device status."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def my_costs_view(request):
    """
    GET /api/tenants/printing/my-costs/
    
    Returns cost overview for the logged-in user.
    """
    my_costs_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        
        # All successful jobs of the user
        # Only sum actual stored cost values (including 0 if that's what was stored)
        all_jobs = PrintJob.objects.filter(
            tenant=tenant,
            status=PrintJob.Status.COMPLETED,
            cost__isnull=False  # Only include jobs with a cost value stored
        )
        
        # Jobs from this month
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_jobs = all_jobs.filter(created_at__gte=month_start)
        
        # Calculate costs - sum only stored cost values (don't recalculate)
        total_cost = sum(job.cost for job in all_jobs) or Decimal('0.00')
        this_month_cost = sum(job.cost for job in this_month_jobs) or Decimal('0.00')
        
        # Calculate pages
        total_pages = sum(job.pages for job in all_jobs if job.pages) or 0
        this_month_pages = sum(job.pages for job in this_month_jobs if job.pages) or 0
        
        serializer = MyCostsSerializer({
            'total_cost': total_cost,
            'this_month_cost': this_month_cost,
            'total_pages': total_pages,
            'this_month_pages': this_month_pages,
            'total_jobs': all_jobs.count(),
            'this_month_jobs': this_month_jobs.count()
        })
        
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Tenant.DoesNotExist:
        return Response(
            {"error": "Tenant profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in my_costs_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving costs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def my_sessions_view(request):
    """
    GET /api/tenants/printing/my-sessions/
    
    Returns all sessions of the logged-in user.
    """
    my_sessions_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        sessions = PrintSession.objects.filter(tenant=tenant).order_by('-started_at')
        
        serializer = PrintSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Tenant.DoesNotExist:
        return Response(
            {"error": "Tenant profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in my_sessions_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving sessions."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def my_scans_view(request):
    """
    GET /api/tenants/printing/my-scans/
    
    Returns all scans of the logged-in user (from all sessions).
    """
    my_scans_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        scans = Scan.objects.filter(tenant=tenant).order_by('-scanned_at')
        
        # Limit to last 50 scans for performance
        scans = scans[:50]
        
        serializer = ScanSerializer(scans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Tenant.DoesNotExist:
        return Response(
            {"error": "Tenant profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in my_scans_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving scans."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def start_session_view(request):
    """
    POST /api/tenants/printing/sessions/start/
    
    Starts a new print session for the logged-in user.
    """
    start_session_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        
        # Get device
        device = Device.objects.filter(is_active=True).first()
        if not device:
            return Response(
                {"error": "No active device found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if new sessions are allowed
        if not device.allow_new_sessions:
            return Response(
                {"error": "New sessions are currently disabled."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if active session already exists
        active_session = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        if active_session:
            # Check if session has expired
            max_duration = timedelta(minutes=device.max_session_duration_minutes)
            if timezone.now() > active_session.started_at + max_duration:
                active_session.status = PrintSession.Status.EXPIRED
                active_session.ended_at = timezone.now()
                active_session.save()
            else:
                return Response(
                    {"error": "Device is currently in use."},
                    status=status.HTTP_409_CONFLICT
                )
        
        # Check if user already has an active session (only one per user)
        user_active_session = PrintSession.objects.filter(
            tenant=tenant,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        if user_active_session:
            return Response(
                {"error": "You already have an active session."},
                status=status.HTTP_409_CONFLICT
            )
        
        # Create new session
        with transaction.atomic():
            session = PrintSession.objects.create(
                tenant=tenant,
                device=device,
                status=PrintSession.Status.ACTIVE
            )
        
        serializer = PrintSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Tenant.DoesNotExist:
        return Response(
            {"error": "Tenant profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in start_session_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while starting session."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def session_detail_view(request, session_id):
    """
    GET /api/tenants/printing/sessions/{session_id}/
    
    Returns session details (including jobs and scans).
    Automatically updates the status of active print jobs.
    """
    session_detail_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Aktualisiere Status von aktiven Jobs (PRINTING oder PENDING mit CUPS-Job-ID)
        active_jobs = PrintJob.objects.filter(
            session=session,
            cups_job_id__isnull=False
        ).exclude(status__in=[PrintJob.Status.COMPLETED, PrintJob.Status.FAILED, PrintJob.Status.CANCELLED])
        
        for job in active_jobs:
            if job.device and job.device.cups_printer_name and job.cups_job_id:
                job_status = get_job_status(job.device.cups_printer_name, job.cups_job_id)
                if job_status:
                    logger.debug(f"Job {job.cups_job_id} status: state={job_status.get('job_state')}, reasons={job_status.get('job_state_reasons')}")
                    if is_job_completed(job_status['job_state']):
                        job.status = PrintJob.Status.COMPLETED
                        job.completed_at = timezone.now()
                        job.error_message = None  # Remove error message on success
                        # Update page count if available from CUPS
                        # Prefer CUPS value, but keep existing value if CUPS doesn't provide one
                        if 'pages' in job_status and job_status['pages'] is not None and job_status['pages'] > 0:
                            # CUPS provided a valid page count - use it
                            old_pages = job.pages
                            job.pages = job_status['pages']
                            if old_pages != job.pages:
                                logger.info(f"Updated job {job.cups_job_id} pages from {old_pages} to {job.pages} (from CUPS)")
                            else:
                                logger.debug(f"Job {job.cups_job_id} pages unchanged: {job.pages} (from CUPS)")
                        elif job.pages is None or job.pages == 0:
                            # No valid page count from CUPS and no existing value - default to 1
                            job.pages = 1
                            logger.warning(f"Job {job.cups_job_id} has no page count from CUPS (CUPS returned: {job_status.get('pages')}), defaulting to 1")
                        else:
                            # Keep existing page count if CUPS doesn't provide one
                            logger.debug(f"Job {job.cups_job_id} keeping existing page count: {job.pages} (CUPS returned: {job_status.get('pages')})")
                        
                        # Cost is automatically calculated in job.save() (via Model.save() method)
                        # Log BEFORE save to see what will be calculated
                        logger.info(f"Job {job.cups_job_id} before save: pages={job.pages}, color_mode={job.color_mode}, device_price_color={job.device.price_per_page_color if job.device else 'N/A'}, device_price_gray={job.device.price_per_page_gray if job.device else 'N/A'}")
                        job.save()
                        logger.info(f"Job {job.cups_job_id} marked as COMPLETED: pages={job.pages}, color_mode={job.color_mode}, cost={job.cost}")
                    elif is_job_failed(job_status['job_state'], job_status.get('job_state_reasons', [])):
                        job.status = PrintJob.Status.FAILED
                        # Ensure job_state_reasons is treated as a list
                        reasons = job_status.get('job_state_reasons', [])
                        if isinstance(reasons, str):
                            job.error_message = reasons
                        elif isinstance(reasons, list):
                            job.error_message = ', '.join(str(r) for r in reasons)
                        else:
                            job.error_message = str(reasons)
                        job.save()
                        logger.warning(f"Job {job.cups_job_id} marked as FAILED: {job.error_message}")
                    else:
                        # Job is still running (e.g. job-state=4 with reason="job-printing")
                        # Status remains PRINTING, remove error message if present
                        if job.status == PrintJob.Status.FAILED:
                            # Correct: Job is still running, not failed
                            job.status = PrintJob.Status.PRINTING
                            job.error_message = None
                            job.save()
                            logger.info(f"Job {job.cups_job_id} corrected from FAILED to PRINTING (still running)")
                        logger.debug(f"Job {job.cups_job_id} still printing/processing")
                else:
                    # Job not found in CUPS - might mean it's already deleted
                    # After a while (e.g. 2 minutes) assume completed
                    # (CUPS often deletes jobs quickly after printing)
                    time_since_created = timezone.now() - job.created_at
                    if time_since_created > timedelta(minutes=2):
                        # Probably finished printing and removed from CUPS
                        job.status = PrintJob.Status.COMPLETED
                        job.completed_at = timezone.now()
                        job.error_message = None  # Remove error message
                        # Estimate page count (can be updated later)
                        # For now: 1 page as default
                        if job.pages is None:
                            job.pages = 1
                        # Kosten werden automatisch in job.save() berechnet (via Model.save() Methode)
                        job.save()
                        logger.info(f"Job {job.cups_job_id} not found in CUPS, marked as completed (assumed finished)")
        
        serializer = PrintSessionDetailSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in session_detail_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving session details."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def end_session_view(request, session_id):
    """
    POST /api/tenants/printing/sessions/{session_id}/end/
    
    Ends a user's own session.
    """
    end_session_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if session is still active
        if session.status != PrintSession.Status.ACTIVE:
            return Response(
                {"error": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # End session
        with transaction.atomic():
            session.status = PrintSession.Status.COMPLETED
            session.ended_at = timezone.now()
            session.save()
        
        serializer = PrintSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in end_session_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while ending session."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@parser_classes([MultiPartParser, FormParser])  # Allows multipart/form-data for file uploads
@transaction.atomic
def print_job_view(request, session_id):
    """
    POST /api/tenants/printing/sessions/{session_id}/print/
    
    Creates a new print job within a session.
    Expects multipart form with file upload.
    """
    print_job_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user and is active
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if session.status != PrintSession.Status.ACTIVE:
            return Response(
                {"error": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if file was uploaded
        if 'file' not in request.FILES:
            return Response(
                {"error": "No file uploaded."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        filename = file.name
        
        # Parse print options from request
        options_serializer = PrintJobCreateSerializer(data=request.data)
        if not options_serializer.is_valid():
            return Response(
                options_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        options_data = options_serializer.validated_data
        color_mode = options_data.get('color_mode', 'Color')
        copies = options_data.get('copies', 1)
        
        # Log the received options for debugging
        logger.info(f"Creating print job: filename={filename}, color_mode={color_mode}, copies={copies}")
        
        # Create PrintJob
        print_job = PrintJob.objects.create(
            session=session,
            tenant=tenant,
            device=session.device,
            filename=filename,
            color_mode=color_mode,
            status=PrintJob.Status.PENDING
        )
        
        logger.info(f"Created PrintJob {print_job.external_id}: color_mode={print_job.color_mode}, device={print_job.device.name if print_job.device else 'None'}")
        
        # Read file content
        file_data = file.read()
        
        # Extract PDF page count as fallback if CUPS doesn't provide it
        # This helps ensure correct page count especially when CUPS reports incorrectly
        pdf_pages = None
        try:
            from io import BytesIO
            from pypdf import PdfReader
            pdf_reader = PdfReader(BytesIO(file_data))
            pdf_pages = len(pdf_reader.pages)
            logger.info(f"PDF {filename} has {pdf_pages} pages, copies={copies}, total pages={pdf_pages * copies}")
            # Store the estimated page count (PDF pages * copies) as initial value
            # This will be updated by CUPS when the job completes, but serves as fallback
            print_job.pages = pdf_pages * copies
            print_job.save()
            logger.info(f"Set initial pages for job {print_job.external_id}: {print_job.pages} (PDF pages * copies)")
        except Exception as e:
            logger.warning(f"Could not extract PDF page count: {e}")
            # If PDF parsing fails, we'll rely on CUPS
        
        # Prepare CUPS options
        # Try both IPP standard (print-color-mode) and PPD-specific (ColorModel) options
        # Some drivers ignore print-color-mode but accept ColorModel
        cups_options = {
            'copies': str(copies),
        }
        
        # Add color mode - try both option names for maximum compatibility
        if color_mode == 'Color':
            # IPP standard option (works with modern drivers)
            cups_options['print-color-mode'] = 'color'
            # PPD-specific option (works with older drivers that have ColorModel in PPD)
            # Try both CMYK and Color - different PPDs use different values
            # Based on PPD definition "*ColorModel CMYK/Color:" the value can be either "CMYK" or "Color"
            cups_options['ColorModel'] = 'CMYK'  # Primary value from PPD
            # Also try Color as alternative (some PPDs use this)
            # cups_options['ColorModel'] = 'Color'  # Alternative if CMYK doesn't work
        else:
            # Black & white
            cups_options['print-color-mode'] = 'monochrome'
            cups_options['ColorModel'] = 'Gray'
        
        logger.info(f"Prepared CUPS options for color_mode={color_mode}, copies={copies}: {cups_options}")
        
        # Send to CUPS
        cups_job_id = submit_print_job(
            printer_name=session.device.cups_printer_name,
            file_data=file_data,
            filename=filename,
            title=f"SmartDorm Print {print_job.external_id[:8]}",
            options=cups_options
        )
        
        if cups_job_id:
            print_job.cups_job_id = cups_job_id
            print_job.status = PrintJob.Status.PRINTING
            print_job.save()
        else:
            print_job.status = PrintJob.Status.FAILED
            print_job.error_message = "Failed to submit job to CUPS server"
            print_job.save()
        
        serializer = PrintJobSerializer(print_job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in print_job_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while creating print job."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def session_jobs_view(request, session_id):
    """
    GET /api/tenants/printing/sessions/{session_id}/jobs/
    
    Returns all print jobs of a session and updates the status of active jobs.
    """
    session_jobs_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Aktualisiere Status von aktiven Jobs (PRINTING oder PENDING mit CUPS-Job-ID)
        active_jobs = PrintJob.objects.filter(
            session=session,
            cups_job_id__isnull=False
        ).exclude(status__in=[PrintJob.Status.COMPLETED, PrintJob.Status.FAILED, PrintJob.Status.CANCELLED])
        
        for job in active_jobs:
            if job.device and job.device.cups_printer_name and job.cups_job_id:
                job_status = get_job_status(job.device.cups_printer_name, job.cups_job_id)
                if job_status:
                    logger.debug(f"Job {job.cups_job_id} status: state={job_status.get('job_state')}, reasons={job_status.get('job_state_reasons')}")
                    if is_job_completed(job_status['job_state']):
                        job.status = PrintJob.Status.COMPLETED
                        job.completed_at = timezone.now()
                        job.error_message = None  # Remove error message on success
                        # Update page count if available from CUPS
                        # Prefer CUPS value, but keep existing value if CUPS doesn't provide one
                        if 'pages' in job_status and job_status['pages'] is not None and job_status['pages'] > 0:
                            # CUPS provided a valid page count - use it
                            old_pages = job.pages
                            job.pages = job_status['pages']
                            if old_pages != job.pages:
                                logger.info(f"Updated job {job.cups_job_id} pages from {old_pages} to {job.pages} (from CUPS)")
                            else:
                                logger.debug(f"Job {job.cups_job_id} pages unchanged: {job.pages} (from CUPS)")
                        elif job.pages is None or job.pages == 0:
                            # No valid page count from CUPS and no existing value - default to 1
                            job.pages = 1
                            logger.warning(f"Job {job.cups_job_id} has no page count from CUPS (CUPS returned: {job_status.get('pages')}), defaulting to 1")
                        else:
                            # Keep existing page count if CUPS doesn't provide one
                            logger.debug(f"Job {job.cups_job_id} keeping existing page count: {job.pages} (CUPS returned: {job_status.get('pages')})")
                        
                        # Cost is automatically calculated in job.save() (via Model.save() method)
                        # Log BEFORE save to see what will be calculated
                        logger.info(f"Job {job.cups_job_id} before save: pages={job.pages}, color_mode={job.color_mode}, device_price_color={job.device.price_per_page_color if job.device else 'N/A'}, device_price_gray={job.device.price_per_page_gray if job.device else 'N/A'}")
                        job.save()
                        logger.info(f"Job {job.cups_job_id} marked as COMPLETED: pages={job.pages}, color_mode={job.color_mode}, cost={job.cost}")
                    elif is_job_failed(job_status['job_state'], job_status.get('job_state_reasons', [])):
                        job.status = PrintJob.Status.FAILED
                        # Ensure job_state_reasons is treated as a list
                        reasons = job_status.get('job_state_reasons', [])
                        if isinstance(reasons, str):
                            job.error_message = reasons
                        elif isinstance(reasons, list):
                            job.error_message = ', '.join(str(r) for r in reasons)
                        else:
                            job.error_message = str(reasons)
                        job.save()
                        logger.warning(f"Job {job.cups_job_id} marked as FAILED: {job.error_message}")
                    else:
                        # Job is still running (e.g. job-state=4 with reason="job-printing")
                        # Status remains PRINTING, remove error message if present
                        if job.status == PrintJob.Status.FAILED:
                            # Correct: Job is still running, not failed
                            job.status = PrintJob.Status.PRINTING
                            job.error_message = None
                            job.save()
                            logger.info(f"Job {job.cups_job_id} corrected from FAILED to PRINTING (still running)")
                        logger.debug(f"Job {job.cups_job_id} still printing/processing")
                else:
                    # Job not found in CUPS - might mean it's already deleted
                    # After a while (e.g. 2 minutes) assume completed
                    # (CUPS often deletes jobs quickly after printing)
                    time_since_created = timezone.now() - job.created_at
                    if time_since_created > timedelta(minutes=2):
                        # Probably finished printing and removed from CUPS
                        job.status = PrintJob.Status.COMPLETED
                        job.completed_at = timezone.now()
                        job.error_message = None  # Remove error message
                        # Estimate page count (can be updated later)
                        # For now: 1 page as default
                        if job.pages is None:
                            job.pages = 1
                        # Kosten werden automatisch in job.save() berechnet (via Model.save() Methode)
                        job.save()
                        logger.info(f"Job {job.cups_job_id} not found in CUPS, marked as completed (assumed finished)")
        
        jobs = PrintJob.objects.filter(session=session).order_by('-created_at')
        serializer = PrintJobSerializer(jobs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in session_jobs_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving jobs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def start_scan_view(request, session_id):
    """
    POST /api/tenants/printing/sessions/{session_id}/scan/start/
    
    Starts a scan at the printer via Pi service.
    """
    start_scan_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if session is still active
        if session.status != PrintSession.Status.ACTIVE:
            return Response(
                {"error": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Scan options from request (optional, default values)
        resolution = request.data.get('resolution', 300)
        mode = request.data.get('mode', 'Color')  # Color or Gray
        source = request.data.get('source', 'Flatbed')  # Flatbed or ADF
        
        # Call Pi service
        try:
            pi_url = f"{settings.PI_SCAN_SERVICE_URL}/scan/start"
            logger.info(f"Calling Pi scan service at: {pi_url}")
            payload = {
                "session_id": session.external_id,
                "resolution": resolution,
                "mode": mode,
                "source": source
            }
            
            response = requests.post(
                pi_url,
                json=payload,
                timeout=settings.PI_SCAN_SERVICE_TIMEOUT
            )
            
            if response.status_code == 200:
                pi_response = response.json()
                return Response({
                    "scan_id": pi_response.get("scan_id"),
                    "status": pi_response.get("status", "pending"),
                    "message": "Scan started successfully."
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Pi-Service error: {response.status_code} - {response.text}")
                return Response(
                    {"error": f"Scan service error: {response.status_code}"},
                    status=status.HTTP_502_BAD_GATEWAY
                )
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to Pi scan service: {pi_url}")
            return Response(
                {"error": "Scan service timeout. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error to Pi scan service: {pi_url}")
            return Response(
                {"error": "Cannot connect to scan service. Please check configuration."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.error(f"Error calling Pi scan service: {e}", exc_info=True)
            return Response(
                {"error": "An error occurred while starting scan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in start_scan_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while starting scan."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def session_scans_view(request, session_id):
    """
    GET /api/tenants/printing/sessions/{session_id}/scans/
    
    Returns all scans of a session.
    """
    session_scans_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        session = PrintSession.objects.get(external_id=session_id)
        
        # Check if session belongs to user
        if session.tenant != tenant:
            return Response(
                {"error": "Session not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        scans = Scan.objects.filter(session=session).order_by('-scanned_at')
        serializer = ScanSerializer(scans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except (Tenant.DoesNotExist, PrintSession.DoesNotExist):
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in session_scans_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving scans."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def download_scan_view(request, scan_id):
    """
    GET /api/tenants/printing/scans/{scan_id}/download/
    
    Downloads a scanned document.
    """
    download_scan_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        scan = Scan.objects.get(external_id=scan_id)
        
        # Check if scan belongs to user
        if scan.tenant != tenant:
            return Response(
                {"error": "Scan not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Construct file path
        file_path = os.path.join(settings.MEDIA_ROOT, scan.file_path)
        
        if not os.path.exists(file_path):
            logger.warning(f"Scan file not found: {file_path}")
            return Response(
                {"error": "File not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Return file
        file_response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf'
        )
        file_response['Content-Disposition'] = f'attachment; filename="{scan.filename}"'
        return file_response
        
    except (Tenant.DoesNotExist, Scan.DoesNotExist):
        return Response(
            {"error": "Scan not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in download_scan_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while downloading scan."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# Pi Endpoints (without authentication for scan monitor)
# ============================================================================

@api_view(['GET'])
@permission_classes([])  # No authentication required
def active_session_view(request):
    """
    GET /api/printing/active-session/
    
    Called by Raspberry Pi scan monitor to query the current active session.
    No authentication required (only called by internal Pi).
    """
    try:
        device = Device.objects.filter(is_active=True).first()
        if not device:
            return Response({
                'active': False
            }, status=status.HTTP_200_OK)
        
        active_session = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        if active_session:
            # Check if session has expired
            max_duration = timedelta(minutes=device.max_session_duration_minutes)
            if timezone.now() > active_session.started_at + max_duration:
                active_session.status = PrintSession.Status.EXPIRED
                active_session.ended_at = timezone.now()
                active_session.save()
                return Response({
                    'active': False
                }, status=status.HTTP_200_OK)
            
            return Response({
                'active': True,
                'session_id': active_session.external_id
            }, status=status.HTTP_200_OK)
        
        return Response({
            'active': False
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in active_session_view: {e}", exc_info=True)
        return Response({
            'active': False
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([])  # No authentication required
@parser_classes([MultiPartParser, FormParser])  # Allows multipart/form-data for file uploads
def upload_scan_view(request):
    """
    POST /api/printing/scans/
    
    Called by Raspberry Pi scan monitor to upload a scan.
    Body: Multipart with 'file' and 'session_id'
    """
    try:
        session_id = request.data.get('session_id')
        if not session_id:
            return Response(
                {"error": "session_id required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session = PrintSession.objects.get(external_id=session_id)
        
        if session.status != PrintSession.Status.ACTIVE:
            return Response(
                {"error": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if 'file' not in request.FILES:
            return Response(
                {"error": "No file uploaded."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        filename = file.name
        
        # Create scan entry
        # Store file temporarily
        scan_dir = os.path.join(settings.MEDIA_ROOT, 'scans', 'temp', f'session_{session.external_id}')
        os.makedirs(scan_dir, exist_ok=True)
        
        file_path = os.path.join(scan_dir, filename)
        
        # Ensure filename is unique
        counter = 1
        original_file_path = file_path
        while os.path.exists(file_path):
            name, ext = os.path.splitext(original_file_path)
            file_path = f"{name}_{counter}{ext}"
            counter += 1
        
        # Save file
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        # Relative path for DB
        relative_path = os.path.join('scans', 'temp', f'session_{session.external_id}', os.path.basename(file_path))
        
        # Create scan entry
        scan = Scan.objects.create(
            session=session,
            tenant=session.tenant,
            device=session.device,
            filename=os.path.basename(file_path),
            file_path=relative_path
        )
        
        serializer = ScanSerializer(scan)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except PrintSession.DoesNotExist:
        return Response(
            {"error": "Session not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in upload_scan_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while uploading scan."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# Department Management Endpoints (for department administration)
# ============================================================================

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_overview_view(request, device_id):
    """
    GET /api/printing/device/{device_id}/overview/
    
    Overview with status, costs, statistics for a device.
    """
    device_overview_view.required_employee_types = ['DEPARTMENT']
    # TODO: Check if user is in the responsible department
    
    try:
        device = Device.objects.get(id=device_id)
        
        # Active session
        active_session = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        # Statistics
        total_sessions = PrintSession.objects.filter(device=device).count()
        active_sessions_count = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).count()
        total_jobs = PrintJob.objects.filter(device=device).count()
        completed_jobs = PrintJob.objects.filter(
            device=device,
            status=PrintJob.Status.COMPLETED,
            cost__isnull=False  # Only sum stored cost values
        )
        total_pages = sum(job.pages for job in completed_jobs if job.pages) or 0
        total_revenue = sum(job.cost for job in completed_jobs) or Decimal('0.00')
        
        # This month
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_jobs = completed_jobs.filter(created_at__gte=month_start)
        this_month_pages = sum(job.pages for job in this_month_jobs if job.pages) or 0
        this_month_revenue = sum(job.cost for job in this_month_jobs) or Decimal('0.00')
        
        active_session_data = None
        if active_session:
            active_session_data = {
                'session_id': active_session.external_id,
                'tenant_name': active_session.tenant.get_full_name(),
                'started_at': active_session.started_at
            }
        
        from ..serializers import DeviceSerializer
        device_serializer = DeviceSerializer(device)
        
        return Response({
            'device': device_serializer.data,
            'active_session': active_session_data,
            'statistics': {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions_count,
                'total_jobs': total_jobs,
                'total_pages': total_pages,
                'total_revenue': str(total_revenue),
                'this_month_pages': this_month_pages,
                'this_month_revenue': str(this_month_revenue)
            }
        }, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_overview_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving device overview."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_statistics_view(request, device_id):
    """
    GET /api/printing/device/{device_id}/statistics/
    
    Detailed statistics with optional time period parameters.
    Query params: start_date, end_date (optional)
    """
    device_statistics_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        
        # Time period parameters (optional)
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        jobs_query = PrintJob.objects.filter(device=device)
        sessions_query = PrintSession.objects.filter(device=device)
        
        if start_date:
            jobs_query = jobs_query.filter(created_at__gte=start_date)
            sessions_query = sessions_query.filter(started_at__gte=start_date)
        
        if end_date:
            jobs_query = jobs_query.filter(created_at__lte=end_date)
            sessions_query = sessions_query.filter(started_at__lte=end_date)
        
        completed_jobs = jobs_query.filter(status=PrintJob.Status.COMPLETED, cost__isnull=False)
        total_pages = sum(job.pages for job in completed_jobs if job.pages) or 0
        total_revenue = sum(job.cost for job in completed_jobs) or Decimal('0.00')
        
        return Response({
            'device_id': device.id,
            'device_name': device.name,
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'sessions': {
                'total': sessions_query.count(),
                'completed': sessions_query.filter(status=PrintSession.Status.COMPLETED).count(),
                'expired': sessions_query.filter(status=PrintSession.Status.EXPIRED).count(),
                'terminated': sessions_query.filter(status=PrintSession.Status.TERMINATED).count()
            },
            'jobs': {
                'total': jobs_query.count(),
                'completed': completed_jobs.count(),
                'failed': jobs_query.filter(status=PrintJob.Status.FAILED).count(),
                'cancelled': jobs_query.filter(status=PrintJob.Status.CANCELLED).count(),
                'total_pages': total_pages,
                'total_revenue': str(total_revenue)
            }
        }, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_statistics_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving statistics."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_settings_update_view(request, device_id):
    """
    PUT /api/printing/device/{device_id}/settings/
    
    Updates device settings (price, session duration, etc.)
    """
    device_settings_update_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        
        from ..serializers import DeviceSettingsUpdateSerializer
        serializer = DeviceSettingsUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        # Update device
        if 'price_per_page_color' in validated_data:
            device.price_per_page_color = validated_data['price_per_page_color']
        if 'price_per_page_gray' in validated_data:
            device.price_per_page_gray = validated_data['price_per_page_gray']
        if 'max_session_duration_minutes' in validated_data:
            device.max_session_duration_minutes = validated_data['max_session_duration_minutes']
        
        device.save()
        
        from ..serializers import DeviceSerializer
        return Response(DeviceSerializer(device).data, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_settings_update_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while updating device settings."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_toggle_active_view(request, device_id):
    """
    POST /api/printing/device/{device_id}/toggle-active/
    
    Toggles device on/off globally.
    """
    device_toggle_active_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        device.is_active = not device.is_active
        device.save()
        
        from ..serializers import DeviceSerializer
        return Response(DeviceSerializer(device).data, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_toggle_active_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while toggling device."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_toggle_sessions_view(request, device_id):
    """
    POST /api/printing/device/{device_id}/toggle-sessions/
    
    Allows/blocks new sessions.
    """
    device_toggle_sessions_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        device.allow_new_sessions = not device.allow_new_sessions
        device.save()
        
        from ..serializers import DeviceSerializer
        return Response(DeviceSerializer(device).data, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_toggle_sessions_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while toggling sessions."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_terminate_session_view(request, device_id):
    """
    POST /api/printing/device/{device_id}/terminate-session/
    
    Terminates the active session of the device.
    """
    device_terminate_session_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        
        active_session = PrintSession.objects.filter(
            device=device,
            status=PrintSession.Status.ACTIVE
        ).first()
        
        if not active_session:
            return Response(
                {"error": "No active session found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        with transaction.atomic():
            active_session.status = PrintSession.Status.TERMINATED
            active_session.ended_at = timezone.now()
            active_session.save()
        
        serializer = PrintSessionSerializer(active_session)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_terminate_session_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while terminating session."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def device_history_view(request, device_id):
    """
    GET /api/printing/device/{device_id}/history/
    
    Print history with optional filters.
    Query params: start_date, end_date, status (optional)
    """
    device_history_view.required_employee_types = ['DEPARTMENT']
    
    try:
        device = Device.objects.get(id=device_id)
        
        # Filters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status')
        
        sessions_query = PrintSession.objects.filter(device=device)
        
        if start_date:
            sessions_query = sessions_query.filter(started_at__gte=start_date)
        if end_date:
            sessions_query = sessions_query.filter(started_at__lte=end_date)
        if status_filter:
            sessions_query = sessions_query.filter(status=status_filter)
        
        sessions = sessions_query.order_by('-started_at')[:100]  # Limit to 100
        
        serializer = PrintSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Device.DoesNotExist:
        return Response(
            {"error": "Device not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in device_history_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving history."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def tenant_billing_overview_view(request):
    """
    GET /api/printing/tenant-billing-overview/
    
    Returns billing overview for all tenants who have print costs.
    Only tenants with costs > 0 are included.
    """
    tenant_billing_overview_view.required_employee_types = ['DEPARTMENT']
    
    try:
        from django.db.models import Count
        
        # Get all unique tenants who have completed print jobs with stored cost values
        # Aggregate all jobs per tenant (one row per tenant, not per job)
        tenant_ids_with_jobs = PrintJob.objects.filter(
            status=PrintJob.Status.COMPLETED,
            cost__isnull=False
        ).values_list('tenant_id', flat=True).distinct()
        
        # Build billing data by aggregating all jobs per tenant
        billing_data = []
        processed_tenant_ids = set()  # Track processed tenants to avoid duplicates
        
        for tenant_id in tenant_ids_with_jobs:
            # Skip if already processed (safety check)
            if tenant_id in processed_tenant_ids:
                continue
            processed_tenant_ids.add(tenant_id)
            
            tenant = Tenant.objects.get(id=tenant_id)
            
            # Get ALL jobs for this tenant (aggregate all jobs into one entry)
            tenant_jobs = PrintJob.objects.filter(
                tenant=tenant,
                status=PrintJob.Status.COMPLETED,
                cost__isnull=False
            )
            
            # Calculate totals by summing ALL jobs for this tenant
            total_cost = sum(job.cost for job in tenant_jobs) or Decimal('0.00')
            total_pages = sum(job.pages for job in tenant_jobs if job.pages) or 0
            total_jobs = tenant_jobs.count()
            
            # Count sessions
            total_sessions = PrintSession.objects.filter(tenant=tenant).count()
            
            # Only include tenants with total_cost > 0
            if total_cost > Decimal('0.00'):
                billing_data.append({
                    'tenant_id': tenant.id,
                    'tenant_name': tenant.get_full_name(),
                    'surname': tenant.surname,
                    'name': tenant.name,
                    'email': tenant.email or '',
                    'current_room': tenant.current_room or '',
                    'total_cost': str(total_cost),
                    'total_pages': total_pages,
                    'total_jobs': total_jobs,
                    'total_sessions': total_sessions,
                })
        
        # Sort by surname, name
        billing_data.sort(key=lambda x: (x['surname'], x['name']))
        
        from ..serializers import TenantBillingOverviewSerializer
        serializer = TenantBillingOverviewSerializer(billing_data, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in tenant_billing_overview_view: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving billing overview."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

