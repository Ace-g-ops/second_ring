import os
import hashlib
import hmac

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

PHONE_ENCRYPTION_KEY=os.getenv("PHONE_ENCRYPTION_KEY")
PHONE_HASH_SECRET=os.getenv("PHONE_HASH_SECRET")

if not PHONE_ENCRYPTION_KEY or not PHONE_HASH_SECRET:
    raise ValueError("Phone hash or phone encryption key is missing")

fernet = Fernet(PHONE_ENCRYPTION_KEY.encode())

def normalize_phone(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "").strip

def encrypt_phone(phone: str) -> str:
    return fernet.encrypt(normalize_phone(phone).encode()).decode()

def decrypt_phone(encrypted_phone: str) -> str:
    return fernet.decrypt(encrypted_phone.encode()).decode()

def hash_phone(phone: str) -> str:
    normalized = normalize_phone(phone)

    return hmac.new(
        PHONE_HASH_SECRET.encode,
        normalized.encode(),
        hashlib.sha256
    ).hexdigest()

def mask_phone(phone: str) -> str:
    if not phone:
        return ""

    cleaned = normalize_phone(phone)

    if len(cleaned) <= 7:
        return "****"

    return f"{cleaned[:4]}****{cleaned[-3:]}" 