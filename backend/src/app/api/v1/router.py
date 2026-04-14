from fastapi import APIRouter

from app.api.v1.endpoints import chat, designs, health

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])
api_v1_router.include_router(designs.router, prefix="/designs", tags=["designs"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
