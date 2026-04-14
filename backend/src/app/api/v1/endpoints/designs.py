"""Design generation and evaluation endpoints."""

from typing import Any

from fastapi import APIRouter

from app.schemas.designs import GenerateDesignRequest
from app.services.doe_service import call_tool

router = APIRouter()


@router.post("/generate")
async def generate_design(request: GenerateDesignRequest) -> dict[str, Any]:
    """Generate an experimental design matrix.

    Supports full factorial, fractional factorial, Plackett-Burman,
    Box-Behnken, CCD, DSD, optimal, mixture, and Taguchi designs.
    """
    return await call_tool("generate_design", request.to_tool_input())
