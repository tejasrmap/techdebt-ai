import os
import pytest
from app.services.crypto_service import (
    encrypt_credential, decrypt_credential, rotate_credential,
    CredentialDecryptionError, _derive_fernet_key
)
from cryptography.fernet import Fernet

def test_encryption_decryption_roundtrip():
    secret = "sk-live-super-secret-production-token-12345"
    cipher = encrypt_credential(secret)
    assert cipher != secret
    assert len(cipher) > 20

    decrypted = decrypt_credential(cipher)
    assert decrypted == secret

def test_corrupted_ciphertext_never_returns_ciphertext():
    """Security test: Decryption failure must NEVER return raw ciphertext as fallback."""
    fake_cipher = "gAAAAABl-fake-corrupted-ciphertext-that-should-never-be-used-as-raw-key"
    
    # Safe fallback returns empty string, NOT fake_cipher
    res_safe = decrypt_credential(fake_cipher, safe_fallback=True)
    assert res_safe == "", f"Expected empty string on failure, got {res_safe}"
    assert res_safe != fake_cipher

    # Strict mode raises CredentialDecryptionError
    with pytest.raises(CredentialDecryptionError):
        decrypt_credential(fake_cipher, safe_fallback=False)

def test_secret_rotation_with_fallback_keys():
    """Test decrypting ciphertext encrypted under an old key using ENCRYPTION_KEY_FALLBACKS."""
    old_key = "old-legacy-key-before-rotation-2025"
    new_key = "new-fresh-primary-key-after-rotation-2026"

    # Encrypt something with old key directly
    old_fernet = Fernet(_derive_fernet_key(old_key))
    plain = "ghp_myPersonalGitHubAccessToken12345"
    old_cipher = old_fernet.encrypt(plain.encode()).decode()

    # Set new primary key and old key in fallback
    orig_env_key = os.environ.get("ENCRYPTION_KEY")
    orig_fallbacks = os.environ.get("ENCRYPTION_KEY_FALLBACKS")
    try:
        os.environ["ENCRYPTION_KEY"] = new_key
        os.environ["ENCRYPTION_KEY_FALLBACKS"] = old_key

        # Should be able to decrypt old cipher via fallback
        decrypted = decrypt_credential(old_cipher)
        assert decrypted == plain

        # Rotate credential to new key
        new_cipher = rotate_credential(old_cipher)
        assert new_cipher != old_cipher

        # Remove fallback and verify new_cipher decrypts with only new primary key
        del os.environ["ENCRYPTION_KEY_FALLBACKS"]
        re_decrypted = decrypt_credential(new_cipher)
        assert re_decrypted == plain
    finally:
        if orig_env_key:
            os.environ["ENCRYPTION_KEY"] = orig_env_key
        elif "ENCRYPTION_KEY" in os.environ:
            del os.environ["ENCRYPTION_KEY"]

        if orig_fallbacks:
            os.environ["ENCRYPTION_KEY_FALLBACKS"] = orig_fallbacks
        elif "ENCRYPTION_KEY_FALLBACKS" in os.environ:
            del os.environ["ENCRYPTION_KEY_FALLBACKS"]
