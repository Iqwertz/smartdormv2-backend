"""
Renders the archived PDF of a Beitrittserklärung including the SEPA mandate.

This document is the Verein's evidence. A member can dispute a SEPA collection as
unauthorised for thirteen months, and the bank may then ask the creditor to produce the
mandate. So the PDF has to show, on one page: the exact wording that was on screen, the data
that was entered, and who submitted it when from where.

The text is always taken from the terms version stored on the application, never from the
current one - see smartdorm/membership_texts.py.
"""

import io
import logging

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .. import membership_texts
from . import crypto_utils

logger = logging.getLogger(__name__)


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('MTitle', parent=base['Heading1'], fontSize=16, spaceAfter=10),
        'heading': ParagraphStyle('MHeading', parent=base['Heading2'], fontSize=12,
                                  spaceBefore=14, spaceAfter=6),
        'body': ParagraphStyle('MBody', parent=base['Normal'], fontSize=9, leading=12,
                               alignment=TA_JUSTIFY, spaceAfter=6),
        'small': ParagraphStyle('MSmall', parent=base['Normal'], fontSize=7.5, leading=10,
                                alignment=TA_JUSTIFY, textColor=colors.HexColor('#444444'),
                                spaceAfter=5),
        'label': ParagraphStyle('MLabel', parent=base['Normal'], fontSize=9, leading=12),
    }


def _data_table(rows, styles):
    """Two-column label/value table used for the Daten and Mandat blocks."""
    table = Table(
        [[Paragraph(f"<b>{label}</b>", styles['label']), Paragraph(str(value), styles['label'])]
         for label, value in rows],
        colWidths=[6.0 * cm, 10.0 * cm],
    )
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#DDDDDD')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return table


def _yes_no(value):
    return 'Ja' if value else 'Nein'


def render_declaration_pdf(application, tenant=None):
    """
    Build the PDF for one MembershipApplication and return it as bytes.

    The full IBAN is printed: this document is the mandate itself, and a mandate without the
    account number proves nothing. Access to it is gated by the endpoint that serves it.
    """
    from ..models import MembershipApplication

    terms = membership_texts.get_terms(application.terms_version)
    styles = _styles()
    tenant = tenant or application.tenant

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Beitrittserklärung {application.first_name} {application.last_name}",
    )

    story = [
        Paragraph(terms['declaration_heading'], styles['title']),
        Paragraph(terms['declaration_subheading'], styles['body']),
        Spacer(1, 6),
        Paragraph('Daten', styles['heading']),
        _data_table([
            ('Vorname(n)', application.first_name),
            ('Nachname(n)', application.last_name),
            ('Zimmer', tenant.current_room or '-'),
            ('E-Mail', tenant.email or '-'),
            ('Gewünschtes Beitrittsdatum',
             application.requested_join_date.strftime('%d.%m.%Y')),
            ('Mindestens 18 Jahre alt', _yes_no(application.is_of_age)),
        ], styles),
        Spacer(1, 10),
        Paragraph('Einwilligung Amtsliste', styles['heading']),
        Paragraph(
            terms['amtsliste_consent_label'] if application.amtsliste_consent
            else f"<i>{terms['amtsliste_decline_label']}</i> - der Einwilligung in die "
                 f"Veröffentlichung in der Amtsliste wurde nicht zugestimmt.",
            styles['body'],
        ),
        Spacer(1, 6),
        Paragraph(terms['duty_to_notify'], styles['body']),
        Paragraph(terms['statutes_acknowledgement'], styles['body']),
        Paragraph(terms['automatic_end'], styles['body']),
        Paragraph(terms['privacy_notice'], styles['small']),
    ]

    # --- SEPA section ---
    story.append(Paragraph(terms['sepa_heading'], styles['heading']))

    if application.payment_method == MembershipApplication.PaymentMethod.SEPA:
        try:
            iban = crypto_utils.format_iban(application.get_iban())
        except crypto_utils.DecryptionFailed:
            # Better an explicit gap in the document than a PDF that silently omits the
            # account it is supposed to prove.
            logger.error(
                "Could not decrypt IBAN for membership application %s while rendering PDF.",
                application.id,
            )
            iban = '[IBAN konnte nicht entschlüsselt werden]'

        story += [
            Paragraph(terms['sepa_creditor'], styles['body']),
            _data_table([
                ('Vorname(n) Kontoinhaber:in', application.account_holder_first_name),
                ('Nachname(n) Kontoinhaber:in', application.account_holder_last_name),
                ('IBAN', iban),
                ('Mandatsart', 'SEPA-Basislastschrift, wiederkehrende Zahlung'),
            ], styles),
            Spacer(1, 8),
            Paragraph(terms['sepa_mandate_reference_note'], styles['body']),
            Paragraph(terms['sepa_authorisation'], styles['body']),
            Paragraph(terms['sepa_payment_type'], styles['body']),
            Paragraph(terms['sepa_prenotification'], styles['body']),
            Paragraph(f"<b>Zustimmung:</b> {terms['sepa_consent_label']}", styles['body']),
            Paragraph(terms['sepa_documentation_note'], styles['small']),
            Paragraph(terms['sepa_privacy_notice'], styles['small']),
        ]
    else:
        story.append(Paragraph(
            f"<b>{terms['sepa_alternative_label']}</b> Es wurde kein SEPA-Lastschriftmandat "
            f"erteilt. Die Beitragspflicht aus der Mitgliedschaft bleibt hiervon unberührt.",
            styles['body'],
        ))

    # --- Submission record: the part that makes this document evidence ---
    story.append(KeepTogether([
        Paragraph('Dokumentation der Abgabe', styles['heading']),
        _data_table([
            ('Abgegeben am',
             application.submitted_at.strftime('%d.%m.%Y um %H:%M:%S Uhr')
             if application.submitted_at else '-'),
            ('Angemeldetes Benutzerkonto', application.submitted_by_username),
            ('IP-Adresse', application.submitted_ip or '-'),
            ('Textfassung', application.terms_version),
            ('Antragsnummer', application.id),
        ], styles),
        Spacer(1, 6),
        Paragraph(
            'Diese Erklärung wurde elektronisch über SmartDorm abgegeben. Datum und Uhrzeit '
            'der Abgabe wurden automatisch dokumentiert; eine handschriftliche Unterschrift '
            'liegt nicht vor.',
            styles['small'],
        ),
    ]))

    doc.build(story)
    return buffer.getvalue()


def declaration_filename(application):
    """Stable, human-readable filename for downloads and mail attachments."""
    last = ''.join(ch for ch in application.last_name if ch.isalnum()) or 'Mitglied'
    return f"Beitrittserklaerung_{last}_{application.id}.pdf"
