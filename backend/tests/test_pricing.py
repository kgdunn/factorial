"""Unit tests for the Anthropic cost calculation module."""

from __future__ import annotations

from decimal import Decimal

from app.services import pricing


class TestLookupRates:
    def test_exact_family_match(self):
        ir, or_ = pricing.lookup_rates("claude-sonnet-4")
        assert ir == Decimal("3")
        assert or_ == Decimal("15")

    def test_dated_variant_uses_family_rate(self):
        ir, or_ = pricing.lookup_rates("claude-sonnet-4-20250514")
        assert ir == Decimal("3")
        assert or_ == Decimal("15")

    def test_longest_prefix_wins(self):
        # If two prefixes both matched, the longer one should be chosen.
        # claude-opus-4 and claude-opus-4-1 (hypothetical) — verify the
        # lookup picks the longest prefix when multiple match.
        try:
            pricing.MODEL_RATES["claude-opus-4-1"] = (Decimal("20"), Decimal("100"))
            ir, or_ = pricing.lookup_rates("claude-opus-4-1-20260101")
            assert ir == Decimal("20")
            assert or_ == Decimal("100")
        finally:
            pricing.MODEL_RATES.pop("claude-opus-4-1", None)

    def test_unknown_model_returns_zero(self, caplog):
        ir, or_ = pricing.lookup_rates("gpt-4")
        assert ir == Decimal("0")
        assert or_ == Decimal("0")
        assert any("No pricing entry" in rec.message for rec in caplog.records)


class TestCalculateCost:
    def test_sonnet_snapshot_is_exact(self):
        # 100 input tokens at $3/MTok = $0.0003
        # 50 output tokens at $15/MTok = $0.00075
        # raw = $0.00105, markup 50% -> $0.001575
        snap = pricing.calculate_cost("claude-sonnet-4-20250514", 100, 50)
        assert snap["input_rate_usd_per_mtok"] == Decimal("3")
        assert snap["output_rate_usd_per_mtok"] == Decimal("15")
        assert snap["input_cost_usd"] == Decimal("0.0003")
        assert snap["output_cost_usd"] == Decimal("0.00075")
        assert snap["raw_cost_usd"] == Decimal("0.00105")
        assert snap["markup_rate"] == pricing.CURRENT_MARKUP_RATE
        assert snap["markup_cost_usd"] == Decimal("0.00105") * (Decimal("1") + pricing.CURRENT_MARKUP_RATE)

    def test_opus_rates_applied(self):
        snap = pricing.calculate_cost("claude-opus-4-20260101", 1_000_000, 0)
        # 1M input tokens at $15/MTok = $15
        assert snap["input_cost_usd"] == Decimal("15")
        assert snap["output_cost_usd"] == Decimal("0")
        assert snap["raw_cost_usd"] == Decimal("15")

    def test_zero_tokens(self):
        snap = pricing.calculate_cost("claude-sonnet-4", 0, 0)
        assert snap["input_cost_usd"] == Decimal("0")
        assert snap["output_cost_usd"] == Decimal("0")
        assert snap["raw_cost_usd"] == Decimal("0")
        assert snap["markup_cost_usd"] == Decimal("0")

    def test_unknown_model_zero_cost(self):
        snap = pricing.calculate_cost("some-other-model", 1000, 1000)
        assert snap["input_rate_usd_per_mtok"] == Decimal("0")
        assert snap["output_rate_usd_per_mtok"] == Decimal("0")
        assert snap["raw_cost_usd"] == Decimal("0")
        assert snap["markup_cost_usd"] == Decimal("0")
        # Markup rate is still recorded — it's the rate that was in force,
        # which is meaningful independent of whether the cost resolved.
        assert snap["markup_rate"] == pricing.CURRENT_MARKUP_RATE

    def test_markup_applied_correctly(self):
        snap = pricing.calculate_cost("claude-sonnet-4", 1_000_000, 1_000_000)
        raw = Decimal("3") + Decimal("15")  # $18
        expected = raw * (Decimal("1") + pricing.CURRENT_MARKUP_RATE)
        assert snap["raw_cost_usd"] == raw
        assert snap["markup_cost_usd"] == expected

    def test_platform_key_billable_equals_markup(self):
        # On the platform path, billable_to_user_usd is just an alias for
        # markup_cost_usd — they must agree byte-for-byte so balance
        # ledger reads / writes never disagree on rounding.
        snap = pricing.calculate_cost("claude-sonnet-4", 100, 50)
        assert snap["byok_used"] is False
        assert snap["billable_to_user_usd"] == snap["markup_cost_usd"]


class TestCalculateCostBYOK:
    def test_byok_zeros_markup_and_billable(self):
        # Same model + tokens as the platform-key snapshot above, but
        # byok_used=True must zero both markup_cost_usd and
        # billable_to_user_usd while keeping raw_cost_usd accurate.
        snap = pricing.calculate_cost("claude-sonnet-4", 100, 50, byok_used=True)
        assert snap["byok_used"] is True
        assert snap["raw_cost_usd"] == Decimal("0.00105")
        assert snap["markup_cost_usd"] == Decimal("0")
        assert snap["billable_to_user_usd"] == Decimal("0")

    def test_byok_keeps_rates_recorded(self):
        # The rates are still snapshotted on BYOK rows so the message
        # rows accurately describe what Anthropic charged the user.
        snap = pricing.calculate_cost("claude-sonnet-4", 1_000_000, 1_000_000, byok_used=True)
        assert snap["input_rate_usd_per_mtok"] == Decimal("3")
        assert snap["output_rate_usd_per_mtok"] == Decimal("15")
        assert snap["raw_cost_usd"] == Decimal("18")
        # markup_rate is the rate that was *in force* — meaningful for
        # auditing even if it didn't get applied.
        assert snap["markup_rate"] == pricing.CURRENT_MARKUP_RATE

    def test_byok_default_is_false(self):
        # Existing call sites that don't pass byok_used must keep the
        # historical platform-key behaviour unchanged.
        snap = pricing.calculate_cost("claude-sonnet-4", 100, 50)
        assert snap["byok_used"] is False
        # Markup applied as before.
        assert snap["markup_cost_usd"] == Decimal("0.00105") * (Decimal("1") + pricing.CURRENT_MARKUP_RATE)
