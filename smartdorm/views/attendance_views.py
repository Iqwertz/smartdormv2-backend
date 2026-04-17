from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
import uuid

from ..permissions import GroupAndEmployeeTypePermission
from ..models import Event, AttendanceSession, AttendanceRecord, Tenant, get_active_tenants, BaseAttendanceRecord
from ..serializers import EventSerializer, AttendanceSessionSerializer, AttendanceRecordSerializer, BaseAttendanceRecordSerializer

def _is_event_admin(request, event):
    user_groups = [group.name for group in request.user.groups.all()]
    if 'ADMIN' in user_groups:
        return True
    
    # Check if user is in any of the configured admin_groups
    admin_groups = event.admin_groups
    if isinstance(admin_groups, list):
        return any(group in user_groups for group in admin_groups)
    return False

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_manageable_events_view(request):
    events = Event.objects.all().order_by('-created_at')
    manageable = [event for event in events if _is_event_admin(request, event)]
    serializer = EventSerializer(manageable, many=True)
    return Response(serializer.data)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_create_events_view(request):
    """
    GET: List all events.
    POST: Create a new event (restricted to Network/Heimrat/ADMIN).
    """
    # For GET, we return all events.
    if request.method == 'GET':
        events = Event.objects.all().order_by('-created_at')
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)
        
    elif request.method == 'POST':
        # Check permissions for creating
        user_groups = [group.name for group in request.user.groups.all()]
        if not any(g in user_groups for g in ['ADMIN', 'Netzwerkreferat', 'Heimrat']):
            return Response({"error": "Insufficient permissions to create events."}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def detail_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'GET':
        serializer = EventSerializer(event)
        return Response(serializer.data)
        
    # For PUT/DELETE, must be an event admin
    if not _is_event_admin(request, event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    if request.method == 'PUT':
        serializer = EventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'DELETE':
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_create_sessions_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'GET':
        sessions = AttendanceSession.objects.filter(event=event).order_by('-date', '-id')
        serializer = AttendanceSessionSerializer(sessions, many=True)
        return Response(serializer.data)
        
    elif request.method == 'POST':
        if not _is_event_admin(request, event):
            return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)

        raw_title = request.data.get('title', '')
        title = raw_title.strip() if isinstance(raw_title, str) else ''
        if not title:
            title = f"{event.name} - {timezone.now().date().strftime('%d.%m.%Y')}"

        # Create a new session for today
        session = AttendanceSession.objects.create(event=event, title=title, status='CREATED', current_part=0)
        serializer = AttendanceSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def toggle_session_status_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)

    if session.status == 'CREATED':
        session.status = 'ACTIVE'
        session.current_part = 1
        session.secret_token = str(uuid.uuid4())
        session.last_rotated_at = timezone.now()
    elif session.status == 'ACTIVE':
        session.status = 'CLOSED'
        session.current_part = 0
        session.secret_token = None
    elif session.status == 'CLOSED':
        session.status = 'ACTIVE'
        session.current_part = session.current_part if session.current_part > 0 else 1
        session.secret_token = str(uuid.uuid4())
        session.last_rotated_at = timezone.now()

    session.save()
    serializer = AttendanceSessionSerializer(session)
    return Response(serializer.data)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def delete_session_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)

    if AttendanceRecord.objects.filter(session=session).exists():
        return Response(
            {"error": "Session has attendance records. Clear all tracked attendance before deleting this session."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def start_session_part_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    part = request.data.get('part')
    if part is None:
        return Response({"error": "Must provide a 'part' number to start."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        part = int(part)
    except ValueError:
        return Response({"error": "'part' must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    if part < 1 or part > session.event.parts_count:
        return Response({"error": f"Part must be between 1 and {session.event.parts_count}."}, status=status.HTTP_400_BAD_REQUEST)
        
    session.status = 'ACTIVE'
    session.current_part = part
    session.secret_token = str(uuid.uuid4())
    session.last_rotated_at = timezone.now()
    session.save()
    
    serializer = AttendanceSessionSerializer(session)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def stop_session_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    session.status = 'CLOSED'
    session.current_part = 0
    session.secret_token = None
    session.save()
    
    serializer = AttendanceSessionSerializer(session)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def get_current_qr_token_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    if session.status != 'ACTIVE' or session.current_part == 0:
        return Response({"error": "Session is not active."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Rotate token if older than 30 seconds
    now = timezone.now()
    if not session.last_rotated_at or now - session.last_rotated_at > timedelta(seconds=30):
        session.previous_secret_token = session.secret_token
        session.secret_token = str(uuid.uuid4())
        session.last_rotated_at = now
        session.save()
        
    return Response({
        "token": session.secret_token,
        "part": session.current_part,
        "session_id": session.id,
        "session_title": session.title,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def scan_attendance_view(request):
    """
    Tenant endpoint to submit a scanned QR code.
    """
    session_id = request.data.get('session_id')
    token = request.data.get('token')
    
    if not session_id or not token:
        return Response({"error": "session_id and token are required."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        session = AttendanceSession.objects.get(id=session_id)
    except AttendanceSession.DoesNotExist:
        return Response({"error": "Die gescannte Session existiert nicht."}, status=status.HTTP_404_NOT_FOUND)
    
    # We must map current user to a tenant
    try:
        tenant = Tenant.objects.get(username=request.user.username)
    except Tenant.DoesNotExist:
        return Response({"error": "Dein Benutzerkonto ist mit keinem Mieter verknüpft."}, status=status.HTTP_403_FORBIDDEN)
    
    # Verify the session is active and the token matches
    if session.status != 'ACTIVE' or session.current_part == 0:
        return Response({"error": "Attendance session is currently closed."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Accept current token, or previous token if within a 15-second grace period
    now = timezone.now()
    grace_period_active = session.last_rotated_at and (now - session.last_rotated_at).total_seconds() < 15
    
    is_valid_token = (session.secret_token == token) or (grace_period_active and session.previous_secret_token == token)
    
    if not is_valid_token:
        return Response({"error": "Invalid or expired QR code. Please scan again."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Has the tenant already scanned this part?
    record, created = AttendanceRecord.objects.get_or_create(
        tenant=tenant,
        session=session,
        part=session.current_part,
        defaults={'is_manual_override': False}
    )
    
    if not created:
        return Response(
            {"message": f"Du bist bereits für {session.title or 'diese Session'} Teil {session.current_part} angemeldet.", "session_title": session.title},
            status=status.HTTP_200_OK,
        )
        
    return Response(
        {"message": f"Erfolgreich für {session.title or 'die Session'} Teil {session.current_part} angemeldet!", "session_title": session.title},
        status=status.HTTP_201_CREATED,
    )

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def attendance_report_view(request, session_id):
    """
    Returns an attendance matrix for a specific session.
    """
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    records = AttendanceRecord.objects.filter(session=session)
    tenants = Tenant.objects.filter(move_out__gte=timezone.now().date())
    
    # Build the matrix
    # Result format: [{tenant_id: x, tenant_name: "Y Z", parts: [1, 2], manual_overrides: [1]}]
    tenant_records = {}
    for tenant in tenants:
        tenant_records[tenant.id] = {
            "tenant_id": tenant.id,
            "tenant_name": tenant.get_full_name(),
            "surname": tenant.surname,
            "name": tenant.name,
            "current_room": tenant.current_room,
            "current_floor": tenant.current_floor,
            "parts_attended": [],
            "manual_overrides": []
        }
        
    for r in records:
        if r.tenant_id in tenant_records:
            tenant_records[r.tenant_id]["parts_attended"].append(r.part)
            if r.is_manual_override:
                tenant_records[r.tenant_id]["manual_overrides"].append(r.part)
        else:
            # In case an inactive tenant scanned / was overridden
            tenant_records[r.tenant.id] = {
                "tenant_id": r.tenant.id,
                "tenant_name": r.tenant.get_full_name(),
                "surname": r.tenant.surname,
                "name": r.tenant.name,
                "current_room": r.tenant.current_room,
                "current_floor": r.tenant.current_floor,
                "parts_attended": [r.part],
                "manual_overrides": [r.part] if r.is_manual_override else []
            }

    rows = list(tenant_records.values())
    rows.sort(key=lambda row: (row["tenant_name"].lower(), row["tenant_id"]))

    return Response({
        "session": AttendanceSessionSerializer(session).data,
        "rows": rows,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def manual_override_view(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    if not _is_event_admin(request, session.event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
        
    tenant_id = request.data.get('tenant_id')
    part = request.data.get('part')
    present = request.data.get('present', True)
    
    if tenant_id is None or part is None:
        return Response({"error": "tenant_id and part are required."}, status=status.HTTP_400_BAD_REQUEST)
        
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    if present:
        AttendanceRecord.objects.update_or_create(
            tenant=tenant,
            session=session,
            part=part,
            defaults={'is_manual_override': True}
        )
    else:
        AttendanceRecord.objects.filter(tenant=tenant, session=session, part=part).delete()
        
    return Response({"message": "Override applied successfully."})

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def my_attendance_history_view(request):
    """
    Returns attendance history for the logged-in tenant.
    """
    try:
        tenant = Tenant.objects.get(username=request.user.username)
    except Tenant.DoesNotExist:
        return Response([]) # Non-tenant users simply have no history
        
    records = AttendanceRecord.objects.filter(tenant=tenant).select_related('session__event').order_by('-session__date', 'part')
    
    serializer = AttendanceRecordSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def base_attendance_overview_view(request, event_id):
    """
    Returns a list of all active tenants with their attendance summary for a specific event.
    A session counts as attended if the tenant has at least event.required_parts
    distinct parts logged in that session.
    """
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_admin(request, event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
    
    active_tenants = get_active_tenants()
    required_parts_threshold = max(1, event.required_parts)
    
    tenant_summaries = []
    for tenant in active_tenants:
        # Count sessions where enough parts were logged for this tenant
        attended_sessions_count = AttendanceRecord.objects.filter(
            tenant=tenant,
            session__event=event
        ).values('session_id').annotate(
            parts_logged=Count('part', distinct=True)
        ).filter(
            parts_logged__gte=required_parts_threshold
        ).count()
        
        # Get base attendance for this tenant and event
        base_attendance = BaseAttendanceRecord.objects.filter(
            tenant=tenant,
            event=event
        ).first()
        base_attendance_count = base_attendance.parts_count if base_attendance else 0
        
        total_attendance = attended_sessions_count + base_attendance_count
        
        tenant_summaries.append({
            'tenant_id': tenant.id,
            'name': tenant.name,
            'surname': tenant.surname,
            'current_room': tenant.current_room,
            'current_floor': tenant.current_floor,
            'attended_sessions_count': attended_sessions_count,
            'required_parts_threshold': required_parts_threshold,
            'base_attendance_count': base_attendance_count,
            'total_attendance_count': total_attendance,
        })
    
    # Sort by surname, then name
    tenant_summaries.sort(key=lambda x: (x['surname'].lower(), x['name'].lower()))
    
    return Response(tenant_summaries)


@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def tenant_attendance_detail_view(request, event_id, tenant_id):
    """
    Returns detailed attendance information for a specific tenant in a specific event.
    Sessions are grouped (not split into one row per part).
    """
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_admin(request, event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    # Get all attendance records for this tenant in this event
    scanned_records = AttendanceRecord.objects.filter(
        tenant=tenant,
        session__event=event
    ).select_related('session').order_by('-session__date', 'part')
    
    # Get base attendance record if it exists
    base_attendance = BaseAttendanceRecord.objects.filter(
        tenant=tenant,
        event=event
    ).first()
    
    grouped_sessions = {}
    for record in scanned_records:
        session_id = record.session.id
        if session_id not in grouped_sessions:
            grouped_sessions[session_id] = {
                'session_id': session_id,
                'session_title': record.session.title or f"Session {session_id}",
                'session_date': record.session.date,
                'parts_attended': [],
                'has_manual_override': False,
                'latest_timestamp': record.timestamp,
            }

        grouped_sessions[session_id]['parts_attended'].append(record.part)
        if record.is_manual_override:
            grouped_sessions[session_id]['has_manual_override'] = True
        if record.timestamp > grouped_sessions[session_id]['latest_timestamp']:
            grouped_sessions[session_id]['latest_timestamp'] = record.timestamp

    scanned_sessions = list(grouped_sessions.values())
    scanned_sessions.sort(
        key=lambda s: (s['session_date'], s['session_id']),
        reverse=True,
    )
    
    return Response({
        'tenant_id': tenant.id,
        'tenant_name': f"{tenant.name} {tenant.surname}",
        'current_room': tenant.current_room,
        'current_floor': tenant.current_floor,
        'scanned_sessions': scanned_sessions,
        'base_attendance': {
            'id': base_attendance.id if base_attendance else None,
            'parts_count': base_attendance.parts_count if base_attendance else 0,
            'note': base_attendance.note if base_attendance else None,
            'created_at': base_attendance.created_at if base_attendance else None,
            'updated_at': base_attendance.updated_at if base_attendance else None,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def add_or_update_base_attendance_view(request, event_id, tenant_id):
    """
    Create or update base attendance for a tenant in a specific event.
    Request body: {parts_count: int, note: str (optional)}
    """
    event = get_object_or_404(Event, id=event_id)
    if not _is_event_admin(request, event):
        return Response({"error": "You are not an admin for this event."}, status=status.HTTP_403_FORBIDDEN)
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    parts_count = request.data.get('parts_count')
    note = request.data.get('note', '')
    
    if parts_count is None:
        return Response({"error": "parts_count is required."}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        parts_count = int(parts_count)
        if parts_count < 0:
            raise ValueError("parts_count must be non-negative")
    except (ValueError, TypeError):
        return Response({"error": "parts_count must be a non-negative integer."}, status=status.HTTP_400_BAD_REQUEST)
    
    if parts_count == 0:
        # Delete base attendance record if it exists
        BaseAttendanceRecord.objects.filter(tenant=tenant, event=event).delete()
        return Response({"message": "Base attendance removed."}, status=status.HTTP_204_NO_CONTENT)
    
    # Create or update
    base_attendance, created = BaseAttendanceRecord.objects.update_or_create(
        tenant=tenant,
        event=event,
        defaults={
            'parts_count': parts_count,
            'note': note if note else None,
        }
    )
    
    serializer = BaseAttendanceRecordSerializer(base_attendance)
    return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


