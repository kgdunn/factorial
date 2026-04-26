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
    *,
    byok_used: bool = False,
) -> dict[str, Decimal | bool]:
    """Snapshot the rates, costs, markup, and billable amount for a call.

    ``byok_used`` flips two fields:

    - ``markup_cost_usd`` becomes 0 (we do not add a platform markup
      to a key that bills the user directly at Anthropic).
    - ``billable_to_user_usd`` becomes 0 (the user is billed at the
      Anthropic side; nothing flows through our balance ledger).

    For platform-key turns ``markup_cost_usd = raw * (1 + markup_rate)``
    matches the historical formula, and ``billable_to_user_usd ==
    markup_cost_usd``. Historical rows on disk continue to satisfy
    ``billable_to_user_usd == markup_cost_usd`` because they were all
    written under that branch.

    The ``raw_cost_usd`` field stays accurate either way — it is what
    Anthropic charged for the call, which is real cost regardless of
    who paid it. Margin reporting can subtract BYOK rows by filtering
    on ``byok_used``.
    """
    input_rate, output_rate = lookup_rates(model)
    input_cost = (Decimal(input_tokens) * input_rate) / _MTOK
    output_cost = (Decimal(output_tokens) * output_rate) / _MTOK
    raw = input_cost + output_cost
    markup_rate = CURRENT_MARKUP_RATE
    markup_cost = _ZERO if byok_used else raw * (Decimal(1) + markup_rate)
    billable = _ZERO if byok_used else markup_cost
    return {
        "input_rate_usd_per_mtok": input_rate,
        "output_rate_usd_per_mtok": output_rate,
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "raw_cost_usd": raw,
        "markup_rate": markup_rate,
        "markup_cost_usd": markup_cost,
        "billable_to_user_usd": billable,
        "byok_used": byok_used,
    }
