"""Deterministic quote formula, identical to examples/04-contract-first and
mirrored bit-for-bit on the Quarkus side (QuoteCalculator.java):

    quote.currency = "USD"
    quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")
"""
from __future__ import annotations

from collections.abc import Iterable

from app.models import Cargo, CargoRequest, Money

_RATE_PER_KG = 2.50


def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = f"{total_weight_kg * _RATE_PER_KG:.2f}"
    return Money(currency="USD", amount=amount)
