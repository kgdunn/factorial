"""Anthropic API cost calculation.

Owns the rate table and the per-call cost snapshot. Costs are computed at
call time using the rates and markup in force at that instant, then stored
on the ``Message`` row so historical values remain correct even after the
rate table or markup changes.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# USD per 1M tokens, keyed by a prefix of the model id returned by Anthropic
# (``response.model``, e.g. ``"claude-sonnet-4-20250514"``). Lookup uses
# longest-prefix match so dated variants fall back to their family rate.
# Values are (input_rate, output_rate).
MODEL_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4": (Decimal("15"), Decimal("75")),
    "claude-sonnet-4": (Decimal("3"), Decimal("15")),
    "claude-haiku-4": (Decimal("1"), Decimal("5")),
}

# Markup applied on top of Anthropic's raw cost. 0.50 means we bill the
# customer at 1.5x our cost. Change here + deploy to adjust over time;
# historical rows keep the rate that was in force when they were written.
CURRENT_MARKUP_RATE: Decimal = Decimal("0.50")

_MTOK = Decimal("1000000")
_ZERO = Decimal("0")


def lookup_rates(model: str) -> tuple[Decimal, Decimal]:
    """Return (input_rate, output_rate) per million tokens for ``model``.

    Longest-prefix match against ``MODEL_RATES``. Returns ``(0, 0)`` and
    logs a warning if no prefix matches so an unrecognised model does not
    break the API call — the row is still persisted with zero cost and can
    be back-filled later if needed.
    """
    best_prefix = ""
    for prefix in MODEL_RATES:
        if model.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
    if not best_prefix:
        logger.warning("No pricing entry for model %r; storing zero cost.", model)
        return _ZERO, _ZERO
    return MODEL_RATES[best_prefix]


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Decimal | bool]:
    """Snapshot the rates, costs, markup, and billable amount for a call.

    The returned dict carries, among other keys:

    - ``raw_cost_usd`` — ``input_cost + output_cost``, what Anthropic
      charges us for this call.
    - ``markup_rate`` — the markup multiplier in force (e.g. ``0.50``
      for a 1.5x markup).
    - ``markup_cost_usd`` — the **total** billable amount
      (``raw_cost * (1 + markup_rate)``), not the markup portion
      alone. The field name is kept for schema compatibility with
      rows already persisted on ``Message``.
    - ``billable_to_user_usd`` — alias for ``markup_cost_usd``.
    """
    input_rate, output_rate = lookup_rates(model)
    input_cost = (Decimal(input_tokens) * input_rate) / _MTOK
    output_cost = (Decimal(output_tokens) * output_rate) / _MTOK
    raw = input_cost + output_cost
    markup_rate = CURRENT_MARKUP_RATE
    markup_cost = raw * (Decimal(1) + markup_rate)
    billable = markup_cost
    return {
        "input_rate_usd_per_mtok": input_rate,
        "output_rate_usd_per_mtok": output_rate,
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "raw_cost_usd": raw,
        "markup_rate": markup_rate,
        "markup_cost_usd": markup_cost,
        "billable_to_user_usd": billable,
    }
