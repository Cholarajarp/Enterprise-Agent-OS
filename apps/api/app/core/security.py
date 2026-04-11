"""JWT token verification and FastAPI authentication dependencies.

Tokens are expected to be RS256-signed JWTs issued by the platform identity
provider. The public key is loaded from ``settings.JWT_PUBLIC_KEY``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=True)


class TokenPayload(BaseModel):
    """Validated claims extracted from a JWT access token."""

    sub: UUID = Field(..., description="User ID (subject)")
    org_id: UUID = Field(..., description="Organisation ID")
    roles: list[str] = Field(default_factory=list, description="RBAC role list")
    exp: datetime = Field(..., description="Token expiry (UTC)")


def verify_token(token: str) -> TokenPayload:
    """Decode and validate an RS256-signed JWT.

    Args:
        token: Raw JWT string (without ``Bearer `` prefix).

    Returns:
        Parsed and validated ``TokenPayload``.

    Raises:
        HTTPException: 401 if the token is expired, malformed, or fails
            signature verification.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error_code": "INVALID_TOKEN",
            "message": "Could not validate credentials",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=["RS256"],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise credentials_exception from exc

    # Ensure required custom claims are present
    if "org_id" not in payload:
        raise credentials_exception

    try:
        token_data = TokenPayload(
            sub=payload["sub"],
            org_id=payload["org_id"],
            roles=payload.get("roles", []),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except (KeyError, ValueError) as exc:
        raise credentials_exception from exc

    # Explicit expiry check (jose does it too, but be explicit)
    if token_data.exp < datetime.now(tz=timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "TOKEN_EXPIRED",
                "message": "Access token has expired",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> TokenPayload:
    """FastAPI dependency that extracts and verifies the Bearer token.

    Usage::

        @router.get("/protected")
        async def protected(user: TokenPayload = Depends(get_current_user)):
            ...

    Args:
        credentials: Automatically injected by ``HTTPBearer``.

    Returns:
        Validated ``TokenPayload`` for the current request.
    """
    return verify_token(credentials.credentials)


async def require_role(
    *required_roles: str,
):
    """Factory for role-checking dependencies.

    Usage::

        admin_only = Depends(require_role("admin"))

    Args:
        *required_roles: At least one of these roles must be present in the token.

    Returns:
        An async dependency function.
    """

    async def _checker(
        user: Annotated[TokenPayload, Depends(get_current_user)],
    ) -> TokenPayload:
        if not any(r in user.roles for r in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "INSUFFICIENT_ROLE",
                    "message": f"One of {required_roles} required",
                },
            )
        return user

    return _checker
