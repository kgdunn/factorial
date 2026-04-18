from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.api.v1.endpoints import (
    admin_users,
    auth,
    chat,
    designs,
    experiments,
    health,
    password_reset,
    roles,
    shares_public,
    signup,
    tools,
)

api_v1_router = APIRouter()

# Health endpoints: public (no auth) — needed for docker-compose healthcheck & monitoring.
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])

# Auth endpoints: public (register, login, refresh). /me is protected within the endpoint.
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Password reset / first-time setup: mostly public (the token itself is the credential).
api_v1_router.include_router(password_reset.router, prefix="/auth", tags=["auth"])

# Signup endpoints: public (request, invite) + admin (list, approve, reject).
api_v1_router.include_router(signup.router, prefix="/signup", tags=["signup"])

# Roles: GET is public (for the signup form); mutations are admin-only.
api_v1_router.include_router(roles.router, prefix="/roles", tags=["roles"])

# Admin user management.
api_v1_router.include_router(admin_users.router, prefix="/admin/users", tags=["admin-users"])

# Public share endpoints: no auth — viewers use a revocable token.
api_v1_router.include_router(shares_public.router, prefix="/public", tags=["public-shares"])

# Protected endpoints: require JWT or API key.
_auth = [Depends(require_auth)]
api_v1_router.include_router(designs.router, prefix="/designs", tags=["designs"], dependencies=_auth)
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"], dependencies=_auth)
api_v1_router.include_router(tools.router, prefix="/tools", tags=["tools"], dependencies=_auth)
api_v1_router.include_router(experiments.router, prefix="/experiments", tags=["experiments"], dependencies=_auth)
