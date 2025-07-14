import ldap
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def create_ldap_user(username, password, first_name, last_name, email, group_dns=None):
    """
    Creates a new user in the LDAP directory and adds them to specified groups.
    """
    if group_dns is None:
        group_dns = []
        
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    # This OU should be where new users are stored.
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        # Check if user already exists #This can fail when the user was a subtenant before #todo
        try:
            con.search_s(user_dn, ldap.SCOPE_BASE)
            logger.error(f"LDAP user creation failed: User '{username}' already exists.")
            raise ValueError(f"A user with the username '{username}' already exists.")
        except ldap.NO_SUCH_OBJECT:
            pass # Good, user does not exist.

        # Prepare user attributes for inetOrgPerson
        attrs = [
            ('objectClass', [b'inetOrgPerson', b'top']),
            ('cn', [username.encode('utf-8')]),
            ('sn', [last_name.encode('utf-8')]),
            ('givenName', [first_name.encode('utf-8')]),
            ('mail', [email.encode('utf-8')]),
            ('userPassword', [password.encode('utf-8')]),
            ('employeeType', [b'TENANT']), # Custom attribute used by this app
        ]

        # Add the new user to LDAP
        con.add_s(user_dn, attrs)
        logger.info(f"Successfully created LDAP user: {user_dn}")
        
        # Add the new user to the specified groups
        for group_dn in group_dns:
            try:
                mod_list = [(ldap.MOD_ADD, 'member', [user_dn.encode('utf-8')])]
                con.modify_s(group_dn, mod_list)
                logger.info(f"Successfully added LDAP user '{username}' to group '{group_dn}'.")
            except ldap.LDAPError as e:
                logger.error(f"Failed to add user '{username}' to group '{group_dn}': {e}")
                pass

        return True

    except ldap.LDAPError as e:
        logger.error(f"LDAP error during user creation for '{username}': {e}")
        raise ConnectionError(f"Could not write to the authentication server: {e}")
    finally:
        if 'con' in locals() and con:
            con.unbind_s()