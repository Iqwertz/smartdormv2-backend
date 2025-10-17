import ldap
from django.conf import settings
import logging
import uuid
import hashlib
from passlib.hash import ldap_salted_sha1 as ssha

logger = logging.getLogger(__name__)


# Implemented MD4 Hasing here since the servers openssl version doesnt support it.
def _F(x, y, z): return (x & y) | (~x & z)
def _G(x, y, z): return (x & y) | (x & z) | (y & z)
def _H(x, y, z): return x ^ y ^ z

def _left_rotate(x, n):
    return ((x << n) & 0xffffffff) | (x >> (32 - n))

class PurePythonMD4:
    def __init__(self, message=b''):
        self._A = 0x67452301
        self._B = 0xefcdab89
        self._C = 0x98badcfe
        self._D = 0x10325476
        self._message = message
        self._length = len(message) * 8
        self._process()

    def _process(self):
        message = bytearray(self._message)
        message.append(0x80)
        while len(message) % 64 != 56:
            message.append(0x00)
        message += self._length.to_bytes(8, 'little')

        for i in range(0, len(message), 64):
            chunk = message[i:i+64]
            X = [int.from_bytes(chunk[j:j+4], 'little') for j in range(0, 64, 4)]
            
            AA, BB, CC, DD = self._A, self._B, self._C, self._D

            # Round 1
            s1 = [3, 7, 11, 19]
            for j in range(16):
                k = j
                s = s1[j % 4]
                t = (self._A + _F(self._B, self._C, self._D) + X[k]) & 0xffffffff
                self._A, self._B, self._C, self._D = self._D, _left_rotate(t, s), self._B, self._C
            
            # Round 2
            s2 = [3, 5, 9, 13]
            for j in range(16):
                k = (j // 4) + (j % 4) * 4
                s = s2[j % 4]
                t = (self._A + _G(self._B, self._C, self._D) + X[k] + 0x5a827999) & 0xffffffff
                self._A, self._B, self._C, self._D = self._D, _left_rotate(t, s), self._B, self._C

            # Round 3
            s3 = [3, 9, 11, 15]
            k_map = [0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15]
            for j in range(16):
                k = k_map[j]
                s = s3[j % 4]
                t = (self._A + _H(self._B, self._C, self._D) + X[k] + 0x6ed9eba1) & 0xffffffff
                self._A, self._B, self._C, self._D = self._D, _left_rotate(t, s), self._B, self._C

            self._A = (self._A + AA) & 0xffffffff
            self._B = (self._B + BB) & 0xffffffff
            self._C = (self._C + CC) & 0xffffffff
            self._D = (self._D + DD) & 0xffffffff

    def hexdigest(self):
        return ''.join(x.to_bytes(4, 'little').hex() for x in [self._A, self._B, self._C, self._D])

def _calculate_nt_hash(password):
    """Calculates the NT password hash (MD4 of UTF-16LE encoded password)"""
    encoded_password = password.encode('utf-16le')
    md4_hash = PurePythonMD4(encoded_password).hexdigest()
    return md4_hash.upper()

def create_ldap_user(username, password, first_name, last_name, email, group_dns=None, userType='TENANT'):
    """
    Creates a new user in the LDAP directory with Samba attributes and adds them to specified groups.
    """
    if group_dns is None:
        group_dns = []
        
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"
    user_dn = f"cn={username},{user_base_dn}"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        # Check if user already exists
        try:
            con.search_s(user_dn, ldap.SCOPE_BASE)
            logger.error(f"LDAP user creation failed: User '{username}' already exists.")
            raise ValueError(f"A user with the username '{username}' already exists.")
        except ldap.NO_SUCH_OBJECT:
            pass  # Good, user does not exist.

        # --- Prepare all required user attributes ---
        ssha_password = ssha.hash(password)
        nt_password = _calculate_nt_hash(password)
        
        # No hyphens, for legacy reasons
        user_uid = str(uuid.uuid4()).replace('-', '')
        samba_sid = str(uuid.uuid4()).replace('-', '')

        attrs = [
            ('objectClass', [b'inetOrgPerson', b'sambaSamAccount']),
            ('cn', [username.encode('utf-8')]),
            ('sn', [last_name.encode('utf-8')]),
            ('givenName', [first_name.encode('utf-8')]),
            ('displayName', [f"{first_name} {last_name}".encode('utf-8')]),
            ('mail', [email.encode('utf-8')]),
            ('userPassword', [ssha_password.encode('utf-8')]),
            ('employeeType', [userType.encode('utf-8')]),
            ('uid', [user_uid.encode('utf-8')]),
            ('sambaSID', [samba_sid.encode('utf-8')]),
            ('sambaNTPassword', [nt_password.encode('utf-8')]),
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
                # Log error but continue, as user creation was the main goal
                logger.error(f"Failed to add user '{username}' to group '{group_dn}': {e}")
                pass

        return True

    except ldap.LDAPError as e:
        logger.error(f"LDAP error during user creation for '{username}': {e}")
        raise ConnectionError(f"Could not write to the authentication server: {e}")
    finally:
        if 'con' in locals() and con:
            con.unbind_s()

def update_ldap_password(username, new_password):
    """
    Updates the password of an existing LDAP user, including the Samba NT hash.
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

        # Prepare new hashed passwords
        ssha_password = ssha.hash(new_password)
        nt_password = _calculate_nt_hash(new_password)

        # Update both userPassword and sambaNTPassword
        mod_list = [
            (ldap.MOD_REPLACE, 'userPassword', [ssha_password.encode('utf-8')]),
            (ldap.MOD_REPLACE, 'sambaNTPassword', [nt_password.encode('utf-8')])
        ]
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

def find_ldap_user_by_email(email):
    """
    Finds an LDAP user by email address.
    Returns (username, full_name) if found, (None, None) if not found.
    """
    ldap_uri = settings.AUTH_LDAP_SERVER_URI
    admin_dn = settings.AUTH_LDAP_BIND_DN
    admin_password = settings.AUTH_LDAP_BIND_PASSWORD
    user_base_dn = "ou=users,dc=schollheim,dc=net"

    try:
        con = ldap.initialize(ldap_uri)
        con.protocol_version = ldap.VERSION3
        con.simple_bind_s(admin_dn, admin_password)

        # Search for user by email
        search_filter = f"(mail={email})"
        result = con.search_s(user_base_dn, ldap.SCOPE_SUBTREE, search_filter, ['cn', 'givenName', 'sn'])
        
        if result:
            # Extract username and full name from LDAP result
            dn, attrs = result[0]
            username = attrs['cn'][0].decode('utf-8') if 'cn' in attrs else None
            first_name = attrs['givenName'][0].decode('utf-8') if 'givenName' in attrs else ""
            last_name = attrs['sn'][0].decode('utf-8') if 'sn' in attrs else ""
            full_name = f"{first_name} {last_name}".strip()
            
            logger.info(f"Found LDAP user by email '{email}': username='{username}', name='{full_name}'")
            return username, full_name
        else:
            logger.info(f"No LDAP user found with email '{email}'")
            return None, None

    except ldap.LDAPError as e:
        logger.error(f"LDAP error during email search for '{email}': {e}")
        raise ConnectionError(f"Could not search LDAP for email '{email}': {e}")
    finally:
        if 'con' in locals() and con:
            con.unbind_s()