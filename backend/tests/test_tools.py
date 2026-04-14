"""Tests for the tool registry and stub tools."""

import pytest

from app.services.exceptions import ToolExecutionError
from app.services.tools import execute_tool_call, get_tool_specs


class TestGetToolSpecs:
    def test_returns_both_tools(self):
        specs = get_tool_specs()
        names = {s["name"] for s in specs}
        assert "create_design" in names
        assert "analyze_results" in names

    def test_spec_count(self):
        specs = get_tool_specs()
        assert len(specs) == 2

    def test_spec_format_matches_anthropic_schema(self):
        """Each spec must have name, description, and input_schema (JSON Schema object)."""
        for spec in get_tool_specs():
            assert "name" in spec
            assert "description" in spec
            assert "input_schema" in spec
            schema = spec["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema


class TestCreateDesignStub:
    def test_basic_two_factor(self):
        result = execute_tool_call(
            "create_design",
            {
                "factors": [
                    {"name": "Temperature", "low": 150.0, "high": 200.0},
                    {"name": "Pressure", "low": 1.0, "high": 5.0},
                ],
            },
        )
        assert result["design_type"] == "full_factorial"
        assert result["n_factors"] == 2
        assert result["n_runs"] == 4
        assert result["factor_names"] == ["Temperature", "Pressure"]
        assert len(result["design_coded"]) == 4
        assert len(result["design_actual"]) == 4
        assert len(result["run_order"]) == 4

    def test_three_factor(self):
        result = execute_tool_call(
            "create_design",
            {
                "factors": [
                    {"name": "A", "low": 0.0, "high": 1.0},
                    {"name": "B", "low": 0.0, "high": 1.0},
                    {"name": "C", "low": 0.0, "high": 1.0},
                ],
                "design_type": "ccd",
            },
        )
        assert result["n_factors"] == 3
        assert result["n_runs"] == 8  # 2^3 for stub
        assert result["design_type"] == "ccd"

    def test_actual_values_use_factor_bounds(self):
        result = execute_tool_call(
            "create_design",
            {
                "factors": [
                    {"name": "Temp", "low": 100.0, "high": 200.0},
                ],
            },
        )
        actual_values = {row["Temp"] for row in result["design_actual"]}
        assert actual_values == {100.0, 200.0}

    def test_coded_values_are_minus_one_plus_one(self):
        result = execute_tool_call(
            "create_design",
            {
                "factors": [{"name": "X", "low": 0, "high": 10}],
            },
        )
        coded_values = {row["X"] for row in result["design_coded"]}
        assert coded_values == {-1, 1}


class TestAnalyzeResultsStub:
    def test_basic_analysis(self):
        result = execute_tool_call(
            "analyze_results",
            {
                "factor_names": ["Temperature", "Pressure"],
                "model_type": "linear",
            },
        )
        assert result["model_type"] == "linear"
        assert "r_squared" in result
        assert "adj_r_squared" in result
        assert "coefficients" in result
        assert "intercept" in result
        assert "p_values" in result
        assert "significant_factors" in result
        assert "anova" in result
        assert "diagnostics" in result

    def test_coefficients_match_factors(self):
        names = ["A", "B", "C"]
        result = execute_tool_call("analyze_results", {"factor_names": names})
        assert set(result["coefficients"].keys()) == set(names)
        assert set(result["p_values"].keys()) == set(names)

    def test_anova_has_required_fields(self):
        result = execute_tool_call("analyze_results", {"factor_names": ["X"]})
        anova = result["anova"]
        assert "f_statistic" in anova
        assert "p_value" in anova
        assert "df_model" in anova
        assert "df_residual" in anova

    def test_defaults_when_optional_fields_omitted(self):
        result = execute_tool_call("analyze_results", {"factor_names": ["X1", "X2"]})
        assert result["model_type"] == "linear"


class TestExecuteToolCallErrors:
    def test_unknown_tool_raises(self):
        with pytest.raises(ToolExecutionError, match="Unknown tool"):
            execute_tool_call("nonexistent_tool", {})

    def test_error_includes_tool_name(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            execute_tool_call("bad_tool", {})
        assert exc_info.value.tool_name == "bad_tool"
