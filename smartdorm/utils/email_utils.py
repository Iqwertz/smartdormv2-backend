import os
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

ATTACHMENTS_BASE_DIR = os.path.join(settings.BASE_DIR, 'smartdorm', 'static')

PRODUCTION = os.environ.get('PRODUCTION', 'False').lower() in ['true', '1', 'yes']
DEVELOPER_EMAIL = os.environ.get('DEVELOPER_EMAIL')

def send_email_message(
    recipient_list,
    subject,
    html_template_name,
    text_template_name=None, # Optional: if not provided, text will be stripped from HTML
    context=None,
    attachment_paths=None,
    from_email=None
):
    """
    Sends an email using HTML and optionally plain text templates.

    Args:
        recipient_list (list): A list of recipient email addresses.
        subject (str): The subject of the email.
        html_template_name (str): Path to the HTML template (e.g., 'welcome.html').
                                   Relative to Django's template directories.
        text_template_name (str, optional): Path to the plain text template.
                                            If None, text content is stripped from HTML.
        context (dict, optional): A dictionary of context variables for the templates.
        attachment_paths (list, optional): A list of paths to files to attach.
                                           Paths are relative to ATTACHMENTS_BASE_DIR.
                                           (e.g., ['pdfs/report.pdf', 'images/logo.png'])
        from_email (str, optional): The sender's email address. Defaults to DEFAULT_FROM_EMAIL.

    Returns:
        bool: True if the email was sent successfully, False otherwise.
    """
    if context is None:
        context = {}
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL

    try:
        # Render HTML content
        html_content = render_to_string(html_template_name, context)

        # Render plain text content
        if text_template_name:
            text_content = render_to_string(text_template_name, context)
        else:
            text_content = strip_tags(html_content) # Fallback: strip tags from HTML

        # If in development mode, redirect all emails to the developer's email
        if not PRODUCTION:
            if DEVELOPER_EMAIL:
                recipient_list = [DEVELOPER_EMAIL]
                logger.info(f"Development mode: redirecting email that should go to {recipient_list} to developer email {DEVELOPER_EMAIL}")
            else:
                logger.error("DEVELOPER_EMAIL environment variable is not set. Cannot redirect email in development mode.")
                logger.error("Not sending email as no developer email is configured.")
                return False

        # Create the email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content, # Plain text body
            from_email=from_email,
            to=recipient_list
        )
        email.attach_alternative(html_content, "text/html") # Attach HTML version

        # Add attachments
        if attachment_paths:
            for rel_path in attachment_paths:
                full_path = os.path.join(ATTACHMENTS_BASE_DIR, rel_path)
                if os.path.exists(full_path):
                    try:
                        # Determine content type automatically or set explicitly if needed
                        email.attach_file(full_path)
                        logger.info(f"Successfully attached file: {full_path}")
                    except Exception as e:
                        logger.error(f"Could not attach file {full_path}: {e}")
                else:
                    logger.warning(f"Attachment file not found: {full_path}")

        # Send the email
        email.send(fail_silently=False)
        logger.info(f"Email sent successfully to {recipient_list} with subject '{subject}'.")
        return True

    except FileNotFoundError as e:
        logger.error(f"Email template not found: {e}. Searched in: {settings.TEMPLATES[0]['DIRS']}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_list} with subject '{subject}': {e}", exc_info=True)
        return False