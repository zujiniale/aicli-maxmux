"""
db/crypto.py — Optional Fernet encryption wrapper for chat history.
Key is derived from a password or machine fingerprint via SHA-256.
"""
import base64
import hashlib
from cryptography.fernet import Fernet


def derive_key(password: str) -> bytes:
    """Derive a Fernet-compatible key from a string via SHA-256."""
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())


class ChatEncryption:
    def __init__(self, password: str):
        self.fernet = Fernet(derive_key(password))

    def encrypt(self, text: str) -> str:
        return self.fernet.encrypt(text.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode()).decode()
