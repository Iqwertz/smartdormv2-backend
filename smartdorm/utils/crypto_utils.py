"""
Symmetric encryption for the few fields that must not sit in the database in plaintext.

Only the HSV membership feature uses this so far: an IBAN plus the SEPA mandate data belong
to a different legal entity than the tenancy data around them, and Art. 32 DSGVO expects
payment data to be protected beyond plain access control.

Scope of the protection, honestly stated: this defends against a leaked database dump or an
old backup. It does not defend against an attacker who already runs the application, because
the key sits in the same .env the app reads. Anything stronger would need a KMS/HSM, which is
out of proportion for a Verein of this size.

Keys live in FIELD_ENCRYPTION_KEYS as a comma-separated list of urlsafe-base64 Fernet keys.
The first entry encrypts; every entry can decrypt, so a key can be rotated by prepending a
new one and re-saving the affected rows before dropping the old key.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

logger = logging.getLogger(__name__)


class EncryptionKeyMissing(RuntimeError):
    """Raised when encrypted data is used but no key is configured."""


class DecryptionFailed(RuntimeError):
    """Raised when a stored token cannot be decrypted with any configured key."""


_fernet_cache = None


def _get_fernet() -> MultiFernet:
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    raw_keys = getattr(settings, 'FIELD_ENCRYPTION_KEYS', [])
    if not raw_keys:
        raise EncryptionKeyMissing(
            "FIELD_ENCRYPTION_KEYS is not configured. Membership payment data cannot be "
            "read or written without it. Add it to .env - see .sample.env."
        )

    try:
        _fernet_cache = MultiFernet([Fernet(key) for key in raw_keys])
    except (ValueError, TypeError) as exc:
        raise EncryptionKeyMissing(
            f"FIELD_ENCRYPTION_KEYS contains an invalid Fernet key: {exc}"
        ) from exc

    return _fernet_cache


def reset_key_cache():
    """Drop the cached MultiFernet. Only needed in tests that swap the key setting."""
    global _fernet_cache
    _fernet_cache = None


def encrypt_str(plain: str) -> str:
    """Encrypt a string into a storable token. Empty input yields an empty token."""
    if not plain:
        return ''
    return _get_fernet().encrypt(plain.encode('utf-8')).decode('ascii')


def decrypt_str(token: str) -> str:
    """
    Decrypt a token produced by encrypt_str().

    Fails loudly rather than returning garbage: a token that no configured key can open
    means the key was rotated away or the row was tampered with, and silently handing back
    an empty IBAN would produce a wrong SEPA collection file.
    """
    if not token:
        return ''
    try:
        return _get_fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except InvalidToken as exc:
        raise DecryptionFailed(
            "Stored value could not be decrypted with any configured key in "
            "FIELD_ENCRYPTION_KEYS. The key may have been rotated away."
        ) from exc


# --- IBAN handling -------------------------------------------------------------------

# Length of a valid IBAN per country, for the countries a Schollheim member plausibly banks
# with (SEPA scheme participants). An unknown country code is rejected rather than guessed.
IBAN_LENGTHS = {
    'AD': 24, 'AT': 20, 'BE': 16, 'BG': 22, 'CH': 21, 'CY': 28, 'CZ': 24, 'DE': 22,
    'DK': 18, 'EE': 20, 'ES': 24, 'FI': 18, 'FR': 27, 'GB': 22, 'GI': 23, 'GR': 27,
    'HR': 21, 'HU': 28, 'IE': 22, 'IS': 26, 'IT': 27, 'LI': 21, 'LT': 20, 'LU': 20,
    'LV': 21, 'MC': 27, 'MT': 31, 'NL': 18, 'NO': 15, 'PL': 28, 'PT': 25, 'RO': 24,
    'SE': 24, 'SI': 19, 'SK': 24, 'SM': 27, 'VA': 22,
}


def normalize_iban(raw: str) -> str:
    """Strip spaces and lowercase letters so stored and compared IBANs have one shape."""
    if not raw:
        return ''
    return ''.join(raw.split()).upper()


def validate_iban(raw: str) -> bool:
    """
    Check an IBAN's country, length and ISO 7064 mod-97 checksum.

    Catches typos and transposed digits before they reach the bank, where a bad IBAN comes
    back as a rejected collection days later.
    """
    iban = normalize_iban(raw)

    if len(iban) < 5 or not iban[:2].isalpha() or not iban[2:4].isdigit():
        return False

    expected_length = IBAN_LENGTHS.get(iban[:2])
    if expected_length is None or len(iban) != expected_length:
        return False

    if not iban[4:].isalnum():
        return False

    # Move the first four characters to the end, map letters to numbers (A=10 .. Z=35),
    # then the whole number must be congruent to 1 modulo 97.
    rearranged = iban[4:] + iban[:4]
    digits = ''.join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def format_iban(raw: str) -> str:
    """Group an IBAN into blocks of four for display: 'DE89 3704 0044 0532 0130 00'."""
    iban = normalize_iban(raw)
    return ' '.join(iban[i:i + 4] for i in range(0, len(iban), 4))


def mask_iban(raw: str) -> str:
    """
    Render an IBAN with everything but the country prefix and last four characters hidden.

    Used everywhere the full number is not strictly needed, so a screenshot or a shared
    screen does not leak account numbers.
    """
    iban = normalize_iban(raw)
    if len(iban) <= 8:
        return iban
    return format_iban(f"{iban[:4]}{'X' * (len(iban) - 8)}{iban[-4:]}").replace('X', '•')


def iban_last4(raw: str) -> str:
    """The last four characters, stored alongside the ciphertext for masked display."""
    iban = normalize_iban(raw)
    return iban[-4:] if len(iban) >= 4 else ''
