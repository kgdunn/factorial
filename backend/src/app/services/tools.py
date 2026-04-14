"""Tool registry and stub tools for the DOE agent.

Provides ``get_tool_specs()`` and ``execute_tool_call()`` with the same
public API as ``process_improve.tool_spec``.  Once the real process-improve
package is deployed, this module will be replaced by imports from that package.

The two stub tools (``create_design`` and ``analyze_results``) return
realistic fake data so the agent loop can be tested end-to-end.
"""

from __future__ import annotations

import itertools
import random
from typing import Any

from app.services.exceptions import ToolExecutionError

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def _register(name: str, description: str, input_schema: dict[str, Any], handler: Any) -> None:
    """Register a tool with its Anthropic-format spec and handler."""
    _TOOL_REGISTRY[name] = {
        "spec": {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        },
        "handler": handler,
    }


def get_tool_specs() -> list[dict[str, Any]]:
    """Return all tool specs in the format expected by the Anthropic ``tools=`` parameter."""
    return [entry["spec"] for entry in _TOOL_REGISTRY.values()]


def execute_tool_call(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call to the registered handler.

    Raises
    ------
    ToolExecutionError
        If the tool name is not in the registry.
    """
    if tool_name not in _TOOL_REGISTRY:
        available = sorted(_TOOL_REGISTRY)
        raise ToolExecutionError(
            f"Unknown tool {tool_name!r}. Available: {available}",
            tool_name=tool_name,
        )
    return _TOOL_REGISTRY[tool_name]["handler"](tool_input)


# ---------------------------------------------------------------------------
# Stub tool: create_design
# ---------------------------------------------------------------------------


def _handle_create_design(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Generate a fake experimental design matrix.

    Returns a realistic-looking result matching the output format of
    ``process_improve.experiments.tools.generate_design``.
    """
    factors = tool_input["factors"]
    design_type = tool_input.get("design_type", "full_factorial")
    n_factors = len(factors)
    factor_names = [f["name"] for f in factors]

    # Build coded design matrix from all combinations of -1 / +1
    coded_levels = list(itertools.product([-1, 1], repeat=n_factors))
    n_runs = len(coded_levels)

    design_coded = [dict(zip(factor_names, row, strict=True)) for row in coded_levels]

    # Build actual-units matrix using factor low/high (or defaults)
    design_actual = []
    for row in coded_levels:
        actual_row: dict[str, float] = {}
        for i, f in enumerate(factors):
            low = f.get("low", -1.0)
            high = f.get("high", 1.0)
            actual_row[f["name"]] = low if row[i] == -1 else high
        design_actual.append(actual_row)

    run_order = list(range(1, n_runs + 1))
    random.Random(42).shuffle(run_order)  # noqa: S311 — deterministic stub data, not crypto

    return {
        "design_type": design_type,
        "n_factors": n_factors,
        "n_runs": n_runs,
        "factor_names": factor_names,
        "design_coded": design_coded,
        "design_actual": design_actual,
        "run_order": run_order,
    }


_register(
    name="create_design",
    description=(
        "Generate an experimental design matrix for a designed experiment. "
        "Supports full factorial, fractional factorial, Plackett-Burman, Box-Behnken, "
        "Central Composite (CCD), Definitive Screening (DSD), and D-optimal designs. "
        "Returns the design matrix in both coded (-1/+1) and actual units, plus metadata. "
        "Use this when a user wants to plan or create a new experimental design."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "factors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Factor name."},
                        "low": {"type": "number", "description": "Low level value."},
                        "high": {"type": "number", "description": "High level value."},
                        "type": {
                            "type": "string",
                            "enum": ["continuous", "categorical", "mixture"],
                            "description": "Factor type. Defaults to continuous.",
                        },
                        "units": {"type": "string", "description": "Units of measurement."},
                    },
                    "required": ["name"],
                },
                "description": "List of factor specifications.",
                "minItems": 1,
            },
            "design_type": {
                "type": "string",
                "enum": [
                    "full_factorial",
                    "fractional_factorial",
                    "plackett_burman",
                    "box_behnken",
                    "ccd",
                    "dsd",
                    "d_optimal",
                ],
                "description": "Design type. Auto-selected when omitted.",
            },
            "budget": {
                "type": "integer",
                "description": "Maximum number of experimental runs.",
                "minimum": 1,
            },
            "center_points": {
                "type": "integer",
                "description": "Number of center-point replicates (default 3).",
                "minimum": 0,
            },
        },
        "required": ["factors"],
    },
    handler=_handle_create_design,
)


# ---------------------------------------------------------------------------
# Stub tool: analyze_results
# ---------------------------------------------------------------------------


def _handle_analyze_results(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Analyse experimental results and return fake statistical output.

    Returns a realistic-looking result matching the output format of
    ``process_improve.experiments.tools.analyze_experiment``.
    """
    factor_names = tool_input.get("factor_names", ["X1", "X2"])
    model_type = tool_input.get("model_type", "linear")

    rng = random.Random(42)  # noqa: S311 — deterministic stub data, not crypto
    coefficients = {name: round(rng.uniform(-3.0, 3.0), 3) for name in factor_names}
    p_values = {name: round(rng.uniform(0.001, 0.15), 4) for name in factor_names}
    significant = [name for name, p in p_values.items() if p < 0.05]

    return {
        "model_type": model_type,
        "r_squared": 0.943,
        "adj_r_squared": 0.912,
        "coefficients": coefficients,
        "intercept": round(rng.uniform(5.0, 50.0), 2),
        "p_values": p_values,
        "significant_factors": significant,
        "anova": {
            "f_statistic": round(rng.uniform(8.0, 30.0), 2),
            "p_value": round(rng.uniform(0.0001, 0.01), 5),
            "df_model": len(factor_names),
            "df_residual": max(1, 2 ** len(factor_names) - len(factor_names) - 1),
        },
        "diagnostics": {
            "durbin_watson": round(rng.uniform(1.5, 2.5), 3),
            "shapiro_wilk_p": round(rng.uniform(0.1, 0.9), 3),
        },
    }


_register(
    name="analyze_results",
    description=(
        "Fit a statistical model to experimental results and return analysis. "
        "Computes coefficients, p-values, R-squared, ANOVA table, and diagnostics. "
        "Supports linear, interaction, and quadratic model types. "
        "Use this when a user has experimental results and wants to understand "
        "which factors are significant and how they affect the response."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "factor_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of the factors in the experiment.",
                "minItems": 1,
            },
            "response_values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Observed response values for each experimental run.",
            },
            "model_type": {
                "type": "string",
                "enum": ["linear", "interaction", "quadratic"],
                "description": "Type of model to fit. Defaults to linear.",
            },
            "design_matrix": {
                "type": "array",
                "items": {
                    "type": "object",
                },
                "description": "Design matrix rows (coded or actual). Each row is a dict of factor_name -> value.",
            },
        },
        "required": ["factor_names"],
    },
    handler=_handle_analyze_results,
)
