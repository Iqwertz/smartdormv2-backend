"""
HSV e.V. membership: Beitrittsantrag, Aufnahmeentscheidung und SEPA-Mandatsregister.

The Verein is a legally separate entity from the Schollheim e.V. whose tenancy data the rest
of this application manages, which is why membership lives behind its own /api/membership/
namespace with its own groups rather than under the Verwaltung endpoints.

Permissions use the group_required() factory from ..permissions. The older
`view.required_groups = [...]` style found elsewhere in this codebase does nothing on
@api_view endpoints - see the note on group_required().
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .. import config as app_config
from .. import membership_texts
from ..models import (
    DirectDebitItem, DirectDebitRun, Membership, MembershipApplication,
    MembershipPrompt, Tenant,
)
from ..permissions import group_required
from ..serializers import (
    DirectDebitItemSerializer, DirectDebitRunSerializer,
    MembershipApplicationCreateSerializer, MembershipApplicationSerializer,
    MembershipMandateUpdateSerializer, MembershipSerializer,
)
from ..utils import crypto_utils, email_utils, membership_pdf, sepa_utils

logger = logging.getLogger(__name__)

IsMembershipApprover = group_required(*app_config.MEMBERSHIP_APPROVER_GROUPS)
IsFinanceDepartment = group_required(*app_config.MEMBERSHIP_FINANCE_GROUPS)

MINIMUM_AGE = 18


# --- helpers --------------------------------------------------------------------------

def _get_tenant(request):
    """The Tenant behind the logged-in account, or None for non-tenant accounts."""
    return Tenant.objects.filter(username=request.user.username).first()


def _client_ip(request):
    """
    Best-effort client IP for the submission record.

    Behind the reverse proxy the direct peer is the proxy, so the forwarded header is
    preferred when present. This is documentation of the submission, not authentication -
    a spoofable header is acceptable here and nothing is authorised based on it.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _age_on(birthday, reference=None):
    reference = reference or timezone.now().date()
    if not birthday:
        return None
    return (
        reference.year - birthday.year
        - ((reference.month, reference.day) < (birthday.month, birthday.day))
    )


def _fee():
    return Decimal(str(app_config.HSV_MEMBERSHIP_FEE_EUR))


# --- tenant-facing endpoints ----------------------------------------------------------

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def my_membership_status_view(request):
    """
    What the dashboard needs to decide whether to show the join dialog.

    Deliberately never 404s: the frontend asks this on every dashboard load, and a state
    machine is easier to reason about there than a missing-resource error.
    """
    tenant = _get_tenant(request)
    if not tenant:
        return Response({'state': 'NOT_A_TENANT'})

    membership = Membership.objects.filter(tenant=tenant).first()
    if membership:
        return Response({
            'state': 'MEMBER',
            'membership': MembershipSerializer(membership).data,
        })

    open_application = MembershipApplication.objects.filter(
        tenant=tenant, status=MembershipApplication.Status.SUBMITTED
    ).first()
    if open_application:
        return Response({
            'state': 'SUBMITTED',
            'submitted_at': open_application.submitted_at,
        })

    if MembershipPrompt.objects.filter(tenant=tenant).exists():
        return Response({'state': 'OPTED_OUT'})

    age = _age_on(tenant.birthday)
    if age is not None and age < MINIMUM_AGE:
        # Minors cannot validly join or grant a SEPA mandate without their guardians
        # (ss 107 f. BGB), so the online route is closed rather than silently invalid.
        return Response({
            'state': 'INELIGIBLE',
            'reason': membership_texts.get_terms()['minor_notice'],
        })

    last_rejection = MembershipApplication.objects.filter(
        tenant=tenant, status=MembershipApplication.Status.REJECTED
    ).first()
    return Response({
        'state': 'NONE',
        'previously_rejected': bool(last_rejection),
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def membership_terms_view(request):
    """The current declaration text plus the values to prefill the form with."""
    tenant = _get_tenant(request)
    terms = membership_texts.get_terms()

    return Response({
        'terms_version': membership_texts.CURRENT_TERMS_VERSION,
        'terms': terms,
        'fee': str(_fee()),
        'creditor_id': app_config.HSV_CREDITOR_ID,
        'creditor_name': app_config.HSV_CREDITOR_NAME,
        'creditor_address': app_config.HSV_CREDITOR_ADDRESS,
        'privacy_policy_url': app_config.HSV_PRIVACY_POLICY_URL,
        'statutes_url': app_config.HSV_STATUTES_URL,
        'prefill': {
            'first_name': tenant.name if tenant else '',
            'last_name': tenant.surname if tenant else '',
        },
    })


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@transaction.atomic
def apply_for_membership_view(request):
    """
    Record a Beitrittserklärung.

    Everything that makes the submission provable later - the text version, the timestamp,
    the account that submitted it, the rendered PDF - is written in the same transaction as
    the application itself.
    """
    tenant = _get_tenant(request)
    if not tenant:
        return Response(
            {'error': 'Nur Bewohner:innen können dem HSV e.V. beitreten.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if Membership.objects.filter(tenant=tenant).exists():
        return Response(
            {'error': 'Für dich ist bereits eine Mitgliedschaft hinterlegt.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if MembershipApplication.objects.filter(
        tenant=tenant, status=MembershipApplication.Status.SUBMITTED
    ).exists():
        return Response(
            {'error': 'Dein Antrag liegt bereits zur Prüfung vor.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    age = _age_on(tenant.birthday)
    if age is not None and age < MINIMUM_AGE:
        return Response(
            {'error': membership_texts.get_terms()['minor_notice']},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = MembershipApplicationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    application = MembershipApplication(
        tenant=tenant,
        status=MembershipApplication.Status.SUBMITTED,
        first_name=data['first_name'],
        last_name=data['last_name'],
        requested_join_date=data['requested_join_date'],
        is_of_age=data['is_of_age'],
        amtsliste_consent=data['amtsliste_consent'],
        statutes_accepted=data['statutes_accepted'],
        payment_method=data['payment_method'],
        account_holder_first_name=data.get('account_holder_first_name', ''),
        account_holder_last_name=data.get('account_holder_last_name', ''),
        mandate_confirmed=data.get('mandate_confirmed', False),
        terms_version=membership_texts.CURRENT_TERMS_VERSION,
        submitted_ip=_client_ip(request),
        submitted_by_username=request.user.username,
    )
    application.set_iban(data.get('iban', ''))

    try:
        application.save()
    except IntegrityError:
        # The partial unique constraint caught a double submit racing this one.
        return Response(
            {'error': 'Dein Antrag liegt bereits zur Prüfung vor.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # submitted_at is only populated after the insert, and the PDF prints it.
    application.refresh_from_db()
    try:
        pdf_bytes = membership_pdf.render_declaration_pdf(application, tenant=tenant)
        application.declaration_pdf = pdf_bytes
        application.save(update_fields=['declaration_pdf'])
    except Exception:
        # The application itself is valid and recorded; a missing archive copy must not
        # discard it. It is regenerable from the stored data and terms version.
        logger.exception(
            "Could not render declaration PDF for membership application %s.", application.id
        )
        pdf_bytes = None

    _send_submission_emails(application, tenant, pdf_bytes)

    logger.info(
        "User '%s' submitted membership application %s (payment method: %s, terms: %s).",
        request.user.username, application.id, application.payment_method,
        application.terms_version,
    )
    return Response(
        {
            'message': 'Deine Beitrittserklärung wurde übermittelt. Du erhältst eine '
                       'Bestätigung per E-Mail.',
            'application_id': application.id,
        },
        status=status.HTTP_201_CREATED,
    )


def _send_submission_emails(application, tenant, pdf_bytes):
    """Confirm to the applicant (with their copy of the declaration) and alert the Referate."""
    attachments = None
    if pdf_bytes:
        attachments = [(
            membership_pdf.declaration_filename(application),
            pdf_bytes,
            'application/pdf',
        )]

    email_utils.send_email_message(
        recipient_list=[tenant.email],
        subject='Deine Beitrittserklärung zum HSV e.V.',
        html_template_name='email/tenant-membership-submitted.html',
        context={
            'tenant': tenant,
            'application': application,
            'fee': str(_fee()),
        },
        extra_attachments=attachments,
    )

    email_utils.send_email_message(
        recipient_list=[app_config.MEMBERSHIP_EMAIL],
        subject=f"Neuer Mitgliedsantrag: {application.first_name} {application.last_name}",
        html_template_name='email/department-membership-application.html',
        context={'tenant': tenant, 'application': application},
    )


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def opt_out_view(request):
    """Stop asking. Joining is voluntary, so 'no' has to be an answer that sticks."""
    tenant = _get_tenant(request)
    if not tenant:
        return Response({'error': 'Kein Bewohnerdatensatz gefunden.'},
                        status=status.HTTP_403_FORBIDDEN)

    MembershipPrompt.objects.get_or_create(tenant=tenant)
    return Response({'message': 'Du wirst nicht erneut gefragt. Ein Beitritt ist '
                                'jederzeit über das Menü möglich.'})


@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def undo_opt_out_view(request):
    """Reverse an opt-out, so the tenant can still join later from the menu."""
    tenant = _get_tenant(request)
    if not tenant:
        return Response({'error': 'Kein Bewohnerdatensatz gefunden.'},
                        status=status.HTTP_403_FORBIDDEN)

    MembershipPrompt.objects.filter(tenant=tenant).delete()
    return Response({'message': 'Hinweis wieder aktiviert.'})


# --- approver-facing endpoints --------------------------------------------------------

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsMembershipApprover])
def list_applications_view(request):
    """Applications by status: OPEN (default), APPROVED, REJECTED, ALL."""
    requested = (request.query_params.get('status') or 'OPEN').upper()
    queryset = MembershipApplication.objects.select_related('tenant')

    if requested == 'OPEN':
        queryset = queryset.filter(status=MembershipApplication.Status.SUBMITTED)
    elif requested in {MembershipApplication.Status.APPROVED,
                       MembershipApplication.Status.REJECTED}:
        queryset = queryset.filter(status=requested)
    elif requested != 'ALL':
        return Response(
            {'error': "Ungültiger Status. Erlaubt: OPEN, APPROVED, REJECTED, ALL."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(MembershipApplicationSerializer(queryset, many=True).data)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsMembershipApprover])
@transaction.atomic
def decide_application_view(request, application_id):
    """
    Approve or reject a Beitrittsantrag.

    Approval is the moment the membership legally begins, so it is also where the
    Mandatsreferenz is assigned and communicated - the mandate text promises the member will
    learn it before the first collection.
    """
    application = get_object_or_404(
        MembershipApplication.objects.select_related('tenant'), id=application_id
    )

    if application.status != MembershipApplication.Status.SUBMITTED:
        return Response(
            {'error': 'Über diesen Antrag wurde bereits entschieden.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    decision = (request.data.get('decision') or '').upper()
    note = (request.data.get('note') or '').strip()
    tenant = application.tenant
    now = timezone.now()

    if decision == 'REJECTED':
        application.status = MembershipApplication.Status.REJECTED
        application.decided_at = now
        application.decided_by = request.user.username
        application.decision_note = note
        application.save(update_fields=['status', 'decided_at', 'decided_by', 'decision_note'])

        email_utils.send_email_message(
            recipient_list=[tenant.email],
            subject='Dein Mitgliedsantrag beim HSV e.V.',
            html_template_name='email/tenant-membership-rejection.html',
            context={'tenant': tenant, 'application': application, 'note': note},
        )
        logger.info("User '%s' rejected membership application %s.",
                    request.user.username, application.id)
        return Response({'message': 'Der Antrag wurde abgelehnt.'})

    if decision != 'APPROVED':
        return Response(
            {'error': "Ungültige Entscheidung. Erlaubt sind 'APPROVED' und 'REJECTED'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Membership.objects.filter(tenant=tenant).exists():
        return Response(
            {'error': 'Für diese Person besteht bereits eine Mitgliedschaft.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # The approver may correct the requested date; otherwise the member's wish stands,
    # but never earlier than the day the Verein actually admitted them.
    join_date = application.requested_join_date
    raw_join_date = request.data.get('join_date')
    if raw_join_date:
        try:
            join_date = date.fromisoformat(raw_join_date)
        except ValueError:
            return Response({'error': 'Ungültiges Beitrittsdatum.'},
                            status=status.HTTP_400_BAD_REQUEST)

    is_sepa = application.payment_method == MembershipApplication.PaymentMethod.SEPA

    membership = Membership(
        tenant=tenant,
        application=application,
        joined_on=join_date,
        amtsliste_consent=application.amtsliste_consent,
        amtsliste_consent_at=application.submitted_at if application.amtsliste_consent else None,
        payment_method=application.payment_method,
        account_holder=(
            f"{application.account_holder_first_name} "
            f"{application.account_holder_last_name}".strip()
        ),
        mandate_status=(
            Membership.MandateStatus.ACTIVE if is_sepa else Membership.MandateStatus.NONE
        ),
        mandate_signed_on=application.submitted_at.date() if is_sepa else None,
        mandate_reference=(
            sepa_utils.build_mandate_reference(tenant.id, join_date) if is_sepa else None
        ),
        iban_ciphertext=application.iban_ciphertext,
        iban_last4=application.iban_last4,
    )

    try:
        membership.save()
    except IntegrityError:
        # mandate_reference is unique; a collision means this tenant already has a mandate
        # from an earlier membership in the same year.
        logger.exception("Mandate reference collision approving application %s.", application.id)
        return Response(
            {'error': 'Die Mandatsreferenz konnte nicht vergeben werden, weil sie bereits '
                      'existiert. Bitte wende dich an das Finanzenreferat.'},
            status=status.HTTP_409_CONFLICT,
        )

    application.status = MembershipApplication.Status.APPROVED
    application.decided_at = now
    application.decided_by = request.user.username
    application.decision_note = note
    application.save(update_fields=['status', 'decided_at', 'decided_by', 'decision_note'])

    email_utils.send_email_message(
        recipient_list=[tenant.email],
        subject='Willkommen im HSV e.V.',
        html_template_name='email/tenant-membership-approval.html',
        context={
            'tenant': tenant,
            'membership': membership,
            'fee': str(_fee()),
            'creditor_id': app_config.HSV_CREDITOR_ID,
            'collection_day': app_config.HSV_COLLECTION_DAY,
            'prenotification_days': app_config.HSV_PRENOTIFICATION_DAYS,
            'is_sepa': is_sepa,
        },
    )

    logger.info(
        "User '%s' approved membership application %s for tenant %s "
        "(join date: %s, mandate reference: %s).",
        request.user.username, application.id, tenant.id, join_date,
        membership.mandate_reference or '-',
    )
    return Response({
        'message': 'Der Antrag wurde genehmigt.',
        'mandate_reference': membership.mandate_reference,
        'joined_on': membership.joined_on,
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsMembershipApprover])
def application_pdf_view(request, application_id):
    """
    Serve the archived declaration.

    Streamed through this permission-checked view rather than from MEDIA_ROOT, because the
    document contains the member's full IBAN and the media directory may be served directly
    by the webserver.
    """
    application = get_object_or_404(MembershipApplication, id=application_id)
    if not application.declaration_pdf:
        return Response({'error': 'Für diesen Antrag ist kein PDF hinterlegt.'},
                        status=status.HTTP_404_NOT_FOUND)

    logger.info("User '%s' downloaded the declaration PDF of membership application %s.",
                request.user.username, application.id)

    response = HttpResponse(bytes(application.declaration_pdf),
                            content_type='application/pdf')
    response['Content-Disposition'] = (
        f'inline; filename="{membership_pdf.declaration_filename(application)}"'
    )
    return response


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsMembershipApprover])
def list_members_view(request):
    """The member register. IBANs are masked; revealing one is a separate, logged request."""
    include_ended = request.query_params.get('include_ended') == 'true'
    queryset = Membership.objects.select_related('tenant')
    if not include_ended:
        queryset = queryset.filter(ended_on__isnull=True)

    return Response(MembershipSerializer(queryset, many=True).data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsMembershipApprover])
def reveal_iban_view(request, tenant_id):
    """
    Return one member's full IBAN.

    Separate from the list endpoint on purpose: this way the full account number is only
    decrypted when somebody actually needs it, and every such access is attributable in the
    log. The privacy notice in the Beitrittserklärung promises exactly this.
    """
    membership = get_object_or_404(Membership.objects.select_related('tenant'),
                                   tenant_id=tenant_id)
    if not membership.iban_ciphertext:
        return Response({'error': 'Für dieses Mitglied ist keine IBAN hinterlegt.'},
                        status=status.HTTP_404_NOT_FOUND)

    try:
        iban = membership.get_iban()
    except crypto_utils.DecryptionFailed:
        logger.error("IBAN of membership %s could not be decrypted.", tenant_id)
        return Response(
            {'error': 'Die IBAN konnte nicht entschlüsselt werden. Der Schlüssel in '
                      'FIELD_ENCRYPTION_KEYS passt nicht zu diesem Datensatz.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info("User '%s' revealed the IBAN of member %s (%s).",
                request.user.username, tenant_id, membership.tenant.get_full_name())

    return Response({
        'tenant_id': tenant_id,
        'iban': crypto_utils.format_iban(iban),
        'account_holder': membership.account_holder,
        'mandate_reference': membership.mandate_reference,
    })


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsFinanceDepartment])
@transaction.atomic
def update_mandate_view(request, tenant_id):
    """
    Correct bank details or revoke a mandate after the fact (Finanzenreferat).

    Changing the IBAN restarts the mandate sequence: the new account has never been debited
    under this mandate, so the next collection must go out as FRST again.
    """
    membership = get_object_or_404(Membership.objects.select_related('tenant'),
                                   tenant_id=tenant_id)

    serializer = MembershipMandateUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    changes = []

    if 'account_holder' in data:
        membership.account_holder = data['account_holder']
        changes.append('Kontoinhaber:in')

    if data.get('iban'):
        membership.set_iban(data['iban'])
        membership.last_collection_on = None
        membership.mandate_signed_on = timezone.now().date()
        changes.append('IBAN (Mandatssequenz auf FRST zurückgesetzt)')

    if 'mandate_status' in data:
        membership.mandate_status = data['mandate_status']
        changes.append(f"Mandatsstatus -> {data['mandate_status']}")

    if not changes:
        return Response({'error': 'Keine Änderungen übermittelt.'},
                        status=status.HTTP_400_BAD_REQUEST)

    membership.save()
    logger.info("User '%s' updated the SEPA mandate of member %s: %s.",
                request.user.username, tenant_id, '; '.join(changes))

    return Response({
        'message': 'Mandat aktualisiert.',
        'membership': MembershipSerializer(membership).data,
    })


# --- SEPA collection ------------------------------------------------------------------

def _collectable_memberships(collection_date):
    """
    Active members with a usable mandate, in a stable order.

    Excluding tenants whose move_out has already passed is a deliberate safety net rather
    than duplication: ending a membership is hooked into the departure flow, but if any exit
    path ever misses that hook, the worst outcome here is a skipped collection instead of
    debiting somebody who moved out months ago.
    """
    return [
        membership
        for membership in Membership.objects.select_related('tenant').filter(
            Q(ended_on__isnull=True) | Q(ended_on__gte=collection_date),
            mandate_status=Membership.MandateStatus.ACTIVE,
        ).exclude(
            tenant__move_out__lt=collection_date
        ).order_by('tenant__surname', 'tenant__name')
        if membership.is_collectable_on(collection_date)
    ]


def _parse_run_request(request):
    """Shared parsing for the preview and create endpoints."""
    raw_date = request.data.get('collection_date')
    if not raw_date:
        raise ValueError('Bitte gib ein Fälligkeitsdatum an.')
    try:
        collection_date = date.fromisoformat(raw_date)
    except ValueError:
        raise ValueError('Ungültiges Fälligkeitsdatum.')

    raw_amount = request.data.get('amount')
    try:
        amount = Decimal(str(raw_amount)) if raw_amount is not None else _fee()
    except (InvalidOperation, TypeError):
        raise ValueError('Ungültiger Betrag.')
    if amount <= 0:
        raise ValueError('Der Betrag muss größer als 0 sein.')

    return collection_date, amount


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsFinanceDepartment])
def preview_direct_debit_view(request):
    """
    Show who would be collected before anything is generated.

    Worth a separate step: creating a run advances every included member's mandate sequence,
    which is not something to discover after the fact.
    """
    try:
        collection_date, amount = _parse_run_request(request)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    memberships = _collectable_memberships(collection_date)
    items = [{
        'tenant_id': m.tenant_id,
        'name': m.account_holder or m.tenant.get_full_name(),
        'mandate_reference': m.mandate_reference,
        'sequence_type': m.sequence_type,
        'amount': amount,
        'iban_masked': m.iban_masked,
    } for m in memberships]

    config_error = None
    try:
        sepa_utils.check_creditor_config()
    except sepa_utils.SepaConfigError as exc:
        config_error = str(exc)

    active_members = Membership.objects.filter(
        Q(ended_on__isnull=True) | Q(ended_on__gte=collection_date)
    ).count()
    skipped = active_members - len(memberships)

    return Response({
        'collection_date': collection_date,
        'amount': str(amount),
        'member_count': len(items),
        'total_amount': str(amount * len(items)),
        'first_collections': sum(1 for i in items if i['sequence_type'] == 'FRST'),
        'recurring_collections': sum(1 for i in items if i['sequence_type'] == 'RCUR'),
        'skipped_members': skipped,
        'config_error': config_error,
        'items': DirectDebitItemSerializer(items, many=True).data,
    })


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsFinanceDepartment])
@transaction.atomic
def create_direct_debit_view(request):
    """
    Generate and persist the pain.008 file for one collection date.

    Persisting it, rather than regenerating on download, is what keeps FRST/RCUR honest: the
    run records that these members have now been collected once.
    """
    try:
        collection_date, amount = _parse_run_request(request)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    memberships = _collectable_memberships(collection_date)
    if not memberships:
        return Response(
            {'error': 'Es gibt derzeit kein Mitglied mit einem einziehbaren SEPA-Mandat.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        xml, items, message_id = sepa_utils.build_direct_debit_xml(
            memberships, collection_date, amount
        )
    except sepa_utils.SepaConfigError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except crypto_utils.DecryptionFailed as exc:
        logger.exception("Could not decrypt a member IBAN while building a collection file.")
        return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as exc:
        logger.exception("Building the SEPA collection file failed.")
        return Response(
            {'error': f'Die SEPA-Datei konnte nicht erzeugt werden: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    run = DirectDebitRun.objects.create(
        message_id=message_id,
        collection_date=collection_date,
        amount_per_member=amount,
        member_count=len(items),
        total_amount=amount * len(items),
        xml=xml,
        created_by=request.user.username,
    )

    DirectDebitItem.objects.bulk_create([
        DirectDebitItem(
            run=run,
            membership=item['membership'],
            mandate_reference=item['mandate_reference'],
            sequence_type=item['sequence_type'],
            amount=item['amount'],
            end_to_end_id=item['end_to_end_id'],
        )
        for item in items
    ])

    # Advance the sequence so the next run for these members goes out as RCUR.
    Membership.objects.filter(
        tenant_id__in=[item['membership'].tenant_id for item in items]
    ).update(last_collection_on=collection_date)

    logger.info(
        "User '%s' created SEPA collection run %s (MsgId %s) for %s: %s members, %s EUR.",
        request.user.username, run.id, message_id, collection_date,
        run.member_count, run.total_amount,
    )

    return Response(
        {
            'message': f'SEPA-Datei für {run.member_count} Mitglieder erstellt.',
            'run': DirectDebitRunSerializer(run).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsFinanceDepartment])
def list_direct_debit_runs_view(request):
    return Response(DirectDebitRunSerializer(DirectDebitRun.objects.all(), many=True).data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, IsFinanceDepartment])
def download_direct_debit_view(request, run_id):
    """Download a previously generated file. Contains IBANs - hence the finance-only gate."""
    run = get_object_or_404(DirectDebitRun, id=run_id)

    logger.info("User '%s' downloaded SEPA collection run %s (MsgId %s).",
                request.user.username, run.id, run.message_id)

    response = HttpResponse(run.xml, content_type='application/xml')
    response['Content-Disposition'] = (
        f'attachment; filename="sepa-lastschrift-{run.collection_date}.xml"'
    )
    return response
