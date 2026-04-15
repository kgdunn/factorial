from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.api.v1.endpoints import auth, chat, designs, experiments, health, tools

api_v1_router = APIRouter()

# Health endpoints: public (no auth) — needed for docker-compose healthcheck & monitoring.
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])

# Auth endpoints: public (register, login, refresh). /me is protected within the endpoint.
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Protected endpoints: require JWT or API key.
_auth = [Depends(require_auth)]
api_v1_router.include_router(designs.router, prefix="/designs", tags=["designs"], dependencies=_auth)
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"], dependencies=_auth)
api_v1_router.include_router(tools.router, prefix="/tools", tags=["tools"], dependencies=_auth)
api_v1_router.include_router(experiments.router, prefix="/experiments", tags=["experiments"], dependencies=_auth)
