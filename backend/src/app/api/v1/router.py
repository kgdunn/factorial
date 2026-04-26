from fastapi import APIRouter, Depends

from app.api.csrf import require_csrf
from app.api.deps import require_auth
from app.api.v1.endpoints import (
    admin_events,
    admin_feedback,
    admin_users,
    auth,
    byok,
    chat,
    designs,
    experiments,
    feedback,
    health,
    mcp,
    password_reset,
    roles,
    shares_public,
    signup,
    tools,
    uploads,
)
from app.config import settings

api_v1_router = APIRouter()

# Health endpoints: public (no auth) — needed for docker-compose healthcheck & monitoring.
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])

# Auth endpoints: public (login). Logout and sessions-management endpoints
# enforce CSRF inline via per-endpoint dependencies (see auth.py); the
# router-level dep here would block /login itself, which has no cookie yet.
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Password reset / first-time setup: public — the email-link token IS the
# credential. CSRF doesn't apply because there's no session cookie yet.
api_v1_router.include_router(password_reset.router, prefix="/auth", tags=["auth"])

# Signup endpoints: public (request, invite) + admin (list, approve, reject).
# Admin endpoints inside this router gate on require_admin and need CSRF;
# applied per-endpoint inside signup.py.
api_v1_router.include_router(signup.router, prefix="/signup", tags=["signup"])

# Roles: GET is public (for the signup form); mutations are admin-only.
api_v1_router.include_router(roles.router, prefix="/roles", tags=["roles"], dependencies=[Depends(require_csrf)])

# Admin routers: all gate on require_admin internally. Apply CSRF at the
# router level so every state-changing admin endpoint is covered.
api_v1_router.include_router(
    admin_users.router,
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_csrf)],
)
api_v1_router.include_router(
    admin_events.router,
    prefix="/admin/events",
    tags=["admin-events"],
    dependencies=[Depends(require_csrf)],
)
api_v1_router.include_router(
    admin_feedback.router,
    prefix="/admin/feedback",
    tags=["admin-feedback"],
    dependencies=[Depends(require_csrf)],
)

# Public share endpoints: no auth — viewers use a revocable token.
api_v1_router.include_router(shares_public.router, prefix="/public", tags=["public-shares"])

# Protected endpoints: require cookie or API key, plus CSRF on unsafe methods.
_auth = [Depends(require_auth), Depends(require_csrf)]
api_v1_router.include_router(designs.router, prefix="/designs", tags=["designs"], dependencies=_auth)
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"], dependencies=_auth)
api_v1_router.include_router(tools.router, prefix="/tools", tags=["tools"], dependencies=_auth)
api_v1_router.include_router(experiments.router, prefix="/experiments", tags=["experiments"], dependencies=_auth)
api_v1_router.include_router(
    uploads.router,
    prefix="/experiments/uploads",
    tags=["experiment-uploads"],
    dependencies=_auth,
)
api_v1_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"], dependencies=_auth)
api_v1_router.include_router(byok.router, prefix="/byok", tags=["byok"], dependencies=_auth)

# Hosted MCP endpoint: off by default. Mounts only when operators
# explicitly enable it. Auth + per-identity CPU budget + rate limit
# are enforced inside the router itself.
if settings.mcp_enabled:
    api_v1_router.include_router(mcp.router, prefix=settings.mcp_path_prefix, tags=["mcp"])
