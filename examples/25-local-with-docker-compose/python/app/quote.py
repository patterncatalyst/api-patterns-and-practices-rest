"""Deterministic quote formula, identical on both stacks (mirrors
examples/04-contract-first/python/app/quote.py):

    quote.currency = "USD"
    quote.amount   = format(sum(cargo[].dimensions.weightKg) * 2.50, ".2f")

The amount is always rendered as a decimal STRING ("1250.00"), per
`#/$defs/Money` in the shared schema — never a JSON number.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.models import Cargo, CargoRequest, Money

_RATE_PER_KG = 2.50


def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = f"{total_weight_kg * _RATE_PER_KG:.2f}"
    return Money(currency="USD", amount=amount)
