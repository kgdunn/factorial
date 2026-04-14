"""Pydantic schemas for design generation endpoints."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# TODO: replace with `from process_improve.experiments.factor import Factor`
#       once process-improve is available in the deployment environment.


class FactorType(StrEnum):
    """Type of experimental factor."""

    continuous = "continuous"
    categorical = "categorical"
    mixture = "mixture"


class Factor(BaseModel):
    """Specification for a single experimental factor.

    Local stub mirroring ``process_improve.experiments.factor.Factor`` so
    the API schema and request validation remain identical while the
    process-improve package is not yet deployed.
    """

    name: str
    type: FactorType = FactorType.continuous
    low: float | None = None
    high: float | None = None
    levels: list[Any] | None = None
    units: str = ""

    @model_validator(mode="after")
    def _validate_factor(self) -> "Factor":
        if self.type == FactorType.continuous:
            if self.low is None or self.high is None:
                raise ValueError(f"Factor '{self.name}': continuous factors require 'low' and 'high'.")
            if self.low >= self.high:
                raise ValueError(f"Factor '{self.name}': 'low' ({self.low}) must be less than 'high' ({self.high}).")
        elif self.type == FactorType.categorical:
            if not self.levels or len(self.levels) < 2:
                raise ValueError(f"Factor '{self.name}': categorical factors require 'levels' with at least 2 entries.")
        elif self.type == FactorType.mixture:
            if self.low is None:
                self.low = 0.0
            if self.high is None:
                self.high = 1.0
        return self


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
