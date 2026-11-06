import os
import base64
import hashlib
import logging
from typing import Optional, List
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

logger = logging.getLogger(__name__)

class CredentialDecryptionError(ValueError):
    """Raised when ciphertext cannot be safely decrypted by any configured key."""
    pass

def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive deterministic 32-byte urlsafe base64 key using SHA-256."""
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived)

def _get_primary_fernet() -> Fernet:
    raw_key = os.getenv("ENCRYPTION_KEY") or settings.SECRET_KEY
    return Fernet(_derive_fernet_key(raw_key))

def _get_all_fernets() -> List[Fernet]:
    """Return primary Fernet followed by any configured rotation fallback Fernets."""
    fernets = [_get_primary_fernet()]
    fallbacks = os.getenv("ENCRYPTION_KEY_FALLBACKS", "")
    if fallbacks:
        for k in fallbacks.split(","):
            k_clean = k.strip()
            if k_clean:
                fernets.append(Fernet(_derive_fernet_key(k_clean)))
    return fernets

def encrypt_credential(plain_text: Optional[str]) -> str:
    """Encrypt sensitive credentials at rest using current primary key."""
    if not plain_text or not plain_text.strip():
        return ""
    f = _get_primary_fernet()
    return f.encrypt(plain_text.strip().encode("utf-8")).decode("utf-8")

def decrypt_credential(cipher_text: Optional[str], safe_fallback: bool = True) -> str:
    """
    Decrypt sensitive credentials at rest.
    Tries primary key, then fallback keys in order.
    NEVER returns the raw ciphertext on decryption failure to prevent
    treating ciphertext as valid credentials.
    """
    if not cipher_text or not cipher_text.strip():
        return ""

    raw_cipher = cipher_text.strip()
    cipher_bytes = raw_cipher.encode("utf-8")

    fernets = _get_all_fernets()
    for f in fernets:
        try:
            return f.decrypt(cipher_bytes).decode("utf-8")
        except (InvalidToken, Exception):
            continue

    logger.warning("Decryption failure for sensitive credential token. Rejecting corrupted/unrecognized ciphertext.")
    if safe_fallback:
        return ""
    raise CredentialDecryptionError("Failed to decrypt sensitive credential: invalid key or corrupted ciphertext")

def rotate_credential(cipher_text: Optional[str]) -> str:
    """
    Re-encrypt an existing credential under the current primary key.
    Useful for key rotation workflows.
    """
    if not cipher_text or not cipher_text.strip():
        return ""
    decrypted = decrypt_credential(cipher_text, safe_fallback=False)
    return encrypt_credential(decrypted)
