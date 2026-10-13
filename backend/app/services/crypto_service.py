import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.config import settings

def _get_fernet_key() -> bytes:
    raw_key = os.getenv("ENCRYPTION_KEY") or settings.SECRET_KEY
    # Derive deterministic 32-byte urlsafe base64 key using SHA-256
    derived = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(derived)

def encrypt_credential(plain_text: Optional[str]) -> str:
    """Encrypt sensitive credentials at rest."""
    if not plain_text or not plain_text.strip():
        return ""
    f = Fernet(_get_fernet_key())
    return f.encrypt(plain_text.strip().encode("utf-8")).decode("utf-8")

def decrypt_credential(cipher_text: Optional[str]) -> str:
    """Decrypt sensitive credentials at rest with fallback if stored unencrypted."""
    if not cipher_text or not cipher_text.strip():
        return ""
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(cipher_text.strip().encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback in case raw key was previously stored before encryption was enabled
        return cipher_text.strip()

