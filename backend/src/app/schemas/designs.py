"""Pydantic schemas for design generation endpoints."""

from typing import Any

from process_improve.experiments.factor import Factor
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class GenerateDesignRequest(BaseModel):
    """Request body for POST /api/v1/designs/generate."""

    factors: list[Factor] = Field(..., min_length=1, description="Factor specifications.")
    design_type: str | None = Field(
        None,
        description="Design type. Auto-selected when omitted.",
        json_schema_extra={
            "enum": [
                "full_factorial",
                "fractional_factorial",
                "plackett_burman",
                "box_behnken",
                "ccd",
                "dsd",
                "d_optimal",
                "i_optimal",
                "a_optimal",
                "mixture",
                "taguchi",
            ]
        },
    )
    budget: int | None = Field(None, ge=1, description="Maximum number of experimental runs.")
    center_points: int = Field(3, ge=0, description="Number of center point replicates.")
    replicates: int = Field(1, ge=1, description="Number of full replicates.")
    resolution: int | None = Field(None, ge=3, le=5, description="Minimum resolution for fractional factorials.")
    alpha: str | None = Field(None, description="Axial distance for CCD designs.")
    random_seed: int = Field(42, description="Seed for reproducible randomization.")

    def to_tool_input(self) -> dict[str, Any]:
        """Convert to the dict format expected by execute_tool_call."""
        data = self.model_dump(exclude_none=True)
        # execute_tool_call expects factors as list[dict], not Factor objects
        data["factors"] = [f.model_dump(exclude_none=True) for f in self.factors]
        return data
