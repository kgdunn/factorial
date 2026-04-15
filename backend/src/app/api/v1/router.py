from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.v1.endpoints import chat, designs, experiments, health, tools

api_v1_router = APIRouter()

# Health endpoints: public (no auth) — needed for docker-compose healthcheck & monitoring.
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])

# Protected endpoints: require API key (will be replaced by JWT in Feature 5).
_auth = [Depends(require_api_key)]
api_v1_router.include_router(designs.router, prefix="/designs", tags=["designs"], dependencies=_auth)
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"], dependencies=_auth)
api_v1_router.include_router(tools.router, prefix="/tools", tags=["tools"], dependencies=_auth)
api_v1_router.include_router(experiments.router, prefix="/experiments", tags=["experiments"], dependencies=_auth)
