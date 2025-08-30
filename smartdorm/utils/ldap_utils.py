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
            
def add_user_to_group(username, group_dn):
    """Adds an existing LDAP user to a specified LDAP group."""
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        mod_list = [(ldap.MOD_ADD, 'member', [user_dn.encode('utf-8')])]
        con.modify_s(group_dn, mod_list)
        logger.info(f"Successfully added LDAP user '{username}' to group '{group_dn}'.")
        return True
    except ldap.TYPE_OR_VALUE_EXISTS:
        logger.warning(f"User '{username}' is already a member of group '{group_dn}'. No action needed.")
        return True
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Failed to add user to group: Group '{group_dn}' or user '{user_dn}' does not exist.")
        return True
    except ldap.LDAPError as e:
        logger.error(f"Failed to add user '{username}' to group '{group_dn}': {e}")
        return False
    finally:
        if 'con' in locals() and con:
            con.unbind_s()

def remove_user_from_group(username, group_dn):
    """Removes an LDAP user from a specified LDAP group."""
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        mod_list = [(ldap.MOD_DELETE, 'member', [user_dn.encode('utf-8')])]
        con.modify_s(group_dn, mod_list)
        logger.info(f"Successfully removed LDAP user '{username}' from group '{group_dn}'.")
        return True
    except ldap.NO_SUCH_ATTRIBUTE:
        logger.warning(f"User '{username}' was not a member of group '{group_dn}'. No action needed.")
        return True
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Failed to remove user from group: Group '{group_dn}' or user '{user_dn}' does not exist.")
        return True
    except ldap.LDAPError as e:
        logger.error(f"Failed to remove user '{username}' from group '{group_dn}': {e}")
        return False
    finally:
        if 'con' in locals() and con:
            con.unbind_s()
            
def delete_ldap_user(username):
    """
    Deletes a user from the LDAP directory.
    """
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        con.delete_s(user_dn)
        logger.info(f"Successfully deleted LDAP user: {user_dn}")
        return True

    except ldap.NO_SUCH_OBJECT:
        logger.warning(f"Attempted to delete LDAP user '{username}', but they do not exist.")
        return True # The end goal is for the user to not exist, so this is a success state.
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during deletion for '{username}': {e}")
        raise ConnectionError(f"Could not delete user from the authentication server: {e}")
    finally:
        if 'con' in locals() and con:
            con.unbind_s()

def update_ldap_password(username, new_password):
    """
    Updates the password of an existing LDAP user.
    """
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        # Update the user's password
        mod_list = [(ldap.MOD_REPLACE, 'userPassword', [new_password.encode('utf-8')])]
        con.modify_s(user_dn, mod_list)
        logger.info(f"Successfully updated password for LDAP user: {username}")
        return True

    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Failed to update password: User '{username}' does not exist in LDAP.")
        raise ValueError(f"User '{username}' does not exist in LDAP.")
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during password update for '{username}': {e}")
        raise ConnectionError(f"Could not update password in the authentication server: {e}")
    finally:
        if 'con' in locals() and con:
            con.unbind_s()