import io
import os
import logging
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from django.conf import settings
from collections import defaultdict
from ..models import Tenant, Engagement, Rental
from .. import config as app_config
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db.models import Sum

logger = logging.getLogger(__name__)

# Base directory where PDF templates are stored
PDF_TEMPLATES_BASE_DIR = os.path.join(settings.BASE_DIR, 'smartdorm', 'templates')

def fill_pdf_form(template_path: str, data_dict: dict) -> io.BytesIO | None:
    """
    Fills a PDF form template with data from a dictionary using pypdf.
    This version is robustly designed to handle PDFs with non-standard AcroForm linking.

    Args:
        template_path (str): The relative path to the PDF template file
                             (e.g., 'pdf/departure-template.pdf').
        data_dict (dict): A dictionary where keys are the PDF form field names
                          and values are the data to fill in.

    Returns:
        io.BytesIO: An in-memory bytes buffer containing the filled PDF,
                    or None if an error occurred.
    """
    full_template_path = os.path.join(PDF_TEMPLATES_BASE_DIR, template_path)

    try:
        with open(full_template_path, "rb") as template_file:
            reader = PdfReader(template_file)
            writer = PdfWriter()

            writer.append_pages_from_reader(reader)

            acroform_key = NameObject("/AcroForm")
            if acroform_key in reader.root_object:
                writer.root_object[acroform_key] = reader.root_object[acroform_key]
                
            writer.update_page_form_field_values(
                writer.pages[0],
                data_dict
            )

            # Create an in-memory buffer to hold the filled PDF
            pdf_buffer = io.BytesIO()
            writer.write(pdf_buffer)
            pdf_buffer.seek(0)

            logger.info(f"Successfully filled PDF template: {template_path}")
            return pdf_buffer

    except FileNotFoundError:
        logger.error(f"PDF template not found at: {full_template_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to fill PDF form for template {template_path}: {e}", exc_info=True)
        return None
    
    
def prepare_extension_application_pdf_data(tenant: Tenant) -> dict:
    """
    Gathers and processes all data needed for the contract extension application PDF.
    
    Args:
        tenant (Tenant): The tenant object for whom to generate the data.

    Returns:
        dict: A dictionary of data ready to be passed to fill_pdf_form.
    """
    # Get all compensated engagements for the tenant
    compensated_engagements = Engagement.objects.filter(
        tenant=tenant,
        compensate=True
    ).select_related('department').order_by('-semester')

    # Get rental history
    rental_history = Rental.objects.filter(
        tenant=tenant
    ).select_related('room').order_by('move_in')

    # Calculate total points
    total_points = compensated_engagements.aggregate(total=Sum('points'))['total'] or Decimal('0.00')

    # Calculate the potential new move-out date
    new_move_out_date = tenant.move_out + timedelta(days=app_config.DEFAULT_EXTENSION_DURATION_DAYS)

    # --- Construct the PDF data dictionary ---
    pdf_data = {
        'Bewerber Nachname': tenant.surname,
        'Bewerber Vorname': tenant.name,
        'Bewerber Zimmernummer': tenant.current_room or 'N/A',
        'Bewerber Mietbeginn': tenant.move_in.strftime('%d.%m.%Y'),
        'Bewerber aktuelles Mietende': tenant.move_out.strftime('%d.%m.%Y'),
        'Bewerber Verlängerungsdatum': new_move_out_date.strftime('%d.%m.%Y'),
        'Bewerber Anz bish Verlaengerungen': str(tenant.extension or 0),
        'Bewerber Gesamtzahl HSV-Punkte': str(total_points),
        'Bewerber ehem Zimmernummern': ", ".join(
            [r.room.name for r in rental_history if r.room and r.room.name != tenant.current_room]
        ),
    }

    # Group identical engagements
    grouped_engagements = defaultdict(lambda: {'semesters': [], 'points': Decimal('0.00')})
    for engagement in compensated_engagements:
        dept_name = engagement.department.name if engagement.department else 'N/A'
        grouped_engagements[dept_name]['semesters'].append(engagement.semester)
        grouped_engagements[dept_name]['points'] += engagement.points

    # Populate the PDF table rows from grouped data
    processed_engagements = list(grouped_engagements.items())
    for i, (dept_name, data) in enumerate(processed_engagements):
        if i >= 9:
            break
        
        row_num = i + 1
        sorted_semesters = sorted(data['semesters'], reverse=True)
        
        pdf_data[f'SemesterRow{row_num}'] = ", ".join(sorted_semesters)
        pdf_data[f'ReferatRow{row_num}'] = dept_name
        pdf_data[f'PunkteRow{row_num}'] = str(data['points'])
        
    return pdf_data