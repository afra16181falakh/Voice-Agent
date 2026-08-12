"""
Password hashing (PBKDF2-HMAC-SHA256) and session token signing/verification
(HMAC-SHA256, JWT-shaped) for mobile app user accounts. Stdlib-only --
deliberately avoids adding bcrypt/PyJWT as new dependencies.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from app.config import settings

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(user_id: str, email: str) -> str:
    header_b64 = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = {"sub": user_id, "email": email, "exp": int(time.time()) + settings.auth.token_expire_days * 86400}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(settings.auth.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_token(token: str) -> Optional[dict]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(settings.auth.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_verification_token(user_id: str) -> str:
    """Same HMAC scheme as session tokens, but a distinct `purpose` claim
    and a short expiry -- keeps this from being usable as a session token
    even though it's signed with the same secret."""
    header_b64 = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = {"sub": user_id, "purpose": "verify_email", "exp": int(time.time()) + 24 * 3600}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(settings.auth.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_verification_token(token: str) -> Optional[str]:
    """Returns the user_id if valid, else None."""
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "verify_email":
        return None
    return payload.get("sub")
