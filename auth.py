"""
FloodIQ — Authentication & Role-Based Access Control (RBAC)

Provides:
- PBKDF2-HMAC-SHA256 password hashing and constant-time verification
- HMAC-SHA256 signed bearer tokens with expiration and logout revocation
- FastAPI dependencies for current_user and role enforcement
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Callable, Optional

from fastapi import Depends, Header, HTTPException, status

from database import get_user_by_id

# Server-side signing secret (ephemeral CSPRNG fallback for local dev if env unset)
_AUTH_SECRET = os.getenv("FLOODIQ_AUTH_SECRET") or secrets.token_hex(32)
TOKEN_TTL_SECONDS = int(os.getenv("FLOODIQ_TOKEN_TTL_SECONDS", "43200"))  # 12 hours

# In-memory revoked token jti set for logout invalidation
_REVOKED_JTIS: set[str] = set()


# ---------------------------------------------------------------------------
# Password Hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt_hex = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of a password against stored PBKDF2 hash."""
    try:
        scheme, salt_hex, expected_hex = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 120_000)
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signed Bearer Tokens (HMAC-SHA256)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_access_token(user: dict[str, Any]) -> str:
    """Create a signed bearer token encoding user_id, role, team_id, exp, and jti."""
    now = int(time.time())
    payload = {
        "sub": user["user_id"],
        "role": user["role"],
        "team_id": user.get("team_id"),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_hex(12),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_AUTH_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Verify signature, expiration, and revocation of a bearer token."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(_AUTH_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig_b64), expected_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        if payload.get("jti") in _REVOKED_JTIS:
            return None
        return payload
    except Exception:
        return None


def revoke_token(token: str) -> None:
    """Revoke a token on logout."""
    payload = decode_access_token(token)
    if payload and payload.get("jti"):
        _REVOKED_JTIS.add(payload["jti"])


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict[str, Any]]:
    """Return authenticated user dict if valid Bearer token provided, else None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        return None
    user = get_user_by_id(payload["sub"])
    if not user:
        return None
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "team_id": user.get("team_id"),
    }


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """Require a valid authenticated user (401 Unauthorized otherwise)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "team_id": user.get("team_id"),
    }


def require_roles(*allowed_roles: str) -> Callable[..., dict[str, Any]]:
    """Dependency factory enforcing one of the specified roles (403 Forbidden otherwise)."""
    def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not authorized for this action. Required: {list(allowed_roles)}",
            )
        return user
    return _dep
