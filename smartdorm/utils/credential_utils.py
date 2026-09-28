"""
Mailing tenants and subtenants new login credentials.

LDAP only stores password hashes, so "resending" credentials always means generating a new
password.
"""

import logging

from smartdorm.utils import email_utils, ldap_utils
from smartdorm.utils.helper import generate_secure_password
from smartdorm.utils.ldap_sync import find_subtenant_account

logger = logging.getLogger(__name__)

KIND_WELCOME = 'WELCOME'
KIND_PASSWORD_RESET = 'PASSWORD_RESET'

TEMPLATES = {
    KIND_WELCOME: ("Dein SmartDorm Zugang", 'email/user-account-creation.html'),
    KIND_PASSWORD_RESET: ("SmartDorm - Passwort zurückgesetzt", 'email/user-password-reset.html'),
}

SUBTENANT_TEMPLATES = {
    KIND_WELCOME: ("Dein Wlan Zugang als Untermieter", 'email/user-account-creation-subtenant.html'),
    KIND_PASSWORD_RESET: TEMPLATES[KIND_PASSWORD_RESET],
}


def sync_ldap_email(tenant):
    """
    Makes the LDAP account's mail match the tenant's email in SmartDorm - the self-service
    password reset looks accounts up by it. Returns True if the mail had to be changed.
    Raises ValueError if the account does not exist, ConnectionError if LDAP is unreachable.
    """
    mails = ldap_utils.get_ldap_user_emails(tenant.username)
    if mails is None:
        raise ValueError(f"Kein Benutzerkonto „{tenant.username}“ gefunden.")

    if (tenant.email or '').strip().lower() in {m.strip().lower() for m in mails}:
        return False

    ldap_utils.update_ldap_user_attributes(tenant.username, email=tenant.email)
    logger.info(f"Synced LDAP mail of '{tenant.username}' to the address stored in SmartDorm.")
    return True


def resend_credentials(tenant, kind):
    """
    Gives the tenant's account a new password and mails it to their current address.

    If the mail cannot be sent, the old password is put back, so a mail outage never
    locks a tenant out of an account they could still use. Raises ValueError /
    ConnectionError when the LDAP account is missing or unreachable; returns whether the
    mail was sent otherwise.
    """
    if not tenant.username:
        raise ValueError("Der Bewohner hat keinen Benutzernamen.")

    sync_ldap_email(tenant)

    subject, template = TEMPLATES[kind]
    return _mail_new_password(tenant.username, tenant.email, tenant.name, subject, template)


def resend_subtenant_credentials(subtenant, kind):
    """
    resend_credentials() for a subtenant. Their account is found by email, so it never
    needs a mail sync - and a main tenant's account is never returned, so this cannot
    reset a tenant's password.
    """
    username = find_subtenant_account(subtenant.email, subtenant.name, subtenant.surname)
    if not username:
        raise ValueError("Kein Benutzerkonto für diesen Untermieter gefunden.")

    subject, template = SUBTENANT_TEMPLATES[kind]
    return _mail_new_password(username, subtenant.email, subtenant.name, subject, template)


def _mail_new_password(username, email, greeting, subject, template):
    """Sets a new password and mails it; puts the old one back if the mail fails."""
    old_hashes = ldap_utils.get_ldap_password_hashes(username)
    password = generate_secure_password()
    ldap_utils.update_ldap_password(username, password)

    sent = email_utils.send_email_message(
        recipient_list=[email],
        subject=subject,
        html_template_name=template,
        context={'greeting': greeting, 'username': username, 'password': password},
    )
    if not sent:
        try:
            ldap_utils.restore_ldap_password_hashes(username, old_hashes)
        except ConnectionError:
            # The new password is set but was never delivered - the next resend fixes it
            logger.error(
                f"Credentials mail for '{username}' failed and the old password could not "
                f"be restored. The account needs a new resend.", exc_info=True
            )
    return sent
