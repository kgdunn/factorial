"""Tests for the tool bridge (process-improve integration)."""

import pytest

from app.services.exceptions import ToolExecutionError
from app.services.tools import execute_tool_call, get_tool_specs


class TestGetToolSpecs:
    def test_returns_all_registered_tools(self):
        specs = get_tool_specs()
        assert len(specs) >= 30  # 31 tools at time of writing; >= allows growth

    def test_spec_format_matches_anthropic_schema(self):
        """Each spec must have name, description, and input_schema (JSON Schema object)."""
        for spec in get_tool_specs():
            assert "name" in spec
            assert "description" in spec
            assert "input_schema" in spec
            schema = spec["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_contains_key_tools(self):
        names = {s["name"] for s in get_tool_specs()}
        assert "generate_design" in names
        assert "analyze_experiment" in names
        assert "robust_summary_stats" in names
        assert "fit_pca" in names

    def test_category_filter(self):
        specs = get_tool_specs(category="experiments")
        assert len(specs) >= 8
        for spec in specs:
            assert spec.get("category") == "experiments"

    def test_names_filter(self):
        specs = get_tool_specs(names=["generate_design", "robust_summary_stats"])
        names = {s["name"] for s in specs}
        assert names == {"generate_design", "robust_summary_stats"}


class TestExecuteToolCall:
    def test_robust_summary_stats(self):
        result = execute_tool_call(
            "robust_summary_stats",
            {"values": [1.0, 2.0, 3.0, 4.0, 5.0]},
        )
        assert "mean" in result
        assert "median" in result
        assert result["N_non_missing"] == 5
        assert result["median"] == 3.0

    def test_generate_design(self):
        result = execute_tool_call(
            "generate_design",
            {
                "factors": [
                    {"name": "Temperature", "low": 150.0, "high": 200.0},
                    {"name": "Pressure", "low": 1.0, "high": 5.0},
                ],
                "design_type": "full_factorial",
            },
        )
        assert result["design_type"] == "full_factorial"
        assert result["n_factors"] == 2
        assert result["n_runs"] >= 4
        assert "design_coded" in result
        assert "design_actual" in result

    def test_error_dict_from_tool(self):
        """Tools that catch errors internally return {\"error\": ...} dicts."""
        result = execute_tool_call(
            "generate_design",
            {
                "factors": [{"name": "A", "low": 0.0, "high": 1.0}],
                "design_type": "box_behnken",
            },
        )
        assert isinstance(result, dict)
        assert "error" in result


class TestExecuteToolCallErrors:
    def test_unknown_tool_raises(self):
        with pytest.raises(ToolExecutionError, match="Unknown tool"):
            execute_tool_call("nonexistent_tool", {})

    def test_error_includes_tool_name(self):
        with pytest.raises(ToolExecutionError) as exc_info:
            execute_tool_call("bad_tool", {})
        assert exc_info.value.tool_name == "bad_tool"
