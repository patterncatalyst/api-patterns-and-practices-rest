"""Deterministic quote formula, identical to examples/04-contract-first and
mirrored bit-for-bit on the Quarkus side (QuoteCalculator.java):

    quote.currency = "USD"
    quote.amount   = round_half_up(sum(cargo[].dimensions.weightKg) * 2.50, 2)

Both stacks round HALF_UP explicitly (Decimal.quantize here, Java's
BigDecimal.setScale(2, RoundingMode.HALF_UP) in QuoteCalculator.java) so
they agree on every input, not just ones that happen to land exactly on
two decimal places.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from app.models import Cargo, CargoRequest, Money

_RATE_PER_KG = 2.50


def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = str(
        Decimal(str(total_weight_kg * _RATE_PER_KG)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    return Money(currency="USD", amount=amount)
