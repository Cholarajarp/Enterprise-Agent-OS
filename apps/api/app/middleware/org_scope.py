"""Organisation-scope middleware.

Extracts ``org_id`` from the verified JWT and attaches it to
``request.state.org_id`` so that every downstream handler and service
can scope database queries without re-decoding the token.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.security import verify_token


class OrgScopeMiddleware(BaseHTTPMiddleware):
    """Inject ``org_id`` from the JWT into ``request.state``.

    Skips unauthenticated paths (health checks, docs) automatically:
    if no ``Authorization`` header is present the middleware is a no-op,
    leaving authentication enforcement to the route-level dependency.
    """

    SKIP_PATHS: set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process the request, injecting org_id when a valid token is present.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware / route handler.

        Returns:
            The downstream response.
        """
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        auth_header: str | None = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token_str = auth_header.removeprefix("Bearer ").strip()
            try:
                token_payload = verify_token(token_str)
                request.state.org_id = token_payload.org_id
                request.state.user_id = token_payload.sub
                request.state.roles = token_payload.roles
            except HTTPException:
                # Token is invalid -- let the route-level Depends raise the 401.
                pass

        return await call_next(request)


def current_org_id(request: Request) -> UUID:
    """Extract the organisation ID injected by ``OrgScopeMiddleware``.

    Intended for use in route handlers and service functions:

        org_id = current_org_id(request)

    Args:
        request: The current FastAPI ``Request``.

    Returns:
        The ``org_id`` UUID for the authenticated tenant.

    Raises:
        HTTPException: 401 if no org_id is set (unauthenticated request).
    """
    org_id: UUID | None = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_ORG_CONTEXT",
                "message": "Organisation context not found; authentication required",
            },
        )
    return org_id
